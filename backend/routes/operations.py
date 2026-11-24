from collections import Counter

from fastapi import APIRouter

from backend import db
from backend.config import settings
from backend.errors import AppError
from backend.services.cloud import require_live
from backend.services.policies import index_policy
from backend.services.workflow import job_response

router = APIRouter(prefix="/api/v1", tags=["operations"])


@router.get("/jobs")
def list_jobs(document_id: str | None = None):
    with db.transaction() as connection:
        return [
            j
            for j in db.all_records(connection, "job")
            if document_id is None or j["data"].get("document_id") == document_id
        ]


@router.post("/documents/{identifier}/ocr", status_code=202)
def request_ocr(identifier: str):
    if settings.ocr_provider == "disabled":
        raise AppError(403, "ocr_disabled", "OCR is disabled in this deployment.")
    if settings.ocr_provider == "textract":
        require_live()
    if settings.ocr_provider == "local":
        from backend.services.local_ocr import require_tesseract

        require_tesseract()
    if settings.ocr_provider == "textract" and not all(
        (
            settings.s3_bucket,
            settings.sns_topic_arn,
            settings.textract_role_arn,
            settings.sqs_queue_url,
        )
    ):
        raise AppError(
            422, "ocr_not_configured", "Configure S3, Textract notification role, SNS, and SQS."
        )
    with db.transaction() as connection:
        document = db.get(connection, identifier, "document")
        if document["data"]["page_count"] > settings.max_document_pages:
            raise AppError(413, "too_many_pages", "Document exceeds the OCR page budget.")
        existing = next(
            (
                j
                for j in db.all_records(connection, "job")
                if j["data"].get("kind") == "ocr"
                and j["data"].get("document_id") == identifier
                and j["data"]["status"] in {"queued", "starting", "waiting"}
            ),
            None,
        )
        if existing:
            return job_response(existing)
        job = db.create(
            connection,
            "job",
            {
                "kind": "ocr",
                "provider": settings.ocr_provider,
                "status": "queued",
                "document_id": identifier,
                "document_version": document["version"],
            },
        )
        return job_response(job)


@router.post("/policies/{identifier}/reindex")
def reindex(identifier: str):
    with db.transaction() as connection:
        policy = db.get(connection, identifier, "policy")
    index_policy(policy)
    with db.transaction() as connection:
        policy = db.get(connection, identifier, "policy")
        return db.update(
            connection,
            policy,
            {
                **policy["data"],
                "indexed": True,
                "index_provider": settings.provider,
                "embedding_model_id": settings.embedding_model_id
                if settings.provider == "bedrock"
                else None,
            },
        )


@router.get("/metrics")
def metrics():
    with db.transaction() as connection:
        jobs = db.all_records(connection, "job")
        actions = db.all_records(connection, "action")
        usage = db.all_records(connection, "usage")
        return {
            "provider": settings.provider,
            "live_calls_enabled": settings.live_calls_enabled,
            "live_send_enabled": settings.live_send_enabled,
            "ocr_provider": settings.ocr_provider,
            "model_id": settings.model_id if settings.provider == "bedrock" else None,
            "operator": settings.operator,
            "documents": len(db.all_records(connection, "document")),
            "job_statuses": dict(Counter(j["data"]["status"] for j in jobs)),
            "action_states": dict(Counter(a["data"]["state"] for a in actions)),
            "usage": usage,
            "cost_note": "Usage counts are not a cloud bill. See cost worksheet.",
        }
