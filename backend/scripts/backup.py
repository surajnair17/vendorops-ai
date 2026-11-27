"""Consistent DB backup plus referenced sources; restore only into a new directory."""

import argparse
import hashlib
import json
import shutil
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from backend import db
from backend.config import settings


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def pdf_name(identifier: str) -> str:
    if str(UUID(identifier)) != identifier:
        raise ValueError("Backup contains an invalid document ID")
    return f"{identifier}.pdf"


@contextmanager
def snapshot_location(destination: Path):
    """Build beside the destination; publish only a complete, closed snapshot."""
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("Destination must not exist; existing data is never overwritten.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.parent / f".{destination.name}.vendorops.lock"
    # Exclusive creation also serializes two backup/restore commands with the same destination.
    handle = lock.open("x")
    try:
        with handle:
            with TemporaryDirectory(
                prefix=".vendorops-snapshot-", dir=destination.parent
            ) as folder:
                staging = Path(folder).resolve() / "snapshot"
                if not staging.is_relative_to(destination.parent):
                    raise ValueError("Snapshot staging escaped the destination directory")
                staging.mkdir()
                yield staging
                if destination.exists():
                    raise ValueError(
                        "Destination appeared during operation; refusing to overwrite it"
                    )
                staging.rename(destination)
    finally:
        # The handle is closed before removal on Windows, including on a failed snapshot.
        lock.unlink()


def backup(destination: Path):
    destination = destination.resolve()
    with snapshot_location(destination) as staging:
        (staging / "sources").mkdir()
        with db.transaction():
            with closing(sqlite3.connect(settings.data_dir / "vendorops.sqlite")) as source:
                with closing(sqlite3.connect(staging / "vendorops.sqlite")) as target:
                    source.backup(target)
                    target.execute("PRAGMA journal_mode=DELETE")
                    for identifier, raw in target.execute(
                        "SELECT id,data FROM records WHERE kind='document'"
                    ):
                        data = json.loads(raw)
                        original = Path(data["source"])
                        if original.is_symlink() or not original.resolve().is_relative_to(
                            settings.data_dir.resolve() / "sources"
                        ):
                            raise ValueError(
                                "Document source is outside the managed sources directory"
                            )
                        if checksum(original) != data["sha256"]:
                            raise ValueError("Source PDF checksum does not match its upload record")
                        copied = staging / "sources" / pdf_name(identifier)
                        shutil.copyfile(original, copied)
                        if checksum(copied) != data["sha256"]:
                            raise ValueError("Source PDF changed during backup")
        manifest = {
            "schema": 2,
            "created_at": db.now(),
            "vectors": "Rebuild from stored policy chunks after restore.",
            "files": {
                path.relative_to(staging).as_posix(): checksum(path)
                for path in sorted(staging.rglob("*"))
                if path.is_file()
            },
        }
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return destination


def restore(source: Path, destination: Path):
    source, destination = source.resolve(), destination.resolve()
    if destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError("Backup and restore directories must not overlap")
    if any(path.is_symlink() or path.is_junction() for path in source.rglob("*")):
        raise ValueError("Backup must not contain symbolic links or junctions")
    with snapshot_location(destination) as staging:
        shutil.copytree(source, staging, dirs_exist_ok=True)
        manifest = json.loads((staging / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("schema") not in {1, 2}:
            raise ValueError("Unsupported backup format")
        actual_files = {
            path.relative_to(staging).as_posix() for path in staging.rglob("*") if path.is_file()
        }
        if manifest["schema"] == 2:
            declared = manifest.get("files", {})
            if not declared or set(declared) != actual_files - {"manifest.json"}:
                raise ValueError("Backup manifest file list does not match its contents")
            if any(checksum(staging / name) != declared[name] for name in declared):
                raise ValueError("Backup checksum verification failed")
        restore_database(staging, destination, actual_files)
    return destination


def restore_database(staging: Path, destination: Path, actual_files: set[str]):
    if not (staging / "vendorops.sqlite").is_file():
        raise ValueError("Backup database is missing")
    with closing(sqlite3.connect(staging / "vendorops.sqlite")) as connection, connection:
        connection.execute("PRAGMA trusted_schema=OFF")
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Backup database failed integrity verification")
        rows = connection.execute("SELECT id,data FROM records WHERE kind='document'").fetchall()
        expected = {"vendorops.sqlite", "manifest.json"}
        for identifier, raw in rows:
            data = json.loads(raw)
            name = pdf_name(identifier)
            expected.add(f"sources/{name}")
            path = staging / "sources" / name
            if not path.is_file() or checksum(path) != data["sha256"]:
                raise ValueError("Backup is missing or has changed a referenced PDF")
            data["source"] = str(destination / "sources" / name)
            connection.execute(
                "UPDATE records SET data=? WHERE id=?", (json.dumps(data), identifier)
            )
        # Do not silently restore approval to execute a possibly already-sent action.
        for identifier, raw in connection.execute(
            "SELECT id,data FROM records WHERE kind='action'"
        ).fetchall():
            data = json.loads(raw)
            if data["state"] in {"queued", "sending"}:
                data["state"] = "unknown"
                connection.execute(
                    "UPDATE records SET data=? WHERE id=?", (json.dumps(data), identifier)
                )
        for identifier, raw in connection.execute(
            "SELECT id,data FROM records WHERE kind='delivery_attempt'"
        ).fetchall():
            data = json.loads(raw)
            if data.get("state") == "sending":
                data.update(state="unknown", error_code="restored_inflight_attempt")
                connection.execute(
                    "UPDATE records SET data=? WHERE id=?", (json.dumps(data), identifier)
                )
        for identifier, raw in connection.execute(
            "SELECT id,data FROM records WHERE kind='job'"
        ).fetchall():
            data = json.loads(raw)
            if data.get("kind") == "email" and data["status"] in {"queued", "running"}:
                data["status"] = "unknown"
                connection.execute(
                    "UPDATE records SET data=? WHERE id=?", (json.dumps(data), identifier)
                )
        for identifier, raw in connection.execute(
            "SELECT id,data FROM records WHERE kind='policy'"
        ).fetchall():
            data = json.loads(raw)
            data["indexed"] = False
            data["index_provider"] = None
            connection.execute(
                "UPDATE records SET data=? WHERE id=?", (json.dumps(data), identifier)
            )
        if actual_files != expected:
            raise ValueError("Backup contains unexpected files")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["backup", "restore"])
    parser.add_argument("destination", type=Path)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    if args.operation == "backup":
        print(backup(args.destination))
    elif args.source:
        print(restore(args.source, args.destination))
    else:
        parser.error("restore requires --source")


if __name__ == "__main__":
    main()
