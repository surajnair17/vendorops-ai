import pytest
from conftest import make_pdf

from backend import db
from backend.config import settings
from backend.errors import AppError
from backend.services.cloud import BedrockProvider, SESEmail, reserve_usage
from backend.services.ocr import complete_ocr, start_ocr_once


def test_cloud_disabled_before_sdk_is_called(client, monkeypatch):
    monkeypatch.setattr(settings, "live_calls_enabled", False)
    monkeypatch.setattr(settings, "ocr_provider", "textract")
    with pytest.raises(AppError) as error:
        BedrockProvider().extract("hello")
    assert error.value.code == "live_calls_disabled"
    assert client.post("/api/v1/documents/anything/ocr").status_code == 403


def test_model_schema_request_usage_and_limit(client, monkeypatch):
    monkeypatch.setattr(settings, "live_calls_enabled", True)
    monkeypatch.setattr(settings, "approved_monthly_budget_usd", 1)
    monkeypatch.setattr(settings, "daily_model_calls", 1)

    class Model:
        def converse(self, **kwargs):
            assert "untrusted" in kwargs["system"][0]["text"]
            assert kwargs["inferenceConfig"]["maxTokens"] == settings.max_output_tokens
            return {
                "output": {"message": {"content": [{"text": '{"document_type":"invoice"}'}]}},
                "usage": {"inputTokens": 10, "outputTokens": 5},
                "stopReason": "end_turn",
            }

    monkeypatch.setattr("backend.services.cloud.aws_client", lambda service: Model())
    assert "invoice" in BedrockProvider().extract("test")
    with pytest.raises(AppError) as error:
        reserve_usage("embedding")
    assert error.value.status == 429
    with db.transaction() as connection:
        assert db.all_records(connection, "usage")[0]["data"]["inputTokens"] == 10


def test_ses_exact_approved_content_contract(client, monkeypatch):
    monkeypatch.setattr(settings, "live_calls_enabled", True)
    monkeypatch.setattr(settings, "live_send_enabled", True)
    monkeypatch.setattr(settings, "approved_monthly_budget_usd", 1)
    monkeypatch.setattr(settings, "ses_sender", "sender@example.test")

    class SES:
        def send_email(self, **kwargs):
            assert kwargs["Destination"] == {"ToAddresses": ["reviewer@example.test"]}
            assert kwargs["Content"]["Simple"]["Body"]["Text"]["Data"] == "Approved content"
            return {"MessageId": "stub-message"}

    monkeypatch.setattr("backend.services.cloud.aws_client", lambda service: SES())
    result = SESEmail().send(
        {
            "id": "a1",
            "data": {
                "recipient": "reviewer@example.test",
                "subject": "Invoice",
                "body": "Approved content",
                "content_revision": 1,
            },
        }
    )
    assert result["message_id"] == "stub-message"
    assert not result["delivery_confirmed"]


def test_ocr_pagination_preserves_digital_pages_and_deduplicates(client, monkeypatch):
    digital = "INV-001"
    document = client.post(
        "/api/v1/documents", files={"file": ("mixed.pdf", make_pdf(digital, ""))}
    ).json()
    with db.transaction() as connection:
        job = db.create(
            connection,
            "job",
            {
                "kind": "ocr",
                "status": "waiting",
                "document_id": document["id"],
                "document_version": document["version"],
                "textract_job_id": "stub-ocr",
                "s3_key": "documents/example.pdf",
            },
        )

    class Textract:
        def get_document_text_detection(self, **kwargs):
            if "NextToken" not in kwargs:
                return {
                    "JobStatus": "SUCCEEDED",
                    "Blocks": [{"BlockType": "LINE", "Page": 1, "Text": "OCR alternative"}],
                    "NextToken": "page2",
                }
            return {
                "JobStatus": "SUCCEEDED",
                "Blocks": [{"BlockType": "LINE", "Page": 2, "Text": "Scanned invoice INV-002"}],
            }

    monkeypatch.setattr("backend.services.ocr.aws_client", lambda service: Textract())
    notification = {"JobTag": job["id"], "JobId": "stub-ocr", "Status": "SUCCEEDED"}
    assert complete_ocr(notification)
    assert complete_ocr(notification)
    stored = client.get(f"/api/v1/documents/{document['id']}").json()
    assert stored["data"]["pages"] == [digital, "Scanned invoice INV-002"]
    with db.transaction() as connection:
        assert len(db.all_records(connection, "text_revision")) == 1


def test_boto_ses_request_validates_against_sdk_without_network(client, monkeypatch):
    import boto3
    from botocore.stub import Stubber

    monkeypatch.setattr(settings, "live_calls_enabled", True)
    monkeypatch.setattr(settings, "live_send_enabled", True)
    monkeypatch.setattr(settings, "approved_monthly_budget_usd", 1)
    monkeypatch.setattr(settings, "ses_sender", "sender@example.test")
    ses = boto3.client(
        "sesv2",
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )
    with Stubber(ses) as stub:
        stub.add_response("send_email", {"MessageId": "stub-id"})
        monkeypatch.setattr("backend.services.cloud.aws_client", lambda service: ses)
        result = SESEmail().send(
            {
                "id": "test",
                "data": {
                    "recipient": "reviewer@example.test",
                    "subject": "Test",
                    "body": "Synthetic",
                    "content_revision": 1,
                },
            }
        )
        assert result["message_id"] == "stub-id"
        stub.assert_no_pending_responses()


def test_failed_embedding_counts_toward_budget(client, monkeypatch):
    from backend.services.cloud import embed_text

    monkeypatch.setattr(settings, "live_calls_enabled", True)
    monkeypatch.setattr(settings, "approved_monthly_budget_usd", 1)
    monkeypatch.setattr(settings, "daily_model_calls", 1)

    class Broken:
        def invoke_model(self, **kwargs):
            raise TimeoutError("provider contents must not be logged")

    monkeypatch.setattr("backend.services.cloud.aws_client", lambda service: Broken())
    with pytest.raises(AppError, match="embedding failed"):
        embed_text("price variance")
    with db.transaction() as connection:
        assert db.all_records(connection, "usage")[0]["data"]["status"] == "unknown"
    with pytest.raises(AppError) as failure:
        reserve_usage("model")
    assert failure.value.status == 429


def test_ocr_start_recovers_with_same_token_and_bounds_retries(client, monkeypatch):
    monkeypatch.setattr(settings, "ocr_provider", "textract")
    monkeypatch.setattr(settings, "live_calls_enabled", True)
    monkeypatch.setattr(settings, "approved_monthly_budget_usd", 1)
    document = client.post("/api/v1/documents", files={"file": ("scan.pdf", make_pdf(""))}).json()
    with db.transaction() as connection:
        job = db.create(
            connection,
            "job",
            {
                "kind": "ocr",
                "status": "queued",
                "document_id": document["id"],
                "document_version": document["version"],
            },
        )
    tokens = []

    class Textract:
        def start_document_text_detection(self, **kwargs):
            tokens.append(kwargs["ClientRequestToken"])
            raise TimeoutError("simulated lost response")

    monkeypatch.setattr("backend.services.ocr.aws_client", lambda service: Textract())
    monkeypatch.setattr(
        "backend.services.ocr.put_source", lambda identifier, content: "documents/source.pdf"
    )
    for _ in range(4):
        start_ocr_once()
        with db.transaction() as connection:
            current = db.get(connection, job["id"])
            if current["data"]["status"] == "starting":
                db.update(connection, current, {**current["data"], "lease_until": "2000-01-01"})
    assert tokens == [job["id"]] * 3
    with db.transaction() as connection:
        assert db.get(connection, job["id"])["data"]["status"] == "failed"
        assert len(db.all_records(connection, "usage")) == 1
