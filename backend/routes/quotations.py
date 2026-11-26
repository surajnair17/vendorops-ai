from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel

from backend import db
from backend.errors import AppError
from backend.services.comparison import current_business
from backend.services.quotations import assess_quote

router = APIRouter(prefix="/api/v1", tags=["quotations"])


class QuoteAssessmentRequest(BaseModel):
    expected_revision_id: str
    as_of: date


def with_staleness(connection, report):
    document = db.get(connection, report["data"]["document_id"], "document")
    return {**report, "stale": document["data"]["revision_id"] != report["data"]["revision_id"]}


@router.post("/documents/{identifier}/quote-assessments", status_code=201)
def create_assessment(identifier: str, payload: QuoteAssessmentRequest):
    with db.transaction() as connection:
        document, revision, business = current_business(connection, identifier)
        if revision["id"] != payload.expected_revision_id:
            raise AppError(409, "stale_revision", "Reload the quote before assessing it.")
        if business.document_type != "quotation":
            raise AppError(422, "quotation_required", "Select a structured quotation.")
        result = assess_quote(business, document["data"]["pages"], payload.as_of)
        report = db.create(
            connection,
            "quote_assessment",
            {
                **result,
                "document_id": identifier,
                "revision_id": revision["id"],
                "provider": revision["data"]["provider"],
            },
        )
        db.audit(connection, identifier, "quote_assessed", {"assessment_id": report["id"]})
        return with_staleness(connection, report)


@router.get("/documents/{identifier}/quote-assessments")
def list_assessments(identifier: str):
    with db.transaction() as connection:
        db.get(connection, identifier, "document")
        return [
            with_staleness(connection, report)
            for report in db.all_records(connection, "quote_assessment")
            if report["data"]["document_id"] == identifier
        ]


@router.get("/quote-assessments/{identifier}")
def read_assessment(identifier: str):
    with db.transaction() as connection:
        return with_staleness(connection, db.get(connection, identifier, "quote_assessment"))
