"""Exercise an empty fixture deployment over HTTP, including its separate OCR/email worker."""

import argparse
import json
import time
from datetime import date

import httpx
import pymupdf

from backend.examples import quotation_examples
from backend.scripts.demo import seed


def verify(api: httpx.Client) -> dict:
    def request(method, path, **kwargs):
        response = api.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    def wait(job, seconds=60):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            record = request("GET", job["status_url"].removeprefix("/api/v1"))
            if record["data"]["status"] in {"succeeded", "failed", "unknown"}:
                assert record["data"]["status"] == "succeeded", record
                return record
            time.sleep(0.25)
        raise TimeoutError("The separate worker did not complete its job")

    metrics = request("GET", "/metrics")
    if (
        metrics["provider"] != "fixture"
        or metrics["live_calls_enabled"]
        or metrics["live_send_enabled"]
    ):
        raise ValueError("Runtime verification requires fixture mode with both live flags disabled")
    if metrics["documents"] or metrics["action_states"]:
        raise ValueError("Use a new, empty demonstration volume; existing work is never reset")
    if metrics["ocr_provider"] != "local" or metrics["vector_store"] != "sqlite":
        raise ValueError("Runtime verification requires local OCR and SQLite retrieval")
    seeded = seed(api)
    policy = next(p for p in request("GET", "/policies") if p["id"] == seeded["policy_id"])
    request(
        "POST",
        f"/policies/{policy['id']}/activate",
        json={"active": True, "expected_version": policy["version"]},
    )
    rule = next(r for r in request("GET", "/rules") if r["data"]["policy_id"] == policy["id"])
    request(
        "POST",
        f"/rules/{rule['id']}/confirm",
        json={"active": True, "expected_version": rule["version"]},
    )
    assessment = request("POST", f"/comparisons/{seeded['comparison_id']}/policy-assessments")
    assert assessment["data"]["evidence"] and assessment["data"]["rule_citations"]
    action = request(
        "POST",
        "/actions",
        json={
            "comparison_id": seeded["comparison_id"],
            "assessment_id": assessment["id"],
            "recipient": request("GET", "/contacts")[0],
            "delivery_mode": "simulated",
        },
    )
    for operation, extra in (("request-review", {}), ("review", {"decision": "approve"})):
        action = request(
            "POST",
            f"/actions/{action['id']}/{operation}",
            json={"expected_version": action["version"], **extra},
        )
    job = request(
        "POST", f"/actions/{action['id']}/execute", json={"expected_version": action["version"]}
    )
    assert wait(job)["data"]["result"]["provider"] == "simulated"
    detail = request("GET", f"/actions/{action['id']}")
    assert len(detail["history"]["delivery_attempt"]) == 1

    with pymupdf.open() as source, pymupdf.open() as scanned:
        page = source.new_page(width=600, height=200)
        page.insert_text((35, 80), "VendorOps OCR CHECK 12345", fontsize=24)
        raster = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
        target = scanned.new_page(width=600, height=200)
        target.insert_image(target.rect, pixmap=raster)
        document = request(
            "POST", "/documents", files={"file": ("runtime-scan.pdf", scanned.tobytes())}
        )
    assert document["data"]["pages"] == [""]
    wait(request("POST", f"/documents/{document['id']}/ocr"))
    recognized = request("GET", f"/documents/{document['id']}")
    assert "12345" in " ".join(recognized["data"]["pages"])

    with pymupdf.open() as quote:
        quote.new_page().insert_text((40, 50), quotation_examples()[0]["text"], fontsize=8)
        record = request(
            "POST", "/documents", files={"file": ("runtime-quote.pdf", quote.tobytes())}
        )
    revision = request("POST", f"/documents/{record['id']}/structure")
    quote_result = request(
        "POST",
        f"/documents/{record['id']}/quote-assessments",
        json={"as_of": date(2026, 11, 26).isoformat(), "expected_revision_id": revision["id"]},
    )
    assert quote_result["data"]["status"] == "checks_passed"
    final = request("GET", "/metrics")
    assert final["usage"] == [] and final["action_states"].get("sent") == 1
    return {
        "status": "passed",
        "documents": final["documents"],
        "pdf": "real",
        "ocr": "local_tesseract",
        "structured_extraction": "fixture",
        "policy_retrieval": "fixture_lexical_sqlite",
        "email": "simulated",
        "delivery_attempts": 1,
        "paid_calls": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url.rstrip("/") + "/api/v1", timeout=30) as api:
        print(json.dumps(verify(api), indent=2))


if __name__ == "__main__":
    main()
