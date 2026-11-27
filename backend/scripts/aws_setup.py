"""Review a deployment locally, check AWS access, then explicitly provision the reviewed plan.

The plan command is offline. Check uses read APIs, never inference, OCR, email, or provisioning.
Deploy requires an exact plan digest and successful preflight. Live flags stay disabled.
"""

import argparse
import hashlib
import json
import re
import subprocess
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.scripts.check_bedrock import check as check_bedrock

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "backend/infra/cloudformation.yaml"
BOOTSTRAP = ROOT / "backend/infra/bootstrap.sh"
REVIEWED_FILES = (
    "backend/infra/cloudformation.yaml",
    "backend/infra/bootstrap.sh",
    "backend/infra/compose.yaml",
    "backend/infra/compose.aws.yaml",
    "backend/Dockerfile",
    "backend/requirements.txt",
    "backend/requirements-cloud.txt",
    "frontend/Dockerfile",
    "frontend/requirements.txt",
)


class Deployment(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    profile: str = "pixel-perfect"
    account_id: str = ""
    region: str = Field(default="ap-southeast-2", pattern=r"^[a-z]{2}(?:-[a-z]+)+-\d$")
    bedrock_region: str = Field(default="ap-southeast-2", pattern=r"^[a-z]{2}(?:-[a-z]+)+-\d$")
    pricing_region: str = ""
    pricing_instance_type: str = "t3.small"
    ec2_hourly_usd: Decimal | None = Field(default=None, gt=0)
    gp3_gb_month_usd: Decimal | None = Field(default=None, gt=0)
    account_plan: Literal["free", "paid"] = "free"
    credits_available_usd: Decimal = Field(default=Decimal(0), ge=0)
    monthly_usage_budget_usd: Decimal = Field(default=Decimal(0), ge=0)
    maximum_out_of_pocket_usd: Decimal = Field(default=Decimal(0), ge=0)
    demo_running_hours: int = Field(default=32, ge=1, le=730)
    instance_type: Literal["t3.small", "t3.medium"] = "t3.small"
    stack_name: str = Field(default="vendorops-demo", pattern=r"^[A-Za-z][A-Za-z0-9-]{0,90}$")
    vpc_id: str = ""
    subnet_id: str = ""
    sender_email: str = ""
    recipient_email: str = ""
    budget_email: str = ""
    enable_textract: bool = False
    release_commit: str = ""

    @model_validator(mode="after")
    def free_plan_features(self):
        if self.bedrock_region != self.region:
            raise ValueError("Bedrock must use the selected project Region.")
        if self.account_plan == "free" and self.enable_textract:
            raise ValueError("Textract requires the Paid plan. Keep local OCR on the Free plan.")
        if self.account_plan == "free" and self.instance_type != "t3.small":
            raise ValueError("Use t3.small on the Free plan; t3.medium is not listed as eligible.")
        for email in (self.sender_email, self.recipient_email, self.budget_email):
            if email and not re.fullmatch(
                r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+", email
            ):
                raise ValueError(
                    "Email parameters must contain a single address without whitespace."
                )
        return self


def plan(config: Deployment) -> dict:
    hosting = None
    if config.ec2_hourly_usd is not None and config.gp3_gb_month_usd is not None:
        hosting = (
            (config.ec2_hourly_usd + Decimal("0.005")) * config.demo_running_hours
            + config.gp3_gb_month_usd * 30
        ).quantize(Decimal("0.01"))
    missing = [
        key
        for key in (
            "account_id",
            "vpc_id",
            "subnet_id",
            "sender_email",
            "recipient_email",
            "budget_email",
            "release_commit",
        )
        if not getattr(config, key)
    ]
    blockers = [f"Missing {key}" for key in missing]
    if hosting is None:
        blockers.append("Enter verified regional EC2 and gp3 prices before approval")
    if config.bedrock_region != config.region:
        blockers.append("Bedrock must use the selected project Region")
    if config.pricing_region != config.region:
        blockers.append("Verify regional EC2/EBS rates and update pricing_region before approval")
    if config.pricing_instance_type != config.instance_type:
        blockers.append("Verify the selected instance rate and update pricing_instance_type")
    if config.account_id and not re.fullmatch(r"\d{12}", config.account_id):
        blockers.append("account_id must have 12 digits")
    if config.release_commit and not re.fullmatch(r"[a-f0-9]{40}", config.release_commit):
        blockers.append("release_commit must be a full Git commit")
    if hosting is not None and config.monthly_usage_budget_usd < hosting + Decimal("1"):
        blockers.append("Approve a usage allowance covering hosting plus at least $1 for services")
    if config.monthly_usage_budget_usd > (
        config.credits_available_usd + config.maximum_out_of_pocket_usd
    ):
        blockers.append("The usage allowance exceeds the declared credits and cash allowance")
    if config.account_plan == "paid" and config.maximum_out_of_pocket_usd == 0:
        blockers.append(
            "The Paid plan cannot guarantee a $0 bill; select Free or review the cash risk"
        )
    reviewed = {
        "configuration": config.model_dump(mode="json"),
        "template_sha256": hashlib.sha256(TEMPLATE.read_bytes()).hexdigest(),
        "bootstrap_sha256": hashlib.sha256(BOOTSTRAP.read_bytes()).hexdigest(),
        "artifact_sha256": {
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in REVIEWED_FILES
        },
        "estimated_hosting_usd": str(hosting) if hosting is not None else None,
        "estimate_note": (
            "Compute + IPv4 for selected hours; 30GB storage for one month. Other usage extra."
        ),
        "resources": [
            f"{config.instance_type} EC2, no inbound ports",
            "30GB encrypted retained gp3 volume",
            "private versioned S3",
            "instance IAM role and SSM access",
            "CloudWatch logs",
            "monthly budget alert",
        ]
        + (["Textract role, SNS, SQS, dead-letter queue, alarm"] if config.enable_textract else []),
        "ocr_provider": "textract" if config.enable_textract else "local Tesseract",
        "live_flags": "disabled at deployment; enable AI/storage separately; approve real emails",
        "blockers": blockers,
    }
    digest = hashlib.sha256(json.dumps(reviewed, sort_keys=True).encode()).hexdigest()
    return {**reviewed, "review_sha256": digest, "ready_for_preflight": not blockers}


def session_for(config: Deployment):
    import boto3
    from botocore.config import Config

    session = boto3.Session(profile_name=config.profile or None, region_name=config.region)
    options = Config(connect_timeout=5, read_timeout=15, retries={"total_max_attempts": 1})
    clients = {}

    def client(name):
        if name not in clients:
            clients[name] = session.client(name, region_name=config.region, config=options)
        return clients[name]

    return client


def check(config: Deployment, client_factory=None) -> dict:
    reviewed = plan(config)
    checks = []
    try:
        client = client_factory or session_for(config)
        identity = client("sts").get_caller_identity()
    except Exception as error:
        return {
            "ready": False,
            "checks": [
                {
                    "name": "login",
                    "status": "blocked",
                    "code": error_code(error),
                    "next_step": f"Run aws login --profile {config.profile}, then retry.",
                }
            ],
        }
    checks.append(
        {
            "name": "project",
            "status": "pass" if identity["Account"] == config.account_id else "blocked",
        }
    )
    checks.append(
        {
            "name": "operator",
            "status": "blocked" if identity["Arn"].endswith(":root") else "pass",
            "note": "Use the signed-in project team member or a federated operator.",
        }
    )
    if any(row["status"] == "blocked" for row in checks):
        return {"ready": False, "checks": checks, "configuration_blockers": reviewed["blockers"]}

    readiness = check_bedrock(
        profile=config.profile,
        region=config.region,
        expected_project_id=config.account_id,
        client_factory=client,
        expected_plan=config.account_plan.upper(),
    )
    checks.extend(readiness["checks"])
    if any(row["status"] == "blocked" for row in checks if row["name"] in {"identity", "plan"}):
        return {"ready": False, "checks": checks, "configuration_blockers": reviewed["blockers"]}

    def inspect(name, operation):
        try:
            detail = operation()
            checks.append({"name": name, "status": "pass", "detail": detail})
        except Exception as error:
            checks.append({"name": name, "status": "blocked", "code": error_code(error)})

    def subnet():
        ec2 = client("ec2")
        row = ec2.describe_subnets(SubnetIds=[config.subnet_id])["Subnets"][0]
        if row["VpcId"] != config.vpc_id or row["State"] != "available":
            raise ValueError("subnet_vpc_mismatch")
        tables = ec2.describe_route_tables(Filters=[{"Name": "vpc-id", "Values": [config.vpc_id]}])
        associated = [
            t
            for t in tables["RouteTables"]
            if any(a.get("SubnetId") == config.subnet_id for a in t.get("Associations", []))
        ]
        selected = associated or [
            t
            for t in tables["RouteTables"]
            if any(a.get("Main") for a in t.get("Associations", []))
        ]
        if not any(
            r.get("DestinationCidrBlock") == "0.0.0.0/0"
            and r.get("GatewayId", "").startswith("igw-")
            and r.get("State") == "active"
            for t in selected
            for r in t.get("Routes", [])
        ):
            raise ValueError("outbound_internet_route_missing")
        return "VPC matches; outbound Internet Gateway route exists; no public inbound ports"

    inspect("network", subnet)
    for address in sorted({config.sender_email, config.recipient_email}):

        def identity_check(email=address):
            verified = client("sesv2").get_email_identity(EmailIdentity=email)
            if not verified.get("VerifiedForSendingStatus"):
                raise ValueError("ses_identity_unverified")
            return "Verified email identity"

        inspect(f"ses:{address}", identity_check)
    return {
        "ready": not reviewed["blockers"] and all(c["status"] == "pass" for c in checks),
        "checks": checks,
        "configuration_blockers": reviewed["blockers"],
        "note": "Read-only checks do not prove inference, delivery, or the credit balance.",
    }


def error_code(error: Exception) -> str:
    if hasattr(error, "response"):
        return error.response.get("Error", {}).get("Code", type(error).__name__)
    return str(error) if isinstance(error, ValueError) else type(error).__name__


def verify_release(config: Deployment):
    """The host checks out this commit, so its runtime files must match the reviewed files."""
    for path in REVIEWED_FILES:
        result = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={ROOT.as_posix()}",
                "-C",
                str(ROOT),
                "show",
                f"{config.release_commit}:{path}",
            ],
            capture_output=True,
            check=False,
            timeout=15,
        )
        committed = result.stdout.decode("utf-8", errors="replace").replace("\r\n", "\n")
        current = (ROOT / path).read_text(encoding="utf-8")
        if result.returncode or committed != current:
            raise ValueError(
                f"The release does not match reviewed {path}. Commit and push the reviewed "
                "files, update release_commit, and review the new plan."
            )


def deploy(config: Deployment, review_sha256: str, client_factory=None) -> dict:
    reviewed = plan(config)
    if reviewed["blockers"] or review_sha256 != reviewed["review_sha256"]:
        raise ValueError("Review the complete current plan and supply its exact review_sha256")
    client = client_factory or session_for(config)
    readiness = check(config, client)
    if not readiness["ready"]:
        raise ValueError("AWS preflight did not pass; run check to inspect blockers")
    verify_release(config)
    parameters = {
        "VpcId": config.vpc_id,
        "PublicSubnetId": config.subnet_id,
        "SenderEmail": config.sender_email,
        "TestRecipientEmail": config.recipient_email,
        "BudgetEmail": config.budget_email,
        "MonthlyBudgetUSD": str(config.monthly_usage_budget_usd),
        "EnableTextract": str(config.enable_textract).lower(),
        "InstanceType": config.instance_type,
        "BedrockRegion": config.bedrock_region,
        "ReleaseCommit": config.release_commit,
    }
    result = client("cloudformation").create_stack(
        StackName=config.stack_name,
        TemplateBody=TEMPLATE.read_text(encoding="utf-8"),
        Parameters=[
            {"ParameterKey": key, "ParameterValue": value} for key, value in parameters.items()
        ],
        Capabilities=["CAPABILITY_IAM"],
        Tags=[{"Key": "Project", "Value": "VendorOps"}],
        ClientRequestToken="vendorops-" + review_sha256[:40],
    )
    return {
        "stack_id": result["StackId"],
        "status": "creation_requested",
        "next_step": "Wait for CREATE_COMPLETE in CloudFormation, then use SSM port forwarding.",
        "live_calls_enabled": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["plan", "check", "deploy", "status"])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--review-sha256", default="")
    args = parser.parse_args()
    try:
        config = Deployment.model_validate_json(args.config.read_text(encoding="utf-8-sig"))
        if args.operation == "plan":
            result = plan(config)
        elif args.operation == "check":
            result = check(config)
        elif args.operation == "deploy":
            result = deploy(config, args.review_sha256)
        else:
            result = session_for(config)("cloudformation").describe_stacks(
                StackName=config.stack_name
            )
        print(json.dumps(result, indent=2, default=str))
        if args.operation == "check" and not result["ready"]:
            raise SystemExit(1)
    except (OSError, ValueError) as error:
        parser.exit(2, f"Configuration error: {error}\n")
    except Exception as error:
        parser.exit(2, f"AWS operation failed: {error_code(error)}\n")


if __name__ == "__main__":
    main()
