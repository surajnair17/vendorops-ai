"""Launch both applications, exercise real HTTP, and shut down only our child processes."""

import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
import pymupdf
from streamlit.testing.v1 import AppTest

from backend.examples import quotation_examples
from backend.scripts.demo import seed


def main() -> None:
    processes = []
    temporary = TemporaryDirectory(prefix="vendorops-smoke-")
    environment = {
        **os.environ,
        "VENDOROPS_DATA_DIR": temporary.name,
        "VENDOROPS_PROVIDER": "fixture",
        "VENDOROPS_VECTOR_STORE": "sqlite",
        "VENDOROPS_LIVE_CALLS_ENABLED": "false",
        "VENDOROPS_LIVE_SEND_ENABLED": "false",
    }
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        for arguments in (
            ["uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "18000"],
            [
                "streamlit",
                "run",
                "frontend/app.py",
                "--server.headless",
                "true",
                "--server.address",
                "127.0.0.1",
                "--server.port",
                "18501",
                "--browser.gatherUsageStats",
                "false",
            ],
        ):
            processes.append(
                subprocess.Popen(
                    [sys.executable, "-m", *arguments],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=flags,
                    env=environment,
                )
            )
        with httpx.Client(timeout=5) as client:
            for url in ("http://127.0.0.1:18000/health", "http://127.0.0.1:18501/_stcore/health"):
                deadline = time.monotonic() + 45
                while True:
                    try:
                        response = client.get(url)
                        response.raise_for_status()
                        break
                    except httpx.HTTPError:
                        if time.monotonic() > deadline:
                            raise
                        time.sleep(0.2)
            with pymupdf.open() as pdf:
                pdf.new_page().insert_text((72, 72), "Smoke invoice INV-001")
                content = pdf.tobytes()
            response = client.post(
                "http://127.0.0.1:18000/api/v1/documents/extract",
                files={"file": ("smoke.pdf", content, "application/pdf")},
            )
            response.raise_for_status()
            assert "INV-001" in response.json()["extracted_text"]
            previous_url = os.environ.get("VENDOROPS_BACKEND_URL")
            os.environ["VENDOROPS_BACKEND_URL"] = "http://127.0.0.1:18000"
            try:
                ui = AppTest.from_file(Path("frontend/app.py").resolve()).run(timeout=30)
                ui.file_uploader[0].upload("smoke.pdf", content, "application/pdf").run()
                ui.button[0].click().run(timeout=30)
                assert not ui.exception, ui.exception
                assert "INV-001" in ui.text_area[0].value
                ui.file_uploader[0].clear().run()
                assert not ui.text_area
                with httpx.Client(base_url="http://127.0.0.1:18000/api/v1", timeout=60) as api:
                    seeded = seed(api)
                    with pymupdf.open() as quote_pdf:
                        quote_pdf.new_page().insert_text(
                            (40, 50), quotation_examples()[0]["text"], fontsize=8
                        )
                        response = api.post(
                            "/documents", files={"file": ("Q-TERMS-001.pdf", quote_pdf.tobytes())}
                        )
                    response.raise_for_status()
                    quote_id = response.json()["id"]
                    response = api.post(f"/documents/{quote_id}/structure")
                    response.raise_for_status()
                ui.sidebar.radio[0].set_value("Quotes").run(timeout=30)
                ui.date_input[0].set_value(date(2026, 11, 26)).run()
                next(b for b in ui.button if b.label == "Assess quotation").click().run(timeout=30)
                assert not ui.exception, ui.exception
                assert any("Supported checks passed" in item.value for item in ui.success)
                for section in ("Documents", "Compare", "Policies", "Actions", "Operations"):
                    ui.sidebar.radio[0].set_value(section).run(timeout=30)
                    assert not ui.exception, (section, ui.exception)
                # Simulated approval/execution exercises durable jobs without authorizing real mail.
                with httpx.Client(base_url="http://127.0.0.1:18000/api/v1", timeout=60) as api:
                    action_id = seeded["action_id"]
                    action = api.get(f"/actions/{action_id}").json()
                    for path, extra in (
                        ("request-review", {}),
                        ("review", {"decision": "approve"}),
                    ):
                        response = api.post(
                            f"/actions/{action_id}/{path}",
                            json={"expected_version": action["version"], **extra},
                        )
                        response.raise_for_status()
                        action = response.json()
                    response = api.post(
                        f"/actions/{action_id}/execute",
                        json={"expected_version": action["version"]},
                    )
                    response.raise_for_status()
                    subprocess.run(
                        [sys.executable, "-m", "backend.worker", "--once"],
                        env=environment,
                        check=True,
                        creationflags=flags,
                        timeout=30,
                    )
                    job = api.get(response.json()["status_url"].removeprefix("/api/v1")).json()
                    assert job["data"]["result"]["provider"] == "simulated"
                    assert job["data"]["status"] == "succeeded"
                print(
                    "PASS: both servers, real HTTP extraction, "
                    "frontend upload/click/result/clear, seeded workspace screens, simulated worker"
                )
            finally:
                if previous_url is None:
                    os.environ.pop("VENDOROPS_BACKEND_URL", None)
                else:
                    os.environ["VENDOROPS_BACKEND_URL"] = previous_url
    finally:
        for process in processes:
            if os.name == "nt" and process.poll() is None:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=flags,
                    check=False,
                )
            elif process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        temporary.cleanup()


if __name__ == "__main__":
    main()
