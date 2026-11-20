from copy import deepcopy
from decimal import Decimal

import pytest

from conftest import make_pdf

from backend.examples import examples
from backend.schemas.business import BusinessDocument
from backend.services.comparison import compare
from backend.errors import AppError


def test_price_difference_is_decimal_and_evidenced():
    order, invoice = [BusinessDocument.model_validate(e["data"]) for e in examples()[3:5]]
    findings = compare(invoice, order)
    assert len(findings) == 1
    assert findings[0]["type"] == "price_variance"
    assert findings[0]["difference"] == "1.00"
    assert findings[0]["evidence"]["invoice"]


def test_missing_is_not_zero_and_repeated_lines_are_ambiguous():
    order = BusinessDocument.model_validate(examples()[0]["data"])
    invoice = BusinessDocument.model_validate(examples()[1]["data"])
    invoice.items[0].quantity = None
    assert "missing_field" in [f["type"] for f in compare(invoice, order)]
    order.items.append(deepcopy(order.items[0]))
    assert "ambiguous_line" in [f["type"] for f in compare(invoice, order)]


def upload_structured(client, index):
    example = examples()[index]
    result = client.post(
        "/api/v1/documents", files={"file": ("sample.pdf", make_pdf(example["text"]))}
    )
    identifier = result.json()["id"]
    assert client.post(f"/api/v1/documents/{identifier}/structure").status_code == 200
    return identifier


def test_auto_match_report_and_staleness(client):
    po = upload_structured(client, 3)
    invoice = upload_structured(client, 4)
    candidates = client.get(f"/api/v1/documents/{invoice}/match-candidates").json()
    assert candidates["automatic_match"] == po
    response = client.post("/api/v1/comparisons", json={"invoice_id": invoice})
    assert response.status_code == 201
    report = response.json()
    assert not client.get(f"/api/v1/comparisons/{report['id']}").json()["stale"]
    document = client.get(f"/api/v1/documents/{invoice}").json()
    client.patch(
        f"/api/v1/documents/{invoice}/structured-data",
        json={
            "expected_revision_id": document["data"]["revision_id"],
            "structured": examples()[4]["data"],
        },
    )
    assert client.get(f"/api/v1/comparisons/{report['id']}").json()["stale"]


def test_currency_units_totals_and_manual_mapping():
    order = BusinessDocument.model_validate(examples()[0]["data"])
    invoice = BusinessDocument.model_validate(examples()[1]["data"])
    invoice.currency = "EUR"
    assert compare(invoice, order)[0]["type"] == "currency_mismatch"
    invoice.currency = "USD"
    invoice.items[0].unit = "case"
    assert "unit_mismatch" in [f["type"] for f in compare(invoice, order)]
    invoice.items[0].unit = "box"
    invoice.total = Decimal("52")
    assert "total_mismatch" in [f["type"] for f in compare(invoice, order)]
    with pytest.raises(AppError):
        compare(invoice, order, {0: 9})
    invoice.total = Decimal("50")
    order.items = [deepcopy(order.items[0]), deepcopy(order.items[0])]
    invoice.items = [deepcopy(invoice.items[0]), deepcopy(invoice.items[0])]
    # Explicit mappings resolve repeated identifiers; totals still expose inconsistencies.
    assert "ambiguous_line" not in [f["type"] for f in compare(invoice, order, {0: 1, 1: 0})]


def test_duplicate_purchase_orders_abstain(client):
    upload_structured(client, 0)
    upload_structured(client, 0)
    invoice = upload_structured(client, 1)
    assert client.get(f"/api/v1/documents/{invoice}/match-candidates").json()["automatic_match"] is None
    assert client.post("/api/v1/comparisons", json={"invoice_id": invoice}).status_code == 409
