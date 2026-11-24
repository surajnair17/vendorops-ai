import hashlib
from uuid import uuid4

from fastapi import APIRouter, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from backend import db
from backend.config import settings
from backend.errors import AppError
from backend.routes.documents import read_pdf_upload
from backend.schemas.business import BusinessDocument, issues_for, source_issues
from backend.services.pdf_extractor import extract_pages
from backend.services.structured import extract_structure

router = APIRouter(prefix="/api/v1", tags=["records"])


def persist_document(filename: str, content: bytes) -> dict:
    pages = extract_pages(content)
    if len(pages) > settings.max_document_pages:
        raise AppError(413, "too_many_pages", "Document exceeds the configured page limit.")
    digest = hashlib.sha256(content).hexdigest()
    identifier = str(uuid4())
    source = settings.data_dir / "sources" / f"{identifier}.pdf"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(content)
    try:
        s3_key = None
        if settings.storage_mode == "s3":
            from backend.services.cloud import put_source

            s3_key = put_source(identifier, content)
        with db.transaction() as connection:
            duplicates = [
                row["id"]
                for row in db.all_records(connection, "document")
                if row["data"]["sha256"] == digest
            ]
            record = db.create(
                connection,
                "document",
                {
                    "filename": filename,
                    "sha256": digest,
                    "pages": pages,
                    "page_count": len(pages),
                    "source": str(source.resolve()),
                    "duplicate_of": duplicates,
                    "revision_id": None,
                    "ocr_status": "not_requested",
                    "s3_key": s3_key,
                },
                identifier,
            )
            db.audit(connection, identifier, "document_uploaded")
            return record
    except Exception:
        source.unlink(missing_ok=True)
        raise


@router.post("/documents", status_code=201)
async def upload_document(file: UploadFile):
    filename, content = await read_pdf_upload(file)
    return await run_in_threadpool(persist_document, filename, content)


@router.get("/documents")
def list_documents():
    with db.transaction() as connection:
        result = []
        for document in db.all_records(connection, "document"):
            structured = None
            if document["data"]["revision_id"]:
                revision = db.get(connection, document["data"]["revision_id"], "revision")
                structured = revision["data"]["structured"]
            result.append(
                {
                    **document,
                    "summary": {
                        "document_type": structured.get("document_type") if structured else None,
                        "document_number": structured.get("document_number")
                        if structured
                        else None,
                    },
                }
            )
        return result


@router.get("/documents/{identifier}/source")
def source_document(identifier: str):
    with db.transaction() as connection:
        document = db.get(connection, identifier, "document")
    return FileResponse(
        document["data"]["source"],
        media_type="application/pdf",
        filename=document["data"]["filename"],
    )


@router.get("/documents/{identifier}")
def read_document(identifier: str):
    with db.transaction() as connection:
        document = db.get(connection, identifier, "document")
        revisions = [
            r
            for r in db.all_records(connection, "revision")
            if r["data"]["document_id"] == identifier
        ]
        attempts = [
            r
            for r in db.all_records(connection, "extraction_attempt")
            if r["data"]["document_id"] == identifier
        ]
        return {**document, "revisions": revisions, "extraction_attempts": attempts}


@router.post("/documents/{identifier}/structure")
def structure_document(identifier: str):
    with db.transaction() as connection:
        document = db.get(connection, identifier, "document")
    try:
        result = extract_structure(
            "\n\n".join(document["data"]["pages"]), document["data"]["pages"]
        )
    except AppError as error:
        with db.transaction() as connection:
            db.create(
                connection,
                "extraction_attempt",
                {
                    "document_id": identifier,
                    "document_version": document["version"],
                    "provider": settings.provider,
                    "status": "failed",
                    "error_code": error.code,
                },
            )
            db.audit(connection, identifier, "extraction_failed", {"code": error.code})
        raise
    with db.transaction() as connection:
        current = db.get(connection, identifier, "document")
        if current["version"] != document["version"]:
            raise AppError(409, "stale_document", "Document changed during extraction.")
        revision = db.create(
            connection,
            "revision",
            {
                **result,
                "document_id": identifier,
                "origin": "model",
                "parent_id": None,
            },
        )
        db.create(
            connection,
            "extraction_attempt",
            {
                "document_id": identifier,
                "revision_id": revision["id"],
                "provider": result["provider"],
                "attempts": result["attempts"],
                "issues": result["issues"],
                "status": "completed",
            },
        )
        db.update(connection, current, {**current["data"], "revision_id": revision["id"]})
        db.audit(connection, identifier, "structured", {"revision_id": revision["id"]})
        return revision


class Correction(BaseModel):
    expected_revision_id: str
    structured: BusinessDocument


@router.patch("/documents/{identifier}/structured-data")
def correct_document(identifier: str, correction: Correction):
    with db.transaction() as connection:
        document = db.get(connection, identifier, "document")
        if document["data"]["revision_id"] != correction.expected_revision_id:
            raise AppError(409, "stale_revision", "Reload the document before saving corrections.")
        issues = issues_for(correction.structured) + source_issues(
            correction.structured, document["data"]["pages"]
        )
        revision = db.create(
            connection,
            "revision",
            {
                "document_id": identifier,
                "structured": correction.structured.model_dump(mode="json"),
                "issues": issues,
                "provider": "human",
                "origin": "human",
                "review_status": "needs_review" if issues else "ready",
                "parent_id": correction.expected_revision_id,
            },
        )
        db.update(connection, document, {**document["data"], "revision_id": revision["id"]})
        db.audit(connection, identifier, "corrected", {"revision_id": revision["id"]})
        return revision
