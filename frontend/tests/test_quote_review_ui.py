import json
from datetime import date
from pathlib import Path

import httpx
from streamlit.testing.v1 import AppTest


def test_manual_initial_review_is_available_without_a_fixture(monkeypatch):
    calls = []
    record = {
        "id": "doc-1",
        "version": 3,
        "data": {
            "filename": "custom.pdf",
            "pages": ["A custom quote"],
            "duplicate_of": [],
            "revision_id": None,
        },
        "summary": {"document_type": None},
        "revisions": [],
        "extraction_attempts": [],
    }

    def request(method, url, **kwargs):
        path = url.split("/api/v1", 1)[1]
        calls.append((method, path, kwargs.get("json")))
        if method == "PATCH":
            payload = kwargs["json"]
            assert payload["expected_revision_id"] is None
            assert payload["expected_document_version"] == 3
            assert payload["structured"]["payment_terms"] == "Payment before delivery"
            record["version"] = 4
            record["data"]["revision_id"] = "rev-1"
            record["revisions"] = [
                {
                    "id": "rev-1",
                    "data": {
                        "provider": "human",
                        "issues": ["Missing currency"],
                        "structured": payload["structured"],
                    },
                }
            ]
            return httpx.Response(200, json=record["revisions"][0])
        responses = {
            "/metrics": {"provider": "fixture"},
            "/documents": [record],
            "/documents/doc-1": record,
            "/jobs": [],
        }
        return httpx.Response(200, json=responses[path])

    monkeypatch.setattr(httpx, "request", request)
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run(timeout=30)
    app.sidebar.radio[0].set_value("Documents").run()
    assert not app.exception
    editor = next(area for area in app.text_area if area.label == "Editable structured JSON")
    values = json.loads(editor.value)
    assert values["taxable_amount"] is None
    values["payment_terms"] = "Payment before delivery"
    editor.set_value(json.dumps(values)).run()
    next(b for b in app.button if b.label == "Save initial reviewed record").click().run()
    assert not app.exception
    assert any("Provider: human" in item.value for item in app.markdown)
    assert any("Missing currency" in item.value for item in app.warning)
    assert sum(method == "PATCH" for method, _, _ in calls) == 1
    assert not any(method == "POST" for method, _, _ in calls)


def test_quote_screen_assesses_exact_revision_and_shows_stale_report(monkeypatch):
    reports = []
    record = {
        "id": "doc-1",
        "data": {"filename": "quote.pdf", "pages": ["Total: 25.00"], "revision_id": "rev-1"},
        "summary": {"document_type": "quotation"},
        "revisions": [
            {
                "id": "rev-1",
                "data": {"provider": "human", "structured": {"total": "25.00", "currency": "USD"}},
            }
        ],
    }

    def request(method, url, **kwargs):
        path = url.split("/api/v1", 1)[1]
        if method == "POST":
            assert kwargs["json"] == {"expected_revision_id": "rev-1", "as_of": "2026-11-26"}
            reports.append(
                {
                    "id": "assessment-1",
                    "stale": False,
                    "data": {
                        "as_of": "2026-11-26",
                        "status": "needs_review",
                        "checks": [],
                        "findings": [
                            {
                                "field": "taxable_amount",
                                "message": "Missing taxable_amount",
                                "expected": None,
                                "evidence": [],
                            }
                        ],
                    },
                }
            )
            return httpx.Response(201, json=reports[-1])
        return httpx.Response(
            200,
            json={
                "/documents": [record],
                "/documents/doc-1": record,
                "/documents/doc-1/quote-assessments": reports,
            }[path],
        )

    monkeypatch.setattr(httpx, "request", request)
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run(timeout=30)
    app.sidebar.radio[0].set_value("Quotes").run()
    app.date_input[0].set_value(date(2026, 11, 26)).run()
    next(b for b in app.button if b.label == "Assess quotation").click().run()
    assert not app.exception
    assert any("Missing taxable_amount" in item.value for item in app.warning)
    reports[0]["stale"] = True
    app.run()
    assert any("Fields changed" in item.value for item in app.warning)
