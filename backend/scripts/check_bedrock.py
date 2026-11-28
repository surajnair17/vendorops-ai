"""Read-only checks for the selected project's regional Bedrock demo readiness.

Catalog availability and authorization do not establish an inference quota. This
command makes no model invocations and creates no resources or support cases.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

QUOTAS = {
    "amazon.nova-lite-v1:0": ("L-70423BF8", "L-E386A278", "L-45E0AD92"),
    # AWS documents embeddings as RPM-throttled, not TPM-throttled. A legacy
    # token-quota entry must not block an otherwise usable embedding model.
    # https://docs.aws.amazon.com/bedrock/latest/userguide/titan-embedding-models.html
    "amazon.titan-embed-text-v2:0": ("L-26C560CE",),
}


def check(
    profile="pixel-perfect",
    region="ap-southeast-2",
    expected_project_id=None,
    client_factory=None,
    expected_plan="FREE",
):
    import boto3
    from botocore.config import Config
    from botocore.exceptions import BotoCoreError, ClientError

    checks = []
    if client_factory is None:
        session = boto3.Session(profile_name=profile, region_name=region)
        options = Config(connect_timeout=5, read_timeout=15, retries={"total_max_attempts": 1})
        clients = {}

        def client_factory(service):
            if service not in clients:
                clients[service] = session.client(service, region_name=region, config=options)
            return clients[service]

    def inspect(name, operation, **metadata):
        try:
            passed, detail = operation()
            row = {"name": name, "status": "pass" if passed else "blocked", "detail": detail}
        except (BotoCoreError, ClientError) as error:
            code = (
                error.response["Error"]["Code"]
                if isinstance(error, ClientError)
                else type(error).__name__
            )
            row = {"name": name, "status": "blocked", "code": code}
        row.update(metadata)
        checks.append(row)
        return row["status"] == "pass"

    def report():
        return {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "profile": profile,
            "region": region,
            "ready": bool(checks) and all(row["status"] == "pass" for row in checks),
            "checks": checks,
            "note": "Read-only checks cannot guarantee invocation success or remaining credit.",
        }

    def identity():
        value = client_factory("sts").get_caller_identity()["Account"]
        return (
            expected_project_id is None or value == expected_project_id,
            "Project identity checked",
        )

    if not inspect("identity", identity):
        return report()

    def plan():
        value = client_factory("freetier").get_account_plan_state()["accountPlanType"]
        return value == expected_plan, {"plan_type": value, "expected_plan": expected_plan}

    if not inspect("plan", plan):
        return report()

    for model_id, codes in QUOTAS.items():

        def catalog(identifier=model_id):
            model = client_factory("bedrock").get_foundation_model(modelIdentifier=identifier)[
                "modelDetails"
            ]
            active = model.get("modelLifecycle", {}).get("status") == "ACTIVE"
            regional = "ON_DEMAND" in model.get("inferenceTypesSupported", [])
            return active and regional, {"active": active, "regional_on_demand": regional}

        def access(identifier=model_id):
            value = client_factory("bedrock").get_foundation_model_availability(modelId=identifier)
            detail = {
                key: value.get(key)
                for key in ("authorizationStatus", "entitlementAvailability", "regionAvailability")
            }
            detail["agreement_status"] = value.get("agreementAvailability", {}).get("status")
            return detail == {
                "authorizationStatus": "AUTHORIZED",
                "entitlementAvailability": "AVAILABLE",
                "regionAvailability": "AVAILABLE",
                "agreement_status": "AVAILABLE",
            }, detail

        inspect("model_catalog", catalog, model_id=model_id)
        inspect("model_access", access, model_id=model_id)
        for code in codes:

            def quota(quota_code=code):
                value = client_factory("service-quotas").get_service_quota(
                    ServiceCode="bedrock", QuotaCode=quota_code
                )["Quota"]
                return value["Value"] > 0, {
                    key: value.get(key) for key in ("QuotaName", "Value", "Adjustable")
                }

            inspect("inference_quota", quota, model_id=model_id, quota_code=code)
    return report()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="pixel-perfect")
    parser.add_argument("--region", default="ap-southeast-2")
    parser.add_argument("--expected-project-id")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = check(args.profile, args.region, args.expected_project_id)
    serialized = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized)
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
