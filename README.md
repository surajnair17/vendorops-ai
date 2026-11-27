<p align="center">
  <img src="backend/docs/assets/banner.svg" alt="VendorOps AI — vendor documents, clear decisions" width="100%">
</p>

<p align="center">
  <a href="https://github.com/surajnair17/vendorops-ai/actions/workflows/test.yml"><img src="https://github.com/surajnair17/vendorops-ai/actions/workflows/test.yml/badge.svg?branch=main" alt="Offline tests and container checks"></a>
  <img src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&amp;logoColor=white" alt="Python 3.13">
  <img src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&amp;logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&amp;logoColor=white" alt="Streamlit">
  <img src="https://img.shields.io/badge/Status-Portfolio_PoC-0f766e" alt="Portfolio proof of concept">
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> ·
  <a href="#see-it-in-action">Demo video</a> ·
  <a href="#how-it-works">Architecture</a> ·
  <a href="backend/docs/README.md">Documentation</a> ·
  <a href="backend/docs/learning.md">Learning workbook</a>
</p>

**Turn vendor PDFs into purchasing decisions you can review.**

VendorOps AI extracts document text, helps an operator review invoices and quotations, compares
invoices with purchase orders, and connects discrepancies to purchasing policies. Follow-up drafts
retain their evidence and require approval of the exact content before execution.

**Run the local demo without AWS credentials.** It uses synthetic documents, deterministic extraction
fixtures, local storage, and simulated email. Live services and real sending are disabled by default.

**Verified November 28, 2026:** [118 Python tests and four Guard runner checks](backend/docs/status.md),
a completed local browser walkthrough, and one approved **real SES email received in Gmail Spam**.
[Live verification](backend/docs/live-verification.md) separates these results from the blocked AI and deployment checks.

## What you can do

| Step | Capability |
| --- | --- |
| **Extract** | Read digital PDFs; request local Tesseract OCR for scanned pages. |
| **Review** | Inspect source text alongside validated fields; retain every correction as a revision. |
| **Assess quotes** | Review expiry and payment terms; check stated line totals, taxable amounts, tax, and totals. |
| **Compare** | Match an invoice to a purchase order and calculate differences with Python `Decimal`. |
| **Check policy** | Retrieve cited passages and apply only human-confirmed rules. |
| **Approve** | Edit a follow-up draft, approve its exact content, then explicitly execute delivery. |
| **Trace** | Inspect audit history, job outcomes, usage records, and evaluation results. |

Ambiguous matches require review. Editing a source document makes dependent reports stale;
editing an email invalidates its approval. An uncertain delivery outcome requires reconciliation.

## See it in action

[![Download the local demo: three documents, two completed jobs, and an approved simulated follow-up](backend/docs/assets/demo-preview.png)](https://github.com/surajnair17/vendorops-ai/raw/refs/heads/main/backend/docs/assets/vendorops-demo.mp4)

**[Download the full walkthrough · MP4 · 2 min 18 sec](https://github.com/surajnair17/vendorops-ai/raw/refs/heads/main/backend/docs/assets/vendorops-demo.mp4)**

Digital PDF → scanned-invoice OCR → reviewed fields → invoice/PO discrepancy → confirmed policy →
edited draft → approval → simulated delivery → quotation checks.

The recording uses **real PDF parsing and local Tesseract OCR**, **fixture AI extraction and lexical
retrieval**, and **simulated email**. The scanned invoice is explicitly saved as a human-reviewed
revision. It uses synthetic documents throughout. [Chapters and evidence](backend/docs/demo.md#recorded-walkthrough)
· [Reproduce the recording](frontend/README.md#record-an-end-to-end-walkthrough).

<details>
<summary><strong>Explore the application screens</strong></summary>

Digital PDF upload and text extraction:

![Actual local application extracting a synthetic invoice, with source text and document metrics](backend/docs/assets/extraction.png)

Source text and editable structured data, side by side:

![Document workspace showing a synthetic invoice and its structured extraction](backend/docs/assets/document-review.png)

Quotation dates, terms, tax, and arithmetic for the saved revision:

![Quotation review showing fixture provenance, validity, payment terms, and supported financial checks](backend/docs/assets/quotation-review.png)

Counts from the running local demonstration:

![Operational metrics showing fixture mode, three documents, and an unapproved draft](backend/docs/assets/operations.png)

</details>

The still screenshots use a separate seeded demo with an unapproved draft and no deliveries.
The video executes one approved simulated delivery. [Asset provenance](backend/docs/assets/README.md)
· [Reproduce the screenshots](frontend/README.md#preview-assets).

## Quick start

**Prerequisites:** Git and Python 3.13. Run all commands from the repository root. Docker is optional;
Tesseract is needed only for local OCR.

```bash
git clone https://github.com/surajnair17/vendorops-ai.git
cd vendorops-ai
```

<details open>
<summary><strong>Windows / PowerShell</strong></summary>

Create an environment and install the application and test dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt -r backend/requirements-cloud.txt -r frontend/requirements-dev.txt
Copy-Item backend/.env.example backend/.env
Copy-Item frontend/.env.example frontend/.env
```

Start these processes in **three separate terminals**, each at the repository root:

```powershell
# Terminal 1 — API
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

# Terminal 2 — application
.\.venv\Scripts\python.exe -m streamlit run frontend/app.py --server.address 127.0.0.1

# Terminal 3 — background jobs
.\.venv\Scripts\python.exe -m backend.worker
```

Explicit interpreter paths work without activating the environment or changing PowerShell policies.
Copy configuration files only on first setup; preserve an existing `.env`.

</details>

<details>
<summary><strong>macOS / Linux</strong></summary>

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt -r backend/requirements-cloud.txt -r frontend/requirements-dev.txt
cp -n backend/.env.example backend/.env
cp -n frontend/.env.example frontend/.env
```

In three separate terminals at the repository root:

```bash
# Terminal 1 — API
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

# Terminal 2 — application
.venv/bin/python -m streamlit run frontend/app.py --server.address 127.0.0.1

# Terminal 3 — background jobs
.venv/bin/python -m backend.worker
```

</details>

Open **[the application](http://localhost:8501)** or **[interactive API docs](http://127.0.0.1:8000/docs)**.
The worker processes OCR and approved delivery jobs. Press `Ctrl+C` in each terminal to stop.

### Try the guided demo

With the API running, open another terminal:

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.generate_samples
.\.venv\Scripts\python.exe -m backend.scripts.demo
```

On macOS/Linux, use `.venv/bin/python` in place of the Windows interpreter path.
Samples appear in `backend/artifacts/samples/`. The seeder creates a purchase order, an invoice with
a price difference, an inactive policy, an unconfirmed rule, and an **unapproved** email draft.
Follow **Documents → Compare → Policies → Actions**. See the [demo script](backend/docs/demo.md)
for a ten-minute walkthrough.

To capture the full flow as a captioned MP4, follow the
[browser recording instructions](frontend/README.md#record-an-end-to-end-walkthrough).

For quotation review, upload `backend/artifacts/samples/quotations/Q-TERMS-001.pdf` in Documents,
extract its fixture, then open **Quotes**. Set the assessment date to `2026-11-27` to check its
dates and amounts. Unfamiliar quotes can start with manually reviewed fields. See the
[quotation walkthrough](backend/docs/quotations.md) for supported formulas and limitations.

### Local OCR and containers

For native OCR, install Tesseract with English language data and set
`VENDOROPS_TESSERACT_COMMAND` in `backend/.env` to its executable path when it is not on `PATH`.
Store a scan in Documents, request OCR, and let the worker process it. On PDF Text, an image-only
upload offers **Read scanned PDF with local OCR**; this separate action saves a review copy and
shows the recognized text after refreshing job status. The **Extract Text** operation and its
stateless API still return `no_text` for an image-only document.

If Windows blocks a native Chroma dependency, set `VENDOROPS_VECTOR_STORE=sqlite` in
`backend/.env`. This uses exact cosine retrieval over vectors in SQLite for the small local corpus.
Rebuild existing policy indexes after switching backends. [Index design](backend/docs/architecture.md).

The backend container includes Tesseract. After creating `backend/.env`, an alternative local start is:

```bash
docker compose -f backend/infra/compose.yaml up --build -d
```

This starts the API, frontend, worker, and Chroma. See the [operations guide](backend/docs/operations.md)
for stop, backup, and restore commands. Container builds and startup are checked by Linux CI.

## How it works

```mermaid
flowchart LR
    A[PDF upload] --> B[Text extraction / local OCR]
    B --> C[Validated business record]
    C --> Q[Quotation dates and arithmetic]
    Q --> R[Revision-bound assessment]
    C --> D[Invoice and PO comparison]
    D --> E[Policy evidence + confirmed rules]
    E --> F[Review and email draft]
    F --> G[Approve exact revision]
    G --> H[Durable worker]
    H --> I[Simulated delivery]
```

| Layer | Technology | Responsibility |
| --- | --- | --- |
| Interface | Streamlit, HTTPX | Uploads, review screens, approvals, metrics |
| API | FastAPI, Pydantic | HTTP contracts, validation, workflow entry points |
| Documents | PyMuPDF, Tesseract | Digital text and local scanned-page OCR |
| Business logic | Python, `Decimal` | Matching, arithmetic, confirmed policy rules |
| Persistence | SQLite, SQLAlchemy | Revisioned records, audit events, durable jobs |
| Retrieval | Chroma or local SQLite cosine search | Policy passage retrieval with stored citations |
| Optional cloud adapters | Bedrock, Titan, S3, SES, Textract | Live extraction, embeddings, storage, email, cloud OCR |

Fixture extraction recognizes exact generated examples; it does not invent records for unknown
documents. Fixture retrieval checks offline plumbing; live semantic quality remains unmeasured.
See [architecture and decisions](backend/docs/architecture.md) for the boundaries.

## Repository map

Application source stays in two folders. Root files contain shared project and tooling settings.

<details>
<summary><strong>Explore backend/ and frontend/</strong></summary>

```text
vendorops-ai/
├── backend/
│   ├── main.py              # FastAPI entry point
│   ├── worker.py            # Durable background job runner
│   ├── routes/              # API endpoints by business capability
│   ├── schemas/             # Validated document and response contracts
│   ├── services/            # Extraction, comparison, policies, workflows
│   ├── migrations/          # Versioned SQLite schema
│   ├── tests/               # API, financial, workflow, and recovery checks
│   ├── scripts/             # Demo, sample generation, evaluation, backup
│   ├── docs/                # Documentation hub and presentation assets
│   └── infra/               # Docker Compose and deployment templates
├── frontend/
│   ├── app.py               # Navigation and entry point
│   ├── client.py            # HTTP boundary and readable error handling
│   ├── ui.py                # Shared visual shell
│   ├── views/               # One module per workspace screen
│   ├── assets/              # Shared presentation styles
│   ├── scripts/             # Browser screenshots and end-to-end recordings
│   └── tests/               # Streamlit checks
├── .github/                 # CI and contribution templates
├── AGENTS.md                # Coding-agent project instructions
├── pyproject.toml           # Shared pytest and Ruff configuration
└── README.md
```

Each application folder owns its dependencies, configuration example, Dockerfile, and README.
Runtime data, PDFs, credentials, local configuration, and generated reports are excluded from Git.

</details>

## Verification and current scope

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m backend.scripts.smoke
```

The smoke harness starts real servers, uploads a PDF through Streamlit, visits every workspace
screen, and exercises approved **simulated** delivery using an isolated database.
[Evaluation commands and methodology](backend/docs/evaluation.md) cover fixture, OCR, and live-result scoring.

| Area | Status |
| --- | --- |
| Local review workflow, comparisons, policies, simulated actions, audit, backup/restore | Implemented and tested |
| Local OCR | Tested on a small synthetic corpus; customer-scan accuracy is unverified |
| Quotation fields and deterministic assessments | Implemented locally; ranking and live extraction accuracy remain unverified |
| Bedrock extraction and Titan embeddings | Adapters and read-only preflight implemented; live attempts blocked by zero regional inference quotas |
| SES approval and delivery | One real approved send received in Gmail Spam; inbox placement failed |
| AWS deployment and storage | Templates and adapters implemented; host and live storage verification pending |
| Learning exercises and teach-back | Intended for the learner to complete |

This is a **single-company, single-operator portfolio PoC**. It supports English documents and one
currency per document. Public access, multiple tenants, payment execution, ERP integration, currency
conversion, and cumulative partial-invoice accounting are outside this release.
Read the [verification record](backend/docs/status.md) before interpreting benchmark claims.

**Current cloud blocker:** sign-in and model access were verified in `ap-southeast-2`, but applied
Nova Lite and Titan inference quotas were zero. Three runtime attempts were throttled. A read-only
preflight now blocks further live recordings before inference when quotas are unavailable. The
Free plan remains selected. [AWS setup and quota checks](backend/docs/aws-setup.md#5-verify-each-live-service-separately).
The live SES check and local restoration passed independently; neither establishes live model accuracy.

## Explore further

| I want to… | Start here |
| --- | --- |
| Find the right guide | [Documentation hub](backend/docs/README.md) |
| Understand the backend | [Backend guide](backend/README.md) |
| Work on a screen | [Frontend guide](frontend/README.md) |
| Learn while building | [Workbook](backend/docs/learning.md) · [Phase roadmap](backend/docs/roadmap.md) |
| Try the HTTP contract | [API examples](backend/docs/api.md) |
| Watch or run a portfolio walkthrough | [Download video](https://github.com/surajnair17/vendorops-ai/raw/refs/heads/main/backend/docs/assets/vendorops-demo.mp4) · [Demo guide](backend/docs/demo.md) |
| Prepare optional cloud verification | [AWS setup](backend/docs/aws-setup.md) · [Cost worksheet](backend/docs/costs.md) |
| Make a change | [Contributing](.github/CONTRIBUTING.md) |

Built by [Suraj Nair](https://github.com/surajnair17) as a practical Python backend and document-AI learning project.
