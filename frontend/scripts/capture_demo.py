"""Capture real application screens using isolated synthetic data and no live services."""

import argparse
import os
import re
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
import pymupdf
from playwright.sync_api import expect, sync_playwright

from backend.examples import quotation_examples

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "backend/docs/assets"


@contextmanager
def preview_directory():
    temporary = TemporaryDirectory(prefix="vendorops-preview-")
    try:
        yield temporary.name
    finally:
        # Windows can retain native index-file handles briefly after a child exits.
        for attempt in range(6):
            try:
                temporary.cleanup()
                break
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.2 * (attempt + 1))


def available_port() -> int:
    with socket.socket() as connection:
        connection.bind(("127.0.0.1", 0))
        return connection.getsockname()[1]


def wait_until_ready(url: str, process: subprocess.Popen) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Preview server exited before becoming ready.")
        try:
            httpx.get(url, timeout=2).raise_for_status()
            return
        except httpx.HTTPError:
            time.sleep(0.2)
    raise TimeoutError("Preview server did not become ready.")


def stop(process: subprocess.Popen) -> None:
    if process.poll() is None:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
                check=False,
            )
        else:
            process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def capture(channel: str | None) -> None:
    api_port, ui_port = available_port(), available_port()
    while ui_port == api_port:
        ui_port = available_port()
    processes = []
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with preview_directory() as directory:
        environment = {
            **os.environ,
            "VENDOROPS_DATA_DIR": directory,
            "VENDOROPS_BACKEND_URL": f"http://127.0.0.1:{api_port}",
            "VENDOROPS_PROVIDER": "fixture",
            "VENDOROPS_STORAGE_MODE": "local",
            "VENDOROPS_CHROMA_HOST": "",
            "VENDOROPS_VECTOR_STORE": "sqlite",
            "VENDOROPS_LIVE_CALLS_ENABLED": "false",
            "VENDOROPS_LIVE_SEND_ENABLED": "false",
            "VENDOROPS_OPERATOR": "demo-operator",
            "VENDOROPS_RECIPIENT_ALLOWLIST": "reviewer@example.test",
            "AWS_EC2_METADATA_DISABLED": "true",
        }
        with (Path(directory) / "preview.log").open("w", encoding="utf-8") as log:
            try:
                for arguments in (
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
                        "--theme.primaryColor",
                        "#0f766e",
                    ],
                ):
                    processes.append(
                        subprocess.Popen(
                            [sys.executable, "-m", *arguments],
                            cwd=ROOT,
                            env=environment,
                            stdout=log,
                            stderr=log,
                            creationflags=flags,
                        )
                    )
                wait_until_ready(f"http://127.0.0.1:{api_port}/health", processes[0])
                wait_until_ready(f"http://127.0.0.1:{ui_port}/_stcore/health", processes[1])
                subprocess.run(
                    [sys.executable, "-m", "backend.scripts.demo"],
                    cwd=ROOT,
                    env=environment,
                    stdout=log,
                    stderr=log,
                    check=True,
                    timeout=90,
                    creationflags=flags,
                )
                with httpx.Client(base_url=f"http://127.0.0.1:{api_port}/api/v1") as api:
                    records = api.get("/documents").raise_for_status().json()
                    invoice = next(r for r in records if r["summary"]["document_type"] == "invoice")
                    source = api.get(f"/documents/{invoice['id']}").raise_for_status().json()
                    with pymupdf.open() as pdf:
                        pdf.new_page().insert_text(
                            (40, 50), "\n\n".join(source["data"]["pages"]), fontsize=10
                        )
                        content = pdf.tobytes()
                    example = quotation_examples()[0]
                    with pymupdf.open() as pdf:
                        pdf.new_page().insert_text((40, 50), example["text"], fontsize=8)
                        quote_content = pdf.tobytes()
                    quotation = (
                        api.post("/documents", files={"file": ("Q-TERMS-001.pdf", quote_content)})
                        .raise_for_status()
                        .json()
                    )
                    api.post(f"/documents/{quotation['id']}/structure").raise_for_status()
                ASSETS.mkdir(parents=True, exist_ok=True)
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(channel=channel, headless=True)
                    context = browser.new_context(
                        viewport={"width": 1440, "height": 1320},
                        device_scale_factor=1,
                        color_scheme="light",
                        reduced_motion="reduce",
                    )
                    page = context.new_page()
                    page.set_default_timeout(30000)
                    page.goto(f"http://127.0.0.1:{ui_port}")
                    expect(page.get_by_role("heading", name="PDF text extraction")).to_be_visible()
                    page.locator('input[type="file"]').set_input_files(
                        {
                            "name": source["data"]["filename"],
                            "mimeType": "application/pdf",
                            "buffer": content,
                        }
                    )
                    page.get_by_role("button", name="Extract Text", exact=True).click()
                    expect(page.get_by_role("textbox", name="Extracted text")).to_have_value(
                        re.compile("INV-002")
                    )
                    expect(page.get_by_test_id("stApp")).to_have_attribute(
                        "data-test-script-state", "notRunning"
                    )
                    page.screenshot(
                        path=str(ASSETS / "extraction.png"), full_page=True, animations="disabled"
                    )
                    page.get_by_test_id("stSidebar").get_by_text("Documents", exact=True).click()
                    expect(page.get_by_role("heading", name="Document workspace")).to_be_visible()
                    page.get_by_role("combobox").first.click()
                    page.get_by_role("option", name=re.compile("INV-002.pdf")).click()
                    expect(
                        page.get_by_role("textbox", name="Editable structured JSON")
                    ).to_have_value(re.compile('"document_number": "INV-002"'))
                    expect(page.get_by_test_id("stApp")).to_have_attribute(
                        "data-test-script-state", "notRunning"
                    )
                    page.screenshot(
                        path=str(ASSETS / "document-review.png"),
                        full_page=True,
                        animations="disabled",
                    )
                    page.set_viewport_size({"width": 1440, "height": 1600})
                    page.get_by_test_id("stSidebar").get_by_text("Quotes", exact=True).click()
                    expect(page.get_by_role("heading", name="Quotation review")).to_be_visible()
                    expect(page.get_by_role("button", name="Assess quotation")).to_be_visible()
                    expect(page.get_by_test_id("stApp")).to_have_attribute(
                        "data-test-script-state", "notRunning"
                    )
                    as_of = page.get_by_test_id("stDateInput").locator("input").first
                    as_of.fill(date(2026, 11, 27).strftime("%Y/%m/%d"))
                    as_of.press("Enter")
                    as_of.press("Escape")
                    page.get_by_role("heading", name="Quotation review", exact=True).click()
                    page.wait_for_timeout(700)
                    expect(page.get_by_test_id("stApp")).to_have_attribute(
                        "data-test-script-state", "notRunning"
                    )
                    page.get_by_role("button", name="Assess quotation", exact=True).click()
                    expect(
                        page.get_by_text(
                            "Supported checks passed. This is not purchase approval.", exact=True
                        )
                    ).to_be_visible()
                    expect(page.get_by_test_id("stApp")).to_have_attribute(
                        "data-test-script-state", "notRunning"
                    )
                    page.screenshot(
                        path=str(ASSETS / "quotation-review.png"),
                        full_page=True,
                        animations="disabled",
                    )
                    page.get_by_test_id("stSidebar").get_by_text("Operations", exact=True).click()
                    expect(page.get_by_role("heading", name="Action states")).to_be_visible()
                    expect(
                        page.get_by_text("Provider: fixture · Operator: demo-operator", exact=True)
                    ).to_be_visible()
                    expect(page.get_by_role("heading", name="Document workspace")).to_have_count(0)
                    expect(page.get_by_test_id("stApp")).to_have_attribute(
                        "data-test-script-state", "notRunning"
                    )
                    page.set_viewport_size({"width": 1440, "height": 960})
                    page.screenshot(
                        path=str(ASSETS / "operations.png"), full_page=True, animations="disabled"
                    )
                    mobile = browser.new_context(
                        viewport={"width": 390, "height": 844},
                        device_scale_factor=1,
                        color_scheme="light",
                        reduced_motion="reduce",
                    )
                    mobile_page = mobile.new_page()
                    mobile_page.goto(f"http://127.0.0.1:{ui_port}")
                    expect(
                        mobile_page.get_by_role("heading", name="PDF text extraction")
                    ).to_be_visible()
                    assert mobile_page.evaluate(
                        "document.documentElement.scrollWidth <= window.innerWidth"
                    ), "Mobile layout overflows horizontally"
                    browser.close()
                print(
                    "Captured extraction, document and quotation review, and operations; "
                    "mobile layout passed."
                )
            except Exception:
                log.flush()
                # The log belongs to isolated synthetic processes, not the user's running app.
                print((Path(directory) / "preview.log").read_text(encoding="utf-8")[-5000:])
                raise
            finally:
                for process in reversed(processes):
                    stop(process)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", help="Use an installed browser, for example chrome or msedge.")
    capture(parser.parse_args().channel)


if __name__ == "__main__":
    main()
