# VendorOps AI

A learning-first vendor document intelligence project for a single-company portfolio demo.
Build and verify one milestone before proceeding to the next. Use synthetic documents only.

## Current milestone: PDF text extraction

FastAPI accepts a digital PDF, validates its contents, and uses PyMuPDF to extract text.
Streamlit sends the file over HTTP and displays the result. This endpoint does not retain uploads.
Scanned and blank PDFs return `no_text`; they do not trigger OCR or a paid service.

## Setup on Windows / PowerShell

Python 3.13 is the tested interpreter. Run commands from the repository root.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Optional activation: `.\.venv\Scripts\Activate.ps1`. Activation changes which Python the
terminal finds; it does not install anything. The explicit interpreter commands below also work
without activation or an execution-policy change. Pip installs dependencies into this environment.

Start the backend in one terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Start the frontend in another terminal:

```powershell
.\.venv\Scripts\python.exe -m streamlit run frontend/app.py --server.address 127.0.0.1
```

Open http://localhost:8501. API documentation: http://127.0.0.1:8000/docs.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
curl.exe -F "file=@invoice.pdf" http://127.0.0.1:8000/api/v1/documents/extract
```

Example response (text depends on the PDF):

```json
{
  "filename": "invoice.pdf",
  "page_count": 1,
  "extracted_text": "Invoice INV-001",
  "character_count": 15,
  "extraction_status": "success",
  "message": "Text extracted successfully."
}
```

The default file-size limit is **10 MiB = 10,485,760 bytes**. Configure
`VENDOROPS_MAX_UPLOAD_BYTES` in `.env`. The backend validates actual content; changing a filename
to `.pdf` does not make it a PDF. Errors have the shape
`{"error":{"code":"empty_upload","message":"The uploaded file is empty."}}`.
Missing input returns 422, empty/corrupt PDFs 400, unsupported files 415, oversized files 413,
password-protected PDFs 422, and unexpected failures a generic 500.

## How a PDF travels through the code

1. Streamlit collects bytes from the browser and sends a multipart HTTP POST request.
2. FastAPI routes that request to `backend/routes/documents.py`.
3. `read_pdf_upload` reads at most the limit plus one byte, validates the extension, and closes
   the uploaded file. Temporary framework spool files are not retained.
4. `extract_pages` opens the actual bytes with PyMuPDF and reads every page.
5. `extract_pdf` constructs a Pydantic response. Page boundaries use a form-feed separator.
6. FastAPI serializes the response to JSON. Streamlit displays the response over HTTP.

An HTTP POST sends input to a server for processing. Pydantic defines the shape of data at the
boundary. PyMuPDF reads PDF text; it does not interpret invoice semantics. OCR reads images, and an
LLM interprets text; neither is needed to read an existing digital text layer.

## Roadmap and learning

| Phase | Outcome | Main lesson |
|---|---|---|
| 0 | Environment, Git, repeatable setup | Interpreters and dependencies |
| 1 | PDF extraction | HTTP, validation, exceptions, tests |
| 2 | Structured records and corrections | Schemas, persistence, model boundaries |
| 3 | Matching and discrepancy reports | Decimal arithmetic and deterministic logic |
| 4 | Policy evidence and confirmed rules | Retrieval versus decision making |
| 5 | Review, approval, simulated email | State machines and idempotency |
| 6 | AWS, OCR, approved SES delivery | IAM, jobs, costs, recovery |
| 7 | Evaluation and guided PoC | Honest measurement and communication |

Read [the learning workbook](docs/learning.md). Each phase requires test evidence and your own
teach-back before it counts as a completed learning milestone. AWS spending and real email
delivery remain disabled until their separate configuration and approval requirements are met.

## Limitations

Text extraction order can differ from visual layout, especially in complex tables. An empty
text layer is only a signal that OCR may help, not proof of a scanned document. The application
is for a private, single-operator synthetic demonstration, not public untrusted uploads or real
customer data. File size limits alone do not bound PDF decompression or processing complexity.
