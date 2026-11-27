# Local operation and private AWS demonstration

Run commands from the repository root unless a section says otherwise. Read the cost worksheet
before enabling a live service. The repository never deploys from CI or sends a real email by default.

## Local start and stop

Install the backend, optional AWS SDK, and frontend dependencies using the root README. Copy both
configuration examples to their respective `.env` files if those files do not already exist.
Use separate terminals for the API, Streamlit, and worker:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe -m streamlit run frontend/app.py --server.address 127.0.0.1
.\.venv\Scripts\python.exe -m backend.worker
```

Press Ctrl+C in each terminal to stop. SQLite jobs remain queued after restart. A sending job whose
five-minute lease expires becomes `unknown`; inspect provider/inbox evidence and use Reconcile in
Actions. A failed action must be edited, resubmitted, and approved again before a new execution.
Unknown actions cannot be edited or automatically retried.

Inspect `/health` for API availability and `/api/v1/metrics` for job/action counts and usage records.
The Operations screen shows the same metrics. Application logs contain route templates, HTTP status,
latency, and exception types, excluding PDF contents, model prompts, and email bodies. Debug access
logs should stay disabled when using real data in any future version.

To start a fresh demonstration without deleting existing data, set `VENDOROPS_DATA_DIR` to a new
directory in the backend configuration and restart API and worker with the same value.

## Back up and restore

The backup command creates a consistent SQLite snapshot and copies every referenced source PDF.
Policy chunks, revisions, approvals, jobs, and audit events are in that database. The index is rebuilt
from policy chunks; model secrets and `.env` files are deliberately outside the backup.

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.backup backup backend/artifacts/backups/demo-01
.\.venv\Scripts\python.exe -m backend.scripts.backup restore backend/data-restored --source backend/artifacts/backups/demo-01
```

Both destinations must be new directories. Stop API and worker before switching configuration to
the restored directory. Pending/active email executions are restored as `unknown`, since an older
backup cannot prove that an email was never sent. Restored policies require reindexing: use Rebuild
index on Policies or `POST /api/v1/policies/{id}/reindex`. Paid reindexing requires live-call settings.
Existing active rules keep their citations, and retrieval refuses to use an unrebuilt index.

Upload backups to the stack bucket's `backups/` prefix through your configured AWS tools after
enabling the agreed cloud workflow. Test restoration before relying on a backup schedule.

## Containers

Docker is optional for local learning. The development machine used here has no Docker installation;
container build/runtime verification is a separate gate. Install Docker with Compose using its
[official installation guide](https://docs.docker.com/compose/install/).

```powershell
docker compose -f backend/infra/compose.yaml config --quiet
docker compose -f backend/infra/compose.yaml up --build -d
docker compose -f backend/infra/compose.yaml logs --tail 50 backend worker
docker compose -f backend/infra/compose.yaml stop
```

Host ports bind only to loopback. Backend and worker share a persistent volume; Chroma has its own
volume. Never use `down --volumes` when you need to retain that data. For a container backup, run
the backup module through `docker compose ... exec backend` and copy the result out with `docker
compose ... cp`; Python paths inside the container are Linux paths. The frontend image installs
only frontend dependencies.

## AWS preparation and approval gate

For the selected **Free-plan / local OCR** deployment, use [AWS setup](aws-setup.md). The template
now defaults to t3.small, creates Textract/SNS/SQS only when `EnableTextract=true`, and bootstraps a
pinned `ReleaseCommit` automatically. The following Textract-specific details describe the optional
Paid-plan variant. Both live application flags remain false after bootstrap.

The optional Paid-plan configuration can use one t3.medium host, an encrypted retained volume, a private S3 bucket,
Textract notification role, SNS/SQS/dead-letter queue, application IAM role, a log group, queue alarm,
and a monthly budget alert. It uses an existing VPC and public subnet with outbound Internet access.
There are no inbound application or SSH rules; the assigned IPv4 address supports outbound access.
There is no NAT Gateway, load balancer, or public login. CPU credit mode is standard to avoid surplus
CPU-credit charges; sustained workloads can be throttled.

Before provisioning: agree the spending limit, select the AWS account and region, confirm the subnet,
verify sender and recipient identities in the SES sandbox, and check model access and applied
inference quotas. A zero quota blocks provisioning even when model access is authorized. No credentials
belong in Git or chat. Use an AWS profile for administration and the EC2 instance role at runtime.
Budgets alert after usage is recorded; they are not a billing cap. See [the cost worksheet](costs.md).

Validate locally/CI before deploying:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/infra/requirements.txt
.\.venv\Scripts\python.exe -m backend.scripts.validate_infra
```

The wrapper invokes cfn-lint's installed entry point; it does not contact AWS or provision resources.
CI runs the same validator on Linux. Template validation does not establish successful deployment.

After explicit provisioning authorization, use the AWS CLI with actual values for the named
parameters: `VpcId`, `PublicSubnetId`, `SenderEmail`, `TestRecipientEmail`, `BudgetEmail`, and
`MonthlyBudgetUSD`. Deploy `backend/infra/cloudformation.yaml` with `CAPABILITY_IAM`, then record
all stack outputs. Do not deploy until the estimate and parameter values have been reviewed.

The instance installs Docker, Git, and checksum-verified pinned Compose, checks out the reviewed
release into `/opt/vendorops`, and creates backend configuration from stack references. The instance role
permits release objects under the bucket's `releases/` prefix. No repository URL or access token is
embedded in the template. A release archive can be produced with `git archive` after committing
the intended source.

Fill in backend configuration from stack outputs: document bucket, SNS topic, Textract role ARN,
SQS queue URL, and log group. Set provider, budget, allowed recipient, and verified SES sender.
Keep both live flags false until the private application launches successfully. The EC2 metadata
hop limit supports instance-role access from containers; no long-lived AWS keys are needed.

Forward the remote Streamlit port from your laptop:

```powershell
aws ssm start-session --profile pixel-perfect --region ap-southeast-2 --target INSTANCE_ID --document-name AWS-StartPortForwardingSession --parameters 'portNumber=8501,localPortNumber=8501'
```

Open localhost:8501. The backend stays inside the host/container network. Use a separate forwarding
session for port 8000 only when API inspection is needed. For CloudWatch logging, merge the override:

```powershell
docker compose --env-file backend/.env -f backend/infra/compose.yaml -f backend/infra/compose.aws.yaml up --build -d
```

## Live service verification

1. Run the read-only Bedrock preflight in [AWS setup](aws-setup.md). Confirm the current Free plan,
   reviewed Sydney configuration, positive quotas, and agreed budget before enabling
   `VENDOROPS_LIVE_CALLS_ENABLED`. Restart the processes.
2. Enable `VENDOROPS_PROVIDER=bedrock` and validate one synthetic digital document. Reindex policies
   for Titan; fixture and real embeddings never share a collection.
   The AWS Compose override sets the frontend timeout to 150 seconds for bounded model repairs.
3. On the selected Free plan, upload a scanned synthetic PDF and request **local OCR**. The worker
   renders pages and runs Tesseract; inspect recognized text before model extraction. On the optional
   Paid-plan Textract deployment, the worker uploads the source to S3, starts Textract with an
   idempotency token, and receives completion through SNS/SQS. It fetches all
   result pages, preserves existing digital text, and fills textless pages. Pages containing only a
   watermark still need manual inspection: nonempty digital text is preserved.
4. Inspect failed/partial jobs before requesting another. Start attempts are bounded to three with
   a five-minute lease; repeated requests use the same provider token. Missing completion expires
   after six days, before the provider result-retention window. The dead-letter queue needs manual
   investigation and replay after fixing the cause. Queue alarms are visible in CloudWatch.
5. Create and review an action whose delivery mode is SES. Confirm the address in the test contact
   list. Only then enable `VENDOROPS_LIVE_SEND_ENABLED`, approve the exact revision, and execute it.
   Record the SES ID and separately confirm arrival in the verified test inbox. No script in this
   repository substitutes for that human approval.
6. Restart the worker during a synthetic job, verify no duplicate execution, back up and restore,
   and run the held-out benchmarks. Document every result and limitation.

The single-operator identity in the audit log is configured, not authenticated through a public
identity provider. Use this deployment only for the agreed private demonstration.

## Rollback, cost stop, and teardown

To pause new paid work, disable both live flags and restart API/worker; existing queued work remains
stored. Stop the EC2 host when no demonstration is running. Storage and retained resources can
continue to cost money while compute is stopped.

Before changing a release, back up and record its Git commit/image IDs and database schema version.
Roll back to that release with compatible data, or restore its backup into a new data directory.
Use one API replica and one worker; SQLite is not a multi-host deployment database.

After explicit teardown authorization, stop the containers, take a final backup, and remove the
CloudFormation stack. The bucket and root EBS volume are retained intentionally. Review retained
volumes, S3 versions/backups, snapshots, logs, and other billable resources in the console before
deleting them. Stack deletion alone does not prove all charges have stopped.
