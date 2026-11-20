"""Small JSON-snapshot repository over SQLAlchemy and versioned SQLite migrations.

Documents, revisions, and reports have distinct kinds and Pydantic contracts. Snapshots
keep the learning database small; transactions serialize revision/approval changes.
"""

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text

from backend.config import settings
from backend.errors import AppError


def now() -> str:
    return datetime.now(UTC).isoformat()


@lru_cache(maxsize=8)
def engine_for(directory: str):
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{(path / 'vendorops.sqlite').as_posix()}", connect_args={"timeout": 30}
    )
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")
        connection.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS schema_versions (version INTEGER PRIMARY KEY)"
        )
        connection.commit()
        for migration in sorted((Path(__file__).parent / "migrations").glob("*.sql")):
            version = int(migration.name.split("_")[0])
            if connection.execute(
                text("SELECT 1 FROM schema_versions WHERE version=:v"), {"v": version}
            ).first():
                continue
            for statement in migration.read_text().split(";"):
                if statement.strip():
                    connection.exec_driver_sql(statement)
            connection.execute(text("INSERT INTO schema_versions VALUES (:v)"), {"v": version})
            connection.commit()
    return engine


@contextmanager
def transaction():
    with engine_for(str(settings.data_dir.resolve())).connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def unpack(row) -> dict:
    return {**dict(row), "data": json.loads(row["data"])}


def get(connection, identifier: str, kind: str | None = None) -> dict:
    row = (
        connection.execute(text("SELECT * FROM records WHERE id=:id"), {"id": identifier})
        .mappings()
        .first()
    )
    if row is None or (kind and row["kind"] != kind):
        raise AppError(404, "not_found", "The requested record does not exist.")
    return unpack(row)


def all_records(connection, kind: str) -> list[dict]:
    return [
        unpack(row)
        for row in connection.execute(
            text("SELECT * FROM records WHERE kind=:kind ORDER BY created_at, id"), {"kind": kind}
        ).mappings()
    ]


def create(connection, kind: str, data: dict, identifier: str | None = None) -> dict:
    values = {
        "id": identifier or str(uuid4()),
        "kind": kind,
        "data": json.dumps(data),
        "time": now(),
    }
    connection.execute(text("INSERT INTO records VALUES (:id,:kind,1,:data,:time,:time)"), values)
    return get(connection, values["id"])


def update(connection, record: dict, data: dict) -> dict:
    result = connection.execute(
        text(
            "UPDATE records SET data=:data,version=version+1,updated_at=:time "
            "WHERE id=:id AND version=:version"
        ),
        {"data": json.dumps(data), "time": now(), "id": record["id"], "version": record["version"]},
    )
    if result.rowcount != 1:
        raise AppError(409, "stale_revision", "This record changed. Reload before continuing.")
    return get(connection, record["id"])


def audit(connection, identifier: str, event: str, data: dict | None = None):
    connection.execute(
        text("INSERT INTO events VALUES (:id,:entity,:actor,:event,:data,:time)"),
        {
            "id": str(uuid4()),
            "entity": identifier,
            "actor": settings.operator,
            "event": event,
            "data": json.dumps(data or {}),
            "time": now(),
        },
    )
