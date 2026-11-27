import math

import pytest

from backend import db
from backend.config import settings
from backend.errors import AppError
from backend.services.vectors import SQLiteCollection


def test_exact_cosine_ranking_filter_and_persistence(client):
    store = SQLiteCollection("fixture")
    store.upsert(
        ids=["same", "other", "inactive"],
        documents=["a", "b", "c"],
        embeddings=[[1, 0], [0, 1], [1, 0]],
        metadatas=[{"policy_id": "active"}, {"policy_id": "active"}, {"policy_id": "inactive"}],
    )
    db.engine_for(str(settings.data_dir.resolve())).dispose()
    # Retrieval also works while the caller owns the policy-assessment write transaction.
    with db.transaction():
        result = SQLiteCollection("fixture").query(
            query_embeddings=[[1, 0]], n_results=5, where={"policy_id": {"$in": ["active"]}}
        )
    assert result["ids"] == [["same", "other"]]
    assert result["distances"] == [[0.0, 1.0]]
    assert SQLiteCollection("bedrock-other-model").query(
        query_embeddings=[[1, 0]], n_results=5, where={"policy_id": {"$in": ["active"]}}
    )["ids"] == [[]]


def test_upsert_replaces_and_dimension_mismatch_requires_reindex(client):
    store = SQLiteCollection("demo")
    payload = {"ids": ["one"], "documents": ["text"], "metadatas": [{"policy_id": "p1"}]}
    store.upsert(**payload, embeddings=[[1, 0]])
    store.upsert(**payload, embeddings=[[0, 1]])
    with db.transaction() as connection:
        assert len(db.all_records(connection, "policy_vector")) == 1
    with pytest.raises(AppError) as error:
        store.query(query_embeddings=[[1, 0, 0]], n_results=5, where={"policy_id": {"$in": ["p1"]}})
    assert error.value.code == "reindex_required"


def test_invalid_vector_never_enters_the_index(client):
    with pytest.raises(ValueError):
        SQLiteCollection("demo").upsert(
            ids=["bad"],
            documents=["text"],
            embeddings=[[math.nan]],
            metadatas=[{"policy_id": "p1"}],
        )
    with db.transaction() as connection:
        assert db.all_records(connection, "policy_vector") == []


def test_cosine_handles_extreme_finite_magnitudes_without_overflow(client):
    store = SQLiteCollection("extreme")
    store.upsert(
        ids=["same", "orthogonal"],
        documents=["same", "orthogonal"],
        embeddings=[[1e300, 1e300], [1e300, -1e300]],
        metadatas=[{"policy_id": "p"}, {"policy_id": "p"}],
    )
    result = store.query(
        query_embeddings=[[1e-300, 1e-300]], n_results=2, where={"policy_id": {"$in": ["p"]}}
    )
    assert result["ids"] == [["same", "orthogonal"]]
    assert result["distances"][0] == pytest.approx([0, 1])


def test_switching_index_backend_requires_rebuild(client):
    from test_policies import seed_policy

    from backend.services.policies import retrieve

    policy, _ = seed_policy(client)
    with db.transaction() as connection:
        current = db.get(connection, policy["id"], "policy")
        db.update(connection, current, {**current["data"], "index_store": "chroma"})
    with db.transaction() as connection, pytest.raises(AppError) as error:
        retrieve(connection, "invoice price variance")
    assert error.value.code == "reindex_required"
    assert client.post(f"/api/v1/policies/{policy['id']}/reindex").status_code == 200
    with db.transaction() as connection:
        assert retrieve(connection, "invoice price variance")
