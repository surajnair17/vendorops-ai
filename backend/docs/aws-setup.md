# AWS Free-plan deployment and learning guide

The selected deployment uses **local Tesseract OCR**, a regional Nova Lite model, Titan embeddings,
S3, and SES. Live inference, storage, and email stay disabled until configuration is reviewed.
Textract remains implemented as an optional Paid-plan adapter; it is not needed for scans on this
deployment. Account upgrades are never performed by these scripts.

## 1. Sign in without sharing keys

Install the [official AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html).
Version 2.32 or later supports [browser login](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sign-in.html).
For AWS's newer signup, use the same Builder ID/Google/email sign-in method and choose your existing
project. The root-user form applies to the advanced signup path and may not recognize that login.
Do not create a second account to solve a sign-in mismatch. See the
[new signup and sign-in guide](https://docs.aws.amazon.com/accounts/latest/reference/sign-in-new.html).
For an advanced account, use an IAM or federated operator for deployment. Run locally:

```powershell
aws login --profile pixel-perfect --region ap-southeast-2
aws sts get-caller-identity --profile pixel-perfect
```

On the current development machine, the signed CLI is installed in the user-local programs folder:

```powershell
& "$env:LOCALAPPDATA\Programs\Amazon\AWSCLIV2\aws.exe" login --remote --profile pixel-perfect --region ap-southeast-2
```

This path is machine-local, not part of a fresh clone. Browser login stores temporary credentials
outside this repository. `boto3[crt]` in requirements-cloud.txt supports those credentials. Configure
`VENDOROPS_AWS_PROFILE=pixel-perfect` when running the application locally with live services. EC2 containers use
the instance role instead, so they need neither the local profile nor copied keys.

Agent Toolkit for AWS can install the default AWS skills and register its MCP connection:

```powershell
aws configure agent-toolkit --yes --region us-east-1 --profile pixel-perfect
aws agent-toolkit list-available-skills --region us-east-1 --profile pixel-perfect
```

These commands use the toolkit service Region, us-east-1. The selected project Region remains
ap-southeast-2. The generated MCP entry needs `AWS_MCP_PROXY_PROFILES=pixel-perfect` in its environment;
this differs from the application's `VENDOROPS_AWS_PROFILE` setting. Preserve existing MCP entries.
Restart Codex/VS Code after setup to load the new tools and refreshed executable paths. If desired,
run `/hooks` in Codex to trust the installed AWS skill-update hook; updates wait for that trust.

On Windows, if catalog output fails with a `charmap` Unicode error, set `$env:PYTHONUTF8='1'` and
`$env:PYTHONIOENCODING='utf-8'` in that terminal and retry. If Application Control blocks the generated
proxy executable, keep security settings intact. This machine uses the following tested module
launcher, explicitly approved by the user as an exception to the generated arguments:

```toml
[mcp_servers.aws-mcp]
command = "uvx"
args = ["--from", "mcp-proxy-for-aws@latest", "python", "-m", "mcp_proxy_for_aws.server", "https://aws-mcp.us-east-1.api.aws/mcp", "--metadata", "INSTALL_SOURCE=aws-cli"]

[mcp_servers.aws-mcp.env]
AWS_MCP_PROXY_PROFILES = "pixel-perfect"
```

See [AWS's setup instructions](https://raw.githubusercontent.com/aws/agent-toolkit-for-aws/refs/heads/main/setup-instructions/setup.md).
If the CLI or MCP reports an expired session, renew it with `aws login --profile pixel-perfect`
and reconnect the MCP server. To add another project later, run `aws login --profile NAME`, append
`NAME` to the space-separated `AWS_MCP_PROXY_PROFILES` value, and restart Codex.

**Predict:** what will STS report when you select a different account? How does an EC2 container
obtain temporary credentials without a local profile?

## 2. Prepare a concrete deployment record

```powershell
New-Item -ItemType Directory -Force backend/artifacts/aws | Out-Null
Copy-Item backend/infra/deployment.example.json backend/artifacts/aws/deployment.json
.\.venv\Scripts\python.exe -m backend.scripts.aws_setup plan --config backend/artifacts/aws/deployment.json
```

Edit the ignored copy. Enter the account ID, current credit balance, reviewed usage allowance,
VPC/subnet IDs, sender/recipient/budget email addresses, and the **full pushed release commit**.
For the newer signup, find the project's assigned Region under AWS Settings → Project → Additional
Info. Use that Region for the stack, VPC, SES, and CLI profile; it may differ from the original
us-east-1 default. Check regional EC2/EBS rates and update `pricing_region`, `pricing_instance_type`,
`ec2_hourly_usd`, and `gp3_gb_month_usd` before review. The estimate is based on these entered rates.
`bedrock_region` can remain us-east-1 for regional model APIs, which the new experience allows
outside the project's resource Region. This does not use cross-region inference profiles. See
[project Regions](https://docs.aws.amazon.com/accounts/latest/reference/project-regions.html).
Keep `account_plan=free`, `maximum_out_of_pocket_usd=0`, `instance_type=t3.small`, and
`enable_textract=false`. The expected 32-hour hosting subtotal is about **$3.23**, plus service
usage. A proposed **$10 credit allowance** leaves room for a small synthetic demonstration; it
is not assumed approved, reserved credit, or a billing cap. See [costs](costs.md).

AWS lists t3.small as [Free-plan eligible](https://aws.amazon.com/free/compute/). The host has 2 GiB
RAM and 2 GiB swap on encrypted EBS; it is intended for this small synthetic corpus. Builds run
sequentially. Resource limits, successful boot, and latency still need a real deployment check.

Use an existing subnet with an Internet Gateway default route. Inbound ports stay closed; the host
receives an IPv4 address for outbound package/service access. The read-only checker validates the
subnet's VPC and route. It does not create networking or change the account plan.

In SES in the **selected project Region**, create and verify the exact sender and test-recipient
email identities. You must open the verification links in your own inbox. Stay in the
[SES sandbox](https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html).
The application and runtime IAM both restrict recipients.

**Practise:** locate these resources in the console and explain why neither a public inbound rule
nor a long-lived access key is needed. Verify that credits have not expired before authorizing use.

## 3. Run read-only checks and review the plan

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.validate_infra
.\.venv\Scripts\python.exe -m backend.scripts.aws_setup check --config backend/artifacts/aws/deployment.json
.\.venv\Scripts\python.exe -m backend.scripts.aws_setup plan --config backend/artifacts/aws/deployment.json
```

The checker calls STS, EC2 describe APIs, regional Bedrock model metadata, and SES identity metadata.
It does not invoke a model, OCR, send email, or provision resources. Missing login, wrong account,
root operator, wrong subnet/route, unavailable model metadata, or unverified email identities block
deployment. The credit balance is operator-entered; the checker does not independently validate it.
Model listing also does not prove invocation authorization or quota availability.

The plan displays configuration, resources, estimated hosting, remaining blockers, and a review
digest covering the configuration and local infrastructure/bootstrap files. Changing them changes
the digest. Review the specific account, resources, credit allowance, and release before deployment.

## 4. Provision the reviewed release

Only after the deployment record and allowance have been agreed, use its exact digest:

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.aws_setup deploy --config backend/artifacts/aws/deployment.json --review-sha256 REVIEWED_DIGEST
.\.venv\Scripts\python.exe -m backend.scripts.aws_setup status --config backend/artifacts/aws/deployment.json
```

Deploy creates a new CloudFormation stack; it does not silently update an existing stack. It repeats
preflight and requests IAM capability. Boot installs Docker and checksum-verified pinned Compose,
checks out the selected public Git commit, creates runtime configuration from stack resources, and
starts the four containers. CloudFormation waits for a successful bootstrap signal; inspect events
and `/var/log/cloud-init-output.log` if bootstrap fails. A rolled-back stack can retain encrypted EBS;
review retained resources and costs after any failure.

Install the [Session Manager plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html)
locally, then forward Streamlit using the stack's InstanceId:

```powershell
aws ssm start-session --profile pixel-perfect --region ap-southeast-2 --target INSTANCE_ID --document-name AWS-StartPortForwardingSession --parameters 'portNumber=8501,localPortNumber=8501'
```

Open localhost:8501. First demonstrate fixture documents, local scanned OCR, review, comparisons,
policies, and a simulated send. Keep a copy of the deployed commit and stack outputs.

## 5. Verify each live service separately

Through an SSM shell, edit `/opt/vendorops/backend/.env` for the reviewed service checks:

```text
VENDOROPS_PROVIDER=bedrock
VENDOROPS_LIVE_CALLS_ENABLED=true
VENDOROPS_STORAGE_MODE=s3
VENDOROPS_LIVE_SEND_ENABLED=false
```

Restart backend/worker with the same Compose command used by bootstrap. Set Streamlit's request
timeout to at least 120 seconds using its environment before testing bounded model repairs. Upload
one synthetic digital invoice and verify every field against the source. Upload a scan, request
local OCR, and inspect the recognized text before structuring. Local OCR makes no AWS calls and
records its provider separately from Textract.

Reindex policies for Titan; fixture vectors and real vectors use distinct collections. Run held-out
extraction and retrieval evaluation using the existing scripts and record model versions, usage,
latency, and measured scores. Do not publish fixture accuracy as live-model accuracy.

For SES, draft an action with delivery mode SES; inspect its recipient, subject, body, and findings.
Enable the separate live-send flag only for this reviewed demonstration. Approval and execution
remain separate UI operations. An SES message ID proves acceptance; check the verified inbox to
prove arrival. No setup/evaluation script sends email on your behalf.

**Teach back:** trace a scan through PyMuPDF rasterization → Tesseract → text revision → Bedrock →
comparison → rule evidence → approved SES action. Explain why uncertain sending must not auto-retry.

## 6. Stop, restore, and record evidence

Disable live flags, stop the host outside demonstration hours, and back up the application using
the [operations runbook](operations.md). EBS/S3 retention continues while compute is stopped.
Demonstrate worker restart and backup restoration before marking the deployment verified.

Record stack status, commit, a real digital and scanned result, verified inbox arrival, held-out
scores, measured usage, and the restoration outcome in [status](status.md). These are release gates,
not results established by offline SDK stubs or infrastructure linting.
