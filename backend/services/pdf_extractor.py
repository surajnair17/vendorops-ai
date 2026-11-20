import pymupdf

from backend.errors import AppError
from backend.schemas.documents import ExtractionResponse


def extract_pages(content: bytes) -> list[str]:
    """Parse actual PDF bytes, returning text in page order without retaining the file."""
    if not content:
        raise AppError(400, "empty_upload", "The uploaded file is empty.")
    if not content.lstrip().startswith(b"%PDF-"):
        raise AppError(415, "unsupported_content", "The uploaded content is not a PDF.")
    try:
        with pymupdf.open(stream=content, filetype="pdf") as document:
            if document.needs_pass:
                raise AppError(422, "encrypted_pdf", "Password-protected PDFs are not supported.")
            if not document.page_count:
                raise AppError(400, "empty_pdf", "The PDF has no pages.")
            return [page.get_text(sort=True).strip() for page in document]
    except AppError:
        raise
    except (pymupdf.FileDataError, RuntimeError, ValueError) as error:
        raise AppError(
            400, "corrupt_pdf", "The PDF could not be read. It may be corrupted."
        ) from error


def extract_pdf(content: bytes, filename: str) -> ExtractionResponse:
    pages = extract_pages(content)
    meaningful = any(any(character.isalnum() for character in page) for page in pages)
    text = "\n\n\f\n\n".join(pages) if meaningful else ""
    return ExtractionResponse(
        filename=filename,
        page_count=len(pages),
        extracted_text=text,
        character_count=len(text),
        extraction_status="success" if meaningful else "no_text",
        message=(
            "Text extracted successfully."
            if meaningful
            else "No meaningful text was found. The PDF may be scanned or blank; "
            "OCR is not supported by this endpoint."
        ),
    )
