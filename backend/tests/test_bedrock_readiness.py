from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError, NoCredentialsError

from backend.scripts.check_bedrock import QUOTAS, check


class ReadOnlyAWS:
    def __init__(self):
        self.services = []
        self.zero_quota = None
        self.authorization = "AUTHORIZED"

    def client(self, service):
        assert service in {"sts", "freetier", "bedrock", "service-quotas"}
        self.services.append(service)
        return self

    def get_caller_identity(self):
        return {"Account": "123456789012"}

    def get_account_plan_state(self):
        return {"accountPlanType": "FREE"}

    def get_foundation_model(self, **kwargs):
        return {
            "modelDetails": {
                "modelLifecycle": {"status": "ACTIVE"},
                "inferenceTypesSupported": ["ON_DEMAND"],
            }
        }

    def get_foundation_model_availability(self, **kwargs):
        return {
            "authorizationStatus": self.authorization,
            "entitlementAvailability": "AVAILABLE",
            "regionAvailability": "AVAILABLE",
            "agreementAvailability": {"status": "AVAILABLE"},
        }

    def get_service_quota(self, *, ServiceCode, QuotaCode):
        assert ServiceCode == "bedrock"
        return {
            "Quota": {
                "QuotaName": "Applied inference quota",
                "Value": 0 if QuotaCode == self.zero_quota else 1000,
                "Adjustable": False,
            }
        }


@pytest.mark.parametrize("quota_code", [code for codes in QUOTAS.values() for code in codes])
def test_catalog_and_access_do_not_override_zero_applied_quota(quota_code):
    aws = ReadOnlyAWS()
    aws.zero_quota = quota_code
    report = check(client_factory=aws.client)
    assert not report["ready"]
    blocked = [row for row in report["checks"] if row["status"] == "blocked"]
    assert len(blocked) == 1
    assert blocked[0]["quota_code"] == quota_code
    assert all(row["status"] == "pass" for row in report["checks"] if row["name"] == "model_access")


def test_readiness_checks_project_identity_and_does_not_invoke_models():
    aws = ReadOnlyAWS()
    assert check(expected_project_id="123456789012", client_factory=aws.client)["ready"]
    aws.services.clear()
    report = check(expected_project_id="999999999999", client_factory=aws.client)
    assert not report["ready"]
    assert aws.services == ["sts"]
    assert "123456789012" not in str(report)


def test_embedding_readiness_uses_rpm_without_querying_legacy_token_quota():
    aws = ReadOnlyAWS()
    requested = []
    original = aws.get_service_quota

    def quota(**kwargs):
        requested.append(kwargs["QuotaCode"])
        if kwargs["QuotaCode"] == "L-DE641971":
            raise AssertionError("Embedding TPM is not an inference gate")
        return original(**kwargs)

    aws.get_service_quota = quota
    report = check(client_factory=aws.client)
    assert report["ready"]
    assert "L-26C560CE" in requested
    aws.zero_quota = "L-26C560CE"
    report = check(client_factory=aws.client)
    assert not report["ready"]
    blocked = [row for row in report["checks"] if row["status"] == "blocked"]
    assert len(blocked) == 1 and blocked[0]["quota_code"] == "L-26C560CE"


def test_denied_or_missing_read_access_blocks_without_leaking_error_messages():
    aws = ReadOnlyAWS()

    def denied(**kwargs):
        raise ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "private details"}},
            "GetServiceQuota",
        )

    aws.get_service_quota = denied
    report = check(client_factory=aws.client)
    assert not report["ready"]
    assert "private details" not in str(report)

    def missing(service):
        raise NoCredentialsError()

    assert not check(client_factory=missing)["ready"]


def test_model_authorization_is_checked_separately_from_positive_quotas():
    aws = ReadOnlyAWS()
    aws.authorization = "NOT_AUTHORIZED"
    assert not check(client_factory=aws.client)["ready"]


def test_recording_stops_before_starting_servers_when_readiness_is_blocked(tmp_path, monkeypatch):
    pytest.importorskip("playwright.sync_api")
    from frontend.scripts.record_demo import record

    monkeypatch.setattr(
        "backend.scripts.check_bedrock.check", lambda: {"ready": False, "checks": []}
    )

    def unexpected(*args, **kwargs):
        raise AssertionError("No recording processes should start")

    monkeypatch.setattr("frontend.scripts.record_demo.subprocess.Popen", unexpected)
    with pytest.raises(RuntimeError, match="blocked before inference"):
        record(SimpleNamespace(output=tmp_path / "recording", provider="bedrock"))
    assert (tmp_path / "recording" / "readiness.json").is_file()
