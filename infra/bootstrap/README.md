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

After it completes, note the `state_bucket_name` output. Operators wire it
into `envs/prod` at `init` time via `-backend-config="bucket=..."`; the
other backend keys (`key`, `region`, `encrypt`, `dynamodb_table`) are
committed in `infra/envs/prod/backend.tf` and need no operator input.

## Re-running

Safe. Both resources are `prevent_destroy = true`. Subsequent applies are
idempotent.

## Recovery — when the bootstrap state file is lost

**Why this matters.** Bootstrap deliberately uses **local state** (in
`infra/bootstrap/terraform.tfstate`, gitignored). It has to: it's the
chicken-and-egg — the S3 bucket that backs every other environment's
remote state is the bucket bootstrap creates. There is nowhere remote to
put bootstrap's own state.

The consequence: if the operator's laptop dies (or the working copy is
wiped) and the local state file isn't recovered, **`terraform apply` is
not a recovery path**. Both bootstrap-created resources have
`prevent_destroy = true`, but more immediately, with no state file
Terraform doesn't know they exist — so a fresh `apply` would try to
*create* the bucket and the lock table, and fail at the bucket step with
`BucketAlreadyOwnedByYou` (because the real bucket is still in AWS, just
not in Terraform's state).

The only path forward is `terraform import`, which re-binds the existing
AWS resources to a fresh state file without touching them.

### Step-by-step

```bash
# 1. Move into the bootstrap dir on a fresh checkout.
cd infra/bootstrap

# 2. Recreate terraform.tfvars from the example, with the SAME values
#    that were used originally (account_id, region, owner, cost_center,
#    state_bucket_name, lock_table_name). If you no longer have the
#    original values, see "Reconstructing tfvars from tags" below.
cat > terraform.tfvars <<'EOF'
expected_account_id = "123456789012"
aws_region          = "eu-west-2"
owner               = "flowin-platform-team@hexaware.com"
cost_center         = "UKI-FLOWIN-PROD"
state_bucket_name   = "flowin-tfstate-123456789012-eu-west-2"
lock_table_name     = "flowin-tfstate-locks"
EOF

# 3. Initialise (no remote state for bootstrap; this just downloads
#    the AWS provider).
terraform init

# 4. Import the two existing resources into the new local state.
#    Use the actual bucket and table names — replace the example values.
terraform import aws_s3_bucket.tfstate flowin-tfstate-123456789012-eu-west-2
terraform import aws_dynamodb_table.tflock flowin-tfstate-locks

# 5. Sanity check: plan should now show "no changes". If it shows
#    drift, see "Configuration drift after import" below before
#    applying anything.
terraform plan
```

After step 5 reports no changes, the bootstrap state is restored. The
prod environment's remote state in S3 was never affected by losing the
bootstrap state file — it's a separate state — so once bootstrap is
re-imported, no further recovery action is needed for prod.

### Reconstructing tfvars from tags

`terraform import` produces state, but it does **not** reconstruct
configuration drift. If `plan` after import shows changes, something in
your `terraform.tfvars` does not match the live resources. Most often
that's the `Owner` or `CostCenter` tag (they live in provider
`default_tags`, so they're real on the resources but only appear in
config via tfvars).

You can read the live tags off the resources to recover the original
values:

```bash
# Tags on the state bucket
aws s3api get-bucket-tagging \
  --bucket flowin-tfstate-123456789012-eu-west-2 \
  --query 'TagSet'

# Tags on the lock table
aws dynamodb list-tags-of-resource \
  --resource-arn "arn:aws:dynamodb:eu-west-2:123456789012:table/flowin-tfstate-locks" \
  --query 'Tags'
```

Both should carry `Project=flowin`, `Environment=prod` (or whatever was
set), `Owner`, `CostCenter`, `ManagedBy=terraform`, `Repo`. Plug those
back into `terraform.tfvars` so the next `plan` is clean.

### Avoiding this in the first place

The recovery path works, but it's not free — it requires the operator
to know the bucket and table names, and to reconstruct tfvars. To make
future recovery a non-event, store the bootstrap state file out-of-band
after the first apply. Two reasonable options:

- Encrypt and upload to a **separate** ops S3 bucket in a different
  account (don't put it in the very bucket bootstrap created — same
  blast-radius problem).
- Store it in a team password manager (1Password, BitWarden, etc.) as a
  binary attachment, encrypted at rest by the vault.

Either way, refresh the stored copy whenever bootstrap is re-applied
(rare, but not never — e.g. when bumping provider versions).
