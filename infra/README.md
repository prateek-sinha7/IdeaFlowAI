# VelocityAI — Terraform infrastructure

Terraform for the VelocityAI single-EC2 deployment: one EC2 instance running
nginx + Postgres natively, with the backend (FastAPI/uvicorn) and frontend
(Next.js) as Docker Compose containers pulled from ECR. The backend talks to
AWS Bedrock (Claude Haiku 4.5) for LLM calls.

The codebase follows the **layered reference format**: a one-time `bootstrap`,
a `shared` layer (ECR), and per-environment `foundation` + `app` layers, each
with its own remote-state object. CI/CD is per-environment AWS CodeBuild
runners driven by `buildspec.yml`.

> **Shared account.** This runs in an AWS Organizations account other Hexaware
> projects also use. The cardinal rule: *touch only this project's resources,
> never account-wide settings*. Enforced by the `account_guard` module, the
> per-env IAM deploy roles, and the "no account-wide resources" review rule
> (grep below).

---

## Layout

```
infra/
├── README.md                  # this file
├── buildspec.yml              # CodeBuild pipeline (validate→scan→apply→redeploy)
├── scripts/                   # on-host bootstrap (bootstrap-ec2.sh)
└── terraform/
    ├── bootstrap/             # ONCE: state bucket + lock + KMS + account guard + CI/CD runners (LOCAL state)
    ├── shared/                # ONCE: ECR repos (velocityai/backend, velocityai/frontend) — built once, promoted by tag
    ├── foundation/            # PER-ENV: KMS, network, IAM, secrets, backups  (long-lived)
    ├── app/                   # PER-ENV: compute, DNS, compose+deploy S3 objects, monitoring, resource groups (deploy-time)
    ├── localstack/            # NON-CICD module test fixture (all modules, local state)
    ├── modules/               # reusable modules
    └── policies/              # IAM policy JSON templates
```

### Why foundation / app (and what lives where)

- **foundation** is the slow-changing base for one environment: the project KMS
  CMK, the VPC + endpoints, the EC2 instance role, the SSM Parameter Store
  secrets, and the S3 backup bucket + AWS Backup vault.
- **app** is the deployable unit: the EC2 instance + data EBS volume + EIP, the
  public DNS record, the `docker-compose.yml` + `deploy.env` objects in S3
  (driven by `image_tag`), CloudWatch monitoring, and the Resource Groups. It
  reads foundation's outputs via `terraform_remote_state`.

> **Note — DNS + EIP live in `app`, not `foundation`.** The reference puts its
> data store (RDS) in foundation, but VelocityAI's "database" is Postgres on an
> instance-attached EBS volume, and the EIP/DNS are coupled to the instance
> (`dns` reads the EIP's address; the instance's user-data reads the FQDN).
> Keeping `compute` + `dns` together in `app` avoids a cross-layer state cycle.
> The data EBS volume and EIP carry `prevent_destroy = true`, so they survive
> app rebuilds.

---

## Environments

Three logically-isolated environments in one account: **dev, stage, prod**.
Naming follows the reference convention — **prod is bare**:

| Environment | `name_prefix` | foundation state key | app state key |
|---|---|---|---|
| prod  | `velocityai`        | `velocityai/prod/foundation.tfstate`  | `velocityai/prod/app.tfstate`  |
| stage | `velocityai-stage`  | `velocityai/stage/foundation.tfstate` | `velocityai/stage/app.tfstate` |
| dev   | `velocityai-dev`    | `velocityai/dev/foundation.tfstate`   | `velocityai/dev/app.tfstate`   |

Shared layer state key: `velocityai/shared.tfstate`. Non-overlapping VPC CIDRs:
prod `10.20.0.0/16`, stage `10.30.0.0/16`, dev `10.40.0.0/16`.

Each environment has its own state object, IAM deploy role, CodeBuild runner,
and build log group — strong *logical* isolation in a single account. True
hard isolation needs separate accounts (see the CI/CD section).

---

## Apply order

`bootstrap` (once) → `shared` (once) → `foundation(<env>)` → `app(<env>)`.

### 1. Bootstrap (once per account)

Creates the S3 state bucket, the DynamoDB lock table, a bootstrap KMS key, and
(optionally) the CI/CD runners. Uses **local state**. See
[`terraform/bootstrap/README.md`](terraform/bootstrap/README.md).

```bash
cd infra/terraform/bootstrap
cp bootstrap.tfvars.example bootstrap.tfvars   # edit: account id, region, bucket name
terraform init
terraform apply -var-file=bootstrap.tfvars
```

### 2–4. Shared, foundation, app

Each layer takes its backend config at `init` time (partial config), and the
account id / region as `-var` (so nothing account-specific is committed):

```bash
B=velocityai-tfstate-<account>-<region>   # bootstrap output `state_bucket`
LOCK=velocityai-tfstate-locks
ENV=dev                                    # or stage / prod

# shared (once)
terraform -chdir=infra/terraform/shared init \
  -backend-config="bucket=$B" -backend-config="key=velocityai/shared.tfstate" \
  -backend-config="region=eu-central-1" -backend-config="dynamodb_table=$LOCK" -backend-config="encrypt=true"
terraform -chdir=infra/terraform/shared apply -var="expected_account_id=<account>"

# foundation(<env>)
terraform -chdir=infra/terraform/foundation init \
  -backend-config="bucket=$B" -backend-config="key=velocityai/$ENV/foundation.tfstate" \
  -backend-config="region=eu-central-1" -backend-config="dynamodb_table=$LOCK" -backend-config="encrypt=true"
terraform -chdir=infra/terraform/foundation apply \
  -var-file="$ENV.tfvars" -var="expected_account_id=<account>"

# app(<env>) — image_tag + state_bucket are required
terraform -chdir=infra/terraform/app init \
  -backend-config="bucket=$B" -backend-config="key=velocityai/$ENV/app.tfstate" \
  -backend-config="region=eu-central-1" -backend-config="dynamodb_table=$LOCK" -backend-config="encrypt=true"
terraform -chdir=infra/terraform/app apply \
  -var-file="$ENV.tfvars" -var="expected_account_id=<account>" \
  -var="state_bucket=$B" -var="image_tag=<tag>" -var="alert_email=<email>"
```

In CI this whole sequence runs inside CodeBuild (`buildspec.yml`); operators
only run it manually for the first stand-up or break-glass changes.

---

## CI/CD (per-environment CodeBuild runners)

`bootstrap/cicd.tf` provisions, when `create_gitlab_runner = true`:

- **Shared**: a GitLab CodeConnections connection + the default source
  credential (AWS allows one per account/region).
- **Per environment** (`var.runners`, keyed `dev`/`stage`/`prod`): an IAM
  deploy role (cross-env + confused-deputy trust guards), a CodeBuild project,
  a webhook, and a log group.

Triggers (per `runners[*].trigger_type`): dev/stage on a **branch push**, prod
on a **git tag / GitLab Release**. Each project runs `infra/buildspec.yml`:
`validate → security scan (gitleaks/checkov/trivy) → shared+foundation apply →
build+push backend+frontend images → app apply → SSM redeploy on the host`.
DB migrations run **in-container** (Alembic on backend start).

The frontend image is built **environment-agnostic** (relative URLs nginx
terminates), so one image promotes dev→stage→prod by tag — matching the
shared-ECR promote-by-tag model.

Non-secret per-env config (CORS origins, Bedrock model, alert email) is
injected as `TF_VAR_*` from the runner. **Secrets are never in CodeBuild env**:
`app_secret_key` / `db_password` are auto-generated by the foundation `secrets`
module into SSM SecureStrings.

> **Two shared-account caveats:** (1) the single default GitLab source
> credential is per account/region — coordinate if sibling projects also use
> GitLab CodeConnections; (2) the deploy role's broad `ProvisionStack`
> permissions can't be resource-scoped, and prod's bare `velocityai-*` prefix
> is a superset of `velocityai-stage-*`. Set
> `deploy_permissions_boundary_arn` (scoped to `velocityai-*`) to harden, or
> use separate accounts for true isolation.

**One-time manual step:** after the first bootstrap apply, authorize the GitLab
connection once in the AWS console (Developer Tools → Settings → Connections →
"Update pending connection"). Until then webhooks won't fire.

---

## Account / region guard

Every layer instantiates `modules/account_guard` first: it compares the live
caller account id + region to `expected_account_id` / `aws_region` and aborts
plan/apply on mismatch (a `terraform_data` precondition + `check` blocks).

## Tagging

Provider `default_tags`: `Project=velocityai`, `Environment=<env>`,
`ManagedBy=terraform`, `Repo`, `Owner`, `CostCenter`. Plus a per-resource
`Component` tag (`network`/`compute`/`storage`/`monitoring`/`iam`/`secrets`/
`ecr`/`cicd`/`tfstate`) so Resource Groups can split by component.

## What this does NOT deploy (forbidden in the shared account)

No `aws_organizations_*`, `aws_iam_account_*`, `aws_s3_account_public_access_block`,
`aws_config_*`, `aws_securityhub_*`, `aws_macie2_account`, `aws_guardduty_detector`,
or `aws_*default*`. Audit:

```bash
grep -rE "aws_organizations_|aws_iam_account_|aws_s3_account_public_access_block|aws_config_|aws_securityhub_|aws_macie2_account|aws_guardduty_detector" infra/terraform
```

That should return zero matches.

## Secrets

`app_secret_key` and `db_password` default empty → the `secrets` module
generates strong `random_password` values into SSM SecureStrings (project CMK).
The on-host `velocityai-load-secrets` composes `/etc/velocityai/app.env` from
`/velocityai/<env>/*` at every `velocityai-app` start. Override only to import
an existing key via `TF_VAR_app_secret_key` / `TF_VAR_db_password` (never
committed).

## LocalStack

`terraform/localstack/` is a non-CICD fixture that applies the whole module set
against LocalStack with local state — for offline module testing. See its
[README](terraform/localstack/README.md).

---

## App-code rebrand (out of scope, follow-up)

This conversion rebranded the **infrastructure** (Terraform, on-host scripts,
deploy artifacts) `flowin → velocityai`. The application code under `backend/`
and `frontend/` still contains `flowin` in **product/contract** surfaces that
are a separate, breaking-change effort:

- the `/flowin-handoff` feature name and its agents/routes;
- the API-key prefix `flowin_` and the `X-Flowin-API-Key` header;
- the installer-generated client CLI env vars (`FLOWIN_API_URL`, `FLOWIN_API_KEY`, …);
- a stale `/opt/flowin/backend` comment in `backend/alembic/env.py`.

The infra↔app contract is via generic env vars (`DATABASE_URL`, `SECRET_KEY`,
`CORS_ORIGINS`) written to `/etc/velocityai/app.env`, so the infra rebrand does
**not** break the app. Renaming the app surfaces above (API versioning, key
migration, feature rename) should be planned separately.
