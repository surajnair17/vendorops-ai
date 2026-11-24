# VendorOps AI

A single-company portfolio application for vendor document review, built as a guided learning project.
Use synthetic documents. Live AWS calls and real email sending are **disabled by default**.

## Project layout

```text
backend/
  routes/ services/ schemas/  FastAPI and business logic
  migrations/                SQLite schema migrations
  tests/                     Backend and workflow tests
  scripts/                   Samples, evaluation, demo, backup, smoke checks
  docs/                      Learning, architecture, operations, verification
  infra/                     Compose and CloudFormation
  requirements*.txt          Backend and optional cloud dependencies
  .env.example               Backend configuration
  Dockerfile                 Backend/worker container
frontend/
  app.py client.py workspace.py
  tests/                     Streamlit tests
  requirements*.txt          Frontend dependencies
  .env.example               HTTP connection settings
  Dockerfile                 Frontend container
```

Shared Git/CI metadata, this README, and lint/test configuration stay at the root.
Generated data and artifacts live inside backend/ and are ignored by Git.
The local shared .venv is a development tool, not application source.

## Run locally

Python 3.13 is tested. Run commands **from the repository root**:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt -r backend/requirements-cloud.txt -r frontend/requirements-dev.txt
Copy-Item backend/.env.example backend/.env
Copy-Item frontend/.env.example frontend/.env
```

Start each process in a separate terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe -m streamlit run frontend/app.py --server.address 127.0.0.1
.\.venv\Scripts\python.exe -m backend.worker
```

Open http://localhost:8501. API documentation: http://127.0.0.1:8000/docs.
Activation is optional: explicit interpreter paths avoid PowerShell execution-policy changes.

Generate examples and create an **unapproved** demonstration draft:

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.generate_samples
.\.venv\Scripts\python.exe -m backend.scripts.demo
```

Samples are in backend/artifacts/samples. Use Documents, Compare, Policies, and Actions in
Streamlit. The demo never approves or sends email. Review, approval, and execution are separate.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m backend.scripts.smoke
.\.venv\Scripts\python.exe -m backend.scripts.evaluate
.\.venv\Scripts\python.exe -m backend.scripts.evaluate_retrieval
```

The smoke test uses temporary servers and a separate database. Fixture evaluation scores verify
known responses and deterministic logic; they do not establish real model accuracy.

## Capability and limits

Implemented locally: PDF extraction, exact synthetic extraction fixtures, revisioned corrections,
matching, decimal comparisons, Chroma retrieval, confirmed rules, approval-bound drafts,
durable simulated delivery, audit history, backup/restore, and an evaluation harness.

Prepared for live verification: Bedrock, Titan, S3, asynchronous Textract/SNS/SQS, SES, EC2, and
CloudWatch. Deployment, live OCR/model accuracy, inbox delivery, and cloud costs are not claimed
as verified. Read [verification status](backend/docs/status.md) and
[operations](backend/docs/operations.md).
The [demo guide](backend/docs/demo.md) and [evaluation guide](backend/docs/evaluation.md) explain
the complete local walkthrough and the separate live verification gates.

## Compatible Phase 1 API

```powershell
curl.exe -F "file=@invoice.pdf" http://127.0.0.1:8000/api/v1/documents/extract
```

```json
{"filename":"invoice.pdf","page_count":1,"extracted_text":"Invoice INV-001","character_count":15,"extraction_status":"success","message":"Text extracted successfully."}
```

This endpoint retains no uploads. The default limit is 10 MiB (10,485,760 bytes).
Blank/scanned PDFs return no_text. Persistent review uses POST /api/v1/documents.

## Learn the code

Follow [the workbook](backend/docs/learning.md) and [roadmap](backend/docs/roadmap.md). Trace:

User → Streamlit → HTTP POST → FastAPI → PyMuPDF → Pydantic response → JSON → Streamlit.

PyMuPDF reads text, OCR reads images, an LLM interprets text, retrieval finds policies, and Python
calculates differences. Learner exercises and teach-back remain for you to complete.
