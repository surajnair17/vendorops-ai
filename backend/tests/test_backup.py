import json
import sqlite3
from pathlib import Path

import pytest
from test_comparison import upload_structured
from test_policies import seed_policy

from backend.scripts.backup import backup, restore


@pytest.mark.parametrize("target", ["database", "pdf", "extra"])
def test_corrupt_or_unexpected_backup_never_publishes_destination(client, tmp_path, target):
    upload_structured(client, 0)
    snapshot = backup(tmp_path / "snapshot")
    if target == "database":
        with (snapshot / "vendorops.sqlite").open("ab") as stream:
            stream.write(b"changed after backup")
    elif target == "pdf":
        next((snapshot / "sources").glob("*.pdf")).write_bytes(b"corrupt source")
    else:
        (snapshot / "unexpected.txt").write_text("unexpected")
    destination = tmp_path / "restored"
    with pytest.raises(ValueError, match="manifest|checksum"):
        restore(snapshot, destination)
    assert not destination.exists()
    assert not (tmp_path / ".restored.vendorops.lock").exists()


def test_legacy_backup_still_checks_pdf_hashes(client, tmp_path):
    upload_structured(client, 0)
    snapshot = backup(tmp_path / "legacy")
    (snapshot / "manifest.json").write_text(json.dumps({"schema": 1}))
    assert restore(snapshot, tmp_path / "legacy-restored").is_dir()
    next((snapshot / "sources").glob("*.pdf")).write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        restore(snapshot, tmp_path / "bad-legacy")
    assert not (tmp_path / "bad-legacy").exists()


def test_failed_source_backup_does_not_leave_complete_looking_snapshot(client, tmp_path):
    identifier = upload_structured(client, 0)
    document = client.get(f"/api/v1/documents/{identifier}").json()
    Path(document["data"]["source"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        backup(tmp_path / "snapshot")
    assert not (tmp_path / "snapshot").exists()
    assert not (tmp_path / ".snapshot.vendorops.lock").exists()


def test_restoration_refuses_overlap_and_preserves_inflight_uncertainty(client, tmp_path):
    from test_workflow import approve, new_action

    from backend import db

    action = approve(client, new_action(client))
    job = client.post(
        f"/api/v1/actions/{action['id']}/execute", json={"expected_version": action["version"]}
    ).json()
    with db.transaction() as connection:
        db.create(
            connection,
            "delivery_attempt",
            {"action_id": action["id"], "job_id": job["job_id"], "state": "sending"},
        )
    snapshot = backup(tmp_path / "snapshot")
    with pytest.raises(ValueError, match="overlap"):
        restore(snapshot, snapshot / "restored")
    restored = restore(snapshot, tmp_path / "restored")
    with sqlite3.connect(restored / "vendorops.sqlite") as connection:
        records = connection.execute(
            "SELECT kind,data FROM records WHERE kind IN ('action','job','delivery_attempt')"
        ).fetchall()
        assert all(
            json.loads(data).get("state", json.loads(data).get("status")) == "unknown"
            for _, data in records
        )


def test_restore_relocates_sources_and_preserves_revisions(client, tmp_path):
    identifier = upload_structured(client, 0)
    snapshot = backup(tmp_path / "snapshot")
    restored = restore(snapshot, tmp_path / "restored")
    with sqlite3.connect(restored / "vendorops.sqlite") as connection:
        raw = connection.execute("SELECT data FROM records WHERE id=?", (identifier,)).fetchone()[0]
        data = json.loads(raw)
        assert Path(data["source"]).read_bytes().startswith(b"%PDF")
        assert data["revision_id"]
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_restored_policies_require_index_rebuild(client, tmp_path):
    policy, _ = seed_policy(client)
    snapshot = backup(tmp_path / "snapshot")
    restored = restore(snapshot, tmp_path / "restored")
    with sqlite3.connect(restored / "vendorops.sqlite") as connection:
        raw = connection.execute("SELECT data FROM records WHERE id=?", (policy["id"],)).fetchone()[
            0
        ]
        data = json.loads(raw)
        assert not data["indexed"]
        assert data["index_provider"] is None
