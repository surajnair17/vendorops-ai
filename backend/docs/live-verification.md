# Live integration verification

[Project overview](../../README.md) · [Verification record](status.md) · [AWS setup](aws-setup.md)

On November 28, 2026 (Asia/Kolkata), one synthetic approval-to-SES workflow completed against real
AWS services in `ap-southeast-2`. The message reached the verified owner's **Spam folder**, not the
Inbox. Live structured extraction and semantic retrieval remain blocked by zero inference quotas.
This is component verification; the full live cloud release is incomplete.

The [sanitized result](evidence/live-verification-2026-11-28.json) records observed outcomes without
personal addresses, project IDs, message IDs, credentials, or private document contents.

## What actually ran

| Stage | Execution and observed result |
| --- | --- |
| Source documents | Two synthetic digital PDFs, parsed with PyMuPDF and stored locally |
| Structured records | Known fixture responses, schema validation, and saved revisions; no successful live model response |
| Comparison | Real Python arithmetic produced a report bound to the source revisions |
| Draft review | The exact displayed test draft was approved; approval matched content revision 2 |
| Approval and execution | Real application API routes through an in-process FastAPI client, followed by the durable worker |
| SES | Real sandbox send, one approval and one delivery attempt; SES accepted the message |
| Mailbox | Read-only Gmail inspection matched the provider message ID and confirmed arrival in Spam |
| Worker restart | A second worker pass found no work; the approved action was not sent again |
| Recovery | Consistent SQLite/source backup restored into a new directory; both PDFs and the sent action survived |
| After the check | Live-call and live-send flags disabled; no automatic resend |

The test email described the integration check, disclosed the blocked AI stage, contained no customer
data, and requested no purchasing or payment action. Policy retrieval was tested in the separate local
walkthrough; this SES test does not establish live retrieval quality.

## Delivery result and remaining email work

The receiving headers reported SPF and DKIM passes for the SES sending domain, but DMARC failure
for the Gmail From domain. The application owner can verify an individual Gmail address in SES but
does not control Gmail's domain DNS. Failed domain alignment is a limitation of this test identity;
it is not evidence of the sole reason Gmail selected Spam.

For a stronger delivery demonstration, use a sender domain the owner controls, configure aligned
DKIM and, where appropriate, a custom MAIL FROM domain, then approve a new test explicitly. AWS
documents the required alignment in its [SES DMARC guide](https://docs.aws.amazon.com/ses/latest/dg/send-email-authentication-dmarc.html).
No domain was purchased, no mailbox message was moved, and no second email was sent.

## AWS limits preventing full completion

Read-only checks confirmed the Free plan, expected project, Sydney Region, active model catalog
entries, and authorized model access. The applied quotas below were all zero and non-adjustable
through Service Quotas:

| Model | Quota | Code | Applied value |
| --- | --- | --- | ---: |
| Nova Lite | Tokens per minute | `L-70423BF8` | 0 |
| Nova Lite | Requests per minute | `L-E386A278` | 0 |
| Nova Lite | Tokens per day | `L-45E0AD92` | 0 |
| Titan Text Embeddings V2 | Tokens per minute | `L-DE641971` | 0 |
| Titan Text Embeddings V2 | Requests per minute | `L-26C560CE` | 0 |

The earlier two Nova attempts and one Titan attempt were throttled. This check made no further
runtime inference calls. Raising the local $10 allowance cannot change an AWS quota. A private
Support request has been prepared for the project owner; it has not been submitted on their behalf.
The project remains on the Free plan with no cross-Region inference.

## Storage and deployment gates

An isolated S3-only change set is prepared for review: one private, versioned, AES256-encrypted bucket
and its HTTPS-only policy. It contains no EC2 or inference resources. Local cfn-lint passed, the change
set reached `CREATE_COMPLETE`, and scoped CloudFormation validation reported no errors.

Guard reports two advisory findings: missing S3 access logging and its existing limitation recognizing
the template's valid string-valued HTTPS condition. No durable CloudTrail trail was found, so durable
audit logging has not been verified. The change set has **not been executed**; no bucket or host has
been provisioned. The empty review stack and exact private plan remain pending the owner's approval
and cleanup choice. See the [infrastructure assessment](infrastructure-checks.md) for rule context.

Remaining release evidence:

- Resolve the inference quotas, then measure actual extraction and retrieval on held-out examples.
- Complete approved S3 upload, checksum, cloud backup/download, restoration, and cleanup checks.
- Review and explicitly deploy the private host; verify its health, access, restart, and recovery.
- Demonstrate aligned sender-domain authentication and check actual Inbox placement.
- Record the full live workflow after its missing stages succeed; retain the existing video's fixture labels.

The existing [recording](demo.md#recorded-walkthrough) remains a local demonstration with real OCR,
fixture AI, and simulated email. It does not show this later SES test. Service charges have not been
independently reconciled against billing; the agreed allowance is not a claim of zero measured spend.
