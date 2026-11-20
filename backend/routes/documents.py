from pathlib import PurePosixPath

from fastapi import APIRouter, UploadFile
from starlette.concurrency import run_in_threadpool

from backend.config import settings
from backend.errors import AppError
from backend.schemas.documents import ExtractionResponse
from backend.services.pdf_extractor import extract_pdf

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


async def read_pdf_upload(file: UploadFile) -> tuple[str, bytes]:
    filename = PurePosixPath((file.filename or "document.pdf").replace("\\", "/")).name
    try:
        if not filename.lower().endswith(".pdf"):
            raise AppError(415, "unsupported_file_type", "Upload a file with the .pdf extension.")
        content = bytearray()
        while chunk := await file.read(min(65536, settings.max_upload_bytes + 1 - len(content))):
            content.extend(chunk)
            if len(content) > settings.max_upload_bytes:
                raise AppError(
                    413, "upload_too_large", "The PDF exceeds the configured size limit."
                )
        return filename, bytes(content)
    finally:
        await file.close()


@router.post("/extract", response_model=ExtractionResponse)
async def extract_document(file: UploadFile) -> ExtractionResponse:
    filename, content = await read_pdf_upload(file)
    return await run_in_threadpool(extract_pdf, content, filename)
