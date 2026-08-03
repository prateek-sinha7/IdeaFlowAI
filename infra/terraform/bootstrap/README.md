# VelocityAI Terraform — bootstrap

This is the **one-time** bootstrap that creates the S3 bucket and DynamoDB
table the rest of the VelocityAI Terraform uses for remote state. It runs with
**local state** and is committed to git so it can be re-run if the bucket is
ever destroyed (don't actually destroy it; it's marked `prevent_destroy`).

It also (optionally) provisions the GitHub Actions CI/CD identity — see
[`github_oidc.tf`](./github_oidc.tf). Gated behind `create_github_oidc` and off
by default, so a plain bootstrap creates only the state backend.

## What it creates

- `aws_kms_key` — a bootstrap-local CMK (rotation on, 30-day deletion window)
  that encrypts the state bucket and the lock table.
- `aws_s3_bucket` for Terraform state (versioned, SSE-KMS, TLS-only, BPA on).
- `aws_dynamodb_table` for state locking (PITR + SSE-KMS).
- When `create_github_oidc = true`: the GitHub Actions OIDC identity provider
  (or an adopted existing one), **one ECR-only build role**, and **one deploy
  role per admitted GitHub Environment** — each trusting exactly one OIDC
  subject and scoped to only that environment's SSM prefix and
  `Environment`-tagged instances. (A single shared role cannot isolate
  environments: the `sub` claim is checked once at AssumeRole and never again
  per API call — see the header of [`github_oidc.tf`](./github_oidc.tf).) See
  [`../../../docs/GITHUB_CICD_SETUP.md`](../../../docs/GITHUB_CICD_SETUP.md)
  for the full operator guide.

It creates **nothing else**. In particular it does **not** touch any
account-wide setting (no `aws_s3_account_public_access_block`, no
`aws_organizations_*`, etc.).

## Account-ID guard

The very first thing this module evaluates is a `terraform_data` resource with
`lifecycle.precondition` blocks comparing the live caller's account ID and
region to the effective expected values.

- **Region** is always checked against `var.aws_region`.
- **Account ID**: leave `var.expected_account_id` blank (the default) and the
  guard adopts whatever account the AWS CLI / Terraform provider is currently
  authenticated to — i.e. the live `aws sts get-caller-identity` account, so it
  becomes a no-op that just records the account it ran against. Set
  `var.expected_account_id` to a concrete 12-digit id to make it a hard pin that
  aborts plan/apply on any mismatch (recommended for shared / multi-account org
  setups).

A mismatch aborts plan/apply with a clear error before anything is created.

## Run it once

```bash
cd infra/terraform/bootstrap

cat > bootstrap.tfvars <<'EOF'
# expected_account_id omitted -> auto-adopt the authenticated AWS CLI account.
# Set it to a 12-digit id to hard-pin the guard.
aws_region          = "eu-central-1"
owner               = "velocityai-platform-team@hexaware.com"
cost_center         = "UKI-VELOCITYAI-PROD"
state_bucket_name   = "velocityai-tfstate-eu-central-1"
lock_table_name     = "velocityai-tfstate-locks"
EOF

terraform init
terraform plan  -var-file=bootstrap.tfvars
terraform apply -var-file=bootstrap.tfvars
```

After it completes, note the `state_bucket` / `state_bucket_name` output.
Operators (and the CI pipeline) wire it into each layer at `init` time:

```bash
terraform -chdir=infra/terraform/foundation init \
  -backend-config="bucket=<state_bucket_name>" \
  -backend-config="key=velocityai/<env>/foundation.tfstate" \
  -backend-config="region=eu-central-1" \
  -backend-config="dynamodb_table=velocityai-tfstate-locks" \
  -backend-config="encrypt=true"
```

The per-layer state keys are:

| Layer | State key |
|---|---|
| `shared` | `velocityai/shared.tfstate` |
| `foundation` (per env) | `velocityai/<env>/foundation.tfstate` |
| `app` (per env) | `velocityai/<env>/app.tfstate` |

## Re-running

Safe. The KMS key, state bucket, and lock table are all `prevent_destroy = true`.
Subsequent applies are idempotent.

## Recovery — when the bootstrap state file is lost

**Why this matters.** Bootstrap deliberately uses **local state** (in
`infra/terraform/bootstrap/terraform.tfstate`, gitignored). It has to: it's the
chicken-and-egg — the S3 bucket that backs every layer's remote state is the
bucket bootstrap creates. There is nowhere remote to put bootstrap's own state.

The consequence: if the working copy is wiped and the local state file isn't
recovered, **`terraform apply` is not a recovery path**. The bootstrap-created
resources have `prevent_destroy = true`, but more immediately, with no state
file Terraform doesn't know they exist — so a fresh `apply` would try to
*create* the bucket and the lock table, and fail at the bucket step with
`BucketAlreadyOwnedByYou` (because the real bucket is still in AWS, just not in
Terraform's state).

The only path forward is `terraform import`, which re-binds the existing AWS
resources to a fresh state file without touching them.

### Step-by-step

```bash
# 1. Move into the bootstrap dir on a fresh checkout.
cd infra/terraform/bootstrap

# 2. Recreate bootstrap.tfvars from the example, with the SAME values that
#    were used originally (account_id, region, owner, cost_center,
#    state_bucket_name, lock_table_name). If you no longer have the original
#    values, see "Reconstructing tfvars from tags" below.
cat > bootstrap.tfvars <<'EOF'
# expected_account_id omitted -> auto-adopt the authenticated AWS CLI account.
aws_region          = "eu-central-1"
owner               = "velocityai-platform-team@hexaware.com"
cost_center         = "UKI-VELOCITYAI-PROD"
state_bucket_name   = "velocityai-tfstate-eu-central-1"
lock_table_name     = "velocityai-tfstate-locks"
EOF

# 3. Initialise (no remote state for bootstrap; this just downloads providers).
terraform init

# 4. Import the existing resources into the new local state. Use the actual
#    names — replace the example values.
terraform import -var-file=bootstrap.tfvars aws_kms_key.bootstrap <KMS_KEY_ID>
terraform import -var-file=bootstrap.tfvars aws_s3_bucket.tfstate velocityai-tfstate-eu-central-1
terraform import -var-file=bootstrap.tfvars aws_dynamodb_table.tflock velocityai-tfstate-locks

# 5. Sanity check: plan should now show "no changes". If it shows drift, see
#    "Reconstructing tfvars from tags" below before applying anything.
terraform plan -var-file=bootstrap.tfvars
```

After step 5 reports no changes, the bootstrap state is restored. The layers'
remote state in S3 was never affected by losing the bootstrap state file — it's
separate state — so once bootstrap is re-imported, no further recovery action
is needed for the layers.

### Reconstructing tfvars from tags

`terraform import` produces state, but it does **not** reconstruct
configuration drift. If `plan` after import shows changes, something in your
`bootstrap.tfvars` does not match the live resources. Most often that's the
`Owner` or `CostCenter` tag (they live in provider `default_tags`, so they're
real on the resources but only appear in config via tfvars).

```bash
# Tags on the state bucket
aws s3api get-bucket-tagging \
  --bucket velocityai-tfstate-eu-central-1 \
  --query 'TagSet'

# Tags on the lock table
aws dynamodb list-tags-of-resource \
  --resource-arn "arn:aws:dynamodb:eu-central-1:123456789012:table/velocityai-tfstate-locks" \
  --query 'Tags'
```

Both should carry `Project=velocityai`, `Environment=bootstrap`, `Owner`,
`CostCenter`, `ManagedBy=terraform`, `Repo`. Plug those back into
`bootstrap.tfvars` so the next `plan` is clean.

### Avoiding this in the first place

Store the bootstrap state file out-of-band after the first apply: encrypt and
upload to a **separate** ops bucket in a different account (don't put it in the
very bucket bootstrap created — same blast-radius problem), or store it in a
team password manager as an encrypted attachment. Refresh the stored copy
whenever bootstrap is re-applied.
