# Infrastructure validation

CloudFormation syntax, static security rules, and live deployment checks provide different evidence.
None of them establishes live AI accuracy or successful email delivery.

## Run AWS Guard

The optional infrastructure tool uses AWS's official
[`@aws/cloudformation-guard`](https://github.com/aws-cloudformation/cloudformation-guard/tree/3.4.0/guard/ts-lib)
WebAssembly package, pinned to **3.4.0**. Node.js 20 or later is required for this tool only; the
application remains Python. This installation works on the development machine, where Windows
Application Control blocks the official native Guard executable. Windows security settings remain
unchanged.

The rules are AWS's complete **66-file Well-Architected Security Pillar mapping**, pinned to
[`aws-guard-rules-registry` commit `7f7340c`](https://github.com/aws-cloudformation/aws-guard-rules-registry/tree/7f7340c26ae5d5e8874651dbffeb12e0e9f505b6).
For a fresh clone, run from the repository root:

```powershell
git clone --filter=blob:none --no-checkout https://github.com/aws-cloudformation/aws-guard-rules-registry.git backend/artifacts/aws/guard/rules-registry
git -C backend/artifacts/aws/guard/rules-registry checkout --detach 7f7340c26ae5d5e8874651dbffeb12e0e9f505b6
npm --prefix backend/infra/guard ci --ignore-scripts --no-audit --no-fund
npm --prefix backend/infra/guard test
npm --prefix backend/infra/guard run check
```

Reuse an existing rules checkout rather than cloning over it. The runner rejects a different or
modified checkout. Reports and downloaded dependencies are ignored by Git. It checks the actual
template without altering conditions, filtering findings, or adding rule suppressions.

Exit code **0** means no reported rule violations, **1** means findings need review, and **2** means
validation could not complete. The full structured report is
`backend/artifacts/aws/guard/report.sarif.json`, including rule IDs, messages, source locations, and
tool/rules versions. Some upstream locations point to line 1; the message includes the property path.
On Windows, use `npm.cmd` if PowerShell execution policy blocks the `npm.ps1` wrapper.
Four executable probes check a passing policy example, strict rejection of a public-IP finding,
preservation of advisory findings, and failure on malformed input. They do not provision anything.

CI runs the same scan in explicit `--report-only` mode and publishes its SARIF artifact. That mode
returns success after producing a report containing findings; validator errors still fail the job.
**A green advisory job is not a compliance pass.** Strict local mode returns 1 for the findings below.

## Observed findings: November 28, 2026

The unchanged template produced **12 messages across eight rule IDs**, grouped below. Conditional
resources are checked even though `EnableTextract=false` excludes them from the selected Free-plan
deployment. These findings are retained; no blanket exceptions or suppressions were applied.

| Rule and resource | Messages | Assessment and required follow-up |
| --- | ---: | --- |
| `SNS_ENCRYPTED_KMS` — `CompletionTopic` | 1 | The optional Textract notification topic has no KMS key. Configure encryption and publisher key permissions before enabling that Paid-plan variant. |
| `CLOUDWATCH_ALARM_ACTION_CHECK` — `QueueAlarm` | 3 | The optional Textract backlog alarm has no notification action. Configure a reviewed alert destination before enabling that variant. |
| `S3_BUCKET_LOGGING_ENABLED` — `Documents` | 1 | S3 access logging is absent. Application logs do not replace S3 data-access auditing; add an appropriate audit destination before a customer-data hardening release. |
| `CLOUDWATCH_LOG_GROUP_ENCRYPTED` — `ApplicationLogs` | 1 | The rule requires an explicit KMS key. CloudWatch already encrypts logs at rest by default; customer-managed key control remains a hardening item. |
| `EC2_INSTANCE_NO_PUBLIC_IP` — `Host` | 2 | The reviewed design assigns an IPv4 address for outbound package/AWS access, with no inbound security-group rules. Removing it requires reviewing the outbound-access design and costs. |
| `IAM_NO_INLINE_POLICY_CHECK` — `InstanceRole`, `TextractRole` | 2 | The template uses stack-owned inline service policies. This rule requires managed policies; policy form does not establish whether permissions are sufficient or excessive. Review permissions separately. |
| `EC2_INSTANCES_IN_VPC` — `Host` | 1 | Checker limitation: it only checks top-level `SubnetId`. This template correctly sets `NetworkInterfaces[0].SubnetId`; live preflight checks that subnet's VPC and route. |
| `S3_BUCKET_SSL_REQUESTS_ONLY` — `BucketPolicy` | 1 | Checker limitation: the pinned rule matches only boolean `false`. The existing valid `Bool` condition uses the string `'false'`, denies `s3:*` over insecure transport, and covers the bucket and its objects. |

AWS documents [network-interface subnet configuration](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-ec2-instance-networkinterface.html),
[HTTPS-only S3 policies](https://docs.aws.amazon.com/AmazonS3/latest/userguide/example-bucket-policies.html#example-bucket-policies-use-case-7),
and [default CloudWatch log encryption](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/encrypt-log-data-kms.html).
The exact pinned rules remain available in the registry checkout for inspection.

No template or deployed resource was changed during this assessment. The optional Paid-plan gaps
must be fixed before that variant is used. Stronger audit/key controls remain outside the supported
synthetic private PoC, and the broad ruleset is not fully satisfied. Live deployment still requires
the reviewed resource plan, positive inference quotas, and verified SES identities.

## Learning exercise

Read `s3_bucket_ssl_requests_only.guard` and `ec2_instances_in_vpc.guard` in the rules checkout.
Explain why each reports a finding here. Trace an optional topic's `UseTextract` condition and
explain why a static finding does not prove that the resource exists. Compare the Guard report
with cfn-lint and the read-only AWS readiness report; state what each can and cannot establish.
