# VelocityAI infrastructure — operations runbook

Operational, step-by-step. For the architecture and layout see
[`../README.md`](../README.md).

Apply order is always: **bootstrap → shared → foundation(env) → app(env)**.

---

## 0. Shared-account coordination (do this first)

This runs in a shared AWS Organizations account. Before bootstrapping:

1. **GitLab default credential is one per account/region.** `bootstrap/cicd.tf`
   registers VelocityAI's GitLab CodeConnections as CodeBuild's default GitLab
   source credential. If a sibling project already registered one, coordinate —
   only one can be the default. (Alternatively, run the runners in a region no
   sibling uses GitLab in.)
2. **Permissions boundary.** Set `deploy_permissions_boundary_arn` (scoped to
   `velocityai-*`) on the bootstrap so the per-env deploy roles cannot touch
   non-project resources even via the broad `ProvisionStack` statement. Ask the
   account's security team for (or create) a `velocityai-*` boundary policy.
3. Confirm the **account ID** and **region** (`eu-central-1`) with whoever owns
   the account; the `account_guard` aborts on a mismatch.

---

## 1. Bootstrap (once per account)

```bash
cd infra/terraform/bootstrap
cp bootstrap.tfvars.example bootstrap.tfvars     # edit account id, bucket name, region
terraform init
terraform apply -var-file=bootstrap.tfvars
```

To also create the CI/CD runners, set in `bootstrap.tfvars`:

```hcl
create_gitlab_runner            = true
gitlab_repo_url                 = "https://gitlab.com/hexaware-uki/velocityai.git"
deploy_permissions_boundary_arn = "arn:aws:iam::<acct>:policy/velocityai-boundary"  # recommended
runners = {
  dev   = { branch = "dev",   trigger_type = "branch",  cors_origins = "[\"https://<dev-fqdn>\"]",   bedrock_model_id = "anthropic.claude-haiku-4-5-20251001-v1:0", bedrock_inference_profile_id = "eu.anthropic.claude-haiku-4-5-20251001-v1:0", alert_email = "velocityai-oncall@hexaware.com" }
  stage = { branch = "stage", trigger_type = "branch",  cors_origins = "[\"https://<stage-fqdn>\"]", bedrock_model_id = "anthropic.claude-haiku-4-5-20251001-v1:0", bedrock_inference_profile_id = "eu.anthropic.claude-haiku-4-5-20251001-v1:0", alert_email = "velocityai-oncall@hexaware.com" }
  prod  = { branch = "main",  trigger_type = "release", cors_origins = "[\"https://<prod-fqdn>\"]",  bedrock_model_id = "anthropic.claude-haiku-4-5-20251001-v1:0", bedrock_inference_profile_id = "eu.anthropic.claude-haiku-4-5-20251001-v1:0", alert_email = "velocityai-oncall@hexaware.com" }
}
```

Note the `state_bucket` output (call it `$B` below).

### 1a. Authorize the GitLab connection (one-time, manual)

The connection is created PENDING. In the AWS console: **Developer Tools →
Settings → Connections → velocityai-gitlab → Update pending connection**, and
complete the OAuth handshake. Webhooks do not fire until this is done.

---

## 2. Shared layer (once)

```bash
LOCK=velocityai-tfstate-locks ; REGION=eu-central-1 ; ACCT=<account-id>
terraform -chdir=infra/terraform/shared init \
  -backend-config="bucket=$B" -backend-config="key=velocityai/shared.tfstate" \
  -backend-config="region=$REGION" -backend-config="dynamodb_table=$LOCK" -backend-config="encrypt=true"
terraform -chdir=infra/terraform/shared apply -var="expected_account_id=$ACCT" -var="aws_region=$REGION"
```

Creates the `velocityai/backend` + `velocityai/frontend` ECR repos.

---

## 3. Per-environment foundation + app

Do this per environment (`dev`, then `stage`, then `prod`). In CI this is what
`infra/buildspec.yml` runs; the manual form for a first stand-up:

```bash
ENV=dev   # then stage, then prod

terraform -chdir=infra/terraform/foundation init -reconfigure \
  -backend-config="bucket=$B" -backend-config="key=velocityai/$ENV/foundation.tfstate" \
  -backend-config="region=$REGION" -backend-config="dynamodb_table=$LOCK" -backend-config="encrypt=true"
terraform -chdir=infra/terraform/foundation apply \
  -var-file="$ENV.tfvars" -var="expected_account_id=$ACCT" -var="aws_region=$REGION"

terraform -chdir=infra/terraform/app init -reconfigure \
  -backend-config="bucket=$B" -backend-config="key=velocityai/$ENV/app.tfstate" \
  -backend-config="region=$REGION" -backend-config="dynamodb_table=$LOCK" -backend-config="encrypt=true"
terraform -chdir=infra/terraform/app apply \
  -var-file="$ENV.tfvars" -var="expected_account_id=$ACCT" -var="aws_region=$REGION" \
  -var="state_bucket=$B" -var="image_tag=<tag>" -var="alert_email=velocityai-oncall@hexaware.com"
```

(`app_secret_key`/`db_password` auto-generate; override only via
`TF_VAR_app_secret_key`/`TF_VAR_db_password`.)

---

## 4. CI/CD triggers (steady state)

Once the runners exist and the connection is authorized:

| Environment | Trigger |
|---|---|
| dev   | push to the `dev` branch |
| stage | push to the `stage` branch |
| prod  | a **git tag / GitLab Release** (a plain push to `main` does **not** deploy prod) |

Each build runs `infra/buildspec.yml`: validate → gitleaks/checkov/trivy →
shared+foundation apply → build+push images → app apply → SSM redeploy. DB
migrations run in-container on backend start.

**Rollback** = re-deploy a previous tag: trigger the env with an earlier image
tag (the prior image is retained in ECR — release tags indefinitely, branch
builds for the last N). No rebuild needed.

---

## 5. Day-2 (after the first app apply)

These are deliberately outside Terraform:

1. **On-host full bootstrap.** Run `infra/scripts/bootstrap-ec2.sh` on the new
   instance via SSM RunCommand (Postgres init, nginx, certbot, Docker, systemd
   units). It reads `/etc/velocityai/bootstrap.env` (written by user-data) and
   pulls `config/docker-compose.yml` + `config/deploy.env` from the backup
   bucket. After this, CI redeploys are just `docker compose pull && up -d`.
2. **Confirm the SNS email** subscription (AWS emails `alert_email`).
3. **Request a Bedrock quota increase** for Claude Haiku 4.5 before load tests.
4. **TLS:** certbot issues against the FQDN (nip.io works out of the box; a real
   domain needs the Route 53 path — set `use_nip_io = false` + `route53_zone_name`).

---

## 6. Provider lock files (CI portability note)

The committed `.terraform.lock.hcl` files carry the full `zh:` hash set (so CI
on Linux verifies the downloaded provider) plus a single-platform `h1:`. To
make local `terraform init` work offline on Linux/macOS/Windows alike, run once
in a networked environment and commit the result:

```bash
for d in bootstrap shared foundation app localstack; do
  terraform -chdir=infra/terraform/$d providers lock \
    -platform=linux_amd64 -platform=darwin_arm64 -platform=darwin_amd64 -platform=windows_amd64
done
```

---

## 7. Break-glass / destroy

Durable resources carry `prevent_destroy = true` (KMS CMK, S3 backup bucket,
AWS Backup vault/plan/selection, data EBS volume, EIP, IAM role + profile,
state bucket + lock table). To intentionally remove one, edit out its
`prevent_destroy`, apply, then destroy — only in a declared maintenance window
with a confirmed off-site copy of any data it holds. The LocalStack fixture has
a `destroy.sh` that `state rm`s these first (safe — ephemeral local state).
```
