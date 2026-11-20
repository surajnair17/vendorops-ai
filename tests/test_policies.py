from test_comparison import upload_structured

from backend import db
from backend.services.policies import retrieve


def seed_policy(client, threshold="10"):
    response = client.post(
        "/api/v1/policies",
        json={
            "name": "Purchasing",
            "policy_version": "1",
            "effective_date": "2026-01-01",
            "text": "Invoice price variance up to 10 percent is permitted. "
            "Quantity overage requires review.",
        },
    )
    assert response.status_code == 201, response.text
    policy = response.json()
    assert (
        client.post(
            f"/api/v1/policies/{policy['id']}/activate",
            json={"active": True, "expected_version": policy["version"]},
        ).status_code
        == 200
    )
    rule = client.post(
        "/api/v1/rules",
        json={
            "policy_id": policy["id"],
            "chunk_id": "p1-c1",
            "rule_type": "price_variance_percent",
            "value": threshold,
        },
    ).json()
    return policy, rule


def test_policy_evidence_and_confirmation_boundary(client):
    po, invoice = upload_structured(client, 3), upload_structured(client, 4)
    report = client.post("/api/v1/comparisons", json={"invoice_id": invoice, "po_id": po}).json()
    policy, rule = seed_policy(client)
    path = f"/api/v1/comparisons/{report['id']}/policy-assessments"
    unconfirmed = client.post(path).json()["data"]
    assert unconfirmed["outcomes"][0]["classification"] == "manual_review"
    assert (
        client.post(
            f"/api/v1/rules/{rule['id']}/confirm", json={"active": True, "expected_version": 1}
        ).status_code
        == 200
    )
    confirmed = client.post(path).json()["data"]
    assert confirmed["outcomes"][0]["classification"] == "within_tolerance"
    assert confirmed["evidence"][0]["text"] == policy["data"]["chunks"][0]["text"]
    assert confirmed["rule_citations"][0]["policy_id"] == policy["id"]
    # Conflicting confirmed rules must abstain.
    conflict = client.post(
        "/api/v1/rules",
        json={
            "policy_id": policy["id"],
            "chunk_id": "p1-c1",
            "rule_type": "price_variance_percent",
            "value": "5",
        },
    ).json()
    client.post(
        f"/api/v1/rules/{conflict['id']}/confirm", json={"active": True, "expected_version": 1}
    )
    assert client.post(path).json()["data"]["outcomes"][0]["classification"] == "manual_review"


def test_inactive_policy_excluded_and_invalid_citation(client):
    policy, _ = seed_policy(client)
    client.post(
        f"/api/v1/policies/{policy['id']}/activate", json={"active": False, "expected_version": 3}
    )
    with db.transaction() as connection:
        assert retrieve(connection, "price variance") == []
    response = client.post(
        "/api/v1/rules",
        json={
            "policy_id": policy["id"],
            "chunk_id": "missing",
            "rule_type": "price_variance_percent",
            "value": "10",
        },
    )
    assert response.status_code == 422
