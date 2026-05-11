# Phase C TF Correctness Audit

Scope: correctness only — broken refs, lifecycle, provider drift, state-safety, dead code, deprecation, mis-wiring, fmt/validate, alarm coherence, tagging coherence, user-data shell. Security (IAM scope, KMS, network, secrets) is covered by the parallel agent and deliberately NOT re-litigated here.

Audited tree (byte-identical to deployed `infra` branch):
- `infra/bootstrap/`
- `infra/envs/prod/`
- `infra/envs/localstack/`
- `infra/modules/{account_guard,backups,compute,dns,ecr,iam,kms,monitoring,network,resourcegroups,secrets}/`
- `infra/policies/*.json`
- `infra/scripts/bootstrap-ec2.sh`

Tool versions: Terraform 1.15.1; AWS provider locked at 5.100.0; random 3.8.1; null 3.2.4 (declared but unused — see HIGH-3).

---

## Summary

| Severity | Count |
|---|---|
| CRITICAL (breaks `apply` or causes silent state damage) | 0 |
| HIGH (correctness drift, plan/apply hazard, broken contract) | 9 |
| MEDIUM (maintainability, doc/code drift, unused code) | 12 |
| LOW (style, formatting, redundancy) | 7 |
| Verified clean | 14 areas |

Top 5 (read these first):
1. **HIGH-1** — `terraform fmt` drift in 5 files (re-confirmed from Phase A; not auto-fixed).
2. **HIGH-2** — Comment drift in `modules/iam/main.tf:52-54` claims 3 EU regions in bedrock policy; JSON actually pins 7.
3. **HIGH-4** — `aws_eip.this` mis-tagged `Component = "network"` in `modules/compute/main.tf:173`; README and resourcegroups module both say EIP belongs to `compute` group, so it lands in the wrong AWS Resource Group.
4. **HIGH-5** — `aws_s3_object.compose_yaml` in `envs/prod/main.tf:149` uses `Component = "config"`, but `resourcegroups.components` defines only 7 components (network/compute/storage/monitoring/iam/secrets/ecr). The compose object isn't queryable from any Resource Group.
5. **HIGH-7** — `flowin-load-secrets` (bootstrap-ec2.sh:488) maps `llm/inference_profile_id` SSM parameter to `BEDROCK_INFERENCE_PROFILE_ID`, but Terraform's `modules/secrets/main.tf` never creates that parameter. The case branch is dead; on every boot the loader emits `WARN: ignoring unknown parameter` for it only when the operator manually adds it. Functionally harmless (app reads `BEDROCK_MODEL_ID`), but the secrets module / loader contract is incomplete.

---

## terraform fmt + validate results

```
$ terraform fmt -check -recursive infra/
infra/envs/localstack/providers.tf
infra/envs/localstack/terraform.tfvars
infra/modules/backups/main.tf
infra/modules/kms/main.tf
infra/modules/resourcegroups/variables.tf
EXIT=3
```

```
$ terraform validate (envs/prod)        => Success
$ terraform validate (envs/localstack)  => Success
$ terraform validate (bootstrap)        => Success
```

Per-file fmt drift (diffs run):
- `infra/envs/localstack/providers.tf` — column alignment in the long `endpoints { ... }` map (one entry overflows the longest-key width — `elasticbeanstalk = ...` and `kinesisanalytics = ...` shift indentation of every other line).
- `infra/envs/localstack/terraform.tfvars` — single drift: `backup_bucket_name          = "..."` has extra spaces.
- `infra/modules/backups/main.tf:239-243` — `aws_backup_plan.daily` rule block: when `enable_continuous_backup = false` was added (later), the other attributes were not re-aligned.
- `infra/modules/kms/main.tf:9-15` — `aws_kms_key.this`: `customer_master_key_spec` and `multi_region` attributes break alignment vs. the rest.
- `infra/modules/resourcegroups/variables.tf:17-21` — `default = { ... }` map: keys `storage`, `iam`, `secrets`, `ecr` have one fewer space than `network`, `compute`, `monitoring`.

All five would be auto-fixed by `terraform fmt -recursive infra/`. Recommend wiring a CI gate.

---

## CRITICAL — none

No issues that would break `terraform apply` outright or cause state damage on the next operator-driven plan.

---

## HIGH (correctness drift, plan/apply hazard, broken contract)

### HIGH-1 — terraform fmt drift in 5 files
- Files: see fmt section above.
- Severity: HIGH — Phase A flagged this; still unfixed. Each PR after this point should rebase clean against `terraform fmt -check -recursive`, so the drift will keep growing until a CI gate is added.
- Fix: run `terraform fmt -recursive infra/`, commit, add CI gate (`terraform fmt -check -recursive infra/` as a pre-merge job).

### HIGH-2 — Comment drift: bedrock IAM policy comment lists 3 regions, JSON has 7
- File: `infra/modules/iam/main.tf:52-54`
- The TF comment reads: "*The list is hardcoded in the JSON (eu-central-1, eu-west-1, eu-west-2)*"
- The actual `policies/bedrock-invoke.json` `aws:RequestedRegion` allow list is **7 regions**: `eu-central-1`, `eu-north-1`, `eu-south-1`, `eu-south-2`, `eu-west-1`, `eu-west-2`, `eu-west-3`. (Confirms the Phase B finding.)
- Severity: HIGH — wrong documentation on a security-sensitive comment will mislead the next operator into thinking the policy is tighter than it is, and they'll skip adding (or removing) a region under a false assumption.
- Fix: update the comment to match the 7-region list, or move the list into a TF local so the comment cannot drift again (`local.bedrock_eu_regions = [...]` referenced by both the IAM templatefile and the comment).

### HIGH-3 — `null` provider declared but never used
- Files: `infra/bootstrap/versions.tf:11`, `infra/envs/prod/versions.tf:18`, `infra/envs/localstack/versions.tf:13` (all three).
- No `resource "null_resource"` and no `data "null_*"` anywhere in the tree (`grep -rn "null_" infra/ --include="*.tf"` returns zero).
- Provider is downloaded by `terraform init` (lock files include it: `terraform-provider-null_v3.2.4`), which is wasted bandwidth/disk.
- Severity: HIGH — declared dependencies that don't exist are an early-warning sign of dead code or a half-finished refactor.
- Fix: remove the `null = { ... }` entries from all three `versions.tf` files and run `terraform init -upgrade` to refresh the lock files.

### HIGH-4 — Elastic IP mis-tagged with `Component = "network"`
- File: `infra/modules/compute/main.tf:173`
- The `aws_eip.this` resource is tagged `Component = "network"`, but the README (line 183) and `modules/resourcegroups/variables.tf:16` both classify the EIP under `compute` (the per-component group `flowin-${env}-compute` queries on tag `Component=compute`).
- Effect: the EIP lands in `flowin-${env}-network` instead of `flowin-${env}-compute`; an operator looking up the project's compute resources in the AWS console won't see the EIP.
- Severity: HIGH — visible product surface is wrong; mis-tagging is invisible at apply time (no error), surfaces only when an operator opens the Resource Groups console.
- Fix: change `Component = "network"` → `Component = "compute"` on line 173.

### HIGH-5 — `aws_s3_object.compose_yaml` uses undeclared component value `"config"`
- File: `infra/envs/prod/main.tf:149`
- The object's tags include `Component = "config"`, but `modules/resourcegroups/variables.tf:14-22` defines only 7 components: network, compute, storage, monitoring, iam, secrets, ecr.
- Effect: the compose object isn't reachable through any per-component Resource Group; it only appears in `flowin-${env}-all`.
- Severity: HIGH — analogous to HIGH-4 but at the env layer.
- Fix options (any one of):
  - Change to `Component = "secrets"` (since the loader treats it as config-rotation).
  - Add `config` to the `components` map default in `modules/resourcegroups/variables.tf` and wire a per-component group for it (consistent with the README).
  - Move the compose YAML upload into the secrets module if the intent was config-grouping.

### HIGH-6 — Comment says EU profile spans 7 regions but inference-profile ARN is region-pinned to deploy region
- File: `infra/policies/bedrock-invoke.json:16` — `"arn:${partition}:bedrock:${region}:${account_id}:inference-profile/${inference_profile_id}"`
- Cross-region inference profiles have a single home region for their resource ARN (eu-central-1 for `eu.anthropic.*`), even though the underlying compute spans 7 regions.
- The `aws:RequestedRegion` condition (7 regions) controls where the *call may run*. The ARN region controls where the *profile object lives*. They're different concepts. Today this works because the operator deploys in eu-central-1 (the profile's home), and `${region}` resolves to eu-central-1.
- Risk: if a future operator deploys this stack in eu-west-1 (a permitted RequestedRegion), the inference-profile ARN renders as `arn:aws:bedrock:eu-west-1:<account>:inference-profile/eu.anthropic...`, which does not exist (the profile lives in eu-central-1). The first Bedrock call from the EC2 would 403, and the alarm wiring (cloudwatch dimension on ModelId) wouldn't match either.
- Severity: HIGH — works today, silently breaks if anyone re-uses these modules in another EU region.
- Fix sketch: add a separate `var.bedrock_profile_home_region` (default `eu-central-1`) and substitute it for `${region}` in the inference-profile ARN segment only, OR document that the IAM policy assumes deployment from the profile's home region.

### HIGH-7 — Dead branch / missing parameter: `BEDROCK_INFERENCE_PROFILE_ID`
- File: `infra/scripts/bootstrap-ec2.sh:488` reads:
  `llm/inference_profile_id) emit BEDROCK_INFERENCE_PROFILE_ID "$value" ;;`
- The matching SSM parameter is never created by `modules/secrets/main.tf` — only `llm/region` and `llm/model_id` exist.
- Effect: the case branch is unreachable. The app never receives `BEDROCK_INFERENCE_PROFILE_ID`. This is mostly harmless because when `var.use_inference_profile_for_app = true`, `BEDROCK_MODEL_ID` is already set to the profile ID. But the loader↔secrets contract is incomplete and confusing.
- Severity: HIGH — silent contract mismatch; will trip the next developer who tries to read both env vars.
- Fix sketch: either remove the case branch (the app already reads `BEDROCK_MODEL_ID`), or add `aws_ssm_parameter.llm_inference_profile_id` to `modules/secrets/main.tf` with `value = var.bedrock_inference_profile_id`.

### HIGH-8 — `var.protect_eip` is plumbed but inert
- Files: `infra/modules/compute/variables.tf:117-121`; `infra/envs/localstack/main.tf:149` sets `protect_eip = false`.
- The compute module declares `var.protect_eip` (default `true`) but never references it. The EIP is unconditionally `prevent_destroy = true` (compute/main.tf:189), as documented in the var's own description — the variable is "advisory only" until Terraform loosens its lifecycle-field literal-bool restriction.
- Effect: the localstack env passes `protect_eip = false` thinking it changes behaviour; it doesn't. The destroy.sh workaround (state-rm the EIP before destroy) is the only thing that works.
- Severity: HIGH — operator-misleading API. Phase A confirmed this is intentional (Terraform 1.x rejects var refs in lifecycle), but plumbing the var without referencing it makes future grep-driven understanding harder.
- Fix sketch: either (a) delete the `var.protect_eip` declaration entirely and rely on the destroy.sh workaround; or (b) reference it in a `terraform_data` precondition so a `false` value at apply time emits a diagnostic (not a behaviour change).

### HIGH-9 — `null` provider in lock files but never bound to a resource — wasted init time
- Same root cause as HIGH-3. The lock files (`infra/envs/{prod,localstack}/.terraform.lock.hcl` and `infra/bootstrap/.terraform.lock.hcl`) all pin `hashicorp/null = 3.2.4`. Removing the entries from `versions.tf` and re-running `terraform init -upgrade` drops it from the lock files too.
- (Listed as a separate HIGH because the lock-file drift compounds the dead-dependency hazard — `terraform init` against a fresh checkout pulls the null provider.)

---

## MEDIUM (maintainability, doc/code drift, unused code)

### MED-1 — README claims `aws provider ~> 5.70` but lock files have 5.100.0
- File: `infra/README.md:209` says "AWS provider `~> 5.70`".
- The `~> 5.70` pin is correct (any 5.x ≥ 5.70 satisfies it). Lock files all show 5.100.0. README phrasing is misleading because it implies 5.70 is the in-use version; in practice the floating-minor pin lets 5.100.0 in.
- Fix: clarify the README to say "AWS provider pinned to `~> 5.70` (5.70 or newer minor)".

### MED-2 — `secrets/outputs.tf:7,11` outputs without descriptions
- File: `infra/modules/secrets/outputs.tf`
- `output "app_secret_key_parameter_arn"` and `output "db_password_parameter_arn"` have no `description = ...`.
- Every other output in the tree has a description. Inconsistent.
- Fix: add `description = "ARN of the SECRET_KEY SSM parameter."` and `description = "ARN of the DATABASE_PASSWORD SSM parameter."` respectively.

### MED-3 — `ecr/outputs.tf:26-29` orphan TODO comment
- File: `infra/modules/ecr/outputs.tf:26-29`
- The trailing comment is a TODO about linking ECR push/pull docs. Either complete the link (add reference to the doc that landed) or remove the TODO — it's been here long enough to be stale.

### MED-4 — `description_separator` in localstack is `"-"` but module default is `" - "`
- File: `infra/envs/localstack/main.tf:222` sets `description_separator = "-"`.
- The module default (`infra/modules/resourcegroups/variables.tf:33`) is `" - "` (hyphen with surrounding spaces).
- Effect: in localstack the per-component group descriptions read like "Flowin compute-EC2 root-EBS-volume..." (run-together). In prod they read "Flowin compute - EC2 root EBS volume...".
- Severity: MEDIUM — purely cosmetic; resourcegroups' description validator (`^[\s a-zA-Z0-9_.-]*$`) accepts both.
- Fix: align localstack's value to `" - "` unless there's a localstack-specific reason for the difference (none documented).

### MED-5 — Localstack `components` map has trailing-space artefacts inherited from real-AWS prod
- File: `infra/envs/localstack/main.tf:224-232`
- The localstack overrides include hyphenated descriptions like "EC2 root-EBS-volume EIP" (substituting hyphens for commas the resourcegroups validator rejects). Fine. But "EIP" appears in the **compute** description AND the EIP itself is tagged `Component = "network"` (HIGH-4). The localstack composition then expects the EIP under the compute group; it'll show up in network instead.
- Severity: MEDIUM — same root cause as HIGH-4; documenting it as a downstream symptom.

### MED-6 — Comment drift: `var.bedrock_model_id` in monitoring vs the wiring
- File: `infra/modules/monitoring/variables.tf:80`
- Comment says "*The model ID the app actually invokes — typically the cross-region inference profile (e.g. eu.anthropic.claude-haiku-4-5-...), NOT the foundation-model ID.*"
- Caller-side: `envs/prod/main.tf:248` passes `local.effective_model_id`. When `use_inference_profile_for_app = false`, `effective_model_id` IS the foundation-model ID. So the comment is wrong for the `false` path. Doesn't break anything (the alarm just dimensions on whatever the app sends), but the description is misleading.
- Fix: clarify "*matches whatever string the SDK passes as modelId — profile ID when var.use_inference_profile_for_app=true, foundation-model ID when false*".

### MED-7 — `data_volume_device_name` default `/dev/sdh` vs bootstrap script `DATA_DEV=/dev/nvme1n1`
- Files: `infra/modules/compute/variables.tf:78` (`default = "/dev/sdh"`); `infra/scripts/bootstrap-ec2.sh:85` (`DATA_DEV=/dev/nvme1n1`).
- AWS translates `/dev/sdh` → `/dev/nvme1n1` on Nitro instances, so the two values are aliases of the same device. The bootstrap script hardcodes the nvme name, so it ignores the templatefile-injected `data_device_hint` value entirely (that var is plumbed into `user_data.sh.tpl` as `${data_device_hint}` but unused beyond writing the literal value into `/etc/flowin/bootstrap.env`).
- Severity: MEDIUM — works today, fragile if the operator picks a non-nvme instance class. Worth either deleting `data_device_hint` or threading it through to the bootstrap script's `DATA_DEV` variable.

### MED-8 — Unused module variable `data_volume_device_name` doesn't change behaviour when set
- Same root as MED-7. Listed separately because it's a Terraform-side smell (configurable knob that has no effect).

### MED-9 — `var.detailed_monitoring` and `var.ebs_optimized` only ever flipped in localstack
- Files: `infra/modules/compute/variables.tf:99,105`; only overridden in `infra/envs/localstack/main.tf:140-141`.
- The variables have `default = true` (matches prod). Localstack flips both to false. Prod env doesn't set them. Fine, but the pattern of "module defaults match prod, localstack overrides" is consistent — no real concern, just worth noting that the localstack-specific overrides aren't gated behind a single `is_localstack` flag, so a future env composition won't easily know which defaults to revisit.

### MED-10 — `transition_to_glacier_ir_days` / `noncurrent_version_expiration_days` / `backup_schedule_cron` / `backup_selection_tag_*` never overridden
- File: `infra/modules/backups/variables.tf:71-69` (the four variables).
- Neither prod nor localstack passes these; they all run on module defaults. Acceptable for now; flag for the "module decomposition" review — these could move to a `locals.tf` or be removed if the project never intends to vary them.

### MED-11 — README out-of-date instance-type claim
- File: `infra/README.md:56` says "Compute: one `m6i.2xlarge` Ubuntu 24.04 LTS instance, an encrypted 100 GB gp3 root volume…".
- The TF and tfvars examples agree: `instance_type = "m6i.2xlarge"`. The audit prompt mentioned "t3.medium for pptx-builder" — that string does not appear anywhere in the TF tree. README and code agree on m6i.2xlarge. Listed here only to confirm — no drift.

### MED-12 — `aws_resourcegroups_group` resources tagged `Component = "monitoring"`
- File: `infra/modules/resourcegroups/main.tf:23,55`
- Both the `all` and the per-component groups carry `Component = "monitoring"`. The Resource Groups themselves are technically observability tooling, so `monitoring` is defensible — but the per-component groups self-reference (the `network` group has `Component = "monitoring"`, meaning the group filtering on `Component=network` itself appears in the monitoring group, not the network group). Naming is consistent with intent. Listed for transparency.

---

## LOW (style, formatting, redundancy)

### LOW-1 — Inconsistent indent on `infra/envs/localstack/providers.tf` `endpoints { ... }`
- Same root as the fmt drift; the long-key block (`elasticbeanstalk`, `kinesisanalytics`, `cognitoidentity`) breaks alignment of every adjacent line.

### LOW-2 — `infra/modules/ecr/main.tf:60-65` tags duplicate provider `default_tags`
- The module hand-sets `Project = "flowin"` and `Environment = var.environment`, but the provider's `default_tags` block already supplies both. Harmless but verbose.

### LOW-3 — `Sid` values in `infra/modules/kms/main.tf:140` use string-replacement to derive uniqueness
- File: `infra/modules/kms/main.tf:140`
- Sid construction: `"AllowAdditionalPrincipal${replace(replace(replace(principal, ":", ""), "/", ""), "-", "")}"` — three nested `replace()` calls.
- Today `var.additional_principals` is `[]` so this is unused, but the style is awkward. Future principal ARNs with `.` chars will pass through (SIDs accept `[a-zA-Z0-9-]`), which may surface a different bug.
- Fix: switch to `sha1(principal)` or `substr(md5(principal), 0, 16)` for a deterministic SID suffix.

### LOW-4 — `infra/envs/prod/outputs.tf` outputs for `vpc_endpoint_ids` are a map of service→ID; no `sensitive` flag (correct), no `precondition` (correct).
- Not a problem. Spot-checked all outputs for `sensitive = true` mis-placement — none mark a secret value, and none mark a non-secret value as sensitive. Verified clean.

### LOW-5 — Bedrock-tokens-daily alarm period is exactly the max for `evaluation_periods = 1`
- File: `infra/modules/monitoring/main.tf:695` — `period = 86400`, `evaluation_periods = 1`.
- CloudWatch's product of period × evaluation_periods must be ≤ 86400 for period ≥ 60s — the alarm is at the boundary but legal. (CW's broader cap is 7 days when period ≥ 3600.) Listed only because the comment explanation in `cert_renew_heartbeat` covers the boundary case explicitly while this one doesn't.

### LOW-6 — `infra/scripts/bootstrap-ec2.sh` capitalises `${ENVIRONMENT}` via `${ENVIRONMENT^}`
- File: `bootstrap-ec2.sh:82` — `ENV_TITLE="${ENVIRONMENT^}"`.
- The `^` only capitalises the first character. If `ENVIRONMENT=prod` it yields `Prod` — matches `Flowin/Prod` in the monitoring module's `cw_metric_namespace = "Flowin/${title(var.environment)}"`.
- If `ENVIRONMENT=staging` it yields `Staging`, also matches.
- If `ENVIRONMENT=eu-prod` (hyphenated) it yields `Eu-prod`, while TF would output `Eu-Prod` (Go's `strings.Title` capitalises after every word break including `-`). Subtle mismatch in an unlikely edge case.
- Fix sketch: switch the shell to `python3 -c "import sys; print(sys.argv[1].title())" "$ENVIRONMENT"` for true parity with Go's title-casing, or constrain `var.environment` to a regex that rules out hyphens (already does — `^[a-z][a-z0-9]{1,15}$`). The validation regex disallows hyphens, so today there's no mismatch. Listed for forward safety.

### LOW-7 — `infra/envs/localstack/terraform.tfvars` includes `app_secret_key` and `db_password` as placeholders
- The localstack values are literal strings (`localstack-placeholder-secret-key-32chars-minimum-padding` and `localstack-placeholder-pw-16chars`). The variables are validated for length only. Tagged with `sensitive = true` so they don't appear in `plan` output. Acceptable for a test fixture committed to git, per the .gitignore exception (`!envs/localstack/terraform.tfvars`).
- LOW because: README mentions the tfvars is hermetic, no real secrets, no risk. Just confirm.

---

## Verified clean

The following areas were checked and found correct as-shipped:

1. **`terraform validate`** — clean in all three roots (prod, localstack, bootstrap).
2. **`required_version`** — `>= 1.7.0` in modules, `>= 1.9.0` in env roots; consistent with the cross-variable-validation rationale in `envs/prod/versions.tf:2-8`.
3. **`provider "aws" default_tags`** — consistent shape across prod, localstack, bootstrap. Tags: Project, Environment, ManagedBy, Repo, Owner, CostCenter (+ Component on bootstrap which differs deliberately).
4. **Backend config** — `envs/prod/backend.tf` correctly commits the non-secret keys (key, region, encrypt, dynamodb_table) and leaves bucket as operator-supplied. Bootstrap creates the S3 bucket with versioning + encryption + bucket-scoped public-access block + TLS-only policy + KMS encryption + DynamoDB lock table with PITR. All checked.
5. **`.gitignore`** — covers `*.tfstate`, `*.tfstate.*`, `*.tfstate.backup`, `.terraform/`, `*.tfvars` (with `!envs/localstack/terraform.tfvars` exception). `git check-ignore` confirmed every `terraform.tfstate*` file in localstack is gitignored. **Local tfstate files are NOT tracked in git.**
6. **`prevent_destroy` placement** — checked every occurrence:
   - bootstrap: KMS, state bucket, lock table (correct).
   - kms module: CMK (correct).
   - compute module: data EBS, EIP (correct, with the documented EIP-literal-bool caveat).
   - network module: vpc-flow-logs CW log group (correct).
   - iam module: instance role + profile (correct).
   - backups module: bucket, vault, plan, selection (correct).
   - monitoring module: log groups via for_each (correct).
   - ECR: explicitly `prevent_destroy = false` with rationale (correct).
   - **No prevent_destroy in inappropriate places.**
7. **`create_before_destroy`** — present on `aws_security_group.app` and `aws_security_group.endpoints`. Both SGs reference each other (referenced_security_group_id). Without create_before_destroy, an in-place modification would force a destroy-then-create cycle that breaks the back-reference. Correct.
8. **`ignore_changes`** — every use audited:
   - secrets module (6 instances): `value` on SSM SecureStrings — correct, supports out-of-band rotation.
   - compute module: `ami`, `user_data`, `associate_public_ip_address` — all three with documented upstream-provider-issue rationales; correct.
   - **No `ignore_changes` masks legitimate drift.**
9. **Alarm period × evaluation_periods** — every alarm checked against CloudWatch's 86_400s (eval=1) and 604_800s (eval≥1, period≥3600) caps. All compliant. `cert_renew_heartbeat` is at the inclusive 7-day boundary (86_400 × 7 = 604_800) — comment in code already calls this out.
10. **Account-region guard** — `modules/account_guard` correctly forces precondition + check on both account ID and region. Outputs `depends_on = [terraform_data.guard]` so downstream consumers can't bypass it. Wired into every env composition. Correct.
11. **Route 53 — no prod dependency** — `module.dns` in `envs/prod/main.tf` passes `use_nip_io = var.use_nip_io` (defaulting `false` in `variables.tf:139`, but `true` in `terraform.tfvars.example:73`). Prod with the example tfvars uses nip.io magic DNS — no Route 53 resources created. Correct.
12. **EIP + association ordering** — `aws_eip.this` created first, `aws_eip_association.this` references both EIP and instance. Terraform infers the dependency. Correct.
13. **`metadata_options`** — IMDSv2-required (`http_tokens = "required"`), `http_put_response_hop_limit = 2` with the documented Docker-container rationale. Correct.
14. **Variable validation rules** — sampled across modules. Strong: `expected_account_id` (12 digits), `aws_region` (regex), `availability_zone` (region prefix + cross-var validation), `route53_zone_name` (rejects URLs and trailing dots), `bedrock_model_id` (vendor-prefix gate), `cors_origins` (jsondecode + per-element URL prefix), `log_retention_days` (CloudWatch allowed set), `ssh_allowed_cidrs` (rejects 0.0.0.0/0 + cidrnetmask), `cold_storage_after_days ≤ daily - 90` (cross-var), `description_separator` (regex). Comprehensive.

---

## Specific items from the audit prompt

1. **Comment drift on `iam/main.tf:53` (3 vs 7 regions)** — confirmed; HIGH-2.
2. **EIP `prevent_destroy = true` hardcoded, no var** — intentional per the rationale in `compute/main.tf:181-189` and `compute/variables.tf:117-121`. Terraform 1.x rejects var refs in `lifecycle.prevent_destroy`. Verified.
3. **Bedrock region pinning on inference-profile ARN** — see HIGH-6. The `aws:RequestedRegion` correctly allows 7 EU regions; the inference-profile ARN is region-pinned to deploy region (intentional because that's where the profile object lives), but this conflates compute-fan-out with object-ownership and is fragile if redeployed outside the home region.
4. **alarm period × evaluation_periods cap** — all 17 alarms compliant.
5. **`var.user_data_replace_on_change = false` + `lifecycle.ignore_changes = [user_data]`** — both set on `aws_instance.app`. The combination means: never replace the instance when user-data changes, never even detect the change. Intentional — the user-data only writes `/etc/flowin/bootstrap.env`; the heavy bootstrap runs via SSM RunCommand after first boot. The script is idempotent so re-running is safe.
6. **`terraform.tfstate.backup` files in localstack** — 17 numbered backup files (`terraform.tfstate.1778438217.backup` etc.) + `.backup`. All gitignored. None tracked. Local-disk noise only.
7. **Bootstrap-ec2.sh idempotency** — script is mostly idempotent (recovery-mode detection via `$DATA_MOUNT/16/main/PG_VERSION`, conditional installs guarded by `command -v` / `dpkg -s`, `useradd` guarded by `id -u`). Step §18 (`docker compose down --remove-orphans`) explicitly forces fresh containers on re-runs to avoid stale-ACL bugs. **Re-running is intended and safe** per the script header. Verified.
8. **`terraform plan` against deployed state would be a no-op** — not runnable from this host without AWS creds. Caveats from the audit: with the fmt drift (HIGH-1), the only "drift" the next plan would compute is style-only; no resource diffs expected.
9. **`docker-compose.yml` in prod** — uploaded via `aws_s3_object.compose_yaml` (`envs/prod/main.tf:136-151`) with `source_hash = filemd5(...)` for change detection. KMS-encrypted with the project CMK. Bucket policy denies any non-KMS-encrypted Put, so the upload includes `server_side_encryption = "aws:kms"` + `kms_key_id`. Correct.
10. **Localstack `iam_instance_profile_name = ""`** — documented as a LocalStack EC2 IAM-cache bug. Comment in `envs/localstack/main.tf:117-121` is accurate. Verified.

---

## Notes on scope deferral

The following are explicitly **out of scope** for this audit (covered by the parallel security agent):
- IAM permission scope (Bedrock region pinning detail, KMS Decrypt ViaService granularity, SSM read scope)
- KMS key policy (root-account principal scope, service grants)
- SNS topic policy validation
- Network ACLs / SG ingress/egress rules
- Secrets management (rotation, KMS encryption, SSM-vs-Secrets-Manager)
- Backup vault / object lock defaults from a compliance perspective

These items were observed during the read-through and look defensible at the correctness layer (no broken references, no syntax problems, all wire up via `terraform validate`). The security agent will judge whether the *scopes* are right.
