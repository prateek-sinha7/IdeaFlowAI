# GitHub Actions CI/CD Setup — VelocityAI

Comprehensive operator guide for the GitHub Actions CI/CD pipeline
(`ci.yml` + `deploy.yml`). This replaces the retired GitLab/CodeBuild pipeline.

**Design principles (locked):**

- **No Terraform in CI/CD.** The pipeline does not run `terraform apply`. AWS
  resources (OIDC provider, deploy role) are managed via
  `infra/terraform/bootstrap/github_oidc.tf` and applied once by an admin.
- **GitHub is the single source of truth for environment config.** Config flows
  GitHub → SSM Parameter Store → the running services on each deploy.
- **OIDC only — no static AWS keys** are ever stored in GitHub.
- **No SSH, no open port 22.** Deploys run through SSM RunCommand.
- **Zero host-script changes.** The on-host `velocityai-load-secrets` loader and
  `velocityai-app.service` systemd unit are used as-is.

> **Prerequisite:** the target EC2 instances must already be provisioned and
> bootstrapped via `infra/scripts/bootstrap-ec2.sh` (which installs Docker,
> Postgres, nginx, the `velocityai-load-secrets` loader, and the
> `velocityai-app.service` systemd unit). This runbook only adds the
> GitHub-to-AWS authentication and deploy machinery on top of that existing
> host setup.

> **Naming: environment names are `dev` / `stage` / `prod`, NOT `dev` /
> `staging` / `production`.** This matches the short names already used by
> the live AWS infra — EC2 `Environment` tags, SSM `/velocityai/<env>/*`
> prefixes, and the `github-cicd` IAM role's `ssm:resourceTag/Environment`
> condition are all `dev`/`stage`/`prod`. **Branch names are longer** and do
> NOT map 1:1 to environment names:
>
> | Git branch/tag | GitHub Environment | SSM prefix | EC2 tag |
> |---|---|---|---|
> | `dev` branch | `dev` | `/velocityai/dev` | `Environment=dev` |
> | `staging` branch | `stage` | `/velocityai/stage` | `Environment=stage` |
> | `v*` tag (from `main`) | `prod` | `/velocityai/prod` | `Environment=prod` |
>
> `deploy.yml`'s `resolve` job encodes this mapping — see [§4](#4-trigger-and-tag-matrix).

---

## Table of Contents

1. [What You Need to Do — Operator Checklist](#0-what-you-need-to-do--operator-checklist)
2. [How the Pipeline Works](#how-the-pipeline-works)
3. [Account-Level AWS Setup](#1-account-level-aws-setup-once)
4. [Per-Environment AWS Setup](#2-per-environment-aws-setup)
5. [GitHub Repository Configuration](#3-github-repository-configuration)
6. [Trigger and Tag Matrix](#4-trigger-and-tag-matrix)
7. [First Deploy and Validation](#5-first-deploy-and-validation)
8. [Verification Checklists](#6-verification-checklists)
9. [Troubleshooting](#7-troubleshooting)
10. [Rollback](#8-rollback)
11. [GitLab/CodeBuild (retired)](#9-gitlabcodebuild-retired)
12. [Reference: config key mapping](#10-reference-config-key-mapping)
13. [Architecture Diagram](#11-architecture-diagram)
14. [Appendix A — Connecting GitHub OIDC with AWS (detailed)](#12-appendix-a--connecting-github-oidc-with-aws-detailed)

---

## 0. What You Need to Do — Operator Checklist

This is the end-to-end path from "code merged" to "three environments deploying
automatically." Detailed commands for each step live in the numbered sections
below. Do **dev first**, validate it end-to-end, then repeat for `stage` and
`prod`. Remember: the GitHub Environment names are `dev` / `stage` / `prod`
(not `staging` / `production`) — see the naming callout above.

### Stage 0 — Commit and push (unblocks `ci.yml`)

- [ ] Review changes: `git status`, `git diff`
- [ ] Commit the CI/CD files + fixes
- [ ] Push the branch and open a PR — this triggers `ci.yml` (lint/test/scan, no
      AWS access needed). Confirm it goes green before proceeding.

### Stage 1 — Account-level AWS setup (once) — [§1](#1-account-level-aws-setup-once)

- [ ] Create the GitHub OIDC identity provider (§1.1)
- [ ] Create ECR repos `velocityai/backend` + `velocityai/frontend` (§1.2)
- [ ] Attach ECR lifecycle policies (§1.3)

### Stage 2 — Per-environment AWS setup (dev, then stage, then prod) — [§2](#2-per-environment-aws-setup)

- [ ] Create IAM deploy role `velocityai-gha-deploy-<ENV>` with OIDC trust (§2.1)
- [ ] Tag the EC2 instance `Environment=<ENV>` (§2.2) — **load-bearing**
- [ ] Confirm/create the KMS key for SecureString params (§2.3)
- [ ] Seed the required SSM parameters (§2.4)
- [ ] Store the instance ID at `/velocityai/<ENV>/deploy/instance_id` (§2.5)

### Stage 3 — GitHub configuration — [§3](#3-github-repository-configuration)

- [ ] Create `dev`, `stage`, `prod` Environments (§3.1) — **not** `staging`/`production`
- [ ] Set protection rules (prod requires reviewer + `v*` tags) (§3.1)
- [ ] Add per-environment Variables (§3.2)
- [ ] Add per-environment Secrets (§3.2)

### Stage 4 — First deploy + validation — [§5](#5-first-deploy-and-validation)

- [ ] Trigger a `dev` deploy (push to `dev` branch or manual dispatch)
- [ ] Watch `deploy.yml`: build → deploy → health check
- [ ] Validate the dev environment is serving the new build (§6)
- [ ] Repeat Stages 2–3 for `stage` (triggered by the `staging` branch), then
      `prod` (triggered by a `v*` tag)
- [ ] Decommission the old GitLab/CodeBuild pipeline (§9)

### Decisions you must confirm before Stage 2

- **GitHub org/repo slug** — `Hexaware-HnI/velocityai`. This lives in exactly one
  place: the OIDC trust policies' `sub` condition (§2.1), set via Terraform's
  `github_org_repo`. `deploy.yml` does **not** hardcode the slug. The trust
  condition is an exact `StringEquals` match with no wildcards, so a slug
  mismatch — or an org/repo rename — means **every deploy fails at the OIDC auth
  step** until the trust policy is updated. That is intentional: a wildcard that
  absorbed renames would also admit any similarly-named repository in any
  organisation.
- **OIDC thumbprint** (§1.1) — verify it is current if setting up after mid-2026.
- **AWS region** — this guide uses `eu-central-1` throughout. Change everywhere
  if your account uses a different region.
- **IAM role's `ssm:SendCommand` statement must NOT put the `Environment` tag
  condition on `Resource: "*"`.** `SendCommand` authorizes against both the
  target instance AND the `AWS-RunShellScript` document; the document has no
  `Environment` tag, so a single tag-conditioned `Resource: "*"` statement can
  never be satisfied and every deploy fails with `AccessDeniedException`. Split
  it into two statements — see the corrected policy in [§2.1](#21-iam-deploy-role).

### What is NOT on your plate

- Host scripts (`bootstrap-ec2.sh`, `velocityai-load-secrets`) — untouched.
- `docker-compose.yml`, both Dockerfiles, `backend/docker-entrypoint.sh` — untouched.
- Terraform — stays dormant/reference-only.

---

## How the Pipeline Works

There are two workflows in `.github/workflows/`:

### `ci.yml` — quality gate (no AWS access)

Runs on every `pull_request` and `push`. Three parallel jobs:

- **backend** — `uv`-based: creates a venv, installs from `requirements*.txt`,
  then runs `compileall`, `ruff check`, `pyright`, `lint-imports`, `vulture`,
  and `pytest` (against SQLite — no Postgres service needed).
- **frontend** — Node 20: `npm ci`, `npm run lint`, `npm run test` (vitest
  single-pass), `npm run build`.
- **security-scan** — `gitleaks`, `checkov`, `trivy config`, `tflint`. All
  scanners are installed as checksum-verified release binaries (not via the
  compromised `aquasecurity/*` actions — see the `ci.yml` header for the
  CVE-2026-33634 rationale).

`ci.yml` has `permissions: contents: read` and no OIDC token — it cannot touch
AWS. It is a pure gate.

### `deploy.yml` — build, push, redeploy

Runs on push to the `dev`/`staging` branches, on `v*` tags, or via manual
dispatch. Four jobs:

1. **gate** — calls `ci.yml` as a reusable workflow (lint + test + scan on the
   same commit). **Blocks `build`**, so nothing is published to the shared ECR
   registry until CI is green on that commit.
2. **resolve** — computes the target environment (`dev`/`stage`/`prod`) and
   image tag from the trigger, per the branch/tag → environment mapping above.
   Enforces prod = `v*` tag (hard fail unless `allow_untagged_prod` override)
   **and** that the commit is an ancestor of `main` — a `v*` tag can be created
   on any commit, so the tag name alone proves nothing about what is shipping.
3. **build** — OIDC-assumes the shared **build** role (`AWS_BUILD_ROLE_ARN`;
   ECR-only, no SSM/KMS/EC2 reach), logs into ECR, and first *probes* for an
   existing image with this tag: on a re-run it adopts that image's digest
   instead of re-pushing, which is what keeps `IMMUTABLE` repositories
   compatible with retries. Otherwise it builds the backend (with the
   `opendesign` named build context) and frontend images and pushes them to the
   shared `velocityai/{backend,frontend}` repos under a single `:<tag>` — there
   is no `:<env>-latest` alias. It then scans both images **by digest** with
   trivy at HIGH,CRITICAL and **fails the build** on any fixable finding, and
   outputs the two digests for the deploy job.
4. **deploy** — OIDC-assumes **that environment's own deploy role**
   (`AWS_DEPLOY_ROLE_ARN`), pushes config from GitHub variables/secrets to SSM
   Parameter Store (SecureStrings encrypted with the per-env project CMK alias),
   then runs an SSM RunCommand on the tagged EC2 instance that: asserts
   preconditions (**including that the host's own environment matches the deploy
   target — a mismatch aborts**), writes `docker-compose.yml` (inline, base64),
   pins the images **by digest** (`repo@sha256:...`) in
   `/etc/velocityai/app.env`, runs a pre-deploy `pg_dump` (stage/prod — blocks
   on failure), and recreates the stack. It then health-checks the backend, the
   frontend and the nginx ingress; on failure it **rolls back** to the
   previously pinned digests and verifies service was restored. The workflow
   polls the command to completion either way.

Migrations (`alembic upgrade head`) run automatically inside
`backend/docker-entrypoint.sh` when the container starts — the deploy does not
run them separately.

---

## 1. Account-Level AWS Setup (once)

Run these once per AWS account, using an admin profile. Region is `eu-central-1`
throughout — change if needed.

### 1.1 GitHub OIDC Identity Provider

Lets GitHub Actions authenticate to AWS with short-lived tokens, no stored keys.

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --thumbprint-list "1c58a3a8518e8759bf075b76b750d4f2df264fcd" \
  --client-id-list "sts.amazonaws.com" \
  --region eu-central-1
```

> The thumbprint is GitHub's current intermediate CA fingerprint. Verify at
> https://github.blog/changelog/ if creating after 2026-07. (Modern AWS actually
> validates the OIDC cert chain against trusted CAs, so the thumbprint is largely
> legacy — but the API still requires the field.)

### 1.2 Shared ECR Repositories

```bash
# Backend
aws ecr create-repository \
  --repository-name velocityai/backend \
  --image-tag-mutability MUTABLE \
  --image-scanning-configuration scanOnPush=true \
  --region eu-central-1

# Frontend
aws ecr create-repository \
  --repository-name velocityai/frontend \
  --image-tag-mutability MUTABLE \
  --image-scanning-configuration scanOnPush=true \
  --region eu-central-1
```

> **Note:** MUTABLE tags match the current infra module default and are required
> for the `:latest` moving tag that `deploy.yml` also pushes. Branch-derived
> image tags (`dev-<sha12>`, `stage-<sha12>`) are overwritten on each push;
> release tags (`v*`) are never overwritten by convention. Consider switching
> to IMMUTABLE once the pipeline stabilizes (you would then drop the `:latest`
> tag from `deploy.yml`).

### 1.3 ECR Lifecycle Policy (both repos)

```bash
POLICY='{
  "rules": [
    {
      "rulePriority": 1,
      "description": "Keep last 10 dev/stage branch-derived tags",
      "selection": {
        "tagStatus": "tagged",
        "tagPrefixList": ["dev-","stage-"],
        "countType": "imageCountMoreThan",
        "countNumber": 10
      },
      "action": { "type": "expire" }
    },
    {
      "rulePriority": 2,
      "description": "Expire untagged images after 7 days",
      "selection": {
        "tagStatus": "untagged",
        "countType": "sinceImagePushed",
        "countUnit": "days",
        "countNumber": 7
      },
      "action": { "type": "expire" }
    }
  ]
}'

aws ecr put-lifecycle-policy --repository-name velocityai/backend \
  --lifecycle-policy-text "$POLICY" --region eu-central-1
aws ecr put-lifecycle-policy --repository-name velocityai/frontend \
  --lifecycle-policy-text "$POLICY" --region eu-central-1
```

Release tags (`v*`) are retained indefinitely (no matching rule = no expiry).

---

## 2. Per-Environment AWS Setup

Repeat for `dev`, `stage`, `prod` — **use these short names**, matching the
live infra's EC2 tags and SSM prefixes (see the naming callout above). Replace
`<ENV>` and `<ACCOUNT_ID>` throughout. **Start with dev, validate end-to-end,
then repeat.**

### 2.1 IAM Roles: one build role + one deploy role PER ENVIRONMENT

> **This is the recommended and Terraform-implemented shape** (see
> `infra/terraform/bootstrap/github_oidc.tf`, which builds all of it for you).
> Earlier revisions of this guide offered "or use a single shared role" as an
> equivalent option. **It is not equivalent — do not use it.** The OIDC `sub`
> claim is evaluated exactly once, by `sts:AssumeRoleWithWebIdentity`, and is
> never re-checked on subsequent API calls. A role whose trust admits
> `environment:dev`, `environment:stage` and `environment:prod` therefore hands
> a `dev` job credentials that can write `/velocityai/prod/*` and
> `ssm:SendCommand` a prod-tagged instance. Per-environment tag conditions do
> not prevent this, because the dev job satisfies them for prod too. The
> environment has to be part of the *identity*.

Create:

- **`velocityai-gha-deploy-build`** — trusted for all three environments (the
  artifact is environment-agnostic), holding **only** ECR auth/push/pull/describe
  on the two shared repositories. No SSM, no KMS, no EC2.
- **`velocityai-gha-deploy-<ENV>`** — one per environment, trusted for **exactly
  one** `sub`, holding only that environment's SSM prefix, that environment's
  tagged instances, and `kms:Encrypt` for that environment's parameters. **No ECR
  permissions**: the box pulls images with its own instance role.

Two properties follow, and both are load-bearing:

- A `dev` job cannot assume the `prod` role — STS refuses, because the `sub`
  does not match.
- Even a wrong `EC2_INSTANCE_ID` variable cannot cross environments, because
  `ssm:SendCommand` is restricted to instances tagged for the role's own
  environment.

Because each deploy role is reachable only from its named GitHub Environment,
that Environment's **required reviewers and deployment branch/tag rules become
the access-control boundary** — configure them (§3.1).

> #### ⚠️ Critical: `ssm:SendCommand` must be split into two statements
>
> `ssm:SendCommand` authorizes against **two** resources simultaneously: the
> **document** (`AWS-RunShellScript`) and the **target instance**. If you put
> the `Environment` tag condition on a single statement scoped to
> `Resource: "*"`, the condition is evaluated against *both* resources — but
> the document has no `Environment` tag, so that half of the check can never
> pass, and AWS denies the whole call with:
>
> ```
> AccessDeniedException: ... is not authorized to perform: ssm:SendCommand on
> resource: arn:aws:ec2:...:instance/i-xxxx because no identity-based policy
> allows the ssm:SendCommand action
> ```
>
> **Fix:** two separate statements — the document unconditionally, the
> instance with the tag condition. This is already reflected in the policy
> JSON below (`SSMSendCommandDocument` + `SSMSendCommandInstance`).

**Trust policy (per-environment deploy role):**

Note `StringEquals` and the **exact** `<OWNER>/<REPO>` — no wildcards. A glob
such as `repo:my-org*/my-repo*:...` also matches any other GitHub owner or
repository sharing that prefix, in any organisation, which is a
repo-impersonation path into this AWS account.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:<OWNER>/<REPO>:environment:<ENV>"
        }
      }
    }
  ]
}
```

The **build** role's trust policy is the same except that its `sub` condition
lists all three environment subjects as an array (still `StringEquals`, still
exact):

```json
"token.actions.githubusercontent.com:sub": [
  "repo:<OWNER>/<REPO>:environment:dev",
  "repo:<OWNER>/<REPO>:environment:stage",
  "repo:<OWNER>/<REPO>:environment:prod"
]
```

**Create them via CLI:**

```bash
# Save the trust policy above to trust-<ENV>.json first, then:
aws iam create-role \
  --role-name velocityai-gha-deploy-<ENV> \
  --assume-role-policy-document file://trust-<ENV>.json \
  --description "GitHub Actions OIDC deploy role for VelocityAI <ENV>"

# ...and once, for the shared build role:
aws iam create-role \
  --role-name velocityai-gha-deploy-build \
  --assume-role-policy-document file://trust-build.json \
  --description "GitHub Actions OIDC build role for VelocityAI (ECR only)"
```

In a shared account, attach a permissions boundary scoped to `velocityai-*` to
every one of these roles (`--permissions-boundary`), so a compromised CI role
cannot create IAM identities or touch resources outside the project namespace.

**Inline permissions policy — BUILD role** (ECR only). Save as
`build-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ECRAuth",
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    },
    {
      "Sid": "ECRPushPull",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:DescribeImages",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload"
      ],
      "Resource": [
        "arn:aws:ecr:eu-central-1:<ACCOUNT_ID>:repository/velocityai/backend",
        "arn:aws:ecr:eu-central-1:<ACCOUNT_ID>:repository/velocityai/frontend"
      ]
    }
  ]
}
```

`ecr:DescribeImages` is required, not optional: it is how the workflow resolves
a tag to the digest it deploys, and how a re-run detects an already-pushed image
instead of failing against the `IMMUTABLE` repository.

**Inline permissions policy — DEPLOY role for `<ENV>`.** Save as
`deploy-policy-<ENV>.json`. Note what is *absent*: no ECR (the box pulls with
its instance role), no `kms:Decrypt`/`GenerateDataKey` (the workflow only
writes), no `ssm:ListCommandInvocations` (never called), no
`sts:GetCallerIdentity` (never called).

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SSMPutParameters",
      "Effect": "Allow",
      "Action": "ssm:PutParameter",
      "Resource": "arn:aws:ssm:eu-central-1:<ACCOUNT_ID>:parameter/velocityai/<ENV>/*"
    },
    {
      "Sid": "SSMSendCommandDocument",
      "Effect": "Allow",
      "Action": "ssm:SendCommand",
      "Resource": "arn:aws:ssm:eu-central-1::document/AWS-RunShellScript"
    },
    {
      "Sid": "SSMSendCommandInstance",
      "Effect": "Allow",
      "Action": "ssm:SendCommand",
      "Resource": "arn:aws:ec2:eu-central-1:<ACCOUNT_ID>:instance/*",
      "Condition": {
        "StringEquals": {
          "ssm:resourceTag/Environment": "<ENV>"
        }
      }
    },
    {
      "Sid": "SSMCommandStatus",
      "Effect": "Allow",
      "Action": "ssm:GetCommandInvocation",
      "Resource": "*"
    },
    {
      "Sid": "KMSEncryptSecureStringViaSSM",
      "Effect": "Allow",
      "Action": "kms:Encrypt",
      "Resource": "arn:aws:kms:eu-central-1:<ACCOUNT_ID>:key/<KMS_KEY_ID>",
      "Condition": {
        "StringEquals": {
          "kms:ViaService": "ssm.eu-central-1.amazonaws.com"
        },
        "StringLike": {
          "kms:EncryptionContext:PARAMETER_ARN": "arn:aws:ssm:eu-central-1:<ACCOUNT_ID>:parameter/velocityai/<ENV>/*"
        }
      }
    }
  ]
}
```

The two KMS conditions matter: `kms:ViaService` means the grant is usable only
through SSM, and the `PARAMETER_ARN` encryption context means it is usable only
for this environment's own parameters — so even if the `Resource` were widened
to several keys, a `dev` role still could not encrypt a `prod` parameter.

> If you switch parameters to the **Advanced** tier, add `kms:GenerateDataKey`:
> advanced-tier SecureStrings use envelope encryption rather than a direct
> `kms:Encrypt` call, and the put will fail with `AccessDeniedException` without
> it.

```bash
aws iam put-role-policy \
  --role-name velocityai-gha-deploy-build \
  --policy-name velocityai-gha-deploy-build-inline \
  --policy-document file://build-policy.json

aws iam put-role-policy \
  --role-name velocityai-gha-deploy-<ENV> \
  --policy-name velocityai-gha-deploy-<ENV>-inline \
  --policy-document file://deploy-policy-<ENV>.json
```

Note the resulting role ARNs — in §3.2 you set the build role as
`AWS_BUILD_ROLE_ARN` (the same value in every Environment) and each per-env role
as `AWS_DEPLOY_ROLE_ARN` in its matching Environment.

### 2.2 EC2 Instance Tag

The `SSMSendCommandInstance` condition scopes commands to only instances tagged
with the matching `Environment`. **Without this tag the deploy step fails**
with an access-denied error, which is the intended safety mechanism (a dev
deploy cannot reach a prod box). Use the short env name (`dev`/`stage`/`prod`):

A mis-tagged instance is caught twice: IAM refuses the `SendCommand`, and if a
command does arrive (e.g. sent by a human), `remote-deploy.sh` compares the
host's own `VELOCITYAI_ENVIRONMENT` against the deploy target and aborts on a
mismatch rather than deploying one environment's images onto another's host.

```bash
aws ec2 create-tags --resources <INSTANCE_ID> \
  --tags Key=Environment,Value=<ENV> --region eu-central-1
```

Verify the tag is present:

```bash
aws ec2 describe-tags --filters "Name=resource-id,Values=<INSTANCE_ID>" \
  --region eu-central-1 --query "Tags[].[Key,Value]" --output text
```

You can sanity-check the policy against a real instance ARN and tag value
**without** triggering a workflow run, using the IAM policy simulator:

```bash
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::<ACCOUNT_ID>:role/<ROLE_NAME> \
  --action-names ssm:SendCommand \
  --resource-arns "arn:aws:ec2:eu-central-1:<ACCOUNT_ID>:instance/<INSTANCE_ID>" \
  --context-entries "ContextKeyName=ssm:resourceTag/Environment,ContextKeyValues=<ENV>,ContextKeyType=string" \
  --query "EvaluationResults[].EvalDecision" --output text
# Expect: allowed

aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::<ACCOUNT_ID>:role/<ROLE_NAME> \
  --action-names ssm:SendCommand \
  --resource-arns "arn:aws:ssm:eu-central-1::document/AWS-RunShellScript" \
  --query "EvaluationResults[].EvalDecision" --output text
# Expect: allowed
```

### 2.3 KMS Key

Create (or reuse) a symmetric KMS key for encrypting SSM SecureString parameters
and EBS snapshots. Grant:

- the **per-environment deploy role** → `kms:Encrypt` only, conditioned on
  `kms:ViaService=ssm.<region>.amazonaws.com` and an encryption context matching
  its own `/velocityai/<ENV>/*` prefix (to put SecureStrings). It never reads
  them back, so it needs no `kms:Decrypt`. Add `kms:GenerateDataKey` **only** if
  you move to Advanced-tier parameters.
- the **EC2 instance role** → `kms:Decrypt` (to read them via `velocityai-load-secrets`)

Note the key ID/ARN — it's referenced in the deploy role policy (§2.1) and the
`put-parameter` commands (§2.4).

### 2.4 Seed SSM Parameters

`deploy.yml` pushes config from GitHub into SSM on every run, but for the very
first boot (before any deploy), seed the minimum set so `velocityai-load-secrets`
can compose a valid `/etc/velocityai/app.env`:

```bash
PREFIX="/velocityai/<ENV>"

# Required (SecureString)
aws ssm put-parameter --name "$PREFIX/SECRET_KEY" \
  --type SecureString --key-id <KMS_KEY_ID> \
  --value "$(openssl rand -hex 64)" --region eu-central-1

# DATABASE_PASSWORD is generated ON THE BOX by bootstrap-ec2.sh on fresh
# provision. Only seed it manually here if you are wiring CI before the box
# has ever booted; otherwise the bootstrap already created it.
aws ssm put-parameter --name "$PREFIX/DATABASE_PASSWORD" \
  --type SecureString --key-id <KMS_KEY_ID> \
  --value "<generated-by-bootstrap-ec2.sh-on-first-boot>" --region eu-central-1

# Required (String) — Bedrock LLM config
aws ssm put-parameter --name "$PREFIX/llm/region" \
  --type String --value "eu-central-1" --region eu-central-1

aws ssm put-parameter --name "$PREFIX/llm/model_id" \
  --type String --value "anthropic.claude-haiku-4-5-20251001-v1:0" --region eu-central-1

aws ssm put-parameter --name "$PREFIX/llm/inference_profile_id" \
  --type String --value "eu.anthropic.claude-haiku-4-5-20251001-v1:0" --region eu-central-1
```

The full config-key mapping (what `velocityai-load-secrets` recognizes and how it
maps to app env vars) is in [§10](#10-reference-config-key-mapping).

> **DATABASE_PASSWORD** is owned by the host — generated by `bootstrap-ec2.sh` and
> written to SSM from the instance. GitHub does **not** push it (decision D-5).
>
> **ENV** is hardcoded to `production` on the host by `bootstrap-ec2.sh` (strict
> `SECRET_KEY` validation mode, applied uniformly to all three deploy
> environments — `dev`/`stage`/`prod` all run the app with `ENV=production`).
> GitHub does **not** push it (decision D-6). Don't confuse this app-level
> `ENV` value with the deploy-environment name (`dev`/`stage`/`prod`) — they
> are unrelated concepts that happen to share a name pattern.

### 2.5 SSM Deploy Coordinates

`deploy.yml` reads the target instance ID from the `EC2_INSTANCE_ID` GitHub
variable (§3.2). For parity with the retired buildspec (which read it from SSM),
you may also store it here — harmless and useful for host-side scripts:

```bash
aws ssm put-parameter --name "/velocityai/<ENV>/deploy/instance_id" \
  --type String --value "<INSTANCE_ID>" --region eu-central-1
```

---

## 3. GitHub Repository Configuration

### 3.1 Environments

Create three environments under **Settings → Environments**. **Name them
exactly `dev`, `stage`, `prod`** — `deploy.yml`'s `resolve` job outputs these
exact strings, and the `build`/`deploy` jobs' `environment:` field must match
for the right variables/secrets and protection rules to apply.

| Environment name | Triggered by | Deployment branch/tag rule | Required reviewers |
|---|---|---|---|
| `dev` | push to `dev` branch | `dev` branch | None |
| `stage` | push to `staging` branch | `staging` branch | None |
| `prod` | `v*` tag (from `main`) | Tags matching `v*` | At least 1 reviewer |

The `prod` reviewer requirement is the human approval gate — `deploy.yml`
pauses at the `build`/`deploy` jobs until a reviewer approves, because both jobs
declare `environment: prod` when the resolved environment is `prod`.

> **These rules are now an AWS access-control boundary, not just workflow
> hygiene.** Each environment's deploy role trusts exactly one OIDC subject
> (`repo:<owner>/<repo>:environment:<env>`), so anything that can run a job in
> the `prod` Environment can obtain prod AWS credentials. Configure, and keep
> configured:
>
> - **Required reviewers** on `prod` (and ideally `stage`).
> - **Deployment tag rule** `v*` on `prod`, so an arbitrary branch cannot select
>   that Environment.
> - **Protected tags** matching `v*` at the repository/ruleset level, so only
>   authorised people can create a release tag in the first place.
>
> The workflow additionally refuses a prod deploy whose commit is not an ancestor
> of `main`. That check is necessary but not sufficient on its own — it lives in
> the workflow file, which a commit on the deployed ref could modify. The
> GitHub-side rules above are what make it trustworthy.

### 3.2 Per-Environment Variables and Secrets

For **each** environment, set the following. Variables are visible in logs;
secrets are masked.

**Variables (non-secret):**

| Name | Example value | Notes |
|---|---|---|
| `AWS_BUILD_ROLE_ARN` | `arn:aws:iam::<ACCOUNT>:role/velocityai-gha-deploy-build` | From §2.1. **Same value in all three environments** — the build role is shared. |
| `AWS_DEPLOY_ROLE_ARN` | `arn:aws:iam::<ACCOUNT>:role/velocityai-gha-deploy-dev` | From §2.1. **Environment-specific — must be this environment's own role.** Pasting another environment's ARN fails at STS (by design) rather than deploying with the wrong authority. |
| `AWS_REGION` | `eu-central-1` | |
| `ECR_REGISTRY` | `<ACCOUNT>.dkr.ecr.eu-central-1.amazonaws.com` | |
| `EC2_INSTANCE_ID` | `i-0abc123def456` | The tagged instance from §2.2 |
| `CORS_ORIGINS` | `["https://dev.velocityai.example.com"]` | JSON array string |
| `PUBLIC_BASE_URL` | `https://dev.velocityai.example.com` | |
| `BEDROCK_MODEL_ID` | `anthropic.claude-haiku-4-5-20251001-v1:0` | → `llm/model_id` |
| `BEDROCK_INFERENCE_PROFILE_ID` | `eu.anthropic.claude-haiku-4-5-20251001-v1:0` | → `llm/inference_profile_id` |
| `BEDROCK_CODING_MODEL_ID` | *(optional; empty = use default)* | → `llm/coding_model_id` |
| `ACCESS_TOKEN_EXPIRE_HOURS` | `24` | |
| `HANDOFF_MAX_TRANSCRIPT_BYTES` | *(optional)* | |
| `LANGSMITH_TRACING` | *(optional)* `true`/`false` | |
| `LANGSMITH_PROJECT` | *(optional)* | |

**Secrets (masked):**

| Name | Description |
|---|---|
| `SECRET_KEY` | App JWT signing key (`openssl rand -hex 64`) |
| `LANGSMITH_API_KEY` | *(optional)* LangSmith tracing key |

`deploy.yml` only pushes parameters whose value is non-empty; anything you leave
unset simply isn't written to SSM, and the host loader applies its documented
fallbacks (e.g. `CORS_ORIGINS`/`PUBLIC_BASE_URL` default to the box's FQDN).

### 3.3 Repository Secrets (shared across environments)

None required. All secrets are per-environment.

---

## 4. Trigger and Tag Matrix

| Git event | Environment (GitHub) | SSM prefix / EC2 tag | Image tag | Approval |
|---|---|---|---|---|
| Push to `dev` branch | `dev` | `dev` | `dev-<sha12>` | None |
| Push to `staging` branch | `stage` | `stage` | `stage-<sha12>` | None |
| Tag `v*` (from `main`) | `prod` | `prod` | `<tag>` (e.g. `v1.4.0`) | Required reviewer |
| `workflow_dispatch` (choose `dev`) | `dev` | `dev` | `dev-<current-sha12>` | None |
| `workflow_dispatch` (choose `stage`) | `stage` | `stage` | `stage-<current-sha12>` | None |
| `workflow_dispatch` (choose `prod`) | `prod` | `prod` | `<current-branch/tag-ref-name>` | Required reviewer |

Note the branch name (`dev`/`staging`) and the environment name (`dev`/`stage`)
diverge for the second row — this is intentional (see the naming callout at
the top of this doc). The `resolve` job in `deploy.yml` computes these values;
see the `How the Pipeline Works` section for the flow.

Three things about this table are enforced, not conventional:

- **Every ref is matched explicitly.** There is no "anything else is dev"
  fallback, so adding a branch to the `on:` push filter without adding it here
  fails the run instead of quietly deploying it to dev.
- **`Tag v* (from main)` really means from `main`.** A `v*` tag can be created on
  any commit, so `resolve` verifies the tagged commit is an ancestor of
  `origin/main` and refuses the deploy otherwise. The break-glass override is
  `workflow_dispatch` with `allow_untagged_prod=true`, which is reviewer-gated
  and logged as a warning.
- **The image tag names the artifact; the digest deploys it.** The tag in this
  table is what gets pushed to ECR and what appears in logs. The host is pinned
  to `repo@sha256:...` for the image that tag resolved to, so the bytes that were
  built and scanned are provably the bytes that run. `dev-<sha12>` /
  `stage-<sha12>` are unique per commit, and release tags are immutable in ECR,
  so a tag can never be re-pointed at different content.

---

## 5. First Deploy and Validation

Do this for **dev** first.

1. **Trigger:** push a commit to the `dev` branch, or go to
   **Actions → Deploy → Run workflow → dev**.
2. **Watch the run** in the Actions tab. The jobs execute in order:
   - `resolve` — prints the resolved `env=dev tag=dev-<sha>`.
   - `build` — OIDC auth → ECR login → buildx backend + frontend → push. First
     run is slow (no layer cache); later runs use the GitHub Actions cache.
   - `deploy` — pushes config to SSM, sends the SSM RunCommand, polls it, and
     the on-box script health-checks `/health`.
3. **Confirm success:** the `deploy` job's "Poll SSM command status" step ends
   with `Deploy succeeded.` If it fails, the step prints the box's stdout/stderr
   for debugging (see [§7](#7-troubleshooting)).
4. **Validate the environment** using the checklist in [§6](#6-verification-checklists).
5. **Repeat Stages 2–3** for `stage` (push to the `staging` branch), then
   `prod` (push a `v*` tag).

> **Tip:** for the first dev deploy, watch the box directly in a second terminal
> via Session Manager: `sudo journalctl -u velocityai-app.service -f` and
> `sudo docker compose -f /opt/velocityai/docker-compose.yml logs -f`.

---

## 6. Verification Checklists

### After `ci.yml` (Stage 0)

- [ ] `backend` job green (ruff, pyright, lint-imports, vulture, pytest)
- [ ] `frontend` job green (eslint, vitest, build)
- [ ] `security-scan` job green (gitleaks, checkov, trivy, tflint)

### After a `deploy.yml` run

- [ ] `build` job pushed both images — verify in ECR:
      `aws ecr list-images --repository-name velocityai/backend --region eu-central-1`
- [ ] SSM parameters updated:
      `aws ssm get-parameters-by-path --path /velocityai/<ENV> --recursive --region eu-central-1 --query 'Parameters[].Name'`
- [ ] SSM command succeeded (the poll step ended with `Deploy succeeded.`)
- [ ] App healthy from the box: `curl -fsS http://127.0.0.1:8000/health`
- [ ] App healthy from the internet: `curl -fsS https://<FQDN>/health`
- [ ] Correct image **digest** is live: `grep IMAGE /etc/velocityai/app.env` on
      the box shows `…/velocityai/backend@sha256:…` matching the digest printed
      by the `build` job's "Resolve image digests" step
- [ ] Migrations ran: backend logs show `alembic upgrade head` completed at start

### OIDC / IAM sanity

- [ ] The `build` job's "Configure AWS credentials" step succeeds (proves OIDC
      trust + `AWS_BUILD_ROLE_ARN` are correct).
- [ ] The `deploy` job's "Configure AWS credentials" step succeeds (proves this
      environment's `AWS_DEPLOY_ROLE_ARN` trusts *this* environment's subject).
- [ ] No `AccessDenied` on `ssm:SendCommand` (proves the EC2 `Environment` tag
      matches the role's condition).
- [ ] **Negative check, once per account:** temporarily set `dev`'s
      `AWS_DEPLOY_ROLE_ARN` to the *prod* role ARN and run a dev deploy — it
      must fail at STS with `Not authorized to perform
      sts:AssumeRoleWithWebIdentity`. That failure is the proof that environments
      are actually isolated. Revert the variable afterwards.

---

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `build` job fails at "Configure AWS credentials" with `Not authorized to perform sts:AssumeRoleWithWebIdentity` | OIDC trust `sub` doesn't match `repo:hexaware/velocityai:environment:<ENV>`, or the OIDC provider wasn't created | Verify the org/repo slug and the environment name in the trust policy (§2.1); confirm the provider exists (§1.1) |
| `deploy` job fails at `ssm send-command` with `AccessDeniedException ... instance/i-xxxx because no identity-based policy allows the ssm:SendCommand action` | The `SendCommand` statement puts the `Environment` tag condition on `Resource: "*"`, which also covers the `AWS-RunShellScript` document (untagged) — the condition can never pass. **This is the most common first-deploy failure.** | Split into two statements: document (no condition) + instance (tag condition). See the callout in §2.1. Verify with the `simulate-principal-policy` commands in §2.2. |
| `deploy` job fails at `ssm send-command` with `AccessDenied` for a different reason | EC2 instance missing the `Environment=<ENV>` tag (short name: `dev`/`stage`/`prod`), or wrong instance ARN in the policy | Re-check §2.2; confirm the tag value exactly equals the resolved env name, not the branch name |
| SSM command runs but status = `Failed` | On-box error (compose pull, ECR login, health check) | Read the printed stdout/stderr in the poll step; SSM into the box and check `journalctl -u velocityai-app.service` |
| SSM command fails immediately with `_script.sh: 1: set: Illegal option -o pipefail` / `failed to run commands: exit status 2` | The generated `remote.sh` has no shebang, so `AWS-RunShellScript` executed it with the box's default `/bin/sh` (dash) instead of bash — dash doesn't support `set -o pipefail` | Confirmed fixed in `deploy.yml`: the heredoc now starts with `#!/bin/bash` before `set -euo pipefail` so SSM always runs it under bash regardless of the instance's default shell |
| Health check times out | Image tag not in ECR yet, or app boot error (bad `SECRET_KEY`, DB unreachable) | Confirm `build` pushed the tag; check backend logs; verify `SECRET_KEY` is set and non-default in SSM |
| Config value not reaching the app | Wrong SSM key name — `velocityai-load-secrets` silently drops unknown keys | Use the exact names in [§10](#10-reference-config-key-mapping); Bedrock keys live under `llm/*` |
| `docker compose pull` fails with `manifest unknown` | The digest isn't in the repo the box is pulling from (build job skipped/failed, or `ECR_REGISTRY` points at another account) | Re-run the workflow; confirm the `build` job completed and compare its digests with `/etc/velocityai/app.env` |
| Push to ECR fails with `denied` | Build role missing ECR push actions, or repo ARN mismatch | Re-check the `ECRPushPull` statement resource ARNs (§2.1) |
| Push to ECR fails with `ImagePushNotAllowedException` / `cannot be overwritten because the repository is configured as immutable` | The tag already exists and the "Probe ECR for an existing image" step didn't adopt it — usually because the build role lacks `ecr:DescribeImages` | Add `ecr:DescribeImages` to the build policy (§2.1). Never "fix" this by flipping the repository to `MUTABLE`. |
| Image scan step fails the build on a CVE | The scan is blocking at HIGH,CRITICAL for **fixable** findings | Rebuild on a patched base image or bump the dependency. If genuinely unfixable, add a dated, justified entry to `.trivyignore.images`. |
| `deploy` job fails with `environment mismatch — this host is 'X', the deploy targets 'Y'` | `EC2_INSTANCE_ID` on this Environment points at another environment's box, or the instance's `Environment` tag / `VELOCITYAI_ENVIRONMENT` is wrong | Fix the variable or the tag. This is a deliberate hard stop: continuing would put one environment's images on another's host, and skip that host's pre-deploy backup. |
| `resolve` job fails with `commit … is not an ancestor of origin/main` | A `v*` tag was cut on a commit that isn't merged to `main` | Merge to `main` and re-tag. For a genuine emergency use `workflow_dispatch` with `allow_untagged_prod=true` (reviewer-gated, logged as a warning). |
| Deploy reports `ROLLBACK SUCCEEDED` | The new images failed the health gate; the box was returned to the previous digests | Investigate the printed backend/frontend logs. Note that **migrations are not rolled back** — if the failed release migrated the schema, restore the pre-deploy `pg_dump` (§ backups). |

**Reading a failed SSM command manually:**

```bash
aws ssm get-command-invocation \
  --command-id <COMMAND_ID> \
  --instance-id <INSTANCE_ID> \
  --region eu-central-1 \
  --query '[Status, StandardOutputContent, StandardErrorContent]' --output text
```

---

## 8. Rollback

Images are immutable-by-convention per tag, so rollback is "redeploy an older
tag." Two options:

**Option A — via GitHub (preferred, keeps the audit trail):**

1. Find the last-good short SHA (from a previous green deploy).
2. Re-run that older `deploy.yml` run from the Actions tab
   (**Re-run all jobs**), or push a revert commit to the branch.

**Option B — directly on the box (emergency):**

```bash
# SSM into the box, then:
sudo sed -i 's|^BACKEND_IMAGE=.*|BACKEND_IMAGE=<REGISTRY>/velocityai/backend:<OLD_TAG>|'  /etc/velocityai/app.env
sudo sed -i 's|^FRONTEND_IMAGE=.*|FRONTEND_IMAGE=<REGISTRY>/velocityai/frontend:<OLD_TAG>|' /etc/velocityai/app.env
sudo systemctl restart velocityai-app.service
curl -fsS http://127.0.0.1:8000/health
```

> **Database migrations do not auto-rollback.** If the bad release included a
> destructive migration, restore from the hourly `pg_dump` backup
> (`velocityai-pg-dump` writes to the S3 backup bucket). Prefer forward-only,
> additive migrations to avoid this.

---

## 9. GitLab/CodeBuild (retired)

The GitLab/CodeBuild pipeline has been decommissioned. The following resources
were deleted from the Terraform bootstrap layer:

- `infra/terraform/bootstrap/cicd.tf` — GitLab connection, CodeBuild projects,
  per-env deploy roles, webhooks, log groups.
- `infra/buildspec.yml` — the CodeBuild buildspec.
- `scripts/deploy.sh`, `scripts/first-deploy.sh` — operator scripts that
  referenced the old layout.

All CI/CD is now GitHub Actions (`ci.yml` + `deploy.yml`) with OIDC
authentication (`bootstrap/github_oidc.tf`). If you need to re-create the
GitLab path for any reason, refer to git history (`cicd.tf` last existed at
commit prior to this decommissioning).

---

## 10. Reference: config key mapping

`velocityai-load-secrets` (installed by `bootstrap-ec2.sh`) reads every parameter
under `/velocityai/<ENV>/` and maps recognized keys into `/etc/velocityai/app.env`.
**Unknown keys are logged as a WARN and dropped** — so the key names below are
exact and load-bearing.

| SSM Key (under `/velocityai/<ENV>/`) | Env var the app sees | Pushed by `deploy.yml` from |
|---|---|---|
| `SECRET_KEY` | `SECRET_KEY` | secret `SECRET_KEY` |
| `DATABASE_PASSWORD` | composed → `DATABASE_URL=postgresql://velocityai:<pw>@host.docker.internal:5432/velocityai` | **host-owned, not pushed** |
| `CORS_ORIGINS` | `CORS_ORIGINS` (falls back to `["https://<FQDN>"]` if empty) | var `CORS_ORIGINS` |
| `PUBLIC_BASE_URL` | `PUBLIC_BASE_URL` (falls back to `https://<FQDN>`) | var `PUBLIC_BASE_URL` |
| `ACCESS_TOKEN_EXPIRE_HOURS` | `ACCESS_TOKEN_EXPIRE_HOURS` | var `ACCESS_TOKEN_EXPIRE_HOURS` |
| `HANDOFF_MAX_TRANSCRIPT_BYTES` | `HANDOFF_MAX_TRANSCRIPT_BYTES` | var `HANDOFF_MAX_TRANSCRIPT_BYTES` |
| `LANGSMITH_TRACING` | `LANGSMITH_TRACING` | var `LANGSMITH_TRACING` |
| `LANGSMITH_API_KEY` | `LANGSMITH_API_KEY` | secret `LANGSMITH_API_KEY` |
| `LANGSMITH_PROJECT` | `LANGSMITH_PROJECT` | var `LANGSMITH_PROJECT` |
| `llm/region` | `AWS_REGION` | var `AWS_REGION` |
| `llm/model_id` | `BEDROCK_MODEL_ID` | var `BEDROCK_MODEL_ID` |
| `llm/inference_profile_id` | `BEDROCK_INFERENCE_PROFILE_ID` | var `BEDROCK_INFERENCE_PROFILE_ID` |
| `llm/coding_model_id` | `BEDROCK_CODING_MODEL_ID` | var `BEDROCK_CODING_MODEL_ID` |
| *(anything else)* | — | **logged as WARN, dropped** |

Host-anchored values NOT sourced from SSM (preserved across loader runs):

- `ENV` — hardcoded `production` by `bootstrap-ec2.sh` (strict `SECRET_KEY` guard).
- `BACKEND_IMAGE` / `FRONTEND_IMAGE` — the pinned image tags, updated in place by
  the deploy's SSM RunCommand.

---

## 11. Architecture Diagram

```
GitHub push / tag / workflow_dispatch
        |
        v
  ci.yml (lint, test, security scan — NO AWS access, permissions: contents: read)
    - backend:  uv venv -> ruff / pyright / lint-imports / vulture / pytest
    - frontend: npm ci -> lint / vitest / build
    - scan:     gitleaks / checkov / trivy / tflint (checksum-pinned binaries)
        |
        v  (on dev/staging branch push, or v* tag, or manual dispatch)
  deploy.yml
    job: resolve
      - compute environment (dev|stage|prod) + image tag from the trigger
        (dev branch -> dev; staging branch -> stage; v* tag -> prod)
    job: build   (environment: dev|stage|prod)
      - OIDC assume role (short-lived creds, no static keys)
      - ECR login
      - docker buildx: backend (--build-context opendesign=./skills/opendesign) + frontend
      - push to ECR: velocityai/{backend,frontend}:<tag>  (+ :latest)
    job: deploy  (environment: dev|stage|prod  ⇒ prod waits for reviewer)
      - OIDC assume role (env-scoped)
      - ssm put-parameter: push GitHub vars/secrets to /velocityai/<env>/*
                           (SecureString for secrets; llm/* for Bedrock)
      - ssm send-command to EC2 (tag Environment=<env>):
          0. assert BACKEND_IMAGE=/FRONTEND_IMAGE= lines exist in app.env
             (a missing line would make the sed pin a silent no-op)
          1. write /opt/velocityai/docker-compose.yml (inline, base64 from repo)
             -- THE single source of truth; no S3 copy exists (D-2)
          2. chown data/skills + data/runs to 10001:10001
          3. update BACKEND_IMAGE/FRONTEND_IMAGE in /etc/velocityai/app.env,
             then verify the pins landed on the intended tag
          4. systemctl restart velocityai-app.service
             └─ ExecStartPre: velocityai-load-secrets (SSM -> app.env, composes DATABASE_URL)
             └─ ExecStartPre: docker compose pull
             └─ ExecStart:    docker compose up -d --remove-orphans
                              └─ backend/docker-entrypoint.sh: alembic upgrade head -> uvicorn
          5. curl http://127.0.0.1:8000/health  (retry loop)
      - poll GetCommandInvocation until Success/Failed/TimedOut
        |
        v
  EC2 per env (tag Environment=<env>):
    Docker Compose (backend + frontend) + native Postgres + nginx
    instance-profile IAM: ECR pull, SSM, Bedrock invoke, Param Store read, KMS, S3 backup
```

### Fresh-instance behaviour (consequence of D-2)

`docker-compose.yml` and the image pins exist **only** in the repo and are pushed
to the box by `deploy.yml`. Terraform no longer uploads them to S3 (the
`aws_s3_object.compose_yaml` / `deploy_env` resources were deleted, along with the
`image_tag` variable), because maintaining both copies caused them to silently
diverge — CI updated the box, Terraform updated S3, and a rebuilt instance booted
on a stale compose file plus an ECR-expired tag.

So a newly-created instance:

1. self-provisions the host via `velocityai-firstboot.service` → `bootstrap-ec2.sh`
   (Postgres, nginx, Docker, systemd units, certbot, CloudWatch agent),
2. logs `SKIP: not starting velocityai-app.service` because no compose file is
   present — this is expected, not a failure,
3. writes `/var/lib/velocityai/.bootstrap-done` and stops there.

**A Deploy workflow run is required to start the application.** Disaster recovery
therefore depends on the pipeline; `infra/terraform/RUNBOOK.md` §6.5 documents the
revised RTO and a break-glass path for when GitHub is unavailable.

---

## 12. Appendix A — Connecting GitHub OIDC with AWS (detailed)

> This mirrors the AWS-side steps in
> [`CICD_IMPLEMENTATION_REPORT.md`](./CICD_IMPLEMENTATION_REPORT.md). Both docs
> are kept in sync — use whichever you have open.

### A.1 How it works

GitHub OIDC lets your workflows assume an AWS role via a short-lived token — no
static AWS keys stored in GitHub:

```
GitHub Actions workflow
   │  (1) requests an OIDC token (JWT) for the run
   ▼
token.actions.githubusercontent.com  ── JWT claims: aud=sts.amazonaws.com,
   │                                     sub=repo:<ORG>/<REPO>:environment:<ENV>
   ▼
AWS STS : AssumeRoleWithWebIdentity
   │  (2) validates the JWT against the OIDC provider
   │  (3) checks the role trust policy (aud + sub conditions)
   ▼
Short-lived AWS credentials (~1 hour) → used by every `aws` call in the job
```

### A.2 Step 1 — Create the OIDC identity provider (once per account)

**Console:** IAM → Identity providers → Add provider → OpenID Connect
- Provider URL: `https://token.actions.githubusercontent.com`
- Audience: `sts.amazonaws.com`

**CLI:**

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list "sts.amazonaws.com" \
  --thumbprint-list "1c58a3a8518e8759bf075b76b750d4f2df264fcd" \
  --region <REGION>

# Verify
aws iam list-open-id-connect-providers
```

### A.3 Step 2 — Create the IAM roles + trust policies

> **Do not create one shared role for all three environments.** A previous
> revision of this appendix showed exactly that, with a `StringLike` `sub` list
> covering dev/stage/prod. It does not isolate environments: STS checks the `sub`
> claim once, at AssumeRole, and no later API call re-checks it — so a `dev` job
> ends up holding credentials that are equally valid against prod resources.
> Use the split described in §2.1: **one ECR-only build role** (which may be
> shared, because the artifact is environment-agnostic and the repositories are
> shared) plus **one deploy role per environment**.

The **build** role's trust policy — `StringEquals`, exact owner/repo, all three
environment subjects. Save as `trust-build.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<AWS_ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": [
            "repo:<GITHUB_OWNER>/<REPO>:environment:dev",
            "repo:<GITHUB_OWNER>/<REPO>:environment:stage",
            "repo:<GITHUB_OWNER>/<REPO>:environment:prod"
          ]
        }
      }
    }
  ]
}
```

Each **deploy** role's trust policy is the same with a single-valued `sub`
(`repo:<GITHUB_OWNER>/<REPO>:environment:<ENV>`) — see §2.1.

> **⚠️ Use `StringEquals`, never `StringLike`, and never a wildcard in the
> owner/repo.** `repo:my-org*/my-repo*:environment:prod` also matches any other
> GitHub owner or repository sharing that prefix — in any organisation — so
> anyone able to create such a repository could assume your role. Tolerating an
> org rename is not worth that; a rename should be a deliberate policy update.

> **⚠️ The `environment:` names MUST match your GitHub Environment names
> exactly** — `dev`/`stage`/`prod`, **not** `staging`/`production`. A mismatch
> makes assume-role fail for that environment.

```bash
aws iam create-role --role-name velocityai-gha-deploy-build \
  --assume-role-policy-document file://trust-build.json \
  --permissions-boundary arn:aws:iam::<AWS_ACCOUNT_ID>:policy/velocityai-deploy-boundary \
  --description "GitHub Actions OIDC build role for VelocityAI (ECR only)"

# then once per environment, with trust-<ENV>.json from §2.1:
aws iam create-role --role-name velocityai-gha-deploy-<ENV> \
  --assume-role-policy-document file://trust-<ENV>.json \
  --permissions-boundary arn:aws:iam::<AWS_ACCOUNT_ID>:policy/velocityai-deploy-boundary \
  --description "GitHub Actions OIDC deploy role for VelocityAI <ENV>"
```

### A.4 Step 3 — Attach the permissions policy

Save as `deploy-policy.json`. **The `ssm:SendCommand` permission MUST be split
into two statements** (document + instance) — a single tag-conditioned
`Resource: "*"` statement can never satisfy the untagged `AWS-RunShellScript`
document and every deploy fails with `AccessDeniedException`.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Sid": "ECRAuth", "Effect": "Allow", "Action": "ecr:GetAuthorizationToken", "Resource": "*" },
    {
      "Sid": "ECRPushPull",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage", "ecr:PutImage", "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart", "ecr:CompleteLayerUpload"
      ],
      "Resource": "*"
    },
    { "Sid": "SSMPutParameters", "Effect": "Allow", "Action": "ssm:PutParameter", "Resource": "*" },
    {
      "Sid": "SSMSendCommandDocument",
      "Effect": "Allow",
      "Action": "ssm:SendCommand",
      "Resource": "arn:aws:ssm:*::document/AWS-RunShellScript"
    },
    {
      "Sid": "SSMSendCommandInstance",
      "Effect": "Allow",
      "Action": "ssm:SendCommand",
      "Resource": "arn:aws:ec2:*:<AWS_ACCOUNT_ID>:instance/*",
      "Condition": {
        "StringEquals": { "ssm:resourceTag/Environment": ["dev", "stage", "prod"] }
      }
    },
    {
      "Sid": "SSMCommandStatus",
      "Effect": "Allow",
      "Action": ["ssm:GetCommandInvocation", "ssm:ListCommandInvocations"],
      "Resource": "*"
    },
    {
      "Sid": "KMSForSecureString",
      "Effect": "Allow",
      "Action": ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey"],
      "Resource": "*"
    },
    { "Sid": "STSIdentity", "Effect": "Allow", "Action": "sts:GetCallerIdentity", "Resource": "*" }
  ]
}
```

> **⚠️ The policy above is the DEPRECATED single-role shape, kept only so you can
> recognise it in an existing account. Do not create it.** Every `Resource: "*"`
> and the three-value `Environment` tag condition are precisely what let a `dev`
> run reach prod. It also grants three things the workflow never calls
> (`ssm:ListCommandInvocations`, `sts:GetCallerIdentity`, `kms:Decrypt`) and
> `kms:GenerateDataKey`, which is only needed for Advanced-tier parameters.
>
> **Use the two scoped policies in §2.1 instead** — a build policy with ECR only,
> and a per-environment deploy policy whose every resource names one
> environment. If you find a role like this in the account, migrate GitHub to the
> new `AWS_BUILD_ROLE_ARN` / `AWS_DEPLOY_ROLE_ARN` variables and delete it.

### A.5 Step 4 — Give GitHub the role ARNs

```bash
aws iam get-role --role-name velocityai-gha-deploy-build --query 'Role.Arn' --output text
aws iam get-role --role-name velocityai-gha-deploy-<ENV> --query 'Role.Arn' --output text
```

Set the build role as `AWS_BUILD_ROLE_ARN` (the same value in every Environment)
and each per-environment role as `AWS_DEPLOY_ROLE_ARN` in its matching
Environment (§3.2). `deploy.yml` already consumes both:

```yaml
# build job
- name: Configure AWS credentials (OIDC — build role)
  uses: aws-actions/configure-aws-credentials@e3dd6a429d7300a6a4c196c26e071d42e0343502
  with:
    role-to-assume: ${{ vars.AWS_BUILD_ROLE_ARN }}
    aws-region: ${{ vars.AWS_REGION || env.AWS_REGION_DEFAULT }}

# deploy job
- name: Configure AWS credentials (OIDC — per-env deploy role)
  uses: aws-actions/configure-aws-credentials@e3dd6a429d7300a6a4c196c26e071d42e0343502
  with:
    role-to-assume: ${{ vars.AWS_DEPLOY_ROLE_ARN }}
    aws-region: ${{ vars.AWS_REGION || env.AWS_REGION_DEFAULT }}
```

Both jobs declare `permissions: id-token: write` at **job** level; the workflow
default is `contents: read` only, so jobs that never touch AWS (`gate`,
`resolve`) cannot mint an AWS-audience token at all.

### A.6 Do you need admin access?

You do **not** need GitHub org-owner rights to *use* OIDC.

| Task | Access needed |
|---|---|
| Push workflows, trigger runs, view logs (GitHub) | Repo **Write** |
| Create Environments + variables/secrets (GitHub) | Repo **Admin** (or delegated) |
| Create OIDC provider + IAM role + policy (AWS) | **IAM admin** (one-time) |
| Create ECR/tag EC2/KMS/SSM (AWS) | ECR/EC2/KMS/SSM write |
| Assume the role at deploy time | Nothing extra (the OIDC token does it) |

If you lack IAM admin, an AWS admin can create the provider + roles and hand you
the **role ARNs**; a repo admin then sets `AWS_BUILD_ROLE_ARN` and
`AWS_DEPLOY_ROLE_ARN`. After that, anyone with Write can trigger a dev deploy —
which is exactly why `prod` must carry required reviewers and a `v*` tag rule
(§3.1): with per-environment roles, the ability to run a job in an Environment
*is* the ability to obtain that environment's AWS credentials.

### A.7 Verify (optional, without a workflow)

```bash
# Simulate SendCommand authorization (both must return: allowed)
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::<AWS_ACCOUNT_ID>:role/<ROLE_NAME> \
  --action-names ssm:SendCommand \
  --resource-arns "arn:aws:ssm:<REGION>::document/AWS-RunShellScript" \
  --query "EvaluationResults[].EvalDecision" --output text

aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::<AWS_ACCOUNT_ID>:role/<ROLE_NAME> \
  --action-names ssm:SendCommand \
  --resource-arns "arn:aws:ec2:<REGION>:<AWS_ACCOUNT_ID>:instance/<INSTANCE_ID>" \
  --context-entries "ContextKeyName=ssm:resourceTag/Environment,ContextKeyValues=<ENV>,ContextKeyType=string" \
  --query "EvaluationResults[].EvalDecision" --output text
```

### A.8 OIDC pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `Not authorized to perform sts:AssumeRoleWithWebIdentity` | OIDC provider missing or thumbprint wrong | Re-check A.2 |
| `AccessDenied` assuming the role | Trust `sub` doesn't match the workflow's `repo:<ORG>/<REPO>:environment:<ENV>` claim | Confirm the `environment:` names match your GitHub Environments (`dev`/`stage`/`prod`) |
| Credentials expire mid-job | Normal (~1h TTL) | `configure-aws-credentials` handles refresh |
