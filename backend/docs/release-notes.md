# VendorOps AI — portfolio demo

**Version:** `v0.1.0-demo` · **Date:** November 28, 2026 · **Status:** prerelease

[Project overview](../../README.md) · [Watch the walkthrough](demo.md#recorded-walkthrough) ·
[Run locally](../../README.md#quick-start) · [Verification record](status.md)

This snapshot packages the working local vendor-document review application, its recorded
walkthrough, and the evidence collected from separate live AWS checks. It is a single-operator
portfolio demonstration. The complete live AWS workflow has not been verified.

## Included workflow

- Upload digital PDFs and run local Tesseract OCR on scanned pages.
- Review structured invoice, purchase-order, and quotation records; preserve corrections as revisions.
- Compare invoice quantities and prices using Python `Decimal` and inspect supporting evidence.
- Check quotation expiry, payment terms, stated taxes, taxable amounts, and arithmetic.
- Retrieve policy passages, confirm supported rules, and assess discrepancies against those rules.
- Edit a follow-up, approve its exact revision, and execute a simulated delivery through a durable worker.
- Inspect audit history and operational metrics; back up and restore the database and source files.

The source is organized into `backend/` and `frontend/`, with native setup instructions, Docker
Compose, synthetic examples, evaluation scripts, a learning workbook, and operations documentation.

## Demonstration and verification

The **2 minute 41 second MP4** follows three synthetic documents, two completed jobs, quotation
checks, and one approved simulated send. PDF parsing and OCR are real; AI responses are fixtures,
policy retrieval is lexical, and the scanned record is human-reviewed. The
[recording manifest](assets/demo-manifest.json) records the file checksum and provider modes.

Required GitHub checks cover Python tests, lint/formatting, dependency auditing, HTTP/frontend
smoke checks, offline evaluations, and the actual Linux Compose workflow. The AWS Guard job
publishes advisory findings; its success is not a compliance certification.

Separate live checks verified S3 uploads, download checksums, backup restoration, and test-resource
cleanup. One explicitly approved SES sandbox email reached Gmail's **Spam folder**. These component
checks do not establish model accuracy or completion of the full cloud pipeline.

## Remaining live-cloud work

- Obtain usable Bedrock quotas and measure real extraction and embedding/retrieval quality.
- Deploy and verify the private AWS host, including restart and recovery.
- Complete and record a single live end-to-end workflow after those gates pass.

All four applicable Sydney inference quotas were still zero after sign-in renewal. Mumbai's quota
reads were denied and Nova Lite lacked direct on-demand support there; Hyderabad was not opted in.
The [live verification record](live-verification.md) separates observations from unverified behavior.
The Free plan and Sydney configuration remain selected. Local OCR is the chosen scan path; live
calls and live sending are disabled by default.

## Boundaries

English documents, one currency per document, one selected PO per invoice, and one operator.
Quotation ranking, cumulative fulfilment accounting, payments, ERP updates, public signup, and
multiuser operations are outside this release. Unknown documents do not receive fabricated fixture
results. Customer-document accuracy and production security are not claimed.

Private documents, credentials, local configuration, raw AWS receipts, personal addresses, and
runtime databases are excluded from the published source.
