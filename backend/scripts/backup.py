"""Consistent DB backup plus referenced sources; restore only into a new directory."""

import argparse
import json
import shutil
import sqlite3
from pathlib import Path

from backend import db
from backend.config import settings


def backup(destination: Path):
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "sources").mkdir()
    with db.transaction():
        with sqlite3.connect(settings.data_dir / "vendorops.sqlite") as source:
            with sqlite3.connect(destination / "vendorops.sqlite") as target:
                source.backup(target)
                for identifier, raw in target.execute(
                    "SELECT id,data FROM records WHERE kind='document'"
                ):
                    data = json.loads(raw)
                    shutil.copy2(data["source"], destination / "sources" / f"{identifier}.pdf")
    (destination / "manifest.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "created_at": db.now(),
                "vectors": "Rebuild from stored policy chunks after restore.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return destination


def restore(source: Path, destination: Path):
    source, destination = source.resolve(), destination.resolve()
    if destination.exists():
        raise ValueError("Restore destination must not exist; existing data is never overwritten.")
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if manifest["schema"] != 1:
        raise ValueError("Unsupported backup format")
    shutil.copytree(source, destination)
    with sqlite3.connect(destination / "vendorops.sqlite") as connection:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Backup database failed integrity verification")
        rows = connection.execute("SELECT id,data FROM records WHERE kind='document'").fetchall()
        for identifier, raw in rows:
            data = json.loads(raw)
            path = destination / "sources" / f"{identifier}.pdf"
            if not path.is_file():
                raise ValueError("Backup is missing a referenced PDF")
            data["source"] = str(path)
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
    return destination


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
