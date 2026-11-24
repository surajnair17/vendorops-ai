import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from backend import db
from backend.config import settings
from backend.errors import AppError
from backend.services.cloud import aws_client, put_source, require_live, reserve_usage


def start_ocr_once() -> bool:
    if not settings.live_calls_enabled:
        return False
    with db.transaction() as connection:
        for waiting in db.all_records(connection, "job"):
            if (
                waiting["data"].get("kind") == "ocr"
                and waiting["data"]["status"] == "waiting"
                and datetime.fromisoformat(waiting["created_at"])
                < datetime.now(UTC) - timedelta(days=6)
            ):
                db.update(
                    connection,
                    waiting,
                    {**waiting["data"], "status": "failed", "error_code": "ocr_results_expired"},
                )
        jobs = [
            j
            for j in db.all_records(connection, "job")
            if j["data"].get("kind") == "ocr"
            and (
                j["data"]["status"] == "queued"
                or j["data"]["status"] == "starting"
                and j["data"]["lease_until"] < db.now()
            )
        ]
        if not jobs:
            return False
        job = jobs[0]
        if datetime.fromisoformat(job["created_at"]) < datetime.now(UTC) - timedelta(days=6):
            db.update(
                connection,
                job,
                {**job["data"], "status": "failed", "error_code": "ocr_start_expired"},
            )
            return True
        document = db.get(connection, job["data"]["document_id"], "document")
        if (
            document["version"] != job["data"]["document_version"]
            or job["data"].get("start_attempts", 0) >= 3
        ):
            db.update(
                connection,
                job,
                {
                    **job["data"],
                    "status": "failed",
                    "error_code": "ocr_start_failed_or_document_changed",
                },
            )
            return True
        reserve_usage("ocr", connection, token=job["id"])
        job = db.update(
            connection,
            job,
            {
                **job["data"],
                "status": "starting",
                "start_attempts": job["data"].get("start_attempts", 0) + 1,
                "lease_until": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
            },
        )
    try:
        key = put_source(document["id"], Path(document["data"]["source"]).read_bytes())
        response = aws_client("textract").start_document_text_detection(
            DocumentLocation={"S3Object": {"Bucket": settings.s3_bucket, "Name": key}},
            ClientRequestToken=job["id"],
            JobTag=job["id"],
            NotificationChannel={
                "SNSTopicArn": settings.sns_topic_arn,
                "RoleArn": settings.textract_role_arn,
            },
        )
    except Exception as error:
        # The deterministic token allows safe restart while still within Textract's token window.
        with db.transaction() as connection:
            current = db.get(connection, job["id"], "job")
            db.update(
                connection,
                current,
                {
                    **current["data"],
                    "last_error_code": error.code
                    if isinstance(error, AppError)
                    else "ocr_provider_error",
                },
            )
            db.audit(connection, document["id"], "ocr_start_retry_pending", {"job_id": job["id"]})
        return True
    with db.transaction() as connection:
        current = db.get(connection, job["id"], "job")
        db.update(
            connection,
            current,
            {
                **current["data"],
                "status": "waiting",
                "textract_job_id": response["JobId"],
                "s3_key": key,
            },
        )
        db.audit(connection, document["id"], "ocr_started", {"job_id": job["id"]})
    return True


def complete_ocr(notification: dict) -> bool:
    identifier = notification.get("JobTag")
    if not identifier:
        return False
    with db.transaction() as connection:
        try:
            job = db.get(connection, identifier, "job")
        except AppError:
            return False
        if job["data"].get("kind") != "ocr":
            return False
        if job["data"]["status"] in {"succeeded", "failed"}:
            return True
        if job["data"].get("textract_job_id") != notification.get("JobId"):
            return False
        document = db.get(connection, job["data"]["document_id"], "document")
    status = notification.get("Status")
    if status not in {"SUCCEEDED", "FAILED", "PARTIAL_SUCCESS"}:
        return False
    pages = [[] for _ in range(document["data"]["page_count"])]
    if status == "SUCCEEDED":
        next_token = None
        while True:
            arguments = {"JobId": notification["JobId"]}
            if next_token:
                arguments["NextToken"] = next_token
            result = aws_client("textract").get_document_text_detection(**arguments)
            if result.get("JobStatus") != "SUCCEEDED":
                status = "FAILED"
                break
            for block in result.get("Blocks", []):
                page = block.get("Page", 0)
                if block.get("BlockType") == "LINE" and 1 <= page <= len(pages):
                    pages[page - 1].append(block["Text"])
            next_token = result.get("NextToken")
            if not next_token:
                break
    with db.transaction() as connection:
        current = db.get(connection, job["id"], "job")
        if current["data"]["status"] in {"succeeded", "failed"}:
            return True
        document = db.get(connection, document["id"], "document")
        if status != "SUCCEEDED" or document["version"] != job["data"]["document_version"]:
            db.update(
                connection,
                current,
                {
                    **current["data"],
                    "status": "failed",
                    "error_code": "ocr_failed_or_document_changed",
                },
            )
            return True
        combined = [
            original if original.strip() else "\n".join(scanned)
            for original, scanned in zip(document["data"]["pages"], pages)
        ]
        db.create(
            connection,
            "text_revision",
            {
                "document_id": document["id"],
                "original_pages": document["data"]["pages"],
                "ocr_pages": ["\n".join(p) for p in pages],
                "combined_pages": combined,
                "provider": "textract",
                "job_id": job["id"],
            },
        )
        db.update(
            connection,
            document,
            {
                **document["data"],
                "pages": combined,
                "revision_id": None,
                "ocr_status": "completed",
                "s3_key": job["data"]["s3_key"],
            },
        )
        db.update(
            connection,
            current,
            {**current["data"], "status": "succeeded", "page_count": len(pages)},
        )
        db.audit(connection, document["id"], "ocr_completed", {"job_id": job["id"]})
    return True


def poll_ocr_once() -> bool:
    if not settings.live_calls_enabled or not settings.sqs_queue_url:
        return False
    require_live()
    sqs = aws_client("sqs")
    response = sqs.receive_message(
        QueueUrl=settings.sqs_queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=1
    )
    for message in response.get("Messages", []):
        envelope = json.loads(message["Body"])
        notification = json.loads(envelope["Message"]) if "Message" in envelope else envelope
        if complete_ocr(notification):
            sqs.delete_message(
                QueueUrl=settings.sqs_queue_url, ReceiptHandle=message["ReceiptHandle"]
            )
            return True
    return False
