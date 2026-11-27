import io
import json

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber

from backend import db
from backend.config import settings
from backend.errors import AppError
from backend.services.cloud import aws_client, converse, embed_text, put_source
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


def test_local_sdk_calls_use_the_selected_login_profile_and_resource_region(client, monkeypatch):
    monkeypatch.setattr(settings, "live_calls_enabled", True)
    monkeypatch.setattr(settings, "approved_monthly_budget_usd", 10)
    monkeypatch.setattr(settings, "aws_profile", "pixel-perfect")
    monkeypatch.setattr(settings, "aws_region", "ap-southeast-2")
    monkeypatch.setattr(settings, "bedrock_region", "ap-southeast-2")
    clients = []

    class Session:
        def __init__(self, profile_name):
            assert profile_name == "pixel-perfect"

        def client(self, service, **kwargs):
            clients.append((service, kwargs["region_name"]))

    monkeypatch.setattr(boto3, "Session", Session)
    aws_client("s3")
    aws_client("bedrock-runtime")
    assert clients == [("s3", "ap-southeast-2"), ("bedrock-runtime", "ap-southeast-2")]


def test_cross_region_configuration_is_rejected_before_sdk_or_usage(client, monkeypatch):
    monkeypatch.setattr(settings, "live_calls_enabled", True)
    monkeypatch.setattr(settings, "approved_monthly_budget_usd", 10)
    monkeypatch.setattr(settings, "aws_region", "ap-southeast-2")
    monkeypatch.setattr(settings, "bedrock_region", "us-east-1")

    def unexpected(*args, **kwargs):
        raise AssertionError("A mismatched Region must not create an AWS session")

    monkeypatch.setattr(boto3, "Session", unexpected)
    for operation in (lambda: aws_client("s3"), lambda: converse("Extract", "Synthetic")):
        with pytest.raises(AppError) as error:
            operation()
        assert error.value.code == "region_mismatch"
    with db.transaction() as connection:
        assert not db.all_records(connection, "usage")


@pytest.mark.parametrize("operation", ["converse", "invoke_model"])
def test_throttling_explains_quota_block_and_counts_attempt_without_retry(
    client, monkeypatch, operation
):
    monkeypatch.setattr(settings, "live_calls_enabled", True)
    monkeypatch.setattr(settings, "approved_monthly_budget_usd", 10)
    runtime = boto3.client(
        "bedrock-runtime",
        region_name="ap-southeast-2",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )
    with Stubber(runtime) as stub:
        stub.add_client_error(operation, "ThrottlingException", "private provider contents", 429)
        monkeypatch.setattr("backend.services.cloud.aws_client", lambda service: runtime)
        with pytest.raises(AppError) as error:
            if operation == "converse":
                converse("Extract", "Synthetic")
            else:
                embed_text("policy")
        assert error.value.status == 429
        assert error.value.code == "model_throttled"
        assert "zero quota" in str(error.value)
        stub.assert_no_pending_responses()
    with db.transaction() as connection:
        usage = db.all_records(connection, "usage")
        assert len(usage) == 1
        assert usage[0]["data"]["status"] == "rejected"
        assert usage[0]["data"]["error_code"] == "ThrottlingException"
        assert "private provider contents" not in str(usage)
