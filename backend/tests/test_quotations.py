from copy import deepcopy
from datetime import date
from decimal import Decimal

import pymupdf
import pytest
from conftest import make_pdf
from pydantic import ValidationError

from backend import db
from backend.examples import examples, quotation_examples
from backend.schemas.business import BusinessDocument, issues_for, source_issues
from backend.services.quotations import assess_quote
from backend.services.structured import extract_structure


def quote():
    example = quotation_examples()[0]
    return BusinessDocument.model_validate(example["data"]), [example["text"]]


def test_complete_quote_checks_and_rounding():
    document, pages = quote()
    result = assess_quote(document, pages, date(2026, 12, 31))
    assert result["status"] == "checks_passed"
    assert not result["findings"]
    checks = {check["field"]: check for check in result["checks"]}
    # Independently: 250 * 0.0625 = 15.625 -> 15.63; 300 + 15.63 = 315.63.
    assert checks["tax"]["expected"] == "15.63"
    assert checks["total"]["expected"] == "315.63"
    assert checks["taxable_amount"]["expected"] == "250.00"
    assert all(check["status"] == "passed" for check in result["checks"])


def test_expiry_is_inclusive_and_date_contradictions_need_review():
    document, pages = quote()
    result = assess_quote(document, pages, date(2027, 1, 1))
    expired = next(f for f in result["findings"] if f["type"] == "quote_expired")
    assert expired["actual"] == "2026-12-31"
    assert expired["evidence"][0]["page"] == 1
    document.valid_until = date(2026, 10, 31)
    result = assess_quote(document, pages, date(2026, 10, 1))
    assert {"invalid_date_range", "future_document_date"} <= {f["type"] for f in result["findings"]}


def test_wrong_ocr_quantity_is_flagged_without_repairing_it():
    document, pages = quote()
    document.items[0].quantity = Decimal(3)
    result = assess_quote(document, pages, date(2026, 11, 26))
    finding = next(f for f in result["findings"] if f["field"] == "items.0.total")
    assert finding["expected"] == "375.00"
    assert finding["actual"] == "250.00"
    assert finding["difference"] == "-125.00"
    assert document.items[0].quantity == 3
    assert finding["evidence"]


def test_missing_inputs_are_not_zero_and_unknown_currency_skips_math():
    document, pages = quote()
    document.items[0].quantity = None
    document.discount = None
    document.taxable_amount = None
    document.payment_terms = None
    result = assess_quote(document, pages, date(2026, 11, 26))
    skipped = {check["field"] for check in result["checks"] if check["status"] == "skipped"}
    assert {"items.0.total", "tax", "total", "taxable_amount"} <= skipped
    assert result["status"] == "needs_review"
    document.currency = None
    result = assess_quote(document, pages, date(2026, 11, 26))
    assert any(f["type"] == "unsupported_currency" for f in result["findings"])
    assert not any(check["field"] == "tax" for check in result["checks"])


def test_rate_citation_and_placeholders_require_review():
    document, pages = quote()
    document.tax_rate_percent = Decimal("6.2508")
    document.evidence["tax_rate_percent"].quote = "Tax rate: 6.2508"
    pages = [pages[0].replace("Tax rate: 6.25%", "Tax rate: 6.2508")]
    assert any("percent marker" in issue for issue in source_issues(document, pages))
    document.supplier = "Company Name"
    document.document_number = "[123456]"
    assert len([issue for issue in issues_for(document) if "placeholder" in issue]) == 2
    document.evidence.pop("valid_until")
    assert "Missing source citation for valid_until" in source_issues(document, pages)


@pytest.mark.parametrize("rate", ["-1", "100.01", "NaN", "Infinity", "6.1234567"])
def test_invalid_rates_are_rejected(rate):
    with pytest.raises(ValidationError):
        BusinessDocument(document_type="quotation", tax_rate_percent=rate)


def test_partial_taxable_flags_do_not_infer_a_taxable_base():
    document, pages = quote()
    document.items[1].taxable = None
    result = assess_quote(document, pages, date(2026, 11, 26))
    assert (
        next(c for c in result["checks"] if c["field"] == "taxable_amount")["status"] == "skipped"
    )


def test_tax_and_total_discrepancies_are_independent():
    document, pages = quote()
    document.tax = Decimal("15.62")
    document.total = Decimal("315.6201")
    result = assess_quote(document, pages, date(2026, 11, 26))
    mismatches = {f["field"]: f for f in result["findings"] if f["type"] == "calculation_mismatch"}
    assert mismatches["tax"]["difference"] == "-0.01"
    assert mismatches["total"]["difference"] == "0.0001"


def test_initial_manual_record_after_unknown_fixture_and_stale_version(client):
    doc = client.post(
        "/api/v1/documents", files={"file": ("custom.pdf", make_pdf("Unrecognized quotation"))}
    ).json()
    path = f"/api/v1/documents/{doc['id']}/structured-data"
    assert client.post(f"/api/v1/documents/{doc['id']}/structure").status_code == 422
    payload = {"expected_revision_id": None, "structured": {"document_type": "quotation"}}
    assert client.patch(path, json=payload).status_code == 422
    assert client.patch(path, json={**payload, "expected_document_version": 99}).status_code == 409
    response = client.patch(path, json={**payload, "expected_document_version": doc["version"]})
    assert response.status_code == 200
    revision = response.json()
    assert revision["data"]["provider"] == "human"
    assert revision["data"]["parent_id"] is None
    assert revision["data"]["review_status"] == "needs_review"
    assert client.patch(path, json={**payload, "expected_document_version": 1}).status_code == 409
    # A new engine connection reads the same persisted manual revision.
    from backend.config import settings

    db.engine_for(str(settings.data_dir.resolve())).dispose()
    assert (
        client.get(f"/api/v1/documents/{doc['id']}").json()["data"]["revision_id"] == revision["id"]
    )


def test_quote_fixture_and_assessment_revision_history(client):
    example = quotation_examples()[0]
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((40, 50), example["text"], fontsize=8)
        content = pdf.tobytes()
    document = client.post("/api/v1/documents", files={"file": ("quote.pdf", content)}).json()
    path = f"/api/v1/documents/{document['id']}"
    revision_response = client.post(f"{path}/structure")
    assert revision_response.status_code == 200, revision_response.text
    revision = revision_response.json()
    assert revision["data"]["issues"] == []
    assert revision["data"]["schema_version"] == 2
    payload = {"expected_revision_id": revision["id"], "as_of": "2026-11-26"}
    response = client.post(f"{path}/quote-assessments", json=payload)
    assert response.status_code == 201
    report = response.json()
    assert report["data"]["status"] == "checks_passed"
    assert not report["stale"]
    edited = deepcopy(example["data"])
    edited["valid_until"] = "2026-11-01"
    assert (
        client.patch(
            f"{path}/structured-data",
            json={"expected_revision_id": revision["id"], "structured": edited},
        ).status_code
        == 200
    )
    assert client.get(f"/api/v1/quote-assessments/{report['id']}").json()["stale"]
    assert client.get(f"{path}/quote-assessments").json()[0]["stale"]
    assert client.post(f"{path}/quote-assessments", json=payload).status_code == 409
    with db.transaction() as connection:
        stored = db.get(connection, report["id"], "quote_assessment")
        assert stored["data"]["revision_id"] == revision["id"]


def test_invoice_cannot_use_quotation_endpoint(client):
    example = examples()[1]
    doc = client.post(
        "/api/v1/documents", files={"file": ("invoice.pdf", make_pdf(example["text"]))}
    ).json()
    revision = client.post(f"/api/v1/documents/{doc['id']}/structure").json()
    response = client.post(
        f"/api/v1/documents/{doc['id']}/quote-assessments",
        json={"expected_revision_id": revision["id"], "as_of": "2026-11-26"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "quotation_required"


def test_legacy_schema_and_corpus_stay_compatible():
    assert len(examples()) == 60
    example = examples()[2]
    result = extract_structure(example["text"], [example["text"]])
    assert result["structured"]["valid_until"] is None
    assert result["structured"]["tax_rate_percent"] is None
    assert not result["issues"]
