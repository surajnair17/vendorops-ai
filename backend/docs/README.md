# Documentation

[← Project overview](../../README.md)

Choose a path based on what you want to do. All terminal commands assume the repository root.

## Run and explore

| Guide | What it covers |
| --- | --- |
| [Watch the demo](demo.md#recorded-walkthrough) | A captioned 2-minute local workflow, chapters, provider modes, and observed outcomes |
| [Quick start](../../README.md#quick-start) | Install dependencies, start the three processes, and seed a demo |
| [Guided demo](demo.md) | A ten-minute walkthrough using synthetic vendor documents |
| [Quotation review](quotations.md) | Commercial fields, manual entry, expiry checks, arithmetic, and limitations |
| [API examples](api.md) | Upload requests, response fields, error codes, and workflow endpoints |
| [Backend](../README.md) | API, services, persistence, scripts, and worker responsibilities |
| [Frontend](../../frontend/README.md) | Navigation, screen modules, screenshots, and the browser recorder |

## Understand and learn

For a first review, watch the demo, read the architecture, then inspect the verification record.
For development, start with the quick start and the backend/frontend guides.

| Guide | What it covers |
| --- | --- |
| [Architecture](architecture.md) | Data flow, service boundaries, and design decisions |
| [Learning workbook](learning.md) | Exercises, debugging prompts, and teach-back checkpoints |
| [Phase roadmap](roadmap.md) | Full development scope and remaining release gates |
| [Evaluation](evaluation.md) | Dataset splits, scoring, evidence, and fixture versus live results |
| [Verification record](status.md) | Observed results and what remains unverified |

## Operate and extend

| Guide | What it covers |
| --- | --- |
| [Operations](operations.md) | Start/stop, durable jobs, containers, backup, restore, and recovery |
| [AWS setup](aws-setup.md) | Optional private deployment and separate live-service checks |
| [Live verification](live-verification.md) | Actual S3 uploads/recovery/cleanup, SES delivery, sanitized evidence, and remaining AWS blockers |
| [Infrastructure checks](infrastructure-checks.md) | Reproduce AWS Guard validation and review its findings |
| [Cost worksheet](costs.md) | Hosting assumptions, service usage, and spending controls |
| [Contributing](../../.github/CONTRIBUTING.md) | Change boundaries, checks, and pull requests |

Start with the local fixture demo. A passing fixture evaluation verifies known responses and
workflow behavior; it does not establish model accuracy. Separate real S3 recovery and SES delivery
checks passed, with the email in Spam; host deployment and live AI remain incomplete. Screenshots
use synthetic data; see [asset provenance](assets/README.md).
