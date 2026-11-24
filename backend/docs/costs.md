# Cost worksheet

Live calls and provisioning have not been performed. The application requires an explicitly agreed
budget and opt-in flags; its limits count reserved attempts, including failures. Model and embedding
calls share a daily allowance. OCR counts jobs (each can include up to the configured page maximum),
and email has a separate send allowance. None of these replace AWS billing controls.

## Illustrative hosting estimate, checked November 24, 2026

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
