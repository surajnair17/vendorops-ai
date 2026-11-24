# Verification record — November 24, 2026

## Local milestone

- Application source, dependencies, tests, environment examples, and Dockerfiles are separated into
  `backend/` and `frontend/`. Root files are shared repository/CI configuration.
- **49 tests passed** with Python 3.13.17 on Windows, covering PDF/API behavior, structured output,
  revisions, matching, financial comparisons, policy evidence/rules, approvals, concurrent workers,
  uncertain delivery, bounded OCR retries with stubs, backup/restore, and evaluation scoring.
- Ruff lint and formatting checks pass. Git whitespace checks pass.
- The smoke harness started actual API/Streamlit processes, uploaded through Streamlit's test
  uploader, clicked extraction, verified and cleared displayed results, seeded a reviewable demo,
  visited all screens, and processed one approved **simulated** delivery with a separate worker.
  Temporary processes and data were cleaned up successfully. This is automated frontend testing,
  not a claim of manual browser review.
- CloudFormation passed cfn-lint through `python -m backend.scripts.validate_infra`.
- Offline corpus: 60 digital PDFs, 20 scanned variants, five policies/queries, and adversarial files.
  Exact fixtures produced 60 valid structured outputs, correct header/line fields and source quotes,
  20 correct automatic matches, and the 10 labelled price variances without extra findings.
- Lexical fixture retrieval returned the expected policy first for all five queries. Its recall@5
  is weak evidence on a five-policy corpus. It does not measure Titan's semantic quality.

Commands:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m backend.scripts.smoke
.\.venv\Scripts\python.exe -m backend.scripts.generate_samples
.\.venv\Scripts\python.exe -m backend.scripts.evaluate
.\.venv\Scripts\python.exe -m backend.scripts.evaluate_retrieval
.\.venv\Scripts\python.exe -m backend.scripts.validate_infra
```

Reproducible benchmark JSON is generated under the ignored `backend/artifacts/` directory. See
[evaluation methodology](evaluation.md), [demo steps](demo.md), and [operations](operations.md).

## Remaining gates

- No paid AWS model, embedding, OCR, S3, or SES calls have been made.
- No AWS resources have been provisioned; actual deployment and IAM access remain unverified.
- Docker and AWS CLI are unavailable on this machine. Dockerfile/Compose runtime behavior still
  requires Docker. CI contains Compose and infrastructure checks, but has not been run on GitHub.
- No real email was delivered. SES stubs establish request shape; a verified inbox check is separate.
- Live extraction, semantic retrieval, OCR accuracy, processing costs, and release accuracy targets
  remain unmeasured. Saved outputs can be scored without calling paid services.
- No learning exercise or teach-back is completed on behalf of the user.

Live work needs an agreed budget, selected AWS account/subnet, verified SES identities, model access,
and the deployment checklist. Both live flags stay disabled by default. The small corpus and
single-operator design establish a portfolio PoC, not readiness for real customer data.

## Environment and decisions

Windows application control initially blocked SQLAlchemy's optional native extension. The supported
pure-Python build was installed; no application-control policy was changed. If the same import
error occurs in a fresh environment:

```powershell
$env:DISABLE_SQLALCHEMY_CEXT = '1'
.\.venv\Scripts\python.exe -m pip install --force-reinstall --no-binary SQLAlchemy 'SQLAlchemy>=2.0,<3'
```

SQLite snapshots keep revision history inspectable for learning. Write transactions serialize
approval/job claims; concurrent-worker tests verify one send per queued job. Restoring an old backup
marks pending sends unknown and forces index rebuilding. Failed provider attempts stay in the usage
ledger. See [architecture](architecture.md) for the responsibilities and limitations of each layer.
