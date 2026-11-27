# Verification record — November 27, 2026

## Live attempt and regional quota blocker

- Renewed sign-in verified the expected project through `pixel-perfect` in `ap-southeast-2`.
  The Free Tier API confirmed the Free plan. Both selected models are active and regional
  on-demand models; the availability API reports authorized access and available entitlements.
- The live browser run made two Nova Lite extraction attempts and one Titan embedding attempt.
  All three returned `ThrottlingException`. No successful model response or token counts were
  returned. The run retained human-reviewed source revisions, then stopped because it had no
  retrieved policy evidence. Its partial recording is a failed live attempt, not a completed demo.
- Applied Nova Lite quotas are zero for tokens/minute (`L-70423BF8`), requests/minute
  (`L-E386A278`), and tokens/day (`L-45E0AD92`). Titan Text Embeddings V2 quotas are zero for
  tokens/minute (`L-DE641971`) and requests/minute (`L-26C560CE`). All five are reported as
  non-adjustable through Service Quotas. No positive on-demand inference quota was listed for
  another model in the selected Region. AWS Support must clarify or resolve this project limit;
  increasing the application's credit allowance does not change a zero inference quota.
- Stopped the recording's temporary processes and made no further runtime attempts. No cloud
  resources or support cases were created, no plan or IAM permissions were changed, and no real
  email was sent. Attempt records have unknown billing outcomes; charges are not independently
  verified. The successful offline recording below remains available separately.
- Added `python -m backend.scripts.check_bedrock` and a recorder preflight that checks identity,
  Free-plan status, model catalog/access, and applied regional quotas using read APIs only.
  Zero quotas now block filming before servers or paid calls start. Failed browser runs retain
  partial workflow provenance rather than only the final exception.
- Verification: the real read-only preflight confirmed all five zero quotas. All 104 local tests
  passed, including zero-quota blocking, identity mismatch, model authorization, sanitized read
  failures, and preventing recording processes from starting. Ruff lint and formatting passed.
  The optional recorder test is skipped where Playwright preview dependencies are not installed.

## End-to-end browser recording

- Recorded the actual application at 1440 × 1000, with chapter captions, synthetic inputs, and an
  isolated database. The 2 minute 18 second H.264 MP4 decoded successfully; sampled frames were
  inspected. The recording and its run receipt are local ignored artifacts.
- The completed flow uploaded a digital PDF, stored a PO, ran real Tesseract OCR on a scanned
  invoice, saved a human-reviewed invoice revision, detected the price variance, retrieved policy
  evidence, applied a confirmed rule, edited and approved a draft, executed one simulated delivery,
  assessed quotation terms and arithmetic, and displayed operations.
- The receipt confirms three documents, two successful jobs, a quotation assessment with
  `checks_passed`, one delivery attempt, and approval matching the sent content revision. All
  temporary recording processes stopped. No real email was sent.
- This run used fixture extraction and lexical embeddings; the scanned invoice was explicitly
  reviewed by a human because its OCR text did not match an exact fixture. No live AI accuracy is
  claimed. The approved local-run credit allowance is $10; AWS login remains required and no paid
  AWS calls have occurred.
- Added a repeatable browser recorder and an optional SQLite cosine index for small local policy
  collections. Windows Application Control blocks a native dependency imported by Chroma on this
  machine. The alternative needs no security-policy changes; Chroma remains the default elsewhere.
  Switching index backends requires reindexing. Operations shows the selected backend.
- Verification: 95 tests passed, including exact cosine retrieval, persistence, active-policy
  filtering, replacement, invalid vectors, and backend changes. The real-server HTTP/Streamlit
  smoke passed. The fixture retrieval benchmark returned the expected policy first for all five
  queries; this does not establish semantic retrieval quality.

## Quotation milestone

- Added optional quote expiry, payment terms, percentage tax rate, taxable amount, and line
  taxability. Populated values require source citations; possible identity placeholders and tax-rate
  evidence without a percent marker require review. Earlier records remain compatible.
- Added initial human-reviewed records for unknown fixture documents, with document-version and
  revision checks. Corrections preserve history and continue to display incomplete or unsupported
  fields. Manual entry does not claim model extraction.
- Added revision-bound quote assessments for expiry, date contradictions, line calculations,
  subtotal, stated tax, explicitly taxable line bases, and total. Missing operands skip checks and
  create review findings. Later corrections make saved assessments stale.
- Added a Quotes workspace, a separate synthetic commercial-terms PDF, and the
  [quotation walkthrough](quotations.md). The original 60-document benchmark is unchanged.
- Schema and extraction prompt metadata are version 2. Evaluation no longer hardcodes version 1
  or assumes current versions for saved historical outputs with missing provenance.
- Verification: 91 tests passed; Ruff lint and formatting passed; real-server HTTP/Streamlit smoke
  passed, including a quote assessment and simulated worker delivery. A headless Chrome check of
  the running application also created a successful assessment from the synthetic quotation.
  Existing fixture evaluation produced 60 valid records, 20 correct matches, and the 10 labelled
  discrepancies with no new findings. These remain fixture results, not live-model accuracy.
- The PDF Text screen's opt-in local OCR fix was published separately as `79b78d2`. Private input
  documents, OCR output, screenshots from those documents, configuration, and data remain ignored.
- Live model calls remain disabled pending a reviewed credit usage allowance. Quotation ranking,
  layout-aware OCR/confidence, and broader commercial assessment remain future work.
- Learning exercise and teach-back remain for the learner; see the quotation guide.

## Repository presentation

- The root overview includes a custom SVG banner, CI badge, actual application screenshots,
  a local-flow diagram, setup commands, and links to the documentation hub.
- Frontend screens are separated into `frontend/views/`; `app.py` handles navigation and
  `ui.py` loads the shared visual shell. HTTP and business-workflow boundaries are preserved.
- Screenshot capture uses isolated synthetic data, temporary servers, and disabled live flags.
  It approves no actions and sends no email. Browser capture and mobile layout checks are separate
  from Streamlit's automated smoke walkthrough.
- Application source remains in `backend/` and `frontend/`. Documentation lives in `backend/docs/`,
  and contribution templates and CI metadata live in `.github/`.
- Cleanup verification: 70 tests passed; Ruff lint/format checks and the real-server smoke passed.
  All 69 local documentation links/anchors resolved, documented endpoints matched OpenAPI, and
  the sample extraction response matched the parser. Desktop capture and a 390px viewport check
  passed. GitHub rendered the README successfully; the About description and topics were updated.

## AWS integration update

- The user chose an AWS Free plan with local OCR. Tesseract is now integrated through the durable
  worker, with time/page/raster limits, provenance, stale-result protection, and restart recovery.
  The Windows engine was installed and a real scanned-PDF upload/job test passed.
- The final 70-test suite passed including real local OCR and SDK request-shape checks for
  Converse, Titan, SES, and encrypted S3 upload. The real HTTP/Streamlit/simulated-worker smoke passed.
- Five held-out synthetic scans completed local OCR with zero failures and zero character errors
  across 1,120 reference characters after whitespace normalization. This small result does not
  establish performance on customer scans or live structured extraction accuracy.
- The separate all-scan benchmark completed all 20 synthetic scans with zero failures and zero
  whitespace-normalized character errors across 4,210 reference characters. Those results include
  development examples and must not be presented as a held-out benchmark.
- Added offline deployment planning, declared-credit allowance checks, read-only preflight, and
  explicit deployment bound to a reviewed plan digest. Bootstrap installs verified Compose, checks
  out a pinned public commit, starts containers, and signals CloudFormation readiness.
- Free-plan infrastructure uses t3.small and omits Textract/SNS/SQS by default. Regional Nova Lite
  replaces the cross-region profile; project resource Region and Bedrock API Region are configurable.
- GitHub Actions passed both offline tests and the infrastructure job, including real Linux
  container builds and backend/frontend startup checks, for commit `1c016a5`.
- AWS CLI v2.42.3 and uv 0.13.9 are installed locally using the official installers. The user
  selected profile `pixel-perfect`, the new AWS experience, and project Region `ap-southeast-2`.
  The application and deployment draft use this profile/Region; live flags remain disabled.
- Remote browser authorization completed and STS verified the selected project through profile
  `pixel-perfect`. Its ID is kept in the ignored local deployment record.
- Agent Toolkit installed 26 default skills and registered the AWS MCP entry without changing the
  existing TinyFish connection. Its remote catalog returned 132 skills. The named profile is set
  in `AWS_MCP_PROXY_PROFILES`. New-experience rules were added to root AGENTS.md with stable markers.
- Windows Application Control blocks the generated native proxy launcher. An equivalent Python
  module invocation connected successfully and listed all eight AWS tools without changing any
  Windows security setting. The user approved this exception to the setup guide's generated
  arguments, and the module launcher is now saved. All other Codex settings are preserved.
  After renewing the expired browser session, the saved configuration also connected and listed
  all eight AWS tools. Restart Codex to load them into the interactive session.
- No AWS deployment, live model call, S3 upload, or real email has been performed. Regional rates,
  remaining credits/allowance, and verified SES identities remain required before deployment.

See [AWS setup](aws-setup.md) for the reviewed deployment process and learning exercises.

## Local milestone

- Application source, dependencies, tests, environment examples, and Dockerfiles are separated into
  `backend/` and `frontend/`. Root files are shared repository/CI configuration.
- The earlier **49-test checkpoint** passed with Python 3.13.17 on Windows, covering PDF/API behavior, structured output,
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

- No successful AWS inference has completed. Three Bedrock runtime attempts were throttled;
  no paid OCR, S3, or SES operations have been attempted.
- No AWS resources have been provisioned; actual deployment and IAM access remain unverified.
- Docker is unavailable on this machine. The Linux CI container build/startup checks passed;
  deployment on the selected small AWS host remains unverified. AWS CLI is installed locally.
- No real email was delivered. SES stubs establish request shape; a verified inbox check is separate.
- Live extraction, semantic retrieval, OCR accuracy, processing costs, and release accuracy targets
  remain unmeasured. Saved outputs can be scored without calling paid services.
- No learning exercise or teach-back is completed on behalf of the user.

The bounded local demonstration has an agreed $10 allowance. Cloud deployment still needs a
reviewed resource plan, selected AWS project/subnet, verified SES identities, model access,
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
