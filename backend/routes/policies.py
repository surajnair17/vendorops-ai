from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

from fastapi import APIRouter, UploadFile
from pydantic import BaseModel, Field

from backend import db
from backend.config import settings
from backend.errors import AppError
from backend.routes.documents import read_pdf_upload
from backend.services.pdf_extractor import extract_pages
from backend.services.policies import assess, chunks_for, index_policy

router = APIRouter(prefix="/api/v1", tags=["policies"])


class PolicyInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    policy_version: str = Field(min_length=1, max_length=40)
    effective_date: date
    text: str = Field(min_length=1, max_length=100000)


def save_policy(payload: PolicyInput, pages: list[str]):
    with db.transaction() as connection:
        if any(
            p["data"]["name"] == payload.name
            and p["data"]["policy_version"] == payload.policy_version
            for p in db.all_records(connection, "policy")
        ):
            raise AppError(409, "policy_version_exists", "Use a new policy version.")
        policy = db.create(
            connection,
            "policy",
            {
                **payload.model_dump(mode="json", exclude={"text"}),
                "active": False,
                "indexed": False,
                "chunks": chunks_for(pages),
            },
        )
    index_policy(policy)
    with db.transaction() as connection:
        policy = db.get(connection, policy["id"], "policy")
        return db.update(
            connection,
            policy,
            {**policy["data"], "indexed": True, "index_provider": settings.provider},
        )


@router.post("/policies", status_code=201)
def upload_text_policy(payload: PolicyInput):
    return save_policy(payload, [payload.text])


@router.post("/policies/pdf", status_code=201)
async def upload_pdf_policy(file: UploadFile, name: str, policy_version: str, effective_date: date):
    _, content = await read_pdf_upload(file)
    pages = extract_pages(content)
    from starlette.concurrency import run_in_threadpool

    return await run_in_threadpool(
        save_policy,
        PolicyInput(
            name=name,
            policy_version=policy_version,
            effective_date=effective_date,
            text="\n".join(pages),
        ),
        pages,
    )


@router.get("/policies")
def list_policies():
    with db.transaction() as connection:
        return db.all_records(connection, "policy")


class Activation(BaseModel):
    active: bool
    expected_version: int


@router.post("/policies/{identifier}/activate")
def activate_policy(identifier: str, payload: Activation):
    with db.transaction() as connection:
        policy = db.get(connection, identifier, "policy")
        if policy["version"] != payload.expected_version or not policy["data"]["indexed"]:
            raise AppError(
                409, "policy_not_ready", "Reload and index the policy before activation."
            )
        if payload.active:
            for older in db.all_records(connection, "policy"):
                if (
                    older["id"] != identifier
                    and older["data"]["name"] == policy["data"]["name"]
                    and older["data"]["active"]
                ):
                    db.update(connection, older, {**older["data"], "active": False})
        result = db.update(connection, policy, {**policy["data"], "active": payload.active})
        db.audit(connection, identifier, "policy_activation_changed")
        return result


class RuleInput(BaseModel):
    policy_id: str
    chunk_id: str
    rule_type: Literal[
        "price_variance_percent",
        "quantity_overage_percent",
        "required_field",
        "invoice_value_threshold",
    ]
    value: str


@router.post("/rules", status_code=201)
def create_rule(payload: RuleInput):
    if payload.rule_type == "required_field":
        if payload.value not in {
            "supplier",
            "document_number",
            "document_date",
            "po_number",
            "currency",
            "total",
        }:
            raise AppError(422, "unsupported_field", "Select a supported required field.")
    else:
        try:
            number = Decimal(payload.value)
            if not number.is_finite() or number < 0:
                raise InvalidOperation
        except InvalidOperation as error:
            raise AppError(
                422, "invalid_threshold", "Use a nonnegative finite threshold."
            ) from error
    with db.transaction() as connection:
        policy = db.get(connection, payload.policy_id, "policy")
        if payload.chunk_id not in {c["id"] for c in policy["data"]["chunks"]}:
            raise AppError(422, "invalid_citation", "The cited policy chunk does not exist.")
        return db.create(connection, "rule", {**payload.model_dump(), "confirmed": False})


@router.get("/rules")
def list_rules():
    with db.transaction() as connection:
        return db.all_records(connection, "rule")


@router.post("/rules/{identifier}/confirm")
def confirm_rule(identifier: str, payload: Activation):
    with db.transaction() as connection:
        rule = db.get(connection, identifier, "rule")
        if rule["version"] != payload.expected_version:
            raise AppError(409, "stale_rule", "Reload the rule before confirmation.")
        result = db.update(connection, rule, {**rule["data"], "confirmed": payload.active})
        db.audit(connection, identifier, "rule_confirmation_changed")
        return result


@router.post("/comparisons/{identifier}/policy-assessments", status_code=201)
def create_assessment(identifier: str):
    with db.transaction() as connection:
        return db.create(
            connection,
            "assessment",
            assess(connection, db.get(connection, identifier, "comparison")),
        )
