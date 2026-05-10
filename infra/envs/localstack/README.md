# Flowin Terraform — LocalStack environment

A **hermetic test fixture** that applies the full Flowin Terraform suite
against a local LocalStack Pro container. Use it to validate module changes
end-to-end without touching a real AWS account.

This env is a sibling of `envs/prod/` and shares the same modules; the only
differences are: provider endpoints rewritten to LocalStack, dummy
credentials, local Terraform state, and a small handful of variable
overrides driven by LocalStack quirks (stub AMI, no detailed monitoring,
no EBS optimisation).

## Prerequisites

1. **LocalStack Pro** running on port `4666`. Recommended startup:
   ```bash
   docker run -d --name flowin-localstack-test \
     -p 4666:4566 -p 4710:4510 \
     -e LOCALSTACK_AUTH_TOKEN="$YOUR_PRO_TOKEN" \
     -e SERVICES="ec2,iam,kms,s3,ssm,logs,sns,dynamodb,route53,backup,bedrock,bedrock-runtime,cloudwatch,events,resourcegroupstaggingapi,resource-groups,sts,cloudtrail,acm" \
     -e PERSISTENCE=0 -e EAGER_SERVICE_LOADING=1 -e DEFAULT_REGION=eu-central-1 \
     -v /var/run/docker.sock:/var/run/docker.sock \
     localstack/localstack-pro:2026.4.1
   ```
   Port `4566` is intentionally avoided so this container doesn't collide
   with a team-shared `hexaware-localstack` instance.

2. `awslocal` and `tflocal` (`pip install awscli-local terraform-local`).
   You can also use plain `aws` / `terraform` with explicit
   `AWS_ENDPOINT_URL=http://localhost:4666` — the providers in this env
   already pin every endpoint to that URL.

3. `terraform` >= 1.7 (tested on 1.15).

## Apply

```bash
cd infra/envs/localstack
export PATH=$HOME/Library/Python/3.9/bin:$PATH
export AWS_ENDPOINT_URL=http://localhost:4666
export AWS_DEFAULT_REGION=eu-central-1
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test

# Pre-create the Route 53 zone the dns module looks up.
aws route53 create-hosted-zone \
  --name flowin.test \
  --caller-reference flowin-localstack-$(date +%s) >/dev/null

terraform init
terraform apply -auto-approve
```

Expect ~86 resources created across 10 modules.

## Destroy

`prevent_destroy = true` is set on the KMS CMK, S3 backup bucket, AWS Backup
vault, and EBS data volume. Plain `terraform destroy` will refuse to remove
them, so this env ships a helper:

```bash
./destroy.sh
```

The helper drops those four resources from local state (`terraform state rm`)
and then runs `terraform destroy -auto-approve`. State files are local and
ignored by git, so this is safe to repeat.

## Known LocalStack quirks

- **AMI lookup** — Canonical's filter resolves to nothing in LocalStack, so
  `ami_id` is pinned to a LocalStack stub (`ami-03cf127a`). The `compute`
  module bypasses the data source when `ami_id` is non-empty.
- **`MonitorInstances`** — not implemented; we set `detailed_monitoring =
  false` here.
- **`EbsOptimized`** — rejected on LocalStack stub AMIs; we set
  `ebs_optimized = false` here.
- **Backup-vault `kms_key_arn`** — not echoed back by
  `DescribeBackupVault`, so a second `terraform plan` after a successful
  apply shows drift on this attribute. Re-applying is harmless; it's a
  LocalStack round-trip bug, not a real change.
- **EC2 `iam_instance_profile`** — `RunInstances` returns `NoSuchEntity`
  even when the profile exists in IAM. We pass `iam_instance_profile_name
  = ""` here so the EC2 launch succeeds; the IAM module still creates the
  role + policies + profile so they're exercised.
- **SNS email subscription** stays in `pending confirmation` (no SES) —
  this is expected; the resource itself is created.

None of these affect the prod env; they're confined to overrides in this
directory's `terraform.tfvars` and to the additive variables introduced in
the `compute` module (`ami_id`, `detailed_monitoring`, `ebs_optimized`,
all default-prod-equivalent).

## What this env does NOT validate

- Real Bedrock invocation (LocalStack mocks the API; no live model).
- Actual TLS issuance (no Let's Encrypt round-trip from LocalStack).
- Real cross-region inference profile resolution.
- Outbound connectivity from the EC2 (LocalStack EC2s are stubs, not real
  Linux hosts).

For those, validate against a real AWS sandbox account using `envs/prod/`
or a parallel `envs/sandbox/`.
