# Cost worksheet

Live calls and provisioning have not been performed. The application requires an explicitly agreed
budget and opt-in flags; its limits count reserved attempts, including failures. Model and embedding
calls share a daily allowance. OCR counts jobs (each can include up to the configured page maximum),
and email has a separate send allowance. None of these replace AWS billing controls.

## Free-plan selection, checked November 25, 2026

The user selected the Free plan and local OCR. AWS lists **t3.small** among its
[Free-plan eligible compute types](https://aws.amazon.com/free/compute/). The default now uses that
2 GiB host, with 2 GiB swap on encrypted EBS for the small demonstration. Textract requires the
Paid plan in the [current supported-services list](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html),
so local Tesseract replaces it in the selected deployment. No account upgrade is required by the code.

The [Free plan](https://aws.amazon.com/free/) uses credits and ends after six months or when credits
run out. Credits are not unlimited service usage. Keep the plan unchanged and check the current
balance in Billing. The proposed **$10 allowance is credit consumption**, with **$0 out-of-pocket**;
it is awaiting the user's agreement. The app's budget variable tracks that allowance, not a cash bill.

| Default component | 730-hour month | 32 hours, storage kept all month |
|---|---:|---:|
| t3.small at $0.0209/hour | $15.26 | $0.67 |
| IPv4 at $0.005/hour | $3.65 | $0.16 |
| 30GB gp3 at assumed $0.08/GB-month | $2.40 | $2.40 |
| Hosting subtotal | **$21.31** | **$3.23** |

Rates exclude AI, embedding, SES, S3, logs, requests, transfer, and taxes. Local OCR has no per-page
AWS OCR charge; it consumes the host's compute/storage. Daily application limits and budget alerts
do not enforce total account spend. The estimated 32-hour runtime is a plan, not an automatic stop.

Generate an offline estimate and review record with `python -m backend.scripts.aws_setup plan
--config backend/artifacts/aws/deployment.json`. See [AWS setup](aws-setup.md) for account/identity
checks and the reviewed deployment operation.

## Earlier t3.medium alternative

For Linux in us-east-1, the [AWS T3 table](https://aws.amazon.com/ec2/instance-types/t3/) shows
t3.medium at **$0.0418/hour**. [Public IPv4 pricing](https://aws.amazon.com/vpc/pricing/) lists
**$0.005/hour**. The [EBS pricing example](https://aws.amazon.com/ebs/pricing/) uses **$0.08/GB-month**
for gp3; treat that storage rate as an estimate and verify the selected region in the calculator.

| Component | 730-hour month | 32 running hours, storage retained all month |
|---|---:|---:|
| One t3.medium | $30.51 | $1.34 |
| One in-use public IPv4 | $3.65 | $0.16 |
| 30 GB gp3 at assumed $0.08/GB-month | $2.40 | $2.40 |
| Hosting subtotal | **$36.56** | **$3.90** |

These subtotals exclude model/OCR/embedding/email charges, requests, S3/backups, logs, queues, data
transfer, taxes, and any unrelated account usage. A **$50/month always-on planning envelope** or a
**$15/month short-demo planning envelope** provides a starting point for discussion, not a quote or
spending authorization. Confirm the full estimate in the [AWS calculator](https://aws.amazon.com/calculator/)
before enabling cloud work. Model availability, rates, and taxes may differ at deployment time.

## Per-document worksheet

Enter the chosen provider's current rates rather than assuming a free tier:

| Item | Usage to record | Formula |
|---|---|---|
| Nova extraction/drafting | input/output tokens for every attempt | input tokens × input rate + output tokens × output rate |
| Titan indexing/retrieval | input tokens for chunks and queries | input tokens × embedding rate |
| Textract | processed pages, including retries/new jobs | pages × text-detection page rate |
| SES | attempted sends, accepted message IDs | accepted sends × message rate, plus applicable data charges |
| S3 and backups | GB-month, requests, versions | storage × storage rate + requests × request rate |
| EC2, EBS, IPv4, CloudWatch | uptime, storage, log ingestion | report separately from variable per-document work |

Rate sources: [Bedrock](https://aws.amazon.com/bedrock/pricing/),
[Textract](https://aws.amazon.com/textract/pricing/), [SES](https://aws.amazon.com/ses/pricing/),
[S3](https://aws.amazon.com/s3/pricing/), and [CloudWatch](https://aws.amazon.com/cloudwatch/pricing/).
The `/metrics` usage ledger records model token usage, reservations, and outcomes. Provider failures
can have unknown charges; reconcile them with billing. OCR page counts and S3 storage must also be
checked against provider records. No computed dollar figure in the application is a billing cap.
