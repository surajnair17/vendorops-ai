from datetime import date
from typing import Literal

from fastapi import APIRouter, UploadFile
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from backend import db
from backend.config import settings
from backend.errors import AppError
from backend.routes.documents import read_pdf_upload
from backend.schemas.business import Number
from backend.services.comparison import report_is_stale
from backend.services.pdf_extractor import extract_pages
from backend.services.policies import (
    assess,
    assessment_query,
    chunks_for,
    embedding,
    index_policy,
    policy_signature,
)

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
            {
                **policy["data"],
                "indexed": True,
                "index_provider": settings.provider,
                "index_store": settings.vector_store,
                "embedding_model_id": settings.embedding_model_id
                if settings.provider == "bedrock"
                else None,
            },
        )


@router.post("/policies", status_code=201)
def upload_text_policy(payload: PolicyInput):
    return save_policy(payload, [payload.text])


@router.post("/policies/pdf", status_code=201)
async def upload_pdf_policy(file: UploadFile, name: str, policy_version: str, effective_date: date):
    _, content = await read_pdf_upload(file)
    pages = extract_pages(content)
    from starlette.concurrency import run_in_threadpool

    try:
        payload = PolicyInput(
            name=name,
            policy_version=policy_version,
            effective_date=effective_date,
            text="\n".join(pages),
        )
        if not payload.text.strip():
            raise ValueError("No policy text")
    except ValueError as error:
        raise AppError(
            422,
            "invalid_policy_text",
            "Use a digital PDF with policy text of at most 100,000 characters.",
        ) from error
    return await run_in_threadpool(save_policy, payload, pages)


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
    value: str = Field(min_length=1, max_length=64)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")


@router.post("/rules", status_code=201)
def create_rule(payload: RuleInput):
    if payload.rule_type == "invoice_value_threshold" and payload.currency is None:
        raise AppError(422, "currency_required", "An invoice-value threshold needs a currency.")
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
            number = TypeAdapter(Number).validate_python(payload.value)
        except ValidationError as error:
            raise AppError(
                422,
                "invalid_threshold",
                "Use a nonnegative threshold with at most 18 digits and 6 decimal places.",
            ) from error
        # Canonical values keep equivalent thresholds (10 and 10.0) from conflicting.
        payload.value = format(number.normalize(), "f")
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
        report = db.get(connection, identifier, "comparison")
        signature = policy_signature(connection)
        if report_is_stale(connection, report):
            raise AppError(409, "stale_report", "Recompare the current document revisions first.")
    # A paid embedding reservation must commit even if a later assessment fails.
    # Do not hold the SQLite write transaction across the provider call.
    vector = embedding(assessment_query(report)) if signature else []
    with db.transaction() as connection:
        if policy_signature(connection) != signature:
            raise AppError(409, "stale_policy", "Policies changed during retrieval. Try again.")
        return db.create(
            connection,
            "assessment",
            assess(connection, db.get(connection, identifier, "comparison"), query_vector=vector),
        )


@router.get("/comparisons/{identifier}/policy-assessments")
def list_assessments(identifier: str):
    with db.transaction() as connection:
        db.get(connection, identifier, "comparison")
        return [
            a
            for a in db.all_records(connection, "assessment")
            if a["data"]["comparison_id"] == identifier
        ]
