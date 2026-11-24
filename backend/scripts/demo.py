"""Seed a synthetic walkthrough over real HTTP. Never approves or sends an email."""

import json

import httpx
import pymupdf

from backend.config import settings
from backend.examples import examples


def seed(client) -> dict:

    def request(method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    metrics = request("GET", "/metrics")
    if metrics["provider"] != "fixture" or metrics["live_calls_enabled"]:
        raise ValueError("The sample seeder requires a fixture backend with live calls disabled.")
    documents = []
    for example in examples()[3:5]:
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((40, 50), example["text"], fontsize=10)
            document = request(
                "POST",
                "/documents",
                files={"file": (example["data"]["document_number"] + ".pdf", pdf.tobytes())},
            )
        request("POST", f"/documents/{document['id']}/structure")
        documents.append(document["id"])
    report = request(
        "POST", "/comparisons", json={"invoice_id": documents[1], "po_id": documents[0]}
    )
    contacts = request("GET", "/contacts")
    if not contacts:
        raise ValueError("Configure at least one test recipient")
    policies = request("GET", "/policies")
    policy = next((p for p in policies if p["data"]["name"] == "Demo purchasing"), None)
    if policy is None:
        policy = request(
            "POST",
            "/policies",
            json={
                "name": "Demo purchasing",
                "policy_version": "1",
                "effective_date": "2026-01-01",
                "text": "Invoice unit price variance up to 10 percent is permitted.",
            },
        )
        request(
            "POST",
            "/rules",
            json={
                "policy_id": policy["id"],
                "chunk_id": "p1-c1",
                "rule_type": "price_variance_percent",
                "value": "10",
            },
        )
    action = request(
        "POST",
        "/actions",
        json={
            "comparison_id": report["id"],
            "recipient": contacts[0],
            "delivery_mode": "simulated",
        },
    )
    return {
        "document_ids": documents,
        "comparison_id": report["id"],
        "action_id": action["id"],
        "policy_id": policy["id"],
        "next": "Review the draft in Streamlit. Nothing has been approved or sent.",
    }


def main():
    with httpx.Client(base_url=settings.backend_url + "/api/v1", timeout=60) as client:
        print(json.dumps(seed(client), indent=2))


if __name__ == "__main__":
    main()
