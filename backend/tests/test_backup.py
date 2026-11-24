import json
import sqlite3
from pathlib import Path

from test_comparison import upload_structured
from test_policies import seed_policy

from backend.scripts.backup import backup, restore


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
