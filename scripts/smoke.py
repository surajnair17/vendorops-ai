"""Launch both applications, exercise real HTTP, and shut down only our child processes."""

import os
import subprocess
import sys
import time

import httpx
import pymupdf


def main() -> None:
    processes = []
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
            print("PASS: backend health, Streamlit health, real multipart HTTP extraction")
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
