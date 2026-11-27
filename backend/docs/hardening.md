# Reliability and security hardening

[Project overview](../../README.md) · [Verification record](status.md) · [Live evidence](live-verification.md)

The November 28, 2026 pass strengthens the supported private, single-operator PoC. It does not certify
the application as production ready or establish live model accuracy. The application still requires
AWS quota resolution before its complete live workflow can run.

[Sanitized verification facts](evidence/hardening-2026-11-28.json) retain the observed results without
private documents, addresses, project identifiers, or credentials.

## Changes and evidence

| Area | Protection | Verification |
| --- | --- | --- |
| HTTP requests | Allowed hosts and browser origins; body-size limits before multipart/JSON parsing; bounded upload time; private responses use `no-store` | Declared-size, streamed-size, origin, host, and slow-body regression tests |
| PDFs | Page budget checked before text extraction; cumulative text budget on every PDF route | Tests prove over-budget PDFs never reach page text extraction or persistence |
| Business records | Bounded fields and line counts; whitespace-only identifiers rejected; unresolved source issues prevent automatic matching and clean reports | Validation and comparison regressions, including existing records needing correction |
| Policy rules | Finite decimal bounds prevent enormous exponent expansion; tolerance boundaries use exact multiplication | Adversarial numeric-input tests and deterministic policy tests |
| Models | Page labels count toward input limits; extraction, draft, and embedding calls reject oversized input before reserving usage | Provider-budget tests; AWS calls remain opt-in |
| Delivery | Intent persisted before sending; expired attempts become unknown; late results retained without overwriting reconciliation | Two-worker concurrency, uncertain-send, restart, and late-result tests |
| Workers and OCR | One task failure does not starve other job types; corrupt sources fail visibly; OCR text is bounded; Textract uses the SDK paginator | Worker isolation, OCR budget, multi-page provider, and real local OCR checks |
| Backups | Closed SQLite snapshot, per-file SHA-256 manifest, source-hash checks, staged publication, new-destination enforcement | Corrupt database/PDF, unexpected files, legacy format, failed backup, overlap, and in-flight restoration tests |
| Dependencies | Hash-verified Python 3.13 locks, dependency audit, weekly update configuration | Successful locked install, `pip check`, and no known findings in the follow-up local audit |
| Containers | Three non-root services; no extra capabilities; no privilege escalation; PID and memory bounds; loopback ports | CI checks actual API, SQLite retrieval, local Tesseract, and the separate worker |

Observed locally: **150 Python tests passed**, Ruff lint/formatting passed, and the real-server
frontend walkthrough passed. The runtime verifier also completed four documents, policy evidence,
a quotation assessment, real Tesseract OCR, and exactly one simulated delivery through a separate
worker, with zero paid calls. Actual Chrome screen checks and a 390px mobile layout check passed.
Linux container verification runs separately in CI.
GitHub dependency alerts, private vulnerability reporting, secret scanning, and push protection
were enabled and read back successfully. No paid GitHub feature was enabled.

## Chroma migration

The dependency audit reported unpatched ChromaDB advisories, including critical
[pre-authentication code injection](https://github.com/advisories/GHSA-f4j7-r4q5-qw2c) and
[collection-update code injection](https://github.com/advisories/GHSA-36p7-vc44-83pf). The checked
entries listed no patched version for the installed 1.5.9 release. The supported application now
uses its existing SQLite cosine retriever. The Chroma package and server were removed from installs
and Compose; legacy configuration returns a controlled migration error before model calls.

For an existing installation:

1. Back up existing application data.
2. Set `VENDOROPS_VECTOR_STORE=sqlite` in `backend/.env` and restart API/worker.
3. Uninstall `chromadb` from the project environment and install the checked locks below.
4. Rebuild active policy indexes from their stored chunks. Fixture and Titan vectors remain separate.
5. Stop any old Chroma container from an earlier deployment; preserve its old volume until migration
   is verified. New Compose runs only API, frontend, and worker.

SQLite retrieval scans the small stored corpus directly. It supports actual Titan embeddings when
AWS permits them; fixture embeddings remain lexical test plumbing.

## Reproduce the checks

Run from the repository root. Preserve an existing `.env`; the example defaults disable live calls.

```powershell
.\.venv\Scripts\python.exe -m pip install --require-hashes -r backend/requirements-lock.txt -r frontend/requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt -r frontend/requirements-dev.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pip_audit --local --strict
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m backend.scripts.smoke
```

The audit checks known published advisories, not all possible flaws. Its network-backed result can
change as advisories are published. CI fails on findings and uploads the report. It does not ignore
the Chroma advisories. Dependabot configuration requests weekly dependency and workflow updates.

For a new, empty fixture deployment with its worker running, use
`python -m backend.scripts.check_runtime`. It creates synthetic data and approves only a simulated
action. It refuses existing documents or enabled live flags. CI runs it inside the real backend
container and waits for the separately running worker, including local OCR.

Lock regeneration requires `uv`. Resolve backend first, then constrain frontend to shared versions:

```powershell
uv pip compile backend/requirements-cloud.txt --python-version 3.13 --universal --generate-hashes --no-annotate --output-file backend/requirements-lock.txt
uv pip compile frontend/requirements.txt --constraint backend/requirements-lock.txt --python-version 3.13 --universal --generate-hashes --no-annotate --output-file frontend/requirements-lock.txt
```

Review lock diffs, reinstall, audit, and rerun checks after updating. Deployment review digests bind
both locks, Dockerfiles, Compose files, and the selected release. Older deployment approvals cannot
silently authorize these changed runtime artifacts.

## Remaining release gates

| Gate | Current state and next evidence |
| --- | --- |
| Live inference and retrieval | A fresh read-only AWS check still reports five zero quotas. The project owner must resolve eligibility/quotas with AWS; the prepared private Support request lists exact quota codes. No inference was retried. |
| Held-out live accuracy | Run extraction, scanned-document, matching, and retrieval benchmarks after quotas are available. Fixture scores do not satisfy live targets. |
| Private EC2 deployment | Review the newly changed release and resource plan, deploy explicitly, then verify SSM access, actual-host restart, monitoring, and recovery. No host has been provisioned. |
| Email Inbox placement | The real SES email arrived in Spam. Aligned sender authentication needs a domain the owner controls and its DNS records; verified-address sandbox sending remains available. |
| Infrastructure assurance | Guard findings and missing durable CloudTrail/access logging remain documented in the [assessment](infrastructure-checks.md). They are not a clean compliance pass. |
| Customer/public use | Authentication, tenant separation, abuse controls, load tests, independent security review, and real-document evaluation require a separate hardening release. |

Local source files and backups rely on the operator's filesystem protections. Checksums detect
changed bytes, not a malicious actor rewriting the backup and its manifest. Native PDF/OCR processing
is not a hostile-file sandbox; the container limits bound processes but do not provide a formal
isolation guarantee. Keep the application private and use synthetic documents for this release.

## Learning checkpoint

Sketch the request boundary before FastAPI parsing, then trace a queued email from its committed
attempt through lease expiry and a late provider response. Explain why neither retrying an uncertain
send nor accepting a matching checksum proves the wider workflow is correct. In a disposable backup
copy, change one PDF byte and predict whether restore publishes its destination. Record the observed
result and your explanation in the [learning workbook](learning.md).
