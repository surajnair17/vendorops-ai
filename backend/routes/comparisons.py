from fastapi import APIRouter
from pydantic import BaseModel

from backend import db
from backend.errors import AppError
from backend.services.comparison import (
    compare,
    current_business,
    match_candidates,
    normalized,
    report_is_stale,
    supplier_key,
)

router = APIRouter(prefix="/api/v1", tags=["comparisons"])


class ComparisonRequest(BaseModel):
    invoice_id: str
    po_id: str | None = None
    line_mapping: dict[int, int] | None = None


@router.get("/documents/{identifier}/match-candidates")
def candidates(identifier: str):
    with db.transaction() as connection:
        return match_candidates(connection, identifier)


class SupplierAlias(BaseModel):
    alias: str
    canonical: str


@router.post("/supplier-aliases", status_code=201)
def add_alias(payload: SupplierAlias):
    with db.transaction() as connection:
        if not normalized(payload.alias) or not normalized(payload.canonical):
            raise AppError(422, "empty_alias", "Supplier names cannot be empty.")
        if any(
            normalized(r["data"]["alias"]) == normalized(payload.alias)
            for r in db.all_records(connection, "supplier_alias")
        ):
            raise AppError(409, "alias_exists", "This alias already exists.")
        record = db.create(connection, "supplier_alias", payload.model_dump())
        db.audit(connection, record["id"], "supplier_alias_confirmed")
        return record


@router.post("/comparisons", status_code=201)
def create_comparison(payload: ComparisonRequest):
    with db.transaction() as connection:
        invoice_doc, invoice_rev, invoice = current_business(connection, payload.invoice_id)
        po_id = payload.po_id or match_candidates(connection, payload.invoice_id)["automatic_match"]
        if not po_id:
            raise AppError(
                409, "match_required", "Select a purchase order; no unique match exists."
            )
        _, po_rev, order = current_business(connection, po_id)
        if invoice.document_type != "invoice" or order.document_type != "purchase_order":
            raise AppError(
                422, "invalid_document_pair", "Compare an invoice with a purchase order."
            )
        findings = compare(invoice, order, payload.line_mapping)
        if not invoice.supplier or supplier_key(connection, invoice.supplier) != supplier_key(
            connection, order.supplier
        ):
            findings.append(
                {
                    "type": "supplier_mismatch",
                    "field": "supplier",
                    "expected": order.supplier,
                    "actual": invoice.supplier,
                    "difference": None,
                    "evidence": [],
                    "review_status": "open",
                }
            )
        if invoice_doc["data"]["duplicate_of"]:
            findings.append(
                {"type": "duplicate_upload", "related_ids": invoice_doc["data"]["duplicate_of"]}
            )
        for other in db.all_records(connection, "document"):
            if other["id"] == payload.invoice_id or not other["data"]["revision_id"]:
                continue
            try:
                _, _, candidate = current_business(connection, other["id"])
            except AppError:
                continue
            if (
                candidate.document_type != "invoice"
                or not invoice.supplier
                or supplier_key(connection, candidate.supplier)
                != supplier_key(connection, invoice.supplier)
            ):
                continue
            if invoice.document_number and normalized(candidate.document_number) == normalized(
                invoice.document_number
            ):
                findings.append(
                    {"type": "suspected_duplicate_invoice", "related_ids": [other["id"]]}
                )
            elif invoice.po_number and normalized(candidate.po_number) == normalized(
                invoice.po_number
            ):
                findings.append({"type": "multiple_invoices_for_po", "related_ids": [other["id"]]})
        for label, revision in (("invoice", invoice_rev), ("purchase_order", po_rev)):
            if revision["data"].get("issues"):
                findings.append(
                    {
                        "type": "validation_required",
                        "field": label,
                        "issues": revision["data"]["issues"],
                        "review_status": "open",
                    }
                )
        report = db.create(
            connection,
            "comparison",
            {
                "invoice_id": payload.invoice_id,
                "po_id": po_id,
                "invoice_revision_id": invoice_rev["id"],
                "po_revision_id": po_rev["id"],
                "findings": findings,
                "line_mapping": payload.line_mapping,
                "status": "needs_review" if findings else "matched",
            },
        )
        db.audit(connection, report["id"], "comparison_created")
        return report


@router.get("/comparisons")
def reports():
    with db.transaction() as connection:
        return [
            {**report, "stale": report_is_stale(connection, report)}
            for report in db.all_records(connection, "comparison")
        ]


@router.get("/comparisons/{identifier}")
def report(identifier: str):
    with db.transaction() as connection:
        result = db.get(connection, identifier, "comparison")
        return {**result, "stale": report_is_stale(connection, result)}
