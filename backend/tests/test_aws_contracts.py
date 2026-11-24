import io
import json

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber

from backend import db
from backend.config import settings
from backend.errors import AppError
from backend.services.cloud import converse, embed_text, put_source
from backend.services.policies import retrieve


def test_converse_and_titan_use_regional_models_and_record_actual_usage(client, monkeypatch):
    monkeypatch.setattr(settings, "live_calls_enabled", True)
    monkeypatch.setattr(settings, "approved_monthly_budget_usd", 10)
    monkeypatch.setattr(settings, "model_id", "amazon.nova-lite-v1:0")
    runtime = boto3.client(
        "bedrock-runtime",
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )
    vector = [0.1] * 1024
    body = json.dumps({"embedding": vector, "inputTextTokenCount": 3}).encode()
    with Stubber(runtime) as stub:
        stub.add_response(
            "converse",
            {
                "output": {"message": {"role": "assistant", "content": [{"text": "result"}]}},
                "stopReason": "end_turn",
                "usage": {"inputTokens": 4, "outputTokens": 1, "totalTokens": 5},
                "metrics": {"latencyMs": 12},
            },
            {
                "modelId": "amazon.nova-lite-v1:0",
                "system": [{"text": "Extract"}],
                "messages": [{"role": "user", "content": [{"text": "Synthetic"}]}],
                "inferenceConfig": {"maxTokens": settings.max_output_tokens, "temperature": 0},
            },
        )
        stub.add_response(
            "invoke_model",
            {
                "body": StreamingBody(io.BytesIO(body), len(body)),
                "contentType": "application/json",
            },
            {
                "modelId": settings.embedding_model_id,
                "contentType": "application/json",
                "accept": "application/json",
                "body": json.dumps(
                    {"inputText": "price variance", "dimensions": 1024, "normalize": True}
                ),
            },
        )
        monkeypatch.setattr("backend.services.cloud.aws_client", lambda service: runtime)
        assert converse("Extract", "Synthetic") == "result"
        assert embed_text("price variance") == vector
        stub.assert_no_pending_responses()
    with db.transaction() as connection:
        usage = db.all_records(connection, "usage")
        assert len(usage) == 2
        assert all(row["data"]["status"] == "completed" for row in usage)
        assert {row["data"]["inputTokens"] for row in usage} == {3, 4}


def test_s3_upload_uses_generated_prefix_and_encryption(client, monkeypatch):
    monkeypatch.setattr(settings, "live_calls_enabled", True)
    monkeypatch.setattr(settings, "approved_monthly_budget_usd", 10)
    monkeypatch.setattr(settings, "s3_bucket", "vendorops-test-bucket")
    storage = boto3.client(
        "s3", region_name="us-east-1", aws_access_key_id="testing", aws_secret_access_key="testing"
    )
    with Stubber(storage) as stub:
        stub.add_response(
            "put_object",
            {},
            {
                "Bucket": "vendorops-test-bucket",
                "Key": "documents/generated-id.pdf",
                "Body": b"PDF",
                "ContentType": "application/pdf",
                "ServerSideEncryption": "AES256",
            },
        )
        monkeypatch.setattr("backend.services.cloud.aws_client", lambda service: storage)
        assert put_source("generated-id", b"PDF") == "documents/generated-id.pdf"
        stub.assert_no_pending_responses()


def test_changing_embedding_model_requires_reindex_before_policy_retrieval(client, monkeypatch):
    monkeypatch.setattr(settings, "provider", "bedrock")
    with db.transaction() as connection:
        db.create(
            connection,
            "policy",
            {
                "active": True,
                "effective_date": "2020-01-01",
                "indexed": True,
                "index_provider": "bedrock",
                "embedding_model_id": "an-older-model",
            },
        )
        with pytest.raises(AppError) as error:
            retrieve(connection, "invoice price")
        assert error.value.code == "reindex_required"
