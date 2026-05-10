# Flowin infra/ — consolidated audit report

> **Scope.** Read-only audit of the Terraform suite at `infra/` (modules + bootstrap + envs/prod + envs/localstack), cross-checked against `docs/SIMPLE_AWS_DEPLOYMENT.md`, `docs/WORKFLOWS.md`, and the backend code at `backend/app/`.
>
> **Method.** Four parallel auditors with disjoint dimensions: (A) security & shared-account safety, (B) reliability & state, (C) app-fit (Terraform ↔ application code), (D) operational readiness.
>
> **Verdict.** **Not go-live ready.** Structurally the suite is well-engineered (modern provider idioms, account guard, default tags, KMS everywhere, modules well-isolated). Functionally it is broken at three boundaries that no unit test can catch: the SSM-path → env-var translation, the systemd `ENV` setting, and the CloudWatch log-group + Bedrock metric dimensions. The fixes are mechanical and confined to ~6 files; estimate **half an engineer-day**.

## TL;DR — issues blocking go-live

| Severity | Theme | Count | One-line summary |
|---|---|---|---|
| **P0** | Secrets / env wiring | 4 | TF writes `/flowin/${env}/app/secret_key` but the loader and `Settings` expect `SECRET_KEY`. Boot uses defaults silently — including the `dev-secret-key-change-in-production` literal that A1 was meant to ban. |
| **P0** | Monitoring (silent alarms) | 3 | nginx 5xx alarm and DB-connection alarm watch log groups that nothing writes to; Bedrock alarms watch the foundation-model `ModelId` while the app calls via the inference profile. All three permanently report no-data. |
| **P0** | Backups (broken IAM ↔ doc) | 1 | The doc's `pg_dump → s3` script uses `--sse AES256` and the bucket name `flowin-prod-backups`, both of which the Terraform's bucket policy + `var.bucket_name` reject. RPO 1h is impossible until fixed. |
| **P1** | Reliability + state | 6 | Backup plan/selection lack `prevent_destroy`; EIP not protected; backend.tf for prod is empty (operator can fork state); bootstrap recovery path undocumented; log groups not protected; cross-var validation missing. |
| **P1** | Security tightenings | 4 | KMS decrypt missing the `kms:EncryptionContext:PARAMETER_ARN` condition; S3 backup IAM is broader than the doc claims; no `aws:RequestedRegion` on Bedrock invoke; LangSmith params absent in TF. |
| **P1** | Observability | 5 | Missing alarms (WS disconnect, Bedrock InputTokenCount daily, AWS Backup job failure); host alarms use `treat_missing_data="notBreaching"` so a dead CW Agent goes silent; on-host pg-dump timer has no heartbeat alarm. |
| **P2** | Network hardening | 4 | Default VPC SG not locked down; no VPC flow logs; VPC endpoints have no endpoint policies; default route table unmanaged. |
| **P2** | Documentation drift | 3 | Backup retention 35d in TF vs 365d in doc; doc claims "S3 IAM is write-only" while TF grants reads; doc references `flowin-prod-ws-disconnect-spike` alarm that doesn't exist. |
| **P3** | Hardening / cleanup | ~12 | Vault Lock + Object Lock; `disable_api_termination`; SNS topic policy; cert expiry monitoring; etc. |

## What's right (don't undo)

- **Account-id + region guard.** `infra/modules/account_guard/main.tf:9-46` uses `terraform_data.lifecycle.precondition` (aborts plan/apply on mismatch) plus `check` blocks (warning-level second line). Outputs are wired downstream so a bad apply genuinely cannot proceed.
- **No forbidden resource types.** Verified — `grep -rE "aws_organizations_|aws_iam_account_|aws_s3_account_public_access_block|aws_config_|aws_securityhub_|aws_macie2_account|aws_guardduty_detector|aws_inspector_assessment_target|aws_ec2_default_" infra/ --include="*.tf"` returns zero.
- **Bedrock invoke policy is exactly right.** `infra/policies/bedrock-invoke.json` permits `InvokeModel`, `InvokeModelWithResponseStream`, `Converse`, `ConverseStream` against the foundation-model ARN (region-pinned), the cross-region wildcard (required for inference fan-out), and the inference-profile ARN. Matches `docs/SIMPLE_AWS_DEPLOYMENT.md` §5.3.
- **State backend.** `infra/bootstrap/main.tf` has versioning, BPA, KMS-or-AES256, BucketOwnerEnforced, TLS-only bucket policy, `prevent_destroy` on bucket and DynamoDB lock; PITR on the lock table.
- **SSH defaults.** `var.ssh_allowed_cidrs` defaults `[]` and validates that `0.0.0.0/0` is rejected (`infra/modules/network/variables.tf:43-46`). No accidental world-SSH.
- **`prevent_destroy` placement on stateful resources** matches the README's claimed list (data EBS, KMS key, S3 backup bucket, AWS Backup vault, state bucket, lock table).
- **Modern AWS provider idioms.** No deprecated S3 inline blocks, no inline `aws_iam_role.inline_policy`, no `aws_security_group.ingress`. Provider pinned `~> 5.70`, lockfile committed.
- **Tag discipline.** Provider `default_tags` + per-resource `Component` tag means Resource Groups split correctly. Backup selection is tag-driven (`Backup=true`) and the data EBS is tagged accordingly — both ends match.
- **Bedrock action set is exactly the four the app uses** — verified `ChatBedrockConverse.astream()` in `backend/app/agents/base.py:88-92` calls `ConverseStream`, which is permitted.
- **Instance sizing matches `WORKFLOWS.md` §B7/§B8** — `m6i.xlarge` (16 GB RAM) at 4 vCPU sized for ~150 concurrent sessions / ~50 heavy pipelines. Data EBS 50 GB matches §B8 disk-growth model.
- **VPC interface endpoints** cover every API the IAM role uses (Bedrock + bedrock-runtime + SSM + ssmmessages + ec2messages + Logs + S3 gateway).

---

## Findings by file

### `infra/modules/secrets/main.tf` — Audit C P0 (most severe)

The audit produced this verification table:

| SSM key (TF writes) | Doc Appendix C lists | §9.3 loader → env | Appendix D loader → env | `Settings` reads | Verdict |
|---|---|---|---|---|---|
| `/flowin/${env}/llm/provider` | `/llm/provider` | `provider` | `LLM_PROVIDER` | `LLM_PROVIDER` | App-D OK; §9.3 broken |
| `/flowin/${env}/llm/region` | `/llm/region` | `region` | `LLM_REGION` | **`AWS_REGION`** | **P0 — name mismatch in BOTH loaders** |
| `/flowin/${env}/llm/model_id` | `/llm/model_id` | `model_id` | `LLM_MODEL_ID` | **`BEDROCK_MODEL_ID`** | **P0 — name mismatch in BOTH loaders** |
| `/flowin/${env}/app/secret_key` | doc lists `/flowin/prod/SECRET_KEY` (top-level) | `secret_key` | `app_secret_key` | `SECRET_KEY` | **P0 — TF path wrong, every loader produces wrong env name** |
| `/flowin/${env}/app/db_password` | doc lists `/flowin/prod/DATABASE_PASSWORD` AND `/flowin/prod/DATABASE_URL` | `db_password` | `app_db_password` | (app reads `DATABASE_URL`) | **P0 — app needs composed DATABASE_URL; nothing produces it** |
| `/flowin/${env}/app/cors_origins` | `/flowin/prod/CORS_ORIGINS` (top-level) | `cors_origins` | `app_cors_origins` | `CORS_ORIGINS` | **P0** |
| `/flowin/${env}/app/access_token_expire_hours` | `/flowin/prod/ACCESS_TOKEN_EXPIRE_HOURS` | `access_token_expire_hours` | `app_access_token_expire_hours` | `ACCESS_TOKEN_EXPIRE_HOURS` | **P0** |
| `/flowin/${env}/anthropic/api_key` | yes | `api_key` | `ANTHROPIC_API_KEY` | `ANTHROPIC_API_KEY` | App-D OK; §9.3 broken |
| **MISSING**: `/flowin/${env}/SECRET_KEY` | required (top-level) | – | – | required | **P0** |
| **MISSING**: `/flowin/${env}/DATABASE_URL` | required | – | – | required (alembic + app) | **P0** |
| **MISSING**: `/flowin/${env}/CORS_ORIGINS` | required | – | – | – | **P0** |
| **MISSING**: `/flowin/${env}/ACCESS_TOKEN_EXPIRE_HOURS` | required | – | – | – | **P0** |
| **MISSING**: `/flowin/${env}/ENV` | – | – | – | required by A1 boot guard | **P0 — disarms the SECRET_KEY hard-fail** |

Concrete consequences when applied as-is:
- App boots in `ENV=development` (default in `core/config.py:62`) — A1 SECRET_KEY hard-fail is silently disarmed.
- `SECRET_KEY` falls back to the literal `dev-secret-key-change-in-production` shipped with the codebase.
- `DATABASE_URL` falls back to `sqlite:///./dev.db` — Postgres + alembic are bypassed entirely.
- `CORS_ORIGINS` falls back to `["http://localhost:3000"]` — frontend at the real domain is rejected.

**Fix direction.** Pick one canonical schema and align all three layers. Recommended (matches Appendix C):
- TF writes UPPERCASE top-level keys: `/flowin/${env}/SECRET_KEY`, `/flowin/${env}/DATABASE_URL`, `/flowin/${env}/CORS_ORIGINS`, `/flowin/${env}/ACCESS_TOKEN_EXPIRE_HOURS`, `/flowin/${env}/ENV`.
- Keep nested `/flowin/${env}/llm/*` and `/flowin/${env}/anthropic/*` paths — but change the loader's translation rule for these two namespaces specifically: `llm/provider→LLM_PROVIDER`, `llm/region→AWS_REGION`, `llm/model_id→BEDROCK_MODEL_ID`, `anthropic/api_key→ANTHROPIC_API_KEY`.
- `DATABASE_URL` is composed by the on-host bootstrap (it embeds `127.0.0.1`, which Terraform doesn't know). The doc Appendix D should write the parameter from `flowin-load-secrets` step, not Terraform.

Files to change: `infra/modules/secrets/main.tf`, `infra/modules/secrets/variables.tf`, `docs/SIMPLE_AWS_DEPLOYMENT.md` §9.3 + Appendix C + Appendix D step 9 + Appendix B systemd unit (add `Environment=ENV=production`).

### `infra/modules/monitoring/main.tf` — Audit D P0

Three alarm pathways are silently broken. All would deploy clean and report no-data forever in production:

1. **nginx 5xx alarm** — `main.tf:151-162` filters log group `/flowin/${env}/nginx`; `docs/SIMPLE_AWS_DEPLOYMENT.md:1193-1194` ships nginx access/error to `/flowin/prod/nginx-access` + `nginx-error`.
2. **DB connection alarm** — `main.tf:185-196` filters `/flowin/${env}/uvicorn`; the on-host CW Agent ships uvicorn-via-journald to `/flowin/prod/app`.
3. **Bedrock throttles + 5xx alarms** — `main.tf:222-258` set `dimensions = { ModelId = var.bedrock_model_id }` (foundation-model ID), but the app calls Bedrock via `var.bedrock_inference_profile_id`. CloudWatch metrics dimension by the inference-profile ID, so the alarms watch nothing.

**Fix direction.** Reconcile log-group names in one pass (rename TF groups to `nginx-access` / `nginx-error` / `app` etc., matching the on-host CW Agent config). For Bedrock dimension: pass `local.effective_model_id` (which already exists in `infra/envs/prod/locals.tf:8`) to the monitoring module instead of `var.bedrock_model_id`.

### `infra/modules/backups/` — Audit D P1

Several issues compound to make the documented RPO 1h / retention 365d unachievable:

- **Bucket name** — TF requires operator-supplied `var.bucket_name`; doc's `pg_dump` script writes to hard-coded `s3://flowin-prod-backups`. Mismatch by default. Fix: doc uses `${FLOWIN_BACKUP_BUCKET}` (already plumbed in `infra/envs/prod/main.tf:90-94`).
- **SSE policy** — bucket policy (`backups/main.tf:91-140`) requires `s3:x-amz-server-side-encryption = aws:kms` with the project CMK; doc's script uses `--sse AES256`. Every PUT returns 403. Fix: doc uses `--sse aws:kms --sse-kms-key-id $FLOWIN_KMS_KEY_ID`.
- **Backup plan retention** — TF default 35d, doc says 365d with cold transition at 30d. Fix: bump `daily_backup_retention_days` and add `cold_storage_after_days` to the lifecycle block.
- **Lifecycle gap** — `backups/main.tf:58-89` transitions current versions to GLACIER_IR but never expires them. Bucket grows forever. Fix: add `expiration { days = 365 }` for the `postgres/` prefix.
- **No failure alerting** — no `aws_backup_vault_notifications` and no CW Events rule for `Backup Job State Change`. A failed daily snapshot is silent.
- **No heartbeat for on-host pg-dump timer** — the RPO 1h claim depends on a systemd timer outside Terraform's view; if the timer dies, no alert. Fix: alarm on "no PutObject under `s3://.../postgres/` for >2h".
- **`prevent_destroy` missing** on `aws_backup_plan.daily` and `aws_backup_selection.by_tag` (`backups/main.tf:196-236`).

### `infra/modules/iam/` + `infra/policies/` — Audit A P1/P2

- **`policies/kms-decrypt.json:1-15`** allows `kms:Decrypt`, `kms:GenerateDataKey`, `kms:DescribeKey` on the entire project CMK with no `kms:EncryptionContext:PARAMETER_ARN` condition. The doc §5.3 prescribes the encryption-context-bound condition. Today the EC2 role can decrypt EBS, S3 backup objects, log streams — not just SSM SecureStrings.
- **`policies/s3-backup-rw.json:8-23`** grants `s3:GetObject`, `s3:ListBucket`, `s3:GetBucketLocation` on the entire bucket. Doc §5.3 line 357 explicitly claims "the S3 statement is *write-only* under one prefix" — that promise is not realized.
- **`policies/bedrock-invoke.json`** has no `Condition: { StringEquals: { "aws:RequestedRegion": [...] } }`. A leaked instance credential could invoke Bedrock in any region the account has Bedrock enabled. Cost vector — fix by pinning to the EU regions the inference profile fans to.
- **AWS Backup service-role trust policy** (`backups/main.tf:144-154`) trusts `backup.amazonaws.com` unconditionally. Add `aws:SourceAccount` for confused-deputy defence.

### `infra/modules/network/` — Audit A P2

- **Default VPC SG not locked down.** `aws_vpc.this` is created but no `aws_default_security_group` resource emptying the default. Future foot-gun.
- **VPC endpoint policies missing.** Every interface endpoint and the S3 gateway endpoint defaults to `Action:*, Principal:*, Resource:*` — defence-in-depth gap.
- **No VPC flow logs.** `aws_flow_log` absent. GuardDuty (org-managed) will still detect EC2 compromises, but project-side incident response can't reconstruct flows.
- **Default route table unmanaged.** Same family as default-SG.
- **EC2 missing `disable_api_termination = true`.** Console operator with `ec2:TerminateInstances` can vaporise the box; data EBS survives but reattach is manual.

### `infra/envs/prod/` — Audit B P1

- **`backend.tf` is empty.** Operators must pass every backend-config flag at `init` time. Risk: two engineers `init` against different `key`s and silently fork state. Fix: commit non-secret keys (`key`, `region`, `encrypt`, `dynamodb_table`); leave only `bucket=` for `-backend-config`.
- **Cross-var validation missing.** `availability_zone` is not validated against `aws_region`; `cors_origins` not validated as JSON URL list; `route53_zone_name` not validated for shape; `bedrock_model_id` not validated for `^anthropic\.claude-` prefix.
- **`terraform.tfvars.example` placeholders satisfy length validation.** `app_secret_key = "REPLACE_ME_..."` is 80 chars long, so it passes the `length >= 32` check. Operator who blindly applies the example deploys with a guessable secret. Fix: shorten placeholder so validation rejects it.

### `infra/bootstrap/` — Audit B P1

- **Recovery path undocumented.** Bootstrap uses local state in `infra/bootstrap/terraform.tfstate` (gitignored, correctly). If the operator's laptop dies, both bootstrap resources have `prevent_destroy=true` so they can't be reconstructed via `terraform apply`. The README doesn't mention `terraform import aws_s3_bucket.tfstate <name>` + `terraform import aws_dynamodb_table.tflock <name>` as the recovery path.

---

## Recommended action plan (prioritised)

### Phase 1 — Unblock go-live (~half a day)

| # | Audit | Severity | Action | Files |
|---|---|---|---|---|
| 1 | C | P0 | Align Terraform SSM paths + doc loader + systemd unit so `Settings` actually receives `SECRET_KEY`, `DATABASE_URL`, `CORS_ORIGINS`, `ACCESS_TOKEN_EXPIRE_HOURS`, `ENV`, `AWS_REGION`, `BEDROCK_MODEL_ID`, `LLM_PROVIDER`, `ANTHROPIC_API_KEY` | `infra/modules/secrets/{main,variables}.tf`, `docs/SIMPLE_AWS_DEPLOYMENT.md` (§9.3, App C, App D, App B systemd `Environment=`) |
| 2 | D | P0 | Reconcile log-group names: TF creates `nginx-access` / `nginx-error` / `app`; metric filters target the right ones | `infra/modules/monitoring/main.tf` + on-host CW Agent config in App D |
| 3 | D | P0 | Bedrock alarm dimensions use `local.effective_model_id` (inference profile) | `infra/envs/prod/main.tf` + `infra/modules/monitoring/variables.tf` |
| 4 | D | P0 | pg_dump script: use `--sse aws:kms --sse-kms-key-id $FLOWIN_KMS_KEY_ID` and `${FLOWIN_BACKUP_BUCKET}` | `docs/SIMPLE_AWS_DEPLOYMENT.md` §11 + App D + App B.5 |

### Phase 2 — Production hardening (~1 day)

| # | Audit | Severity | Action |
|---|---|---|---|
| 5 | A | P1 | Add `kms:EncryptionContext:PARAMETER_ARN` condition to `kms-decrypt.json`; tighten `s3-backup-rw.json` to write-only or document the deviation |
| 6 | A | P1 | Add `aws:RequestedRegion` condition to `bedrock-invoke.json` (cost vector on credential leak) |
| 7 | A | P1 | AWS Backup service-role trust policy: add `aws:SourceAccount` + `aws:SourceArn` |
| 8 | B | P1 | `prevent_destroy = true` on backup plan + selection + log groups + EIP (with prod-only `var.protect_eip = true`) |
| 9 | B | P1 | Backend.tf for prod: commit non-secret keys; require only `bucket=` from operator |
| 10 | B | P1 | Document bootstrap recovery via `terraform import` |
| 11 | D | P1 | Add missing alarms: WS disconnect spike, Bedrock InputTokenCount daily, AWS Backup job failure (vault notifications or CW Events) |
| 12 | D | P1 | Switch host alarms (CPU/mem/disk) from `notBreaching` to `breaching` so a dead CW Agent pages |
| 13 | D | P1 | pg-dump timer heartbeat alarm: no S3 PUT under `postgres/` for >2h |
| 14 | D | P1 | AWS Backup retention 365d + cold storage at 30d to match doc |
| 15 | A | P1 | LangSmith parameters (3) added to `secrets` module, optional like `anthropic_api_key` |

### Phase 3 — Defence-in-depth (when post-launch)

| # | Audit | Severity | Action |
|---|---|---|---|
| 16 | A | P2 | Lock down default VPC SG + default route table |
| 17 | A | P2 | Add VPC flow logs (project log group) |
| 18 | A | P2 | Add VPC endpoint policies pinning `aws:PrincipalAccount` |
| 19 | A | P2 | EC2 `disable_api_termination = true` and `disable_api_stop = true` |
| 20 | A | P3 | Backup vault Lock (compliance mode) + S3 Object Lock (governance mode) |
| 21 | D | P3 | Cert expiry monitoring (CW Agent on `/var/log/letsencrypt/*` or Route 53 health check) |
| 22 | D | P3 | Cross-region replication of pg-dumps bucket |
| 23 | A | P3 | SNS topic resource policy with `aws:SourceArn` constraint |
| 24 | B | P3 | `aws_iam_role_policies_exclusive` and `aws_iam_role_policy_attachments_exclusive` to lock attachments |

---

## Per-module scorecard

| Module | A — Security | B — Reliability | C — App-fit | D — Ops |
|---|---|---|---|---|
| `account_guard` | ✅ | ✅ | n/a | n/a |
| `network` | 🟡 (4 P2 hardenings) | ✅ | ✅ | n/a |
| `kms` | 🟡 (1 P1 condition gap) | ✅ | ✅ | n/a |
| `iam` + `policies/` | 🟠 (3 P1 / 1 P2) | ✅ | ✅ Bedrock policy is exact | n/a |
| `secrets` | ✅ encryption | ✅ | ❌ **P0 path mismatch — boot fails** | n/a |
| `compute` | 🟡 (`disable_api_termination`) | 🟡 (EIP `prevent_destroy`) | ✅ | n/a |
| `dns` | ✅ data-source only | ✅ | ✅ | n/a |
| `backups` | 🟡 (S3 IAM scope + trust policy) | 🟡 (plan/selection `prevent_destroy`) | n/a | ❌ **P0 SSE+name mismatch + missing alarms** |
| `monitoring` | 🟡 (no SNS resource policy) | 🟡 (log groups `prevent_destroy`) | n/a | ❌ **P0 broken log-group + Bedrock dimensions** |
| `resourcegroups` | ✅ | ✅ | ✅ tags are right | ✅ |
| `bootstrap` | ✅ | 🟡 (recovery undocumented) | n/a | n/a |

---

## Verdict per audit

- **Audit A (Security & shared-account safety):** Strong foundation. 4 P1 issues to fix before public traffic (KMS context, S3 read scope, Bedrock region condition, Backup trust policy). Hardening list (P2/P3) is normal post-launch work.
- **Audit B (Reliability & state):** One P0 (SNS cross-region for billing alarm — actually a real bug, easy fix). Six P1s, all mechanical. Solid `prevent_destroy` placement on the README's claimed list; gaps are small additions.
- **Audit C (App-fit):** Verdict from the auditor: *"structurally sound but functionally broken at the secrets boundary."* Bedrock IAM is exactly right. Instance sizing matches the §B7/§B8 model. Network endpoints cover every API the backend hits. But the secrets-path / env-var / `ENV=production` mismatch means **deploying as-is will silently boot in development mode with the codebase-shipped default SECRET_KEY** — directly negating the A1 fix.
- **Audit D (Operational):** *"Not go-live ready."* Three P0 alarm pathways are silently broken; pg_dump can't write to its bucket; AWS Backup retention 35d ≠ doc's claimed 365d; no failure alerting on backup jobs.

## Next step

Want me to send agents to fix Phase 1 (the 4 P0 items)? They're tightly coupled — secrets, log groups, Bedrock dimension, pg-dump SSE — and ideally land in one commit so the next LocalStack smoke + future sandbox apply find a coherent system. Estimate: ~half a day.
