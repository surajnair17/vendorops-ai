from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError, NoCredentialsError
from pydantic import ValidationError

from backend.scripts.aws_setup import Deployment, check, deploy, plan
from backend.scripts.check_bedrock import QUOTAS


def configuration(**extra):
    values = dict(
        account_id="123456789012",
        vpc_id="vpc-example",
        subnet_id="subnet-example",
        sender_email="sender@example.test",
        recipient_email="reviewer@example.test",
        budget_email="operator@example.test",
        release_commit="a" * 40,
        monthly_usage_budget_usd=10,
        credits_available_usd=100,
        pricing_region="ap-southeast-2",
        ec2_hourly_usd="0.0264",
        gp3_gb_month_usd="0.096",
    )
    return Deployment(**(values | extra))


class AWS:
    def __init__(self):
        self.created = []
        self.account = "123456789012"
        self.verified = True
        self.gateway = "igw-example"
        self.plan = "FREE"
        self.zero_quota = None
        self.authorization = "AUTHORIZED"

    def get_account_plan_state(self):
        return {"accountPlanType": self.plan}

    def get_foundation_model_availability(self, **kwargs):
        return {
            "authorizationStatus": self.authorization,
            "entitlementAvailability": "AVAILABLE",
            "regionAvailability": "AVAILABLE",
            "agreementAvailability": {"status": "AVAILABLE"},
        }

    def get_service_quota(self, *, ServiceCode, QuotaCode):
        assert ServiceCode == "bedrock"
        return {"Quota": {"Value": 0 if QuotaCode == self.zero_quota else 1000}}

    def get_caller_identity(self):
        return {"Account": self.account, "Arn": f"arn:aws:iam::{self.account}:user/demo"}

    def describe_subnets(self, **kwargs):
        return {"Subnets": [{"VpcId": "vpc-example", "State": "available"}]}

    def describe_route_tables(self, **kwargs):
        return {
            "RouteTables": [
                {
                    "Associations": [{"Main": True}],
                    "Routes": [
                        {
                            "DestinationCidrBlock": "0.0.0.0/0",
                            "GatewayId": self.gateway,
                            "State": "active",
                        }
                    ],
                }
            ]
        }

    def get_foundation_model(self, **kwargs):
        return {
            "modelDetails": {
                "inferenceTypesSupported": ["ON_DEMAND"],
                "modelLifecycle": {"status": "ACTIVE"},
            }
        }

    def get_email_identity(self, **kwargs):
        return {"VerifiedForSendingStatus": self.verified}

    def create_stack(self, **kwargs):
        self.created.append(kwargs)
        return {"StackId": "stack-example"}


def test_free_plan_has_local_ocr_and_explicit_credit_allowance():
    report = plan(configuration())
    assert report["estimated_hosting_usd"] == "3.88"
    assert not report["blockers"]
    assert report["ocr_provider"] == "local Tesseract"
    assert all("Textract" not in resource for resource in report["resources"])
    assert plan(Deployment())["blockers"]
    with pytest.raises(ValidationError, match="Paid plan"):
        configuration(enable_textract=True)
    changed = configuration().model_copy(update={"credits_available_usd": Decimal(0)})
    assert "declared credits" in " ".join(plan(changed)["blockers"])


def test_deployment_binds_review_to_current_configuration_and_never_enables_live_calls(monkeypatch):
    config = configuration()
    aws = AWS()

    def factory(service):
        return aws

    report = plan(config)
    changed = config.model_copy(update={"demo_running_hours": 64})
    with pytest.raises(ValueError, match="exact review"):
        deploy(changed, report["review_sha256"], factory)
    assert not aws.created
    monkeypatch.setattr("backend.scripts.aws_setup.verify_release", lambda value: None)
    result = deploy(config, report["review_sha256"], factory)
    assert result["live_calls_enabled"] is False
    sent = aws.created[0]
    parameters = {p["ParameterKey"]: p["ParameterValue"] for p in sent["Parameters"]}
    assert parameters["EnableTextract"] == "false"
    assert parameters["ReleaseCommit"] == "a" * 40
    assert "VENDOROPS_LIVE_CALLS_ENABLED=false" in sent["TemplateBody"]


@pytest.mark.parametrize("fault", ["account", "verified", "gateway", "plan", "authorization"])
def test_preflight_failure_prevents_resource_creation(fault):
    config = configuration()
    aws = AWS()
    setattr(
        aws,
        fault,
        {
            "account": "999999999999",
            "verified": False,
            "gateway": "nat-example",
            "plan": "PAID",
            "authorization": "NOT_AUTHORIZED",
        }[fault],
    )
    assert not check(config, lambda service: aws)["ready"]
    with pytest.raises(ValueError, match="preflight"):
        deploy(config, plan(config)["review_sha256"], lambda service: aws)
    assert not aws.created


def test_missing_login_and_provider_error_do_not_leak_messages():
    def missing(service):
        raise NoCredentialsError()

    assert check(configuration(), missing)["checks"][0]["code"] == "NoCredentialsError"
    aws = AWS()

    def denied(**kwargs):
        raise ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "secret contents"}}, "GetModel"
        )

    aws.get_foundation_model = denied
    report = check(configuration(), lambda service: aws)
    assert not report["ready"]
    assert "secret contents" not in str(report)


def test_email_parameters_cannot_add_shell_or_configuration_lines():
    data = deepcopy(configuration().model_dump())
    data["sender_email"] = "test@example.com\nCONFIG\nmalicious command"
    with pytest.raises(ValidationError):
        Deployment(**data)


def test_a_project_region_change_requires_regional_prices_to_be_reviewed():
    config = configuration(pricing_region="unverified")
    assert any("regional" in blocker for blocker in plan(config)["blockers"])
    with pytest.raises(ValidationError, match="not listed as eligible"):
        configuration(instance_type="t3.medium")


@pytest.mark.parametrize("code", [code for codes in QUOTAS.values() for code in codes])
def test_zero_inference_quota_prevents_spending_on_a_host(code):
    config = configuration()
    aws = AWS()
    aws.zero_quota = code
    report = check(config, lambda service: aws)
    assert not report["ready"]
    assert any(
        row.get("quota_code") == code and row["status"] == "blocked" for row in report["checks"]
    )
    with pytest.raises(ValueError, match="preflight"):
        deploy(config, plan(config)["review_sha256"], lambda service: aws)
    assert not aws.created


def test_wrong_project_stops_before_other_services_are_inspected():
    aws = AWS()
    aws.account = "999999999999"
    services = []

    def factory(service):
        services.append(service)
        return aws

    report = check(configuration(), factory)
    assert not report["ready"]
    assert services == ["sts"]
    assert aws.account not in str(report)


def test_missing_prices_and_cross_region_configuration_cannot_be_approved():
    report = plan(configuration(ec2_hourly_usd=None, gp3_gb_month_usd=None))
    assert report["estimated_hosting_usd"] is None
    assert not report["ready_for_preflight"]
    with pytest.raises(ValidationError, match="selected project Region"):
        configuration(bedrock_region="us-east-1")


def test_runtime_file_changes_invalidate_the_review_digest(tmp_path, monkeypatch):
    runtime = tmp_path / "compose.yaml"
    runtime.write_text("services: {}", encoding="utf-8")
    monkeypatch.setattr("backend.scripts.aws_setup.ROOT", tmp_path)
    monkeypatch.setattr("backend.scripts.aws_setup.REVIEWED_FILES", ("compose.yaml",))
    first = plan(configuration())
    runtime.write_text("services: {new: {image: different}}", encoding="utf-8")
    second = plan(configuration())
    assert first["review_sha256"] != second["review_sha256"]
    assert first["artifact_sha256"] != second["artifact_sha256"]


def test_a_release_with_different_runtime_files_cannot_create_a_host(monkeypatch):
    config = configuration()
    aws = AWS()
    monkeypatch.setattr(
        "backend.scripts.aws_setup.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=b"outdated release"),
    )
    with pytest.raises(ValueError, match="release does not match"):
        deploy(config, plan(config)["review_sha256"], lambda service: aws)
    assert not aws.created
