from test_comparison import upload_structured

from backend import db
from backend.services.workflow import process_email_once


def new_action(client):
    po, invoice = upload_structured(client, 3), upload_structured(client, 4)
    report = client.post("/api/v1/comparisons", json={"invoice_id": invoice, "po_id": po}).json()
    response = client.post(
        "/api/v1/actions",
        json={"comparison_id": report["id"], "recipient": "reviewer@example.test"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def approve(client, action):
    action = client.post(
        f"/api/v1/actions/{action['id']}/request-review",
        json={"expected_version": action["version"]},
    ).json()
    return client.post(
        f"/api/v1/actions/{action['id']}/review",
        json={"expected_version": action["version"], "decision": "approve"},
    ).json()


def test_approval_and_duplicate_execution(client):
    action = new_action(client)
    path = f"/api/v1/actions/{action['id']}/execute"
    assert client.post(path, json={"expected_version": action["version"]}).status_code == 409
    action = approve(client, action)
    first = client.post(path, json={"expected_version": action["version"]})
    second = client.post(path, json={"expected_version": action["version"]})
    assert first.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]
    assert process_email_once()
    assert not process_email_once()
    job = client.get(first.json()["status_url"]).json()
    assert job["data"]["result"]["provider"] == "simulated"
    assert job["data"]["status"] == "succeeded"


def test_edit_invalidates_approval_and_recipient_guard(client):
    action = approve(client, new_action(client))
    payload = {
        "expected_version": action["version"],
        "recipient": "evil@example.test",
        "subject": "Changed",
        "body": "Changed body",
    }
    assert client.patch(f"/api/v1/actions/{action['id']}", json=payload).status_code == 422
    payload["recipient"] = "reviewer@example.test"
    edited = client.patch(f"/api/v1/actions/{action['id']}", json=payload).json()
    assert edited["data"]["approved_revision"] is None
    assert (
        client.post(
            f"/api/v1/actions/{action['id']}/execute", json={"expected_version": edited["version"]}
        ).status_code
        == 409
    )


def test_uncertain_delivery_never_retries(client):
    action = approve(client, new_action(client))
    response = client.post(
        f"/api/v1/actions/{action['id']}/execute", json={"expected_version": action["version"]}
    )

    class Uncertain:
        def send(self, action):
            raise TimeoutError("might have sent")

    process_email_once(Uncertain())
    assert client.get(response.json()["status_url"]).json()["data"]["status"] == "unknown"
    assert not process_email_once()
    with db.transaction() as connection:
        assert len(db.all_records(connection, "delivery_attempt")) == 1


def test_report_change_blocks_queued_execution(client):
    action = approve(client, new_action(client))
    response = client.post(
        f"/api/v1/actions/{action['id']}/execute", json={"expected_version": action["version"]}
    )
    with db.transaction() as connection:
        report = db.get(connection, action["data"]["comparison_id"], "comparison")
        document = db.get(connection, report["data"]["invoice_id"], "document")
        db.update(connection, document, {**document["data"], "revision_id": "changed"})
    process_email_once()
    assert client.get(response.json()["status_url"]).json()["data"]["status"] == "failed"


def test_expired_sending_lease_recovers_as_unknown_then_can_be_reconciled(client):
    action = approve(client, new_action(client))
    response = client.post(
        f"/api/v1/actions/{action['id']}/execute", json={"expected_version": action["version"]}
    )
    with db.transaction() as connection:
        current = db.get(connection, action["id"])
        db.update(connection, current, {**current["data"], "state": "sending"})
        job = db.get(connection, response.json()["job_id"])
        db.update(
            connection, job, {**job["data"], "status": "running", "lease_until": "2000-01-01"}
        )
    assert not process_email_once()
    current = client.get(f"/api/v1/actions/{action['id']}").json()
    assert current["data"]["state"] == "unknown"
    result = client.post(
        f"/api/v1/actions/{action['id']}/reconcile",
        json={
            "expected_version": current["version"],
            "outcome": "not_sent",
            "evidence": "Checked the test inbox and provider delivery records.",
        },
    )
    assert result.status_code == 200
    assert result.json()["data"]["state"] == "failed"


def test_pending_task_superseded_when_draft_changes(client):
    action = new_action(client)
    pending = client.post(
        f"/api/v1/actions/{action['id']}/request-review",
        json={"expected_version": action["version"]},
    ).json()
    response = client.patch(
        f"/api/v1/actions/{action['id']}",
        json={
            "expected_version": pending["version"],
            "recipient": "reviewer@example.test",
            "subject": "Corrected subject",
            "body": "Please review the corrected draft.",
        },
    )
    assert response.status_code == 200
    detail = client.get(f"/api/v1/actions/{action['id']}").json()
    assert detail["history"]["review_task"][0]["data"]["status"] == "superseded"
    assert len(detail["history"]["action_revision"]) == 2


def test_two_workers_cannot_send_the_same_job(client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Lock

    action = approve(client, new_action(client))
    client.post(
        f"/api/v1/actions/{action['id']}/execute", json={"expected_version": action["version"]}
    )
    calls = []
    lock = Lock()

    class Sender:
        def send(self, item):
            with lock:
                calls.append(item["id"])
            return {"provider": "simulated", "message_id": "concurrent-test"}

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: process_email_once(Sender()), range(2)))
    assert sorted(results) == [False, True]
    assert calls == [action["id"]]
