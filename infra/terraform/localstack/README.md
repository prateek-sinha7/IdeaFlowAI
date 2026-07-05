# VelocityAI Terraform — LocalStack fixture

A **hermetic, non-CICD test harness** that applies the whole VelocityAI module
set against a local LocalStack Pro container. Use it to smoke-test module
changes end to end without an AWS account.

This is NOT a deploy layer. The real deploy path is
`bootstrap -> shared -> foundation(<env>) -> app(<env>)` with remote state
(see [`../../README.md`](../../README.md)). This fixture composes the same
`../modules/*` directly in one root, with local state and LocalStack endpoint
overrides, so it exercises the module wiring offline.

## Prerequisites

1. **LocalStack Pro** on port `4666` (NOT 4566 — avoid colliding with a shared
   container). Include `ecr` in `SERVICES`:
   ```bash
   docker run -d --name velocityai-localstack \
     -p 4666:4566 \
     -e LOCALSTACK_AUTH_TOKEN="$YOUR_PRO_TOKEN" \
     -e SERVICES="ec2,iam,kms,s3,ssm,logs,sns,dynamodb,route53,backup,bedrock,cloudwatch,events,resourcegroupstaggingapi,resource-groups,sts,cloudtrail,acm,ecr" \
     -e PERSISTENCE=0 -e EAGER_SERVICE_LOADING=1 -e DEFAULT_REGION=eu-central-1 \
     -v /var/run/docker.sock:/var/run/docker.sock \
     localstack/localstack-pro:latest
   ```
2. `terraform >= 1.9`, and the `aws` CLI (or `awslocal`).

## Apply

```bash
cd infra/terraform/localstack
export AWS_ENDPOINT_URL=http://localhost:4666
export AWS_DEFAULT_REGION=eu-central-1
export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test

# Pre-create the Route 53 zone the dns module looks up.
aws route53 create-hosted-zone --name velocityai.test \
  --caller-reference ls-$(date +%s) >/dev/null

terraform init
terraform apply -var-file=localstack.tfvars -auto-approve
```

## Destroy

`prevent_destroy` is set on durable resources, so use the helper (it
`state rm`s them first, then destroys):

```bash
./destroy.sh
```

## Known LocalStack quirks (confined to this directory)

- **AMI** pinned to a LocalStack stub (`ami_id`); the Canonical filter resolves
  to nothing.
- **EC2 instance profile** not attached (`iam_instance_profile_name = ""`) —
  LocalStack's EC2 backend can't see IAM-created profiles. The IAM module still
  creates the role/policies/profile so they're exercised.
- **MonitorInstances / EbsOptimized** unimplemented → both `false` here.
- **EIP** is ephemeral (`protect_eip = false`); `disable_api_*` are `false` so
  `destroy.sh` works without `aws ec2 modify-instance-attribute`.
- **Vault Lock / Object Lock** enforcement absent → hardcoded off.
- **ECR** shared repos (`velocityai/backend`, `velocityai/frontend`) — same
  module the shared layer uses.

None of these affect the real layers; they live only in this fixture's
`localstack.tfvars` and the additive `compute` module knobs.
