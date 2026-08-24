# VelocityAI — Terraform infrastructure

Terraform for the VelocityAI single-EC2 deployment: one EC2 instance running
nginx + Postgres natively, with the backend (FastAPI/uvicorn) and frontend
(Next.js) as Docker Compose containers pulled from ECR. The backend talks to
AWS Bedrock (Claude Haiku 4.5) for LLM calls.

The codebase follows the **layered reference format**: a one-time `bootstrap`,
a `shared` layer (ECR), and per-environment `foundation` + `app` layers, each
with its own remote-state object. CI/CD is GitHub Actions
(`.github/workflows/ci.yml` + `deploy.yml`) — it does not run Terraform; it
only builds/pushes images and redeploys containers via SSM RunCommand onto
infrastructure Terraform already created. See
[`docs/GITHUB_CICD_SETUP.md`](../docs/GITHUB_CICD_SETUP.md) for the full
operator guide. The retired GitLab/CodeBuild pipeline is documented in that
same file's §9 for history only.

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
├── scripts/                   # on-host bootstrap (bootstrap-ec2.sh, reconcile-host-config.sh)
└── terraform/
    ├── bootstrap/             # ONCE: state bucket + lock + KMS + account guard + GitHub OIDC identity (LOCAL state)
    ├── shared/                # ONCE: ECR repos (velocityai/backend, velocityai/frontend) — built once, promoted by tag
    ├── foundation/            # PER-ENV: KMS, network, IAM, secrets, backups  (long-lived)
    ├── app/                   # PER-ENV: compute, DNS, compose+deploy S3 objects, monitoring, resource groups (deploy-time)
    ├── localstack/            # NON-CICD module test fixture (all modules, local state)
    ├── modules/               # reusable modules
    └── policies/              # IAM policy JSON templates
```

### Why foundation / app (and what lives where)

> **Cognito.** As of the Cognito migration
> (`.planning/COGNITO-MIGRATION-PLAN.md`), the **foundation** layer also creates
> an Amazon Cognito User Pool per environment — the credential authority for
> user logins and, via four fixed groups, the role/tier authority. It is gated
> on `cognito_enabled` (default **false**), so an environment is unaffected
> until an operator opts in. Module: `infra/terraform/modules/cognito`.
> Cutover procedure: **`infra/COGNITO-CUTOVER-RUNBOOK.md`**.
>
> No Cognito Identity Pool and no hosted UI are created: the browser never calls
> AWS directly (the backend mediates auth via `AdminInitiateAuth`), so temporary
> AWS credentials in the browser have no use case here.

- **foundation** is the slow-changing base for one environment: the project KMS
  CMK, the VPC + endpoints, the EC2 instance role, the Cognito user pool, the SSM Parameter Store
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

Each environment has its own state object, EC2 instance role, SSM parameter
tree, **and its own GitHub Actions deploy role** — strong *logical* isolation in
a single account. A dev deploy cannot reach a prod box because the dev role's
credentials are not trusted for prod and its `ssm:SendCommand` names only
`Environment=dev` instances; this is enforced by the identity, not by a
condition the caller has already satisfied. True hard isolation still needs
separate accounts (see the CI/CD section).

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

This sequence is never run by CI — GitHub Actions does not execute Terraform.
Operators run it manually for the first stand-up of an environment, and
thereafter only when infrastructure itself changes (instance size, alarm
thresholds, DNS strategy). Shipping application code does not need an apply;
see the CI/CD section below.

---

## CI/CD (GitHub Actions — no Terraform in the pipeline)

`bootstrap/github_oidc.tf` provisions, when `create_github_oidc = true`:

- The `token.actions.githubusercontent.com` OIDC identity provider (or an
  adopted existing one — `github_oidc_create_provider = false`).
- **One ECR-only build role** (`<github_cicd_role_name>-build`, default
  `velocityai-gha-deploy-build`): push/pull on the two shared repositories and
  nothing else — no SSM, no KMS, no reach to any EC2 instance.
- **One deploy role per environment** (`<github_cicd_role_name>-<env>`), each
  trusting **exactly one** OIDC subject
  (`repo:<github_org_repo>:environment:<env>`, matched with `StringEquals`) and
  scoped to exactly one SSM prefix (`/velocityai/<env>/*`) and one EC2
  `Environment` tag value.

  This replaced a single shared role that trusted all three environments. That
  design could not isolate them: the OIDC `sub` is evaluated once, at
  `sts:AssumeRoleWithWebIdentity`, and never re-checked per API call — so a
  `dev` job holding those credentials could write `/velocityai/prod/*` and send
  commands to a prod-tagged box. `github_org_repo` must now also be an exact
  `owner/repo` (wildcards are rejected by validation), because a glob admits
  any similarly-prefixed owner/repository in any organisation.

Two workflows in `.github/workflows/`:

- **`ci.yml`** — lint/test/security-scan quality gate (ruff, pyright,
  import-linter, vulture, pytest; eslint, vitest, build; gitleaks, checkov,
  trivy config, tflint). No AWS access.
- **`deploy.yml`** — triggered by a push to `dev`/`staging` or a `v*` tag (or
  manual dispatch). The CI gate must be green on the commit *before* anything is
  pushed to ECR. Then: OIDC-assume the **build** role → build + push the backend
  and frontend images → block on a HIGH/CRITICAL image scan of the exact digests
  → OIDC-assume that environment's **deploy** role → push GitHub-configured
  variables/secrets to SSM → run `.github/scripts/remote-deploy.sh` on the
  tagged EC2 instance via SSM RunCommand (compose file + reconcile script
  shipped inline in the payload, images pinned **by digest** in
  `/etc/velocityai/app.env`, then health-checked). DB migrations run
  **in-container** (Alembic on backend start).

  A `v*` tag only reaches prod if its commit is an ancestor of `main` — tag
  names alone prove nothing about what is being released. Pair that with
  GitHub-side protected tag rules and the prod Environment's reviewers.

  The health gate covers the backend, the frontend **and** the nginx ingress; a
  failure rolls the host back to the previously pinned digests and verifies that
  the rollback restored service. Database migrations are **not** rolled back —
  that is what the pre-deploy `pg_dump` on stage/prod is for.

**Terraform does not run in this pipeline.** `bootstrap`, `shared`,
`foundation(<env>)`, and `app(<env>)` are applied by an operator (see
[Apply order](#apply-order) below); GitHub Actions only builds images and
redeploys containers onto infrastructure that already exists. Full operator
guide: [`docs/GITHUB_CICD_SETUP.md`](../docs/GITHUB_CICD_SETUP.md).

The frontend image is built **environment-agnostic** (relative URLs nginx
terminates), so one image promotes dev→stage→prod unchanged. Promotion is **by
digest**, not by tag: the shared ECR repositories are `IMMUTABLE`, deploys
reference `repo@sha256:...`, and no floating `-latest` alias takes part. A
re-run of an already-built commit adopts the existing image's digest instead of
re-pushing it, which is what keeps immutable tags compatible with retries.

Non-secret per-env config (CORS origins, Bedrock model, alert email) is pushed
from GitHub Environment variables into SSM on every deploy. **Secrets are never
in GitHub Actions env beyond the push itself**: `SECRET_KEY` is a GitHub secret
pushed as an SSM SecureString; `DATABASE_PASSWORD` is host-generated by
`bootstrap-ec2.sh` and never passes through GitHub at all.

> **Shared-account caveat:** each environment now has its own deploy role, whose
> `ssm:SendCommand` is restricted to instances carrying *that* environment's
> `Environment` tag, so CI cannot cross environments. The residual risk is not
> in CI: the broad provisioning Terraform itself performs is applied by an
> operator, and cannot be resource-scoped everywhere. Set
> `deploy_permissions_boundary_arn` (scoped to `velocityai-*`) to harden, or use
> separate AWS accounts for true hard isolation. Note also that the per-role
> boundary is what stops a compromised CI role from creating *new* IAM
> identities outside the project namespace.

**Retired:** the previous GitLab/CodeBuild pipeline (`infra/buildspec.yml`,
`bootstrap/cicd.tf`) is gone. See `docs/GITHUB_CICD_SETUP.md` §9 for a history
note; if you're auditing the AWS account for leftover resources, see that
same section's break-glass/cleanup pointers.

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
