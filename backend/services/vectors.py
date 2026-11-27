"""Exact cosine retrieval for a small local corpus without native vector dependencies."""

import math
from contextlib import nullcontext

from backend import db
from backend.config import settings
from backend.errors import AppError


def vector(values):
    result = [float(value) for value in values]
    if not result or not all(math.isfinite(value) for value in result):
        raise ValueError("Vectors must be nonempty and finite")
    scale = max(map(abs, result))
    if not scale:
        return result
    scaled = [value / scale for value in result]
    norm = math.sqrt(sum(value * value for value in scaled))
    return [value / norm for value in scaled]


class SQLiteCollection:
    def __init__(self, namespace: str, connection=None):
        self.namespace = namespace
        self.connection = connection

    def upsert(self, *, ids, documents, embeddings, metadatas):
        if not len(ids) == len(documents) == len(embeddings) == len(metadatas):
            raise ValueError("Vector batch lengths differ")
        values = [vector(item) for item in embeddings]
        context = nullcontext(self.connection) if self.connection is not None else db.transaction()
        with context as connection:
            existing = {
                row["data"]["vector_id"]: row
                for row in db.all_records(connection, "policy_vector")
                if row["data"]["namespace"] == self.namespace
            }
            for identifier, document, embedding, metadata in zip(ids, documents, values, metadatas):
                data = {
                    "namespace": self.namespace,
                    "vector_id": identifier,
                    "document": document,
                    "embedding": embedding,
                    "metadata": metadata,
                }
                if identifier in existing:
                    db.update(connection, existing[identifier], data)
                else:
                    db.create(connection, "policy_vector", data)

    def query(self, *, query_embeddings, n_results, where):
        permitted = set(where["policy_id"]["$in"])
        context = (
            nullcontext(self.connection)
            if self.connection is not None
            else db.engine_for(str(settings.data_dir.resolve())).connect()
        )
        with context as connection:
            rows = [
                row["data"]
                for row in db.all_records(connection, "policy_vector")
                if row["data"]["namespace"] == self.namespace
                and row["data"]["metadata"]["policy_id"] in permitted
            ]
        output = {"ids": [], "distances": [], "metadatas": []}
        for raw in query_embeddings:
            query = vector(raw)
            norm = math.sqrt(sum(value * value for value in query))
            scored = []
            for row in rows:
                try:
                    candidate = vector(row["embedding"])
                except ValueError as error:
                    raise AppError(
                        409, "reindex_required", "Stored vectors are invalid; rebuild the index."
                    ) from error
                if len(candidate) != len(query):
                    raise AppError(
                        409, "reindex_required", "Rebuild policy vectors with this model."
                    )
                candidate_norm = math.sqrt(sum(value * value for value in candidate))
                similarity = (
                    sum(a * b for a, b in zip(query, candidate)) / (norm * candidate_norm)
                    if norm and candidate_norm
                    else 0
                )
                distance = 1 - max(-1.0, min(1.0, similarity))
                scored.append((distance, row["vector_id"], row["metadata"]))
            selected = sorted(scored, key=lambda row: (row[0], row[1]))[:n_results]
            output["ids"].append([row[1] for row in selected])
            output["distances"].append([row[0] for row in selected])
            output["metadatas"].append([row[2] for row in selected])
        return output
