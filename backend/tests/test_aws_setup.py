from copy import deepcopy
from decimal import Decimal

import pytest
from botocore.exceptions import ClientError, NoCredentialsError
from pydantic import ValidationError

from backend.scripts.aws_setup import Deployment, check, deploy, plan


def configuration(**extra):
    return Deployment(
        account_id="123456789012",
        vpc_id="vpc-example",
        subnet_id="subnet-example",
        sender_email="sender@example.test",
        recipient_email="reviewer@example.test",
        budget_email="operator@example.test",
        release_commit="a" * 40,
        monthly_usage_budget_usd=10,
        credits_available_usd=100,
        **extra,
    )


class AWS:
    def __init__(self):
        self.created = []
        self.account = "123456789012"
        self.verified = True
        self.gateway = "igw-example"

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
    assert report["estimated_hosting_usd"] == "3.23"
    assert not report["blockers"]
    assert report["ocr_provider"] == "local Tesseract"
    assert all("Textract" not in resource for resource in report["resources"])
    assert plan(Deployment())["blockers"]
    with pytest.raises(ValidationError, match="Paid plan"):
        configuration(enable_textract=True)
    changed = configuration().model_copy(update={"credits_available_usd": Decimal(0)})
    assert "declared credits" in " ".join(plan(changed)["blockers"])


def test_deployment_binds_review_to_current_configuration_and_never_enables_live_calls():
    config = configuration()
    aws = AWS()

    def factory(service):
        return aws

    report = plan(config)
    changed = config.model_copy(update={"demo_running_hours": 64})
    with pytest.raises(ValueError, match="exact review"):
        deploy(changed, report["review_sha256"], factory)
    assert not aws.created
    result = deploy(config, report["review_sha256"], factory)
    assert result["live_calls_enabled"] is False
    sent = aws.created[0]
    parameters = {p["ParameterKey"]: p["ParameterValue"] for p in sent["Parameters"]}
    assert parameters["EnableTextract"] == "false"
    assert parameters["ReleaseCommit"] == "a" * 40
    assert "VENDOROPS_LIVE_CALLS_ENABLED=false" in sent["TemplateBody"]


@pytest.mark.parametrize("fault", ["account", "verified", "gateway"])
def test_preflight_failure_prevents_resource_creation(fault):
    config = configuration()
    aws = AWS()
    setattr(
        aws, fault, {"account": "999999999999", "verified": False, "gateway": "nat-example"}[fault]
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
    config = configuration().model_copy(update={"region": "ap-southeast-2"})
    assert any("regional" in blocker for blocker in plan(config)["blockers"])
    with pytest.raises(ValidationError, match="not listed as eligible"):
        configuration(instance_type="t3.medium")
