# Flowin Terraform — bootstrap

This is the **one-time** bootstrap that creates the S3 bucket and DynamoDB
table the rest of the Flowin Terraform uses for remote state. It runs with
**local state** and is committed to git so it can be re-run if the bucket is
ever destroyed (don't actually destroy it; it's marked `prevent_destroy`).

## What it creates

- `aws_s3_bucket` for Terraform state (versioned, SSE-S3, TLS-only, BPA on).
- `aws_dynamodb_table` for state locking (PITR + SSE).

It creates **nothing else**. In particular it does **not** touch any
account-wide setting (no `aws_s3_account_public_access_block`, no
`aws_organizations_*`, etc.).

## Account-ID guard

The very first thing this module evaluates is a `terraform_data` resource with
`lifecycle.precondition` blocks comparing the live caller's account ID and
region to `var.expected_account_id` / `var.aws_region`. A mismatch aborts
plan/apply with a clear error before anything is created.

## Run it once

```bash
cd infra/bootstrap

cat > terraform.tfvars <<EOF
expected_account_id = "123456789012"          # the Flowin AWS account
aws_region          = "eu-west-2"
owner               = "flowin-platform-team@hexaware.com"
cost_center         = "UKI-FLOWIN-PROD"
state_bucket_name   = "flowin-tfstate-123456789012-eu-west-2"
lock_table_name     = "flowin-tfstate-locks"
EOF

terraform init
terraform plan
terraform apply
```

After it completes, copy the outputs into `infra/envs/prod/backend.tf` (the
`bucket =` and `dynamodb_table =` keys).

## Re-running

Safe. Both resources are `prevent_destroy = true`. Subsequent applies are
idempotent.
