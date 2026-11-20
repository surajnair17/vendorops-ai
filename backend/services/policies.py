import hashlib
import math
import re
from decimal import Decimal

from backend import db
from backend.config import settings
from backend.errors import AppError
from backend.services.comparison import current_business, report_is_stale


def chunks_for(pages: list[str]) -> list[dict]:
    chunks = []
    for page_number, page in enumerate(pages, start=1):
        for paragraph in re.split(r"\n\s*\n", page):
            for start in range(0, len(paragraph), 1000):
                passage = paragraph[start : start + 1200].strip()
                if passage:
                    chunks.append(
                        {
                            "id": f"p{page_number}-c{len(chunks) + 1}",
                            "page": page_number,
                            "text": passage,
                        }
                    )
    return chunks


def embedding(text: str) -> list[float]:
    if settings.provider == "bedrock":
        from backend.services.cloud import embed_text

        return embed_text(text)
    # A deliberately simple lexical fixture. Not a semantic embedding or accuracy claim.
    vector = [0.0] * 64
    for token in re.findall(r"[a-z0-9]+", text.casefold()):
        index = int(hashlib.sha256(token.encode()).hexdigest()[:8], 16) % len(vector)
        vector[index] += 1
    norm = math.sqrt(sum(value * value for value in vector)) or 1
    return [value / norm for value in vector]


def collection():
    import chromadb

    client = chromadb.PersistentClient(path=str(settings.data_dir / "vectors"))
    return client.get_or_create_collection(
        f"policies-{settings.provider}-v1",
        embedding_function=None,
        metadata={"hnsw:space": "cosine"},
    )


def index_policy(policy: dict):
    chunks = policy["data"]["chunks"]
    if not chunks:
        raise AppError(422, "empty_policy", "Policy has no text to index.")
    collection().upsert(
        ids=[f"{policy['id']}:{chunk['id']}" for chunk in chunks],
        documents=[chunk["text"] for chunk in chunks],
        embeddings=[embedding(chunk["text"]) for chunk in chunks],
        metadatas=[
            {"policy_id": policy["id"], "page": chunk["page"], "chunk_id": chunk["id"]}
            for chunk in chunks
        ],
    )


def policy_signature(connection) -> list[dict]:
    return [
        {"id": p["id"], "version": p["version"]}
        for p in db.all_records(connection, "policy")
        if p["data"]["active"] and p["data"]["effective_date"] <= db.now()[:10]
    ]


def retrieve(connection, query: str) -> list[dict]:
    active = policy_signature(connection)
    if not active:
        return []
    result = collection().query(
        query_embeddings=[embedding(query)],
        n_results=5,
        where={"policy_id": {"$in": [p["id"] for p in active]}},
    )
    passages = []
    for identifier, distance, metadata in zip(
        result["ids"][0], result["distances"][0], result["metadatas"][0]
    ):
        if distance > (0.85 if settings.provider == "fixture" else 0.7):
            continue
        policy = db.get(connection, metadata["policy_id"], "policy")
        chunk = next(c for c in policy["data"]["chunks"] if c["id"] == metadata["chunk_id"])
        passages.append(
            {
                "citation_id": identifier,
                "policy_id": policy["id"],
                "policy_name": policy["data"]["name"],
                "policy_version": policy["data"]["policy_version"],
                "page": chunk["page"],
                "chunk_id": chunk["id"],
                "text": chunk["text"],
                "distance": distance,
                "provider": settings.provider,
            }
        )
    return passages


def assess(connection, report: dict) -> dict:
    if report_is_stale(connection, report):
        raise AppError(409, "stale_report", "Recompare the current document revisions first.")
    _, _, invoice = current_business(connection, report["data"]["invoice_id"])
    query = "invoice purchasing policy " + " ".join(
        f["type"].replace("_", " ") for f in report["data"]["findings"]
    )
    evidence = retrieve(connection, query)
    active_ids = {p["id"] for p in policy_signature(connection)}
    rules = [
        r
        for r in db.all_records(connection, "rule")
        if r["data"]["confirmed"] and r["data"]["policy_id"] in active_ids
    ]
    outcomes = []
    for index, finding in enumerate(report["data"]["findings"]):
        kind = {
            "price_variance": "price_variance_percent",
            "quantity_variance": "quantity_overage_percent",
        }.get(finding["type"])
        relevant = [r for r in rules if r["data"]["rule_type"] == kind]
        outcome = "manual_review"
        if len({r["data"]["value"] for r in relevant}) == 1:
            expected, actual = Decimal(finding["expected"]), Decimal(finding["actual"])
            if expected > 0 and (kind != "quantity_overage_percent" or actual >= expected):
                percent = abs(actual - expected) / expected * 100
                outcome = (
                    "within_tolerance"
                    if percent <= Decimal(relevant[0]["data"]["value"])
                    else "outside_tolerance"
                )
        outcomes.append(
            {
                "finding_index": index,
                "classification": outcome,
                "rule_ids": [r["id"] for r in relevant],
            }
        )
    for rule in rules:
        data = rule["data"]
        if data["rule_type"] == "required_field":
            outcomes.append(
                {
                    "rule_ids": [rule["id"]],
                    "field": data["value"],
                    "classification": "satisfied"
                    if getattr(invoice, data["value"], None) is not None
                    else "manual_review",
                }
            )
        if data["rule_type"] == "invoice_value_threshold":
            outcomes.append(
                {
                    "rule_ids": [rule["id"]],
                    "classification": "escalate"
                    if invoice.total is None or invoice.total > Decimal(data["value"])
                    else "below_threshold",
                }
            )
    # Include every applied rule's citation, even if it was outside vector top-k.
    rule_citations = []
    for rule in rules:
        policy = db.get(connection, rule["data"]["policy_id"], "policy")
        chunk = next(c for c in policy["data"]["chunks"] if c["id"] == rule["data"]["chunk_id"])
        rule_citations.append(
            {
                "rule_id": rule["id"],
                "policy_id": policy["id"],
                "policy_name": policy["data"]["name"],
                "policy_version": policy["data"]["policy_version"],
                **chunk,
            }
        )
    return {
        "comparison_id": report["id"],
        "evidence": evidence,
        "rule_citations": rule_citations,
        "outcomes": outcomes,
        "policy_signature": policy_signature(connection),
        "rule_signature": [{"id": r["id"], "version": r["version"]} for r in rules],
        "message": "Policy evidence retrieved." if evidence else "Insufficient policy evidence.",
        "provider": settings.provider,
    }
