"""Bounded, offline OCR. Tesseract runs as a subprocess without a shell or network."""

import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pymupdf

from backend import db
from backend.config import settings
from backend.errors import AppError


def require_tesseract() -> str:
    executable = shutil.which(settings.tesseract_command)
    if not executable:
        raise AppError(
            503,
            "local_ocr_unavailable",
            "Tesseract is not installed. Use the backend container or configure its executable.",
        )
    return executable


def recognize_pages(source: Path, original_pages: list[str]) -> list[list[str]]:
    executable = require_tesseract()
    pages = []
    with pymupdf.open(source) as document, TemporaryDirectory(prefix="vendorops-ocr-") as folder:
        if len(document) != len(original_pages) or len(document) > settings.max_document_pages:
            raise AppError(
                422, "ocr_page_mismatch", "The source exceeds or differs from its record."
            )
        for index, page in enumerate(document):
            if original_pages[index].strip():
                pages.append([])
                continue
            # Check dimensions before allocating a raster, including unusually large PDF pages.
            scale = 200 / 72
            if page.rect.width * page.rect.height * scale * scale > 20_000_000:
                raise AppError(413, "ocr_page_too_large", "A page exceeds the OCR raster limit.")
            raster = Path(folder) / "page.png"
            page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csGRAY).save(
                raster
            )
            try:
                result = subprocess.run(
                    [executable, str(raster), "stdout", "-l", "eng", "--psm", "3"],
                    capture_output=True,
                    timeout=settings.ocr_page_timeout_seconds,
                    check=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                    if hasattr(subprocess, "CREATE_NO_WINDOW")
                    else 0,
                )
            except subprocess.TimeoutExpired as error:
                raise AppError(
                    504, "ocr_timeout", "Local OCR exceeded its page time limit."
                ) from error
            except subprocess.CalledProcessError as error:
                raise AppError(422, "ocr_failed", "Tesseract could not process a page.") from error
            if len(result.stdout) > 1_000_000:
                raise AppError(413, "ocr_output_too_large", "OCR output exceeded the page limit.")
            pages.append(result.stdout.decode("utf-8", errors="replace").strip().splitlines())
    return pages


def process_local_ocr_once() -> bool:
    from backend.services.ocr import apply_ocr_result

    if settings.ocr_provider != "local":
        return False
    with db.transaction() as connection:
        jobs = [
            job
            for job in db.all_records(connection, "job")
            if job["data"].get("kind") == "ocr"
            and job["data"].get("provider") == "local"
            and (
                job["data"]["status"] == "queued"
                or job["data"]["status"] == "starting"
                and job["data"].get("lease_until", "") < db.now()
            )
        ]
        if not jobs:
            return False
        job = jobs[0]
        document = db.get(connection, job["data"]["document_id"], "document")
        if job["data"].get("start_attempts", 0) >= 3:
            db.update(
                connection,
                job,
                {**job["data"], "status": "failed", "error_code": "ocr_retry_limit"},
            )
            return True
        lease = settings.max_document_pages * settings.ocr_page_timeout_seconds + 60
        job = db.update(
            connection,
            job,
            {
                **job["data"],
                "status": "starting",
                "start_attempts": job["data"].get("start_attempts", 0) + 1,
                "lease_until": (datetime.now(UTC) + timedelta(seconds=lease)).isoformat(),
            },
        )
    try:
        pages = recognize_pages(Path(document["data"]["source"]), document["data"]["pages"])
    except (AppError, OSError) as error:
        with db.transaction() as connection:
            current = db.get(connection, job["id"], "job")
            db.update(
                connection,
                current,
                {
                    **current["data"],
                    "status": "failed",
                    "error_code": error.code
                    if isinstance(error, AppError)
                    else "ocr_source_unavailable",
                },
            )
            db.audit(connection, document["id"], "ocr_failed", {"job_id": job["id"]})
        return True
    apply_ocr_result(job["id"], pages, "SUCCEEDED", "tesseract")
    return True
