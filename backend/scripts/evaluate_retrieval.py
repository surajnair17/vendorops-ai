"""Evaluate the production retriever in an isolated index with labelled policy queries."""

import argparse
import json
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings
from sqlalchemy import create_engine

from backend import db
from backend.config import settings
from backend.services.policies import chunks_for, embedding, index_policy, retrieve


def evaluate(policies: list[dict], queries: list[dict]) -> dict:
    store = chromadb.EphemeralClient(settings=ChromaSettings(anonymized_telemetry=False))
    vector_store = store.create_collection(
        "retrieval-benchmark", embedding_function=None, metadata={"hnsw:space": "cosine"}
    )
    engine = create_engine("sqlite://")
    hits1 = hits5 = relevant_total = supported = returned = 0
    details = []
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE records (id TEXT PRIMARY KEY, kind TEXT, "
                "version INTEGER, data TEXT, created_at TEXT, updated_at TEXT)"
            )
            for policy in policies:
                record = db.create(
                    connection,
                    "policy",
                    {
                        **policy,
                        "active": True,
                        "indexed": True,
                        "index_provider": settings.provider,
                        "chunks": chunks_for([policy["text"]]),
                    },
                    policy["name"],
                )
                index_policy(record, vector_store)
            for query in queries:
                # Usage reservations persist in the application ledger; this DB holds only labels.
                vector = embedding(query["query"])
                passages = retrieve(connection, query["query"], vector_store, query_vector=vector)
                names = [p["policy_name"] for p in passages]
                expected = set(query["relevant_policy_names"])
                relevant_total += len(expected)
                hits1 += len(expected & set(names[:1]))
                hits5 += len(expected & set(names[:5]))
                for passage in passages:
                    policy = next(p for p in policies if p["name"] == passage["policy_name"])
                    supported += passage["text"] in policy["text"]
                    returned += 1
                details.append(
                    {"query": query["query"], "expected": sorted(expected), "retrieved": names}
                )
    finally:
        engine.dispose()
        store.delete_collection("retrieval-benchmark")
    return {
        "mode": "live_embeddings" if settings.provider == "bedrock" else "fixture_lexical_only",
        "queries": len(queries),
        "policy_count": len(policies),
        "recall_at_1": hits1 / relevant_total if relevant_total else None,
        "recall_at_5": hits5 / relevant_total if relevant_total else None,
        "citation_quote_accuracy": supported / returned if returned else None,
        "details": details,
        "limitation": "Five policies make recall@5 a weak benchmark. "
        "Expand distractor policies and held-out queries before a customer claim.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=Path, default=Path("backend/artifacts/samples"))
    parser.add_argument(
        "--output", type=Path, default=Path("backend/artifacts/retrieval-evaluation.json")
    )
    parser.add_argument(
        "--live", action="store_true", help="Explicitly opt in to configured paid embeddings"
    )
    args = parser.parse_args()
    if args.live != (settings.provider == "bedrock"):
        parser.error(
            "Use fixture mode, or set the bedrock provider with --live and the live-call gates."
        )
    policies = json.loads((args.samples / "policies.json").read_text(encoding="utf-8"))
    queries = json.loads((args.samples / "policy-queries.json").read_text(encoding="utf-8"))
    result = evaluate(policies, queries)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
