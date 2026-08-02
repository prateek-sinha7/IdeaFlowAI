# VelocityAI infrastructure — operations runbook

Operational, step-by-step. For the architecture and layout see
[`../README.md`](../README.md).

Apply order is always: **bootstrap → shared → foundation(env) → app(env)**.

---

## Quickstart — new operator, zero to running (start here)

If you have never stood this up before, read this section first, then follow
the numbered sections in order. This is the whole path from an empty account to
a running `dev` environment with CI/CD.

### A. Prerequisites — tools

Install locally (versions are the tested floor):

| Tool | Version | Why |
|---|---|---|
| Terraform | **>= 1.9** (tested on 1.15.x) | all layers pin `required_version >= 1.9.0`; AWS provider `~> 5.70` |
| AWS CLI | **v2** | apply, SSM, ECR, backups |
| `session-manager-plugin` | latest | `aws ssm start-session` shell into the EC2 (no SSH/port 22) |
| git | any recent | clone the repo |

Verify: `terraform version`, `aws --version`, `session-manager-plugin`.

> **Windows note:** commands below are shown bash-style. On Windows use Git Bash
> or WSL, or translate to PowerShell/CMD (the repo's local-dev rules mandate CMD
> for app dev, but Terraform CLI is identical across shells).

### B. Prerequisites — access

- **AWS credentials** for the target account, via SSO/`aws configure sso` or an
  assumed role. First stand-up (bootstrap + shared) needs broad create rights on
  IAM, KMS, S3, DynamoDB, EC2/VPC, CloudWatch, SNS, Backup, CloudTrail, SSM,
  Route 53, ECR — i.e. the `velocityai-infra-admin` role or equivalent admin.
- **Bedrock model access** enabled for Claude Haiku 4.5 in your region (request
  in the Bedrock console; quota bump comes later in §5).
- **GitHub repo admin** (only if wiring the GitHub Actions pipeline) — to create
  Environments and per-env variables/secrets.
- The **account ID** and **region** (`eu-central-1` throughout), confirmed with
  whoever owns the shared account (§0).

### C. Mental model — what each layer creates

| Layer | Cadence | Creates | Applied by |
|---|---|---|---|
| `bootstrap` | once/account | State bucket + DynamoDB lock + bootstrap KMS; optionally the CI/CD IAM (GitLab runners and/or GitHub OIDC role) | a human admin |
| `shared` | once/account | ECR repos (`velocityai/backend`, `velocityai/frontend`) | human, then CI |
| `foundation(<env>)` | once/env | VPC, KMS CMK, IAM instance role, secrets (SSM), backups | human first, then CI |
| `app(<env>)` | every deploy | EC2 + EBS + EIP, DNS, monitoring, config objects in S3 | human first, then CI |

`bootstrap` and `shared` **must** be applied by a human with elevated creds
(chicken-and-egg: they create the state backend and the role CI later assumes).
`foundation`/`app` can be applied manually for the first environment, then
handed to the pipeline.

### D. Set shared shell variables (used by every command below)

```bash
git clone <repo-url> && cd flowin          # or your checkout path
export ACCT=<account-id>                    # 12-digit AWS account id
export REGION=eu-central-1
export LOCK=velocityai-tfstate-locks
# $B (state bucket name) is set from the bootstrap output in step 2.
```

### E. End-to-end checklist

Do **dev first**, validate it end-to-end, then repeat E5–E6 for `stage` and `prod`.

- [ ] **E0.** Shared-account coordination — [§0](#0-shared-account-coordination-do-this-first)
- [ ] **E1.** Bootstrap the state backend (+ optional CI/CD IAM) — [§1](#1-bootstrap-once-per-account). Capture the `state_bucket` output: `export B=$(terraform -chdir=infra/terraform/bootstrap output -raw state_bucket_name)`
- [ ] **E2.** Wire CI/CD identity — [§1a](#1a-github-actions-cicd-oidc--deploy-role) (Terraform) then
      `docs/GITHUB_CICD_SETUP.md` §2.2–§3 for the GitHub-side config.
      *(Skippable for a pure manual stand-up — you can apply everything by hand
      and add CI later.)*
- [ ] **E3.** Shared layer — ECR repos — [§2](#2-shared-layer-once)
- [ ] **E4.** Foundation + app for `dev` — [§3](#3-per-environment-foundation--app). Do **not** pass `image_tag` (the variable no longer exists — CI owns the tag).
- [ ] **E5.** Day-2 confirmations — [§5](#5-day-2-after-the-first-app-apply). `bootstrap-ec2.sh` runs itself on first boot; just verify the `.bootstrap-done` sentinel ([§5.1](#51-running-bootstrap-ec2sh)). Confirm the SNS email subscription, request the Bedrock quota bump, verify TLS.
- [ ] **E6.** First deploy — **required to start the app.** GitHub: push to `dev`, or **Actions → Deploy → Run workflow → dev** (`GITHUB_CICD_SETUP.md` §5). Until this runs the box is provisioned but idle, and `/health` will not respond.
- [ ] **E7.** Verify (below).
- [ ] **E8.** Repeat E4–E6 for `stage`, then `prod`.

### F. How you know it worked

```bash
# Images landed in ECR
aws ecr list-images --repository-name velocityai/backend --region $REGION

# App healthy on the box (via SSM, no SSH)
aws ssm start-session --target <instance-id>
curl -fsS http://127.0.0.1:8000/health          # {"status":"ok",...}
grep IMAGE /etc/velocityai/app.env                # points at your new <env>-<sha> tag

# App healthy from the internet
curl -fsS https://<fqdn>/health
```

If a step fails, jump to the matching numbered section — each has its own
gotchas — and for CI/CD failures see `docs/GITHUB_CICD_SETUP.md` §7
(troubleshooting). Backups/DR are §6; break-glass/teardown is §9.

---

## 0. Shared-account coordination (do this first)

This runs in a shared AWS Organizations account. Before bootstrapping:

1. **Permissions boundary.** Set `deploy_permissions_boundary_arn` (scoped to
   `velocityai-*`) on the bootstrap so the GitHub deploy role cannot touch
   non-project resources. Ask the account's security team for (or create) a
   `velocityai-*` boundary policy.
2. Confirm the **account ID** and **region** (`eu-central-1`) with whoever owns
   the account; the `account_guard` aborts on a mismatch.
3. **GitHub OIDC provider** — only one per account for a given URL. If a sibling
   project already created it, set `github_oidc_create_provider = false` in your
   tfvars to adopt the existing provider instead of creating a duplicate.

---

## 1. Bootstrap (once per account)

```bash
cd infra/terraform/bootstrap
cp bootstrap.tfvars.example bootstrap.tfvars     # edit account id, bucket name, region
terraform init
terraform apply -var-file=bootstrap.tfvars
```

Note the `state_bucket` output (call it `$B` below).

### 1a. GitHub Actions CI/CD (OIDC + deploy role)

The GitHub Actions pipeline (`ci.yml` + `deploy.yml`) is the **only** CI/CD
path. Its AWS side — the OIDC identity provider, one shared deploy role, the
OIDC trust relationship, and the least-privilege permissions — is codified in
`bootstrap/github_oidc.tf` and is **opt-in** (off by default so a
state-backend-only bootstrap still works). The full operator guide is
[`../../docs/GITHUB_CICD_SETUP.md`](../../docs/GITHUB_CICD_SETUP.md).

Enable it in `bootstrap.tfvars`:

```hcl
create_github_oidc = true
github_org_repo    = "Hexaware-Kiro-Power*/flowin*"
```

then re-apply the bootstrap:

```bash
terraform -chdir=infra/terraform/bootstrap apply -var-file=bootstrap.tfvars
```

Note the outputs and hand them to GitHub:

```bash
terraform -chdir=infra/terraform/bootstrap output github_cicd_role_arn      # → AWS_ROLE_ARN variable per environment
terraform -chdir=infra/terraform/bootstrap output github_oidc_provider_arn
```

Set `github_cicd_role_arn` as the `AWS_ROLE_ARN` variable in each GitHub
Environment (`dev`/`stage`/`prod`), per `GITHUB_CICD_SETUP.md` §3.2. Remaining
non-Terraform setup — creating the GitHub Environments, per-env variables/
secrets, tagging each EC2 `Environment=<env>`, and seeding SSM parameters —
stays in that doc (§2.2–§3).

**Notes / gotchas:**

- The trust policy uses `StringLike` with `repo:Hexaware-Kiro-Power*/flowin*:environment:<env>`. A slug mismatch makes every deploy fail at OIDC auth.
- `ssm:SendCommand` is split into two statements (document + tag-conditioned instance) by design — do not "simplify" it.
- SecureStrings are encrypted with the per-env project CMK (`alias/velocityai` for prod, `alias/velocityai-<env>` otherwise). The instance role can only decrypt that key.

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

Do this per environment (`dev`, then `stage`, then `prod`).

> **One-time-per-environment human step, not part of any deploy.** The GitHub
> Actions pipeline deliberately does **not** run Terraform — it only builds
> images, pushes config to SSM, and restarts the service on an **already
> existing** box. These two applies create the infrastructure it deploys onto:
>
> - `foundation` → VPC, KMS CMK, IAM instance role, SSM secrets, backups
> - `app` → EC2 + data EBS + EIP, DNS record, monitoring, `bootstrap-ec2.sh` in S3
>
> Re-run only when infrastructure itself changes (instance size, alarm
> thresholds, DNS strategy). Shipping application code does **not** need an apply.
>
> **There is no `image_tag` variable.** Terraform does not know or decide which
> image is deployed — `.github/workflows/deploy.yml` owns that end to end (D-2).
> Passing `-var="image_tag=..."` yields a harmless "Value for undeclared
> variable" warning and is ignored. To see what is running, read
> `/etc/velocityai/app.env` on the box.
>
> After the `app` apply the instance self-provisions but the application does
> **not** start — run the GitHub Actions **Deploy** workflow to finish the
> bring-up. See [§5.1](#51-running-bootstrap-ec2sh).

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
  -var="state_bucket=$B" -var="alert_email=<per-env alerts address>"
```

(`app_secret_key`/`db_password` auto-generate; override only via
`TF_VAR_app_secret_key`/`TF_VAR_db_password`.)

`alert_email` has no default and is **not** in the tfvars — pass the environment's
own address (`velocityai-dev-alerts@…` / `-stage-` / `-prod-`) or export
`TF_VAR_alert_email`. Changing it **replaces both SNS subscriptions** and the new
ones start unconfirmed, so don't pass a placeholder value.

**Windows CMD form** (see [§D](#d-set-shared-shell-variables-used-by-every-command-below) for the `set` lines):

```cmd
set ENV=dev

terraform -chdir=infra/terraform/foundation init -reconfigure -backend-config="bucket=%B%" -backend-config="key=velocityai/%ENV%/foundation.tfstate" -backend-config="region=%REGION%" -backend-config="dynamodb_table=%LOCK%" -backend-config="encrypt=true"
terraform -chdir=infra/terraform/foundation apply -var-file="%ENV%.tfvars" -var="expected_account_id=%ACCT%" -var="aws_region=%REGION%"

terraform -chdir=infra/terraform/app init -reconfigure -backend-config="bucket=%B%" -backend-config="key=velocityai/%ENV%/app.tfstate" -backend-config="region=%REGION%" -backend-config="dynamodb_table=%LOCK%" -backend-config="encrypt=true"
terraform -chdir=infra/terraform/app apply -var-file="%ENV%.tfvars" -var="expected_account_id=%ACCT%" -var="aws_region=%REGION%" -var="state_bucket=%B%" -var="alert_email=velocityai-dev-alerts@hexaware.com"
```

---

## 4. CI/CD pipeline (GitHub Actions — steady state)

Two workflows in `.github/workflows/`:

### `ci.yml` — quality gate (no AWS access)

Runs on every PR, push to `main`/`dev`/`staging`, and `v*` tags. Also callable
as a reusable workflow (used by `deploy.yml` as its gate). Three parallel jobs:

- **backend** — ruff, pyright, import-linter, vulture, pytest, pip-audit (warn-only)
- **frontend** — eslint, vitest, build, npm audit (warn-only)
- **security-scan** — gitleaks, checkov, trivy config, tflint

### `deploy.yml` — build, scan, deploy

| Git event | Environment | Image tag | Approval |
|---|---|---|---|
| Push to `dev` | `dev` | `dev-<sha12>` | none |
| Push to `staging` | `stage` | `stage-<sha12>` | none |
| Tag `v*` (from `main`) | `prod` | `<tag>` (e.g. `v1.4.0`) | required reviewer |
| `workflow_dispatch` | chosen | per-env pattern | prod requires reviewer |

**Prod tag enforcement:** prod deploys require a `v*` tag. A non-`v*` ref fails
the `resolve` job with an explicit error. A `allow_untagged_prod` dispatch input
(default false) is the documented break-glass escape for emergencies.

**Job DAG:** `resolve` + `gate` (reusable CI) + `build` run in parallel;
`deploy` waits for all three. A wasted build when CI fails is the accepted
trade-off for ~5 min faster wall time.

**Build:** OIDC assume role → ECR login → buildx backend + frontend → push
`:<tag>` + `:<env>-latest` → trivy image scan (warn-only). No bare `:latest`.

**Deploy:** push GitHub vars/secrets → SSM (SecureStrings encrypted with the
project CMK alias), then SSM RunCommand on the tagged EC2:
1. Pre-condition: assert `BACKEND_IMAGE=`/`FRONTEND_IMAGE=` lines exist in `app.env`
2. Write `docker-compose.yml` (inline, base64 from the repo — D-2)
3. Pin the new image tags in `app.env`, post-condition verify
4. Pre-deploy `pg_dump` (stage/prod only; failure blocks the deploy)
5. `systemctl restart velocityai-app.service` → `velocityai-load-secrets` → `docker compose pull` → `up -d` → `alembic upgrade head`
6. Health-check loop (30 × 10s)

**Rollback** — re-run an older successful deploy from the Actions tab, or use
the break-glass path in RUNBOOK §6.5 to hand-pin a still-resident ECR tag.

---

## 5. Day-2 (after the first app apply)

These are deliberately outside Terraform:

1. **On-host full bootstrap** — see [§5.1](#51-running-bootstrap-ec2sh) below. Normally
   this runs itself; §5.1 covers how to check and how to run it by hand.
2. **First CI deploy** — required to start the app. `bootstrap-ec2.sh` provisions
   the host but does **not** start containers: under D-2 the compose file and image
   pins are delivered inline by the GitHub Actions deploy. Run the **Deploy**
   workflow for the environment (see `docs/GITHUB_CICD_SETUP.md` §5).
3. **Confirm the SNS email** subscription (AWS emails `alert_email`). Until someone
   clicks the link the subscription stays `PendingConfirmation` and **no alerts are
   delivered**. Use the validation helper (M-13):
   `bash infra/terraform/validate-sns-subscriptions.sh <env>`
   This script checks both `velocityai-<env>-alerts` and `velocityai-<env>-critical` topics
   and reports which subscriptions are pending. If the script reports pending subscriptions:
   check your email (including spam) for AWS confirmation links, click to confirm, then re-run.
4. **Request a Bedrock quota increase** for Claude Haiku 4.5 before load tests.
5. **TLS:** certbot issues against the FQDN (nip.io works out of the box; a real
   domain needs the Route 53 path — set `use_nip_io = false` + `route53_zone_name`).
6. **Graceful shutdown timeout** — see [§5.2](#52-graceful-shutdown-timeout-blast-radius) below. The backend now exits cleanly on deploy/restart with a 5-second timeout for draining SSE streams and persisting chat replies, **but any single request slower than 5s will be truncated** (export, render, slow agent invocations). Verify this doesn't hit your typical p99 before load-testing.

### 5.1 Running `bootstrap-ec2.sh`

**You normally do not run this by hand.** Terraform uploads the script to
`s3://<backup-bucket>/config/bootstrap-ec2.sh` (`aws_s3_object.bootstrap_script`),
and the instance's user-data installs `velocityai-firstboot.service`, which fetches
and executes it automatically on first boot — guarded by
`ConditionPathExists=!/var/lib/velocityai/.bootstrap-done` so it runs exactly once
per instance. Expect ~6 minutes.

**Check whether it already ran:**

```bash
aws ssm start-session --target <instance-id> --region $REGION
# on the box:
cat /var/lib/velocityai/.bootstrap-done        # timestamp = completed
sudo systemctl status velocityai-firstboot.service
sudo tail -50 /var/log/velocityai-firstboot.log
sudo tail -50 /var/log/velocityai-bootstrap.log
```

**Run it manually** (recovery, or after editing the script). Two options:

*Option 1 — from your workstation via SSM RunCommand (no SSH):*

```bash
aws ssm send-command \
  --document-name "AWS-RunShellScript" \
  --instance-ids <instance-id> \
  --timeout-seconds 3600 \
  --parameters 'commands=["aws s3 cp s3://<backup-bucket>/config/bootstrap-ec2.sh /opt/velocityai/bootstrap-ec2.sh --region '"$REGION"'","chmod 0755 /opt/velocityai/bootstrap-ec2.sh","bash /opt/velocityai/bootstrap-ec2.sh"]' \
  --region $REGION --query 'Command.CommandId' --output text

# then poll:
aws ssm get-command-invocation --command-id <id> --instance-id <instance-id> \
  --region $REGION --query '[Status,StandardOutputContent,StandardErrorContent]' --output text
```

*Option 2 — interactively on the box:*

```bash
aws ssm start-session --target <instance-id> --region $REGION
sudo bash /opt/velocityai/bootstrap-ec2.sh          # already present after firstboot
```

**To force a re-run of the firstboot unit** (it's sentinel-guarded):

```bash
sudo rm -f /var/lib/velocityai/.bootstrap-done
sudo systemctl start velocityai-firstboot.service
```

The script is **idempotent** and detects two modes: *fresh provision* (blank data
volume → `mkfs.xfs` + `initdb` + generate the DB password into SSM) versus
*recovery* (existing Postgres data dir → skip `initdb`, reuse the SSM password).
Re-running on a healthy box is safe.

**Prerequisites** — it will exit early if these are missing:
`/etc/velocityai/bootstrap.env` (written by user-data, so `terraform apply` of the
app layer must have completed), plus the instance role's `s3_config_read` policy
for the `config/*` prefix and SSM Session Manager access.

**Expected outcome on a fresh box:** host fully provisioned, but the app **not**
running — the script ends with a `SKIP: not starting velocityai-app.service` block
because there is no `docker-compose.yml` yet. That is correct under D-2. Run the
GitHub Actions **Deploy** workflow to finish the bring-up.

### 5.2 Graceful shutdown timeout — blast-radius audit (M-15)

**Configuration:** `backend/docker-entrypoint.sh` sets `--timeout-graceful-shutdown 5` on the uvicorn server.

**Purpose:** When `docker compose stop` or a `docker-entrypoint.sh` restart signal (SIGTERM) arrives, uvicorn now has a 5-second window to:
  1. Stop accepting new connections
  2. Drain in-flight SSE streams (the pump's `await close()` path in run_shutdown.py)
  3. Await pending Concierge tasks (so chat replies finish persisting to the DB)
  4. Close the database pool

**Blast-radius — what gets truncated if still draining after 5s:**

- **Any HTTP request in progress** → aborted mid-response (chunked SSE stream, large file download/export, slow model invocation, slow agent computation)
- **Specifically:** export jobs, render/PDF generation, Bedrock calls, custom-agent calls, SQL queries longer than the timeout
- **Not affected:** completed requests; queued-but-not-started jobs (they timeout server-side per their own limits)

**Impact:** Deploy / restart now takes **~5-8s instead of 30-60s** (the old `docker SIGKILLat stop_grace_period=30s`), but requests slower than 5s will be killed.

**Verify before load-testing:**

```bash
# Locally, with your test suite:
# 1. Find p99 latency for export, render, and agent calls
# 2. Confirm none routinely exceed 4s (leaving headroom)
# 3. If any do, either optimize them or increase the timeout in docker-entrypoint.sh

# On a deployed instance, check the current setting:
aws ssm start-session --target <instance-id> --region $REGION
cat backend/docker-entrypoint.sh | grep timeout-graceful-shutdown
sudo systemctl status velocityai-app.service        # see the running command
```

If any routine operation hits 5s, increase `--timeout-graceful-shutdown` to a value larger than your p99 + 1s buffer, re-apply the app layer (which fetches `docker-entrypoint.sh` from S3), and restart the service.

---

## 6. Backups & disaster recovery

### 6.1 What's protected and how

| Data | Mechanism | RPO | Where |
|---|---|---|---|
| Postgres data (`/var/lib/postgresql`) | Hourly `pg_dump` → S3 (SSE-KMS) | ~1h | `velocityai-pg-dump.timer` on the EC2 |
| Postgres data (`/var/lib/postgresql`) | Nightly EBS snapshot (AWS Backup) | ~24h | `modules/backups` (tag-based selection, `Backup=true` on the data volume) |
| Skills directory (`/opt/velocityai/data/skills`) | Daily tarball → S3 | ~24h | `velocityai-skills-backup.timer` |
| TLS cert/key | Not backed up — recreated by certbot on rebuild | n/a | — |

Both Postgres paths run independently (belt-and-braces): the EBS path restores fast but is crash-consistent (WAL replay on boot); `pg_dump` is slower to restore but portable to any Postgres host.

### 6.2 pg_dump verification

```bash
# List the last few hourly dumps
aws s3 ls "s3://<backup-bucket>/postgres/" --region eu-central-1 | tail -5

# Confirm the timer actually ran (on the instance, via SSM)
aws ssm start-session --target <instance-id>
sudo systemctl list-timers velocityai-pg-dump.timer
sudo journalctl -u velocityai-pg-dump.service --since "-2h"
```

**Known gap:** the `pg_dump_heartbeat` alarm in `modules/monitoring` expects
a custom metric `VelocityAI/Backups::PgDumpHeartbeat`, but the current
`velocityai-pg-dump` script (`infra/scripts/bootstrap-ec2.sh` §16) does not
publish it — it only logs the dump's byte count. Until a
`cloudwatch put-metric-data` call is added to that script, treat the
alarm as **not authoritative** and verify with the commands above instead.
Tracked as a follow-up fix.

### 6.3 Restoring from pg_dump

Must run from an identity that is **not** the production EC2 instance
role — that role is write-only on the backup bucket (`s3_backup_rw` in
`modules/iam` grants `PutObject`, not `GetObject`). Use an operator's SSO
session or a dedicated DR-drill role with `s3:GetObject` + `kms:Decrypt`
scoped to the backup bucket/CMK.

```bash
aws s3 cp "s3://<backup-bucket>/postgres/<timestamp>/velocityai.sql.gz" - \
  | gunzip | psql "$DATABASE_URL"
```

### 6.4 Restoring from EBS snapshot (AWS Backup)

```bash
aws backup list-recovery-points-by-backup-vault \
  --backup-vault-name velocityai-<env>-vault --region eu-central-1

aws backup start-restore-job \
  --recovery-point-arn <arn> \
  --iam-role-arn <backup-role-arn> \
  --metadata '{"encrypted":"true"}' \
  --region eu-central-1
```

Attach the resulting volume to a fresh (or the existing) instance — see the drill below.

### 6.5 Disaster recovery drill — fresh box

Practice quarterly during a maintenance window; record the last-run date here or in the team's runbook tracker.

> **⚠️ Recovery requires a working CI pipeline.** Under D-2 (inline delivery) the
> `docker-compose.yml` and image pins live only in the repo and are pushed to the box
> by `.github/workflows/deploy.yml`. A rebuilt instance provisions its host but comes
> up with **no application containers** until a deploy runs. So DR now depends on
> GitHub being reachable, the repo being in a deployable state, OIDC/IAM working, and
> someone holding deploy rights. This is the accepted trade-off for having a single
> source of truth — but plan for it: if GitHub is unavailable, see the break-glass
> note at the end of this section.

1. Confirm the data volume: `aws ec2 describe-volumes --filters "Name=tag:Name,Values=velocityai-<env>-data"`. Must be `available`, not `in-use` — force-detach if stuck attached to a dead instance.
2. If the data volume was also lost: restore from the latest AWS Backup recovery point (§6.4) **first**, then reattach the restored volume (check `modules/compute`'s attachment wiring — don't assume Terraform adopts a manually created volume).
3. `terraform apply` the `app` layer with the same tfvars — recreates the EC2 instance (`module.compute`), EIP association, and DNS record. Do **not** pass `image_tag`; the variable no longer exists.
4. Wait for the `/var/lib/velocityai/.bootstrap-done` sentinel (~6 min). The script auto-detects recovery mode when a Postgres data dir is already present and skips `initdb`. Expect it to end with `SKIP: not starting velocityai-app.service` — correct, not an error. Troubleshooting: [§5.1](#51-running-bootstrap-ec2sh).
5. **Run the GitHub Actions Deploy workflow** for this environment (**Actions → Deploy → Run workflow → `<env>`**). This is the step that delivers `docker-compose.yml`, pins the image tags, and starts the stack. Without it the box stays idle.
6. Smoke test: `curl https://<fqdn>/health`, log in, run a small pipeline.

**RTO:** ~35-40 min with the data volume intact (~6 min bootstrap + ~10-15 min build & deploy, longer if the ECR layer cache is cold); ~50-55 min when also restoring from an EBS snapshot. **RPO:** last completed hourly `pg_dump` if falling back past the snapshot.

**Break-glass if CI is unavailable.** You can hand-place the two artifacts the deploy would have written, using any still-present ECR tag:

```bash
aws ssm start-session --target <instance-id> --region $REGION
# copy docker-compose.yml from a local checkout, then on the box:
sudo vi /opt/velocityai/docker-compose.yml           # paste repo contents
sudo /usr/local/bin/velocityai-update-image-tag backend  <registry>/velocityai/backend:<tag>
sudo /usr/local/bin/velocityai-update-image-tag frontend <registry>/velocityai/frontend:<tag>
sudo systemctl restart velocityai-app.service
curl -fsS http://127.0.0.1:8000/health
```

List available tags with
`aws ecr list-images --repository-name velocityai/backend --region $REGION`.
The deploy workflow also pushes a moving `:latest` tag, which is usually the safest
choice here. **Include this path in the drill** — it is the only recovery route that
does not depend on GitHub.

---

## 7. Security audit trail (CloudTrail bucket)

`modules/monitoring` stands up a project-owned CloudTrail trail
(`velocityai-<env>-audit`), separate from any org-wide default trail —
needed because the org trail's log group lives in a parent account and
can't have metric filters attached.

- **S3 sink:** `velocityai-<env>-cloudtrail-<account-id>` — versioned, SSE-KMS (project CMK), public access blocked, Glacier transition at 30d, expires at `audit_trail_log_retention_s3_days` (365d default).
- **CW Logs mirror:** `/velocityai/<env>/cloudtrail-audit` — `prevent_destroy=true` (the forensic record must survive trail reconfiguration; the trail and bucket themselves are not protected, so they can be re-topologized).
- **Capture scope:** management events only, account+region-wide (no data events — CloudTrail's advanced-event-selector resource types don't cover SSM Parameter Store or KMS keys).
- **Drives two pager alarms:**
  - `velocityai-<env>-unexpected-secret-read` — any SSM `GetParameter*`/`PutParameter` on `/velocityai/<env>/*` by a principal other than the EC2 instance role.
  - `velocityai-<env>-unexpected-kms-decrypt` — any `kms:Decrypt` against the project CMK by a non-instance-role principal.

### 7.1 If either alarm fires

1. Treat as active compromise until ruled out — do not assume false positive.
2. Identify the caller: CloudWatch Logs Insights on `/velocityai/<env>/cloudtrail-audit`, filter on `$.userIdentity.sessionContext.sessionIssuer.arn` for the alarm's time window.
3. If the caller is not a known operator/CI role: rotate every SSM SecureString (`SECRET_KEY`, `DATABASE_PASSWORD`, any LangSmith key) and take an EBS snapshot of the instance for forensics before touching it further.
4. Cross-reference `/velocityai/<env>/vpc-flow-logs` for anomalous egress around the same timestamp.

---

## 8. Provider lock files (CI portability note)

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

## 9. Break-glass / destroy

Durable resources carry `prevent_destroy = true` (KMS CMK, S3 backup bucket,
AWS Backup vault/plan/selection, data EBS volume, EIP, IAM role + profile,
state bucket + lock table). To intentionally remove one, edit out its
`prevent_destroy`, apply, then destroy — only in a declared maintenance window
with a confirmed off-site copy of any data it holds. The LocalStack fixture has
a `destroy.sh` that `state rm`s these first (safe — ephemeral local state).
```
