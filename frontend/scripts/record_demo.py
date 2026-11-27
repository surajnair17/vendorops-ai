"""Record actual browser interactions against isolated API and worker processes.

The default is offline. Bedrock requires an explicit allowance and a working named
profile. Email delivery is always simulated; this script cannot enable SES sending.
"""

import argparse
import html
import json
import os
import re
import subprocess
import sys
import time
from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pymupdf
from playwright.sync_api import expect, sync_playwright

from backend.examples import quotation_examples, recording_examples
from frontend.scripts.capture_demo import ROOT, available_port, stop, wait_until_ready


class Walkthrough:
    def __init__(self, page, api, output, provider, as_of, pace):
        self.page, self.api, self.output = page, api, output
        self.provider, self.as_of, self.pace = provider, as_of, pace
        self.started = time.monotonic()
        self.chapters = []
        self.receipt = {"provider": provider, "email_provider": "simulated", "as_of": str(as_of)}

    def request(self, method, path, **kwargs):
        return self.api.request(method, path, **kwargs).raise_for_status().json()

    def ready(self):
        self.page.wait_for_timeout(700)
        expect(self.page.get_by_test_id("stApp")).to_have_attribute(
            "data-test-script-state", "notRunning", timeout=150000
        )

    def pause(self, factor=1):
        self.page.wait_for_timeout(self.pace * factor * 1000)

    def chapter(self, title, explanation):
        self.chapters.append({"seconds": round(time.monotonic() - self.started, 1), "title": title})
        print(f"RECORDING: {title}", flush=True)
        self.page.evaluate(
            """({title, explanation, mode}) => {
                let panel = document.getElementById('recording-caption');
                if (!panel) {
                    panel = document.createElement('div');
                    panel.id = 'recording-caption';
                    panel.style.cssText = 'position:fixed;bottom:12px;left:318px;right:24px;'
                        + 'z-index:999999;background:#083b3b;color:white;padding:16px 22px;'
                        + 'border-radius:10px;font:16px/1.45 Segoe UI,sans-serif;'
                        + 'box-shadow:0 6px 30px #0004;pointer-events:none';
                    document.body.appendChild(panel);
                }
                panel.replaceChildren();
                const heading = document.createElement('strong'); heading.textContent = title;
                const body = document.createElement('div'); body.textContent = explanation;
                const badge = document.createElement('small');
                badge.textContent = 'AI: ' + mode + ' | OCR: local Tesseract | Email: simulated';
                badge.style.opacity = '.8';
                panel.append(heading, body, badge);
            }""",
            {"title": title, "explanation": explanation, "mode": self.provider},
        )
        self.pause()

    def screen(self, name):
        self.page.get_by_test_id("stSidebar").get_by_text(name, exact=True).click()
        self.ready()

    def select(self, label, option):
        self.page.get_by_role("combobox", name=label, exact=True).click()
        self.page.get_by_role("option", name=re.compile(re.escape(option))).click()
        self.ready()

    def store(self, filename, content):
        self.upload(filename, content)
        self.page.get_by_role("button", name="Store document", exact=True).click()
        expect(self.page.get_by_test_id("stAlert")).to_contain_text("Document stored")
        self.ready()
        self.select("Document", filename)
        return next(
            record
            for record in self.request("GET", "/documents")
            if record["data"]["filename"] == filename
        )["id"]

    def upload(self, filename, content):
        with self.page.expect_response(
            lambda response: (
                "/_stcore/upload_file/" in response.url and response.request.method == "PUT"
            )
        ) as uploaded:
            self.page.locator('input[type="file"]').first.set_input_files(
                {"name": filename, "mimeType": "application/pdf", "buffer": content}
            )
        assert uploaded.value.ok, "The browser upload failed"
        uploaded.value.finished()
        self.ready()

    def structure_and_review(self, identifier, expected):
        self.page.get_by_role("button", name="Extract structured data", exact=True).click()
        self.ready()
        document = self.request("GET", f"/documents/{identifier}")
        revision = next(
            (r for r in document["revisions"] if r["id"] == document["data"]["revision_id"]), None
        )
        actual = revision["data"]["structured"] if revision else None
        needs_review = actual is None or (revision and revision["data"]["issues"])
        if actual:
            for field in ("document_type", "supplier", "document_number", "po_number", "currency"):
                needs_review = needs_review or actual.get(field) != expected.get(field)
            for field in ("subtotal", "discount", "tax", "freight", "total"):
                value = actual.get(field)
                needs_review = (
                    needs_review
                    or value is None
                    or (
                        expected.get(field) is not None
                        and Decimal(value) != Decimal(expected[field])
                    )
                )
            needs_review = needs_review or len(actual.get("items", [])) != len(expected["items"])
            for observed, labelled in zip(actual.get("items", []), expected["items"]):
                for field in ("quantity", "unit_price", "discount", "tax", "total"):
                    value = observed.get(field)
                    needs_review = (
                        needs_review
                        or value is None
                        or (Decimal(value) != Decimal(labelled[field]))
                    )
            for field in (
                "document_date",
                "valid_until",
                "payment_terms",
                "tax_rate_percent",
                "taxable_amount",
            ):
                if expected.get(field) is not None and actual.get(field) is None:
                    needs_review = True
        if needs_review:
            self.chapter(
                "Review source evidence",
                "Uncertain extraction is corrected against the synthetic source, "
                "with a human revision.",
            )
            reviewed = deepcopy(expected)
            source = "\n\n".join(document["data"]["pages"])
            for field, entry in reviewed["evidence"].items():
                if entry["quote"] not in source:
                    label = {
                        "document_number": "Number:",
                        "document_date": "Date:",
                        "po_number": "PO:",
                        "tax_rate_percent": "Tax rate:",
                        "valid_until": "Valid until:",
                        "payment_terms": "Payment terms:",
                        "taxable_amount": "Taxable amount:",
                    }.get(field, field.replace("_", " ").capitalize() + ":")
                    line = next(
                        (
                            line
                            for line in source.splitlines()
                            if line.casefold().startswith(label.casefold())
                        ),
                        None,
                    )
                    if line:
                        entry["quote"] = line
            editor = self.page.get_by_role("textbox", name="Editable structured JSON", exact=True)
            editor.fill(json.dumps(reviewed, indent=2))
            name = "Save corrected revision" if revision else "Save initial reviewed record"
            self.page.get_by_role("button", name=name, exact=True).click()
            self.ready()
            document = self.request("GET", f"/documents/{identifier}")
            revision = next(
                r for r in document["revisions"] if r["id"] == document["data"]["revision_id"]
            )
        assert revision and revision["data"]["structured"], "No structured record was saved"
        self.receipt.setdefault("documents", []).append(
            {
                "document_id": identifier,
                "revision_id": revision["id"],
                "provider": revision["data"]["provider"],
                "issues": revision["data"]["issues"],
                "attempt_providers": [r["data"]["provider"] for r in document["revisions"]],
            }
        )
        self.pause()

    def action_panel(self, identifier, state=None, subject=None):
        panel = self.page.get_by_test_id("stExpander").filter(has_text=identifier[:8]).first
        summary = panel.locator("summary")
        if state:
            expect(summary).to_contain_text(state)
        if subject:
            expect(summary).to_contain_text(subject)
        self.ready()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            is_open = "e => (e.matches('details') ? e : e.querySelector('details')).open"
            if not panel.evaluate(is_open):
                summary.click()
            self.page.wait_for_timeout(500)
            if panel.evaluate(is_open):
                return panel
        raise TimeoutError("The action review panel did not remain open")

    def run(self, ui_url):
        inputs = []
        for example in [*recording_examples(), quotation_examples()[0]]:
            with pymupdf.open() as document:
                document.new_page().insert_text(
                    (40, 50), example["text"], fontsize=10 if len(inputs) < 2 else 8
                )
                digital = document.tobytes()
                scanned = None
                if len(inputs) == 1:
                    with pymupdf.open() as scan:
                        page = scan.new_page()
                        page.insert_image(page.rect, pixmap=document[0].get_pixmap(dpi=150))
                        scanned = scan.tobytes(deflate=True)
                inputs.append({**example, "digital": digital, "scanned": scanned})
        self.page.goto(ui_url)
        self.ready()
        self.chapter(
            "1. Digital PDF extraction", "A real PDF upload is parsed by PyMuPDF over HTTP."
        )
        self.upload("INV-DEMO-001.pdf", inputs[1]["digital"])
        self.page.get_by_role("button", name="Extract Text", exact=True).click()
        self.ready()
        expect(self.page.get_by_role("textbox", name="Extracted text", exact=True)).to_have_value(
            re.compile("INV-DEMO-001")
        )
        self.pause(2)

        self.screen("Documents")
        self.chapter(
            "2. Structure the purchase order",
            "Read business fields, inspect evidence, and save the source revision.",
        )
        po_id = self.store("PO-DEMO-001.pdf", inputs[0]["digital"])
        self.structure_and_review(po_id, inputs[0]["data"])
        self.chapter(
            "3. Upload a scanned invoice",
            "This PDF contains a page image rather than embedded text.",
        )
        invoice_id = self.store("INV-DEMO-001-scan.pdf", inputs[1]["scanned"])
        self.page.get_by_role("button", name="Request OCR for scanned pages", exact=True).click()
        self.ready()
        deadline = time.monotonic() + 90
        while True:
            jobs = self.request("GET", "/jobs", params={"document_id": invoice_id})
            if jobs and jobs[-1]["data"]["status"] == "succeeded":
                break
            if any(j["data"]["status"] == "failed" for j in jobs):
                raise RuntimeError("OCR job failed")
            if time.monotonic() > deadline:
                raise TimeoutError("OCR job did not finish")
            self.page.wait_for_timeout(500)
        self.page.get_by_role("button", name="Refresh OCR status", exact=True).click()
        self.ready()
        source = self.request("GET", f"/documents/{invoice_id}")["data"]["pages"]
        assert "INV-DEMO-001" in "\n".join(source)
        self.receipt["ocr"] = {
            "provider": "tesseract",
            "status": "succeeded",
            "characters": len("\n".join(source)),
        }
        self.chapter(
            "4. Review OCR and structure the invoice",
            "OCR text is evidence to review; uncertain fields stay visible.",
        )
        self.structure_and_review(invoice_id, inputs[1]["data"])

        self.screen("Compare")
        self.chapter(
            "5. Match and compare",
            "Python compares the PO price 12.50 with the invoice price 13.50.",
        )
        self.page.get_by_role("button", name="Find purchase orders", exact=True).click()
        self.ready()
        self.pause()
        self.page.get_by_role("button", name="Compare documents", exact=True).click()
        self.ready()
        report = self.request("GET", "/comparisons")[-1]
        assert any(f["type"] == "price_variance" for f in report["data"]["findings"])
        self.receipt["comparison"] = report
        self.pause(2)

        self.screen("Policies")
        self.chapter(
            "6. Add policy evidence",
            "Save a purchasing policy before activating it and confirming its numeric rule.",
        )
        self.page.get_by_role("textbox", name="Policy name", exact=True).fill(
            "Demo purchasing policy"
        )
        self.page.get_by_role("textbox", name="Policy text", exact=True).fill(
            "Invoice purchasing policy: unit price variance up to 5 percent is permitted. "
            "An invoice unit price variance above 5 percent requires a corrected invoice "
            "and review."
        )
        date_input = self.page.get_by_test_id("stDateInput").locator("input").first
        date_input.fill("2026/01/01")
        date_input.press("Tab")
        self.page.get_by_role("button", name="Save and index inactive policy", exact=True).click()
        self.ready()
        policy = self.request("GET", "/policies")[-1]
        panel = (
            self.page.get_by_test_id("stExpander").filter(has_text="Demo purchasing policy").first
        )
        panel.locator("summary").click()
        panel.get_by_role("button", name="Toggle activation", exact=True).click()
        self.ready()
        self.page.get_by_role("textbox", name="Rule value", exact=True).fill("5")
        self.page.get_by_role("button", name="Save unconfirmed rule", exact=True).click()
        self.ready()
        self.page.get_by_role("button", name="Confirm / revoke this rule", exact=True).click()
        self.ready()
        self.pause()

        self.screen("Compare")
        self.chapter(
            "7. Apply the confirmed rule",
            "The observed price variance remains; policy classifies it outside the 5% tolerance.",
        )
        report_panel = (
            self.page.get_by_test_id("stExpander").filter(has_text=report["id"][:8]).first
        )
        report_panel.locator("summary").click()
        report_panel.get_by_role("button", name="Assess policy", exact=True).click()
        self.ready()
        assessment = self.request("GET", f"/comparisons/{report['id']}/policy-assessments")[-1]
        assert assessment["data"]["evidence"], "No relevant policy passage was retrieved"
        assert any(
            o["classification"] == "outside_tolerance" for o in assessment["data"]["outcomes"]
        )
        self.receipt["policy_assessment"] = assessment
        self.pause(2)

        self.screen("Actions")
        self.chapter(
            "8. Draft and review",
            "The follow-up cites the report. A test recipient and simulated delivery are explicit.",
        )
        self.page.get_by_role("textbox", name="Policy assessment ID (optional)", exact=True).fill(
            assessment["id"]
        )
        self.select("Action", "corrected_invoice")
        self.page.get_by_role("button", name="Create draft", exact=True).click()
        self.ready()
        action = self.request("GET", "/actions")[-1]
        panel = self.action_panel(action["id"], state="draft")
        self.pause(2)
        panel.get_by_role("textbox", name="Subject", exact=True).fill(
            "Demo: corrected invoice requested"
        )
        panel.get_by_role("textbox", name="Body", exact=True).fill(
            action["data"]["body"] + "\n\nSynthetic demonstration only. Please review the price "
            "before issuing a corrected invoice."
        )
        panel.get_by_role("button", name="Save edit and invalidate approval", exact=True).click()
        self.ready()
        panel = self.action_panel(
            action["id"], state="draft", subject="Demo: corrected invoice requested"
        )
        self.chapter(
            "9. Approve the exact revision",
            "Approval and execution are separate operations; edited content needs fresh approval.",
        )
        panel.get_by_role("button", name="Submit for review", exact=True).click()
        self.ready()
        self.action_panel(action["id"], state="pending_review").get_by_role(
            "button", name="Approve exact revision", exact=True
        ).click()
        self.ready()
        self.pause()
        self.action_panel(action["id"], state="approved").get_by_role(
            "button", name="Execute approved action", exact=True
        ).click()
        self.ready()
        deadline = time.monotonic() + 30
        while True:
            action = self.request("GET", f"/actions/{action['id']}")
            if action["data"]["state"] == "sent":
                break
            if action["data"]["state"] in {"failed", "unknown"} or time.monotonic() > deadline:
                raise RuntimeError("Simulated action did not complete successfully")
            self.page.wait_for_timeout(500)
        assert action["data"]["delivery"]["provider"] == "simulated"
        assert action["data"]["approved_revision"] == action["data"]["content_revision"]
        assert len(action["history"]["delivery_attempt"]) == 1
        self.receipt["action"] = action
        self.page.get_by_role("button", name="Refresh action status", exact=True).click()
        self.ready()
        panel = self.action_panel(action["id"], state="sent")
        self.chapter(
            "10. Durable delivery and history",
            "The worker recorded one simulated delivery tied to approval of this exact content.",
        )
        panel.get_by_role("button", name="Load revision and approval history", exact=True).click()
        self.ready()
        self.pause(2)

        self.screen("Documents")
        self.chapter(
            "11. Review a quotation",
            "Quotation expiry, payment terms, taxable amount, tax rate, "
            "and totals use their own assessment.",
        )
        quote_id = self.store("Q-TERMS-001.pdf", inputs[2]["digital"])
        self.structure_and_review(quote_id, inputs[2]["data"])
        self.screen("Quotes")
        as_of = self.page.get_by_test_id("stDateInput").locator("input").first
        as_of.fill(self.as_of.strftime("%Y/%m/%d"))
        as_of.press("Tab")
        self.ready()
        self.page.get_by_role("button", name="Assess quotation", exact=True).click()
        self.ready()
        quote_report = self.request("GET", f"/documents/{quote_id}/quote-assessments")[-1]
        assert quote_report["data"]["status"] == "checks_passed", quote_report["data"]["findings"]
        self.receipt["quote_assessment"] = quote_report
        self.pause(2)

        self.screen("Operations")
        self.chapter(
            "12. Verify outcomes",
            "Inspect provider mode, completed jobs, action history, and measured model usage.",
        )
        self.receipt["metrics"] = self.request("GET", "/metrics")
        self.receipt["audit_events"] = self.request("GET", "/audit")
        self.receipt["policy_id"] = policy["id"]
        self.receipt["status"] = "completed"
        self.receipt["chapters"] = self.chapters
        self.pause(2)
        self.page.set_content(
            '<body style="background:#083b3b;color:white;'
            'font:24px/1.6 Segoe UI;padding:80px 120px">'
            '<p style="color:#7dd3c6">VENDOROPS AI / RUN COMPLETE</p>'
            "<h1>Documents to an approved follow-up</h1>"
            "<p>Digital PDF extraction and scanned-page OCR completed.</p>"
            "<p>Invoice–PO price variance detected. Confirmed policy applied.</p>"
            "<p>Draft edited, exact revision approved, and one simulated delivery recorded.</p>"
            "<p>Quotation expiry, terms, and financial checks passed.</p>"
            f"<p>Extraction mode: {html.escape(self.provider)}. "
            "Email: simulated. No real email was sent.</p>"
            "<p>Application history and the run receipt retain the evidence.</p></body>"
        )
        self.pause(3)
        return self.receipt


def record(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    api_port, ui_port = available_port(), available_port()
    while api_port == ui_port:
        ui_port = available_port()
    processes = []
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    environment = {
        **os.environ,
        "VENDOROPS_DATA_DIR": str(output / "data"),
        "VENDOROPS_BACKEND_URL": f"http://127.0.0.1:{api_port}",
        "VENDOROPS_PROVIDER": args.provider,
        "VENDOROPS_STORAGE_MODE": "local",
        "VENDOROPS_CHROMA_HOST": "",
        "VENDOROPS_VECTOR_STORE": "sqlite",
        "VENDOROPS_LIVE_CALLS_ENABLED": str(args.provider == "bedrock").lower(),
        "VENDOROPS_LIVE_SEND_ENABLED": "false",
        "VENDOROPS_AWS_PROFILE": "pixel-perfect",
        "VENDOROPS_AWS_REGION": "ap-southeast-2",
        "VENDOROPS_BEDROCK_REGION": "ap-southeast-2",
        "VENDOROPS_MODEL_ID": "amazon.nova-lite-v1:0",
        "VENDOROPS_EMBEDDING_MODEL_ID": "amazon.titan-embed-text-v2:0",
        "VENDOROPS_MAX_MODEL_CHARACTERS": "24000",
        "VENDOROPS_APPROVED_MONTHLY_BUDGET_USD": str(args.allowance),
        "VENDOROPS_DAILY_MODEL_CALLS": "20",
        "VENDOROPS_MAX_OUTPUT_TOKENS": "4096",
        "VENDOROPS_MAX_DOCUMENT_PAGES": "5",
        "VENDOROPS_OCR_PROVIDER": "local",
        "VENDOROPS_OPERATOR": "demo-operator",
        "VENDOROPS_RECIPIENT_ALLOWLIST": "reviewer@example.test",
        "VENDOROPS_REQUEST_TIMEOUT_SECONDS": "150",
        "AWS_EC2_METADATA_DISABLED": "true",
    }
    receipt = {"status": "failed", "provider": args.provider, "email_provider": "simulated"}
    with (output / "servers.log").open("w", encoding="utf-8") as log:
        try:
            for command in (
                ["uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(api_port)],
                [
                    "streamlit",
                    "run",
                    "frontend/app.py",
                    "--server.headless",
                    "true",
                    "--server.address",
                    "127.0.0.1",
                    "--server.port",
                    str(ui_port),
                    "--server.fileWatcherType",
                    "none",
                    "--browser.gatherUsageStats",
                    "false",
                    "--theme.base",
                    "light",
                ],
                ["backend.worker"],
            ):
                processes.append(
                    subprocess.Popen(
                        [sys.executable, "-m", *command],
                        cwd=ROOT,
                        env=environment,
                        stdout=log,
                        stderr=log,
                        creationflags=flags,
                    )
                )
            wait_until_ready(f"http://127.0.0.1:{api_port}/health", processes[0])
            wait_until_ready(f"http://127.0.0.1:{ui_port}/_stcore/health", processes[1])
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel=args.channel, headless=True)
                context = browser.new_context(
                    viewport={"width": 1440, "height": 1000},
                    record_video_dir=str(output / "raw"),
                    record_video_size={"width": 1440, "height": 1000},
                    color_scheme="light",
                    reduced_motion="reduce",
                )
                page = context.new_page()
                page.set_default_timeout(60000)
                video = page.video
                try:
                    mode = "LIVE BEDROCK" if args.provider == "bedrock" else "OFFLINE FIXTURES"
                    page.set_content(
                        '<body style="background:#083b3b;color:white;'
                        'font:24px Segoe UI;padding:100px">'
                        '<p style="color:#7dd3c6">VENDOROPS AI</p>'
                        "<h1>End-to-end document review</h1>"
                        f"<p>{html.escape(mode)} | Real PDF extraction | Real local OCR</p>"
                        "<p>Invoice / PO comparison · Policy evidence · "
                        "Human approval · Simulated email</p>"
                        "<p>Includes quotation review. Synthetic documents only. "
                        "No real email is sent.</p>"
                        f"<p>{args.as_of} · Locally hosted · "
                        f"Approved AWS allowance: ${args.allowance:g}</p></body>"
                    )
                    page.wait_for_timeout(args.pace * 2000)
                    with httpx.Client(
                        base_url=f"http://127.0.0.1:{api_port}/api/v1", timeout=150
                    ) as api:
                        flow = Walkthrough(page, api, output, args.provider, args.as_of, args.pace)
                        receipt = flow.run(f"http://127.0.0.1:{ui_port}")
                    page.screenshot(path=str(output / "final-screen.png"), full_page=True)
                except Exception as error:
                    page.screenshot(path=str(output / "failure-screen.png"), full_page=True)
                    receipt.update({"error_type": type(error).__name__, "error": str(error)[:1500]})
                    raise
                finally:
                    context.close()
                    video.save_as(str(output / "browser.webm"))
                    browser.close()
        finally:
            for process in reversed(processes):
                stop(process)
            receipt["live_processes_stopped"] = True
            (output / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    import imageio_ffmpeg

    with (output / "encoding.log").open("w", encoding="utf-8") as log:
        subprocess.run(
            [
                imageio_ffmpeg.get_ffmpeg_exe(),
                "-y",
                "-i",
                str(output / "browser.webm"),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-an",
                str(output / "VendorOps-AI-End-to-End.mp4"),
            ],
            check=True,
            stdout=log,
            stderr=log,
            timeout=300,
            creationflags=flags,
        )
    print(
        f"PASS: completed pipeline and saved {output / 'VendorOps-AI-End-to-End.mp4'}", flush=True
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="A new output directory")
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--provider", choices=["fixture", "bedrock"], default="fixture")
    parser.add_argument("--allowance", type=float, default=0)
    parser.add_argument("--channel", default="chrome")
    parser.add_argument("--pace", type=float, default=2.5)
    args = parser.parse_args()
    if not 0 <= args.allowance <= 10 or args.provider == "bedrock" and args.allowance <= 0:
        parser.error("Bedrock needs an approved allowance; this recording is limited to $10.")
    if not 0.1 <= args.pace <= 10:
        parser.error("Pace must be between 0.1 and 10 seconds.")
    record(args)


if __name__ == "__main__":
    main()
