from copy import deepcopy

import pymupdf
import pytest
from conftest import make_pdf
from pydantic import ValidationError
from test_comparison import upload_structured
from test_policies import seed_policy

from backend import db
from backend.config import settings
from backend.examples import examples
from backend.schemas.business import BusinessDocument
from backend.services.structured import extract_structure


def test_page_limit_precedes_text_extraction_on_every_pdf_route(client, monkeypatch):
    content = make_pdf("one", "two")
    monkeypatch.setattr(settings, "max_document_pages", 1)

    def forbidden(*args, **kwargs):
        raise AssertionError("Page budget must be checked before extraction")

    monkeypatch.setattr(pymupdf.Page, "get_text", forbidden)
    for route in (
        "/documents/extract",
        "/documents",
        "/policies/pdf?name=X&policy_version=1&effective_date=2026-01-01",
    ):
        response = client.post("/api/v1" + route, files={"file": ("many.pdf", content)})
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "too_many_pages"
    assert client.get("/api/v1/documents").json() == []


def test_expanded_pdf_text_budget_is_enforced(client, monkeypatch):
    monkeypatch.setattr(settings, "max_extracted_characters", 5)
    response = client.post(
        "/api/v1/documents",
        files={"file": ("large-text.pdf", make_pdf("More than five characters"))},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "extracted_text_too_large"
    assert client.get("/api/v1/documents").json() == []


@pytest.mark.parametrize("field", ["supplier", "document_number", "po_number"])
def test_blank_identifiers_are_not_usable_business_values(field):
    data = deepcopy(examples()[1]["data"])
    data[field] = "   "
    with pytest.raises(ValidationError):
        BusinessDocument.model_validate(data)


def test_unreviewed_source_is_never_automatically_matched_or_marked_clean(client):
    po, invoice = upload_structured(client, 0), upload_structured(client, 1)
    with db.transaction() as connection:
        document = db.get(connection, invoice, "document")
        revision = db.get(connection, document["data"]["revision_id"], "revision")
        db.update(
            connection,
            revision,
            {
                **revision["data"],
                "issues": ["Missing source citation for supplier"],
                "review_status": "needs_review",
            },
        )
    assert (
        client.get(f"/api/v1/documents/{invoice}/match-candidates").json()["automatic_match"]
        is None
    )
    report = client.post("/api/v1/comparisons", json={"invoice_id": invoice, "po_id": po}).json()
    assert report["data"]["status"] == "needs_review"
    assert any(f["type"] == "validation_required" for f in report["data"]["findings"])


@pytest.mark.parametrize("value", ["1e1000000", "NaN", "Infinity", "-1", "0.1234567"])
def test_rule_thresholds_reject_unsafe_decimal_inputs(client, value):
    policy, _ = seed_policy(client)
    response = client.post(
        "/api/v1/rules",
        json={
            "policy_id": policy["id"],
            "chunk_id": "p1-c1",
            "rule_type": "price_variance_percent",
            "value": value,
        },
    )
    assert response.status_code == 422


def test_page_labels_count_toward_the_model_input_budget(monkeypatch):
    class Provider:
        mode = "bedrock"

        def extract(self, *args, **kwargs):
            raise AssertionError("Oversized payload must never reach the provider")

    from backend.errors import AppError

    monkeypatch.setattr(settings, "max_model_characters", 5)
    with pytest.raises(AppError) as error:
        extract_structure("abc", ["abc"], Provider())
    assert error.value.code == "model_input_too_large"


def test_retired_vector_backend_is_blocked_before_paid_embeddings(client, monkeypatch):
    from backend.errors import AppError
    from backend.services.policies import embedding

    monkeypatch.setattr(settings, "vector_store", "chroma")
    monkeypatch.setattr(settings, "provider", "bedrock")
    with pytest.raises(AppError) as error:
        embedding("never send this")
    assert error.value.code == "unsupported_vector_store"


def test_invalid_legacy_revision_returns_review_error_instead_of_internal_failure(client):
    invoice = upload_structured(client, 1)
    with db.transaction() as connection:
        document = db.get(connection, invoice, "document")
        revision = db.get(connection, document["data"]["revision_id"], "revision")
        data = deepcopy(revision["data"])
        data["structured"]["supplier"] = "   "
        db.update(connection, revision, data)
    response = client.get(f"/api/v1/documents/{invoice}/match-candidates")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "structured_review_required"


def test_ocr_output_budget_preserves_the_original_document(client, monkeypatch):
    from backend.services.ocr import apply_ocr_result

    document = client.post("/api/v1/documents", files={"file": ("scan.pdf", make_pdf(""))}).json()
    with db.transaction() as connection:
        job = db.create(
            connection,
            "job",
            {
                "kind": "ocr",
                "status": "starting",
                "document_id": document["id"],
                "document_version": document["version"],
            },
        )
    monkeypatch.setattr(settings, "max_extracted_characters", 2)
    assert apply_ocr_result(job["id"], [["over budget"]], "SUCCEEDED", "tesseract")
    assert client.get(f"/api/v1/documents/{document['id']}").json()["data"]["pages"] == [""]
    assert (
        client.get(f"/api/v1/jobs/{job['id']}").json()["data"]["error_code"] == "ocr_text_too_large"
    )


def test_worker_failure_does_not_starve_other_job_types(monkeypatch, caplog):
    from backend import worker

    calls = []

    def broken():
        raise RuntimeError("private document details")

    def successful():
        calls.append("local_ocr")
        return True

    monkeypatch.setattr(worker, "process_email_once", broken)
    monkeypatch.setattr(worker, "process_local_ocr_once", successful)
    monkeypatch.setattr(worker, "start_ocr_once", lambda: False)
    monkeypatch.setattr(worker, "poll_ocr_once", lambda: False)
    assert worker.run_once() == (True, True)
    assert calls == ["local_ocr"]
    assert "private document details" not in caplog.text
