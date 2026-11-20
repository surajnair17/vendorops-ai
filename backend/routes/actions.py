from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import text

from backend import db
from backend.config import settings
from backend.errors import AppError
from backend.services.workflow import (allowed_recipients, check_recipient, check_version,
                                       ensure_current, job_response)

router = APIRouter(prefix="/api/v1", tags=["actions"])


class DraftInput(BaseModel):
    comparison_id: str
    assessment_id: str | None = None
    recipient: str
    action_type: Literal["clarification", "corrected_invoice", "internal_escalation"] = "clarification"
    delivery_mode: Literal["simulated", "ses"] = "simulated"


@router.get("/contacts")
def contacts():
    return allowed_recipients()


@router.post("/actions", status_code=201)
def draft(payload: DraftInput):
    check_recipient(payload.recipient)
    with db.transaction() as connection:
        report = db.get(connection, payload.comparison_id, "comparison")
        if payload.assessment_id:
            assessment = db.get(connection, payload.assessment_id, "assessment")
            if assessment["data"]["comparison_id"] != report["id"]:
                raise AppError(422, "assessment_mismatch", "Choose an assessment of this report.")
        findings = report["data"]["findings"]
        subject = {"clarification": "Invoice clarification requested",
                   "corrected_invoice": "Corrected invoice requested",
                   "internal_escalation": "Invoice review escalation"}[payload.action_type]
        body = (f"Please review comparison {report['id']}.\n" +
                "\n".join(f"- {f['type']}: {f.get('field', 'document')} "
                          f"(expected {f.get('expected', 'review')}; actual {f.get('actual', 'review')})"
                          for f in findings) + "\nPlease clarify these findings. No payment is authorized.")
        data = {**payload.model_dump(), "recipient": payload.recipient.strip().casefold(),
                "subject": subject, "body": body, "state": "draft", "content_revision": 1,
                "approved_revision": None, "job_id": None, "draft_provider": "fixture_template"}
        ensure_current(connection, {"data": data})
    if settings.provider == "bedrock":
        from backend.services.cloud import draft_email
        generated = draft_email(subject, body)
        data.update(generated)
        data["draft_provider"] = "bedrock"
    with db.transaction() as connection:
        ensure_current(connection, {"data": data})
        action = db.create(connection, "action", data)
        db.create(connection, "action_revision", {"action_id": action["id"], **data})
        db.audit(connection, action["id"], "draft_created")
        return action


@router.get("/actions")
def list_actions():
    with db.transaction() as connection:
        return db.all_records(connection, "action")


class ExpectedVersion(BaseModel):
    expected_version: int


class EditInput(ExpectedVersion):
    recipient: str
    subject: str = Field(min_length=1, max_length=200, pattern=r"^[^\r\n]+$")
    body: str = Field(min_length=1, max_length=10000)


@router.patch("/actions/{identifier}")
def edit(identifier: str, payload: EditInput):
    check_recipient(payload.recipient)
    with db.transaction() as connection:
        action = db.get(connection, identifier, "action")
        check_version(action, payload.expected_version)
        if action["data"]["state"] not in {"draft", "pending_review", "approved", "rejected", "failed"}:
            raise AppError(409, "invalid_transition", "This action cannot be edited in its current state.")
        data = {**action["data"], **payload.model_dump(exclude={"expected_version"}),
                "state": "draft", "approved_revision": None,
                "content_revision": action["data"]["content_revision"] + 1, "job_id": None}
        ensure_current(connection, {"data": data})
        result = db.update(connection, action, data)
        db.create(connection, "action_revision", {"action_id": identifier, **data})
        db.audit(connection, identifier, "draft_edited_approval_invalidated")
        return result


@router.post("/actions/{identifier}/request-review")
def request_review(identifier: str, payload: ExpectedVersion):
    with db.transaction() as connection:
        action = db.get(connection, identifier, "action")
        check_version(action, payload.expected_version)
        ensure_current(connection, action)
        if action["data"]["state"] != "draft":
            raise AppError(409, "invalid_transition", "Only drafts can be submitted for review.")
        result = db.update(connection, action, {**action["data"], "state": "pending_review"})
        db.create(connection, "review_task", {"action_id": identifier,
                  "content_revision": action["data"]["content_revision"], "status": "pending"})
        db.audit(connection, identifier, "review_requested")
        return result


class Decision(ExpectedVersion):
    decision: Literal["approve", "reject"]


@router.post("/actions/{identifier}/review")
def review(identifier: str, payload: Decision):
    with db.transaction() as connection:
        action = db.get(connection, identifier, "action")
        check_version(action, payload.expected_version)
        ensure_current(connection, action)
        if action["data"]["state"] != "pending_review":
            raise AppError(409, "invalid_transition", "Only pending actions can be reviewed.")
        state = "approved" if payload.decision == "approve" else "rejected"
        result = db.update(connection, action, {**action["data"], "state": state,
                           "approved_revision": action["data"]["content_revision"] if state == "approved" else None})
        db.create(connection, "approval", {"action_id": identifier, "decision": payload.decision,
                  "content_revision": action["data"]["content_revision"], "operator": settings.operator})
        for task in db.all_records(connection, "review_task"):
            if task["data"]["action_id"] == identifier and task["data"]["status"] == "pending":
                db.update(connection, task, {**task["data"], "status": state})
        db.audit(connection, identifier, state)
        return result


@router.post("/actions/{identifier}/execute", status_code=202)
def execute(identifier: str, payload: ExpectedVersion):
    with db.transaction() as connection:
        action = db.get(connection, identifier, "action")
        if action["data"]["job_id"]:
            return job_response(db.get(connection, action["data"]["job_id"], "job"))
        check_version(action, payload.expected_version)
        ensure_current(connection, action)
        if action["data"]["state"] != "approved" or action["data"]["approved_revision"] != action["data"]["content_revision"]:
            raise AppError(409, "approval_required", "Approve this exact action revision before execution.")
        if action["data"]["delivery_mode"] == "ses":
            from backend.services.cloud import require_live
            require_live(send=True)
        job = db.create(connection, "job", {"kind": "email", "status": "queued", "action_id": identifier})
        db.update(connection, action, {**action["data"], "state": "queued", "job_id": job["id"]})
        db.audit(connection, identifier, "execution_queued")
        return job_response(job)


@router.get("/jobs/{identifier}")
def job(identifier: str):
    with db.transaction() as connection:
        return db.get(connection, identifier, "job")


class ReconcileInput(ExpectedVersion):
    outcome: Literal["sent", "not_sent"]
    evidence: str = Field(min_length=10, max_length=1000)


@router.post("/actions/{identifier}/reconcile")
def reconcile(identifier: str, payload: ReconcileInput):
    with db.transaction() as connection:
        action = db.get(connection, identifier, "action")
        check_version(action, payload.expected_version)
        if action["data"]["state"] != "unknown":
            raise AppError(409, "invalid_transition", "Only unknown deliveries need reconciliation.")
        state = "sent" if payload.outcome == "sent" else "failed"
        result = db.update(connection, action, {**action["data"], "state": state,
                           "reconciliation": payload.model_dump()})
        job = db.get(connection, action["data"]["job_id"], "job")
        db.update(connection, job, {**job["data"], "status": "succeeded" if state == "sent" else "failed"})
        db.audit(connection, identifier, "delivery_reconciled", payload.model_dump())
        return result


@router.get("/audit")
def audit_history():
    with db.transaction() as connection:
        return [dict(row) for row in connection.execute(text("SELECT * FROM events ORDER BY created_at")).mappings()]
