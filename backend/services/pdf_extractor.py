import pymupdf

from backend.config import settings
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
            if document.page_count > settings.max_document_pages:
                raise AppError(413, "too_many_pages", "Document exceeds the configured page limit.")
            pages, characters = [], 0
            for page in document:
                text = page.get_text(sort=True).strip()
                characters += len(text)
                if characters > settings.max_extracted_characters:
                    raise AppError(
                        413, "extracted_text_too_large", "PDF text exceeds the processing limit."
                    )
                pages.append(text)
            return pages
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
