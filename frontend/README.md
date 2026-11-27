# Frontend

[← Project overview](../README.md) · [Documentation](../backend/docs/README.md)

Streamlit displays extraction, document review, comparisons, policies, actions, and metrics.
It communicates through HTTP only and never imports backend logic or opens the database.

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m streamlit run frontend/app.py --server.address 127.0.0.1
.\.venv\Scripts\python.exe -m pytest frontend/tests -q
```

Copy .env.example to .env in this folder. It configures VENDOROPS_BACKEND_URL and the request
timeout. Dependencies and the Dockerfile are separate from the backend.

## Module map

| Path | Responsibility |
| --- | --- |
| `app.py` | Entry point, navigation, and screen selection |
| `client.py` | HTTP requests and readable backend errors |
| `ui.py` | Shared header, sidebar branding, and style loading |
| `assets/style.css` | Visual presentation with responsive cards and native theme support |
| `views/extract.py` | Stateless text extraction and a separate opt-in local OCR action for scans |
| `views/documents.py` | Persistent documents, OCR requests, revisions, and corrections |
| `views/quotations.py` | Expiry, payment terms, financial checks, and revision-bound quotation assessments |
| `views/comparisons.py` | Invoice/PO selection, findings, and policy assessments |
| `views/policies.py` | Policy versions and confirmed rule management |
| `views/actions.py` | Drafts, approvals, execution, reconciliation, and history |
| `views/operations.py` | Provider mode, job outcomes, action states, and usage |

Each screen exposes `render()`. The UI retains native Streamlit controls and focus indicators.
Styling does not change approval rules, delivery mode, or provider configuration.
Structured fields currently use validated JSON editing, a transparent learning interface that
can later become a customer-friendly form.

Documents without a usable model result also offer **Save initial reviewed record**. This manual
path records provider `human` and preserves unknown values. The **Quotes** screen assesses the
saved revision without AI calls; see [quotation review](../backend/docs/quotations.md).

## Preview assets

The root README uses actual browser screenshots of an isolated local demo. After installing the
full development environment from the root quick start, install the optional preview dependency:

```powershell
.\.venv\Scripts\python.exe -m pip install -r frontend/requirements-preview.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m frontend.scripts.capture_demo
```

If Google Chrome is already installed, skip the browser download and use
`python -m frontend.scripts.capture_demo --channel chrome` with the project interpreter.
Use `.venv/bin/python` on macOS/Linux.

The script starts temporary API and frontend processes on available local ports, seeds synthetic
documents over HTTP, uploads an invoice through the browser, and captures three desktop screens.
It also checks the mobile layout. It creates no approvals or deliveries, disables live calls,
uses temporary storage, and stops its own processes afterward. Output goes to
`backend/docs/assets/`; review images before committing them. Browser tooling is optional and is
not installed in the application container.

## Record an end-to-end walkthrough

With the optional preview dependencies and Chrome installed, run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m frontend.scripts.record_demo --output backend/artifacts/recordings/my-demo --as-of 2026-11-27 --provider fixture
```

Choose a new output directory each time. The recorder launches isolated API, Streamlit, and worker
processes, then drives the actual browser: digital upload, scanned-invoice OCR, reviewed fields,
invoice/PO comparison, policy activation and rule confirmation, draft editing, approval, simulated
delivery, quotation checks, and operations. Tesseract must be installed and configured for local OCR.
Unknown fixture OCR output is explicitly corrected as a human revision using the synthetic source.

Outputs include a captioned WebM, an H.264 MP4, and `receipt.json` containing the actual outcomes and
provider provenance. Temporary servers stop when the run ends; generated data remains in the output
directory for inspection and is ignored by Git. Failed runs retain a screenshot and partial WebM;
they are not successful demonstrations. The recording contains no microphone audio.

The recorder always uses local storage, local OCR, a SQLite cosine index, and simulated email. It
creates no AWS infrastructure and never enables SES. `--provider bedrock --allowance 10` enables paid
Nova/Titan calls only inside its child processes, using `pixel-perfect` in `ap-southeast-2`. Use that
option only after reviewing current pricing, confirming the Free plan and selected project, and
authorizing the allowance. A read-only preflight checks model access and applied inference quotas
before starting servers; a zero or unreadable quota blocks recording without invoking a model.
The allowance argument is a configuration check, not a billing cap.
Inspect the receipt: a live provider setting alone does not prove extraction accuracy or successful
inference. Application defaults remain offline.
