from datetime import UTC, datetime, timedelta

from backend import db
from backend.config import settings
from backend.errors import AppError
from backend.services.comparison import report_is_stale
from backend.services.policies import policy_signature


def allowed_recipients() -> list[str]:
    return [
        value.strip().casefold()
        for value in settings.recipient_allowlist.split(",")
        if value.strip()
    ]


def check_recipient(recipient: str):
    if recipient.strip().casefold() not in allowed_recipients():
        raise AppError(
            422, "recipient_not_allowed", "Choose a recipient from the test contact list."
        )


def ensure_current(connection, action: dict):
    data = action["data"]
    report = db.get(connection, data["comparison_id"], "comparison")
    if report_is_stale(connection, report):
        raise AppError(
            409, "stale_report", "The underlying documents changed. Create a new report and draft."
        )
    if data.get("assessment_id"):
        assessment = db.get(connection, data["assessment_id"], "assessment")
        if assessment["data"]["policy_signature"] != policy_signature(connection):
            raise AppError(
                409, "stale_policy", "Policies changed. Reassess before drafting a new action."
            )
        active_ids = {p["id"] for p in policy_signature(connection)}
        rules = [
            {"id": r["id"], "version": r["version"]}
            for r in db.all_records(connection, "rule")
            if r["data"]["confirmed"] and r["data"]["policy_id"] in active_ids
        ]
        if assessment["data"]["rule_signature"] != rules:
            raise AppError(409, "stale_rule", "Confirmed rules changed. Reassess before drafting.")
    check_recipient(data["recipient"])


def check_version(record: dict, expected: int):
    if record["version"] != expected:
        raise AppError(409, "stale_revision", "Reload this action before continuing.")


def job_response(job: dict) -> dict:
    return {
        "job_id": job["id"],
        "status": job["data"]["status"],
        "status_url": f"/api/v1/jobs/{job['id']}",
    }


class SimulatedEmail:
    def send(self, action: dict) -> dict:
        return {
            "provider": "simulated",
            "message_id": f"simulated-{action['id']}",
            "delivery_confirmed": False,
        }


def recover_expired(connection):
    for job in db.all_records(connection, "job"):
        if (
            job["data"].get("kind") == "email"
            and job["data"]["status"] == "running"
            and job["data"]["lease_until"] < db.now()
        ):
            action = db.get(connection, job["data"]["action_id"], "action")
            db.update(connection, action, {**action["data"], "state": "unknown"})
            db.update(
                connection,
                job,
                {
                    **job["data"],
                    "status": "unknown",
                    "message": "Worker lease expired; reconcile before any resend.",
                },
            )
            db.audit(connection, action["id"], "delivery_unknown")


def process_email_once(sender=None) -> bool:
    with db.transaction() as connection:
        recover_expired(connection)
        queued = [
            j
            for j in db.all_records(connection, "job")
            if j["data"].get("kind") == "email" and j["data"]["status"] == "queued"
        ]
        if not queued:
            return False
        job = queued[0]
        action = db.get(connection, job["data"]["action_id"], "action")
        try:
            ensure_current(connection, action)
            if (
                action["data"]["state"] != "queued"
                or action["data"]["approved_revision"] != action["data"]["content_revision"]
            ):
                raise AppError(409, "approval_required", "Approval is missing or no longer valid.")
            # Revalidate live configuration before marking a job as sending.
            if action["data"]["delivery_mode"] == "ses":
                from backend.services.cloud import require_live

                require_live(send=True)
        except AppError as error:
            db.update(connection, action, {**action["data"], "state": "failed"})
            db.update(
                connection, job, {**job["data"], "status": "failed", "error_code": error.code}
            )
            db.audit(connection, action["id"], "execution_blocked", {"code": error.code})
            return True
        action = db.update(connection, action, {**action["data"], "state": "sending"})
        job = db.update(
            connection,
            job,
            {
                **job["data"],
                "status": "running",
                "lease_until": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
            },
        )
        db.audit(connection, action["id"], "execution_started")
    try:
        if sender is None:
            if action["data"]["delivery_mode"] == "ses":
                from backend.services.cloud import SESEmail

                sender = SESEmail()
            else:
                sender = SimulatedEmail()
        result = sender.send(action)
        state, status = "sent", "succeeded"
    except AppError as error:
        # Adapter uses AppError only for definite pre-send/explicit rejection failures.
        result, state, status = {"error_code": error.code}, "failed", "failed"
    except Exception:
        result, state, status = {"error_code": "delivery_uncertain"}, "unknown", "unknown"
    with db.transaction() as connection:
        action = db.get(connection, action["id"], "action")
        job = db.get(connection, job["id"], "job")
        if job["data"]["status"] != "running":
            # Recovery may have marked a late response unknown; don't overwrite reconciliation.
            return True
        db.update(connection, action, {**action["data"], "state": state, "delivery": result})
        db.update(connection, job, {**job["data"], "status": status, "result": result})
        db.create(
            connection,
            "delivery_attempt",
            {"action_id": action["id"], "job_id": job["id"], "state": state, **result},
        )
        db.audit(connection, action["id"], f"delivery_{state}", result)
    return True
