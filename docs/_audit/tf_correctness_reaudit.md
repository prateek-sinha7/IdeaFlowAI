# Phase C TF Correctness Re-Audit

Scope: verify the C1+C2 fixes applied to the `infra-agent-integration` branch and hunt for any regressions or NEW correctness issues introduced by those fixes. Security findings remain out of scope (security agent owns them).

Tools used: `terraform 1.15.1`, `terraform fmt -recursive`, `terraform validate` (with `-backend=false`), `bash -n`. `tflint` and `shellcheck` not installed locally.

---

## Summary

| Severity | Count |
|---|---|
| CRITICAL (breaks apply / state damage) | 0 |
| HIGH (regression or contract gap introduced by the fixes) | 3 |
| MEDIUM | 3 |
| LOW | 2 |
| Fixes verified CLEAN | 9 of 10 |

Headline:
- C1-1 through C1-4, C1-6, C1-7, C1-8, C2-2 verified clean.
- **C1-5 (`llm_inference_profile_id` SSM parameter)** is INCOMPLETE — `envs/localstack/main.tf:92` does not wire `bedrock_inference_profile_id` to `module.secrets`, so the new resource will not be created in localstack and the "dead branch" problem is reproduced there.
- **C2-1 (CloudTrail audit trail)** introduces TWO new HIGH issues:
  1. `infra/envs/localstack/destroy.sh` does not state-rm the new `aws_cloudwatch_log_group.audit_trail` (which has `prevent_destroy = true`) — `bash destroy.sh` will fail in localstack until amended.
  2. Comment in `infra/modules/kms/main.tf:162-164` claims a `kms:EncryptionContext` defense-in-depth control that does NOT exist in the rendered policy.
- One MEDIUM regression: a comment block in the CloudTrail bucket section (`infra/modules/monitoring/main.tf:1100-1102`) promises an `aws_s3_bucket_lifecycle_configuration` resource that is not present, so the CloudTrail S3 deliveries will accumulate without Glacier transition or expiry.

---

## terraform fmt + validate + bash -n results

```
$ terraform fmt -check -recursive infra/
EXIT=0
```

```
$ cd infra/envs/prod && terraform init -backend=false && terraform validate
Initializing provider plugins found in the configuration...
- terraform.io/builtin/terraform is built in to Terraform
- Reusing previous version of hashicorp/random from the dependency lock file
- Reusing previous version of hashicorp/aws from the dependency lock file
- Using previously-installed hashicorp/aws v5.100.0
- Using previously-installed hashicorp/random v3.8.1
... Warning: Deprecated Parameter
The parameter "dynamodb_table" is deprecated. Use parameter "use_lockfile" instead.
Terraform has been successfully initialized!
Success! The configuration is valid.
```

```
$ cd infra/envs/localstack && terraform init -backend=false && terraform validate
Initializing modules...
... Using previously-installed hashicorp/aws v5.100.0
... Using previously-installed hashicorp/random v3.8.1
Terraform has been successfully initialized!
Success! The configuration is valid.
```

```
$ cd infra/bootstrap && terraform init -backend=false && terraform validate
... Reusing previous version of hashicorp/aws / hashicorp/null
... Using previously-installed hashicorp/aws v5.100.0
... Using previously-installed hashicorp/null v3.2.4
Terraform has been successfully initialized!
Success! The configuration is valid.
```

```
$ bash -n infra/scripts/bootstrap-ec2.sh
EXIT=0

$ bash -n infra/envs/localstack/destroy.sh
EXIT=0
```

All three validate clean and fmt drift is zero. Bootstrap's `null` provider is still declared (per scope: not in the C1-6 fix list).

---

## Fix verification (C1 + C2)

| Fix | Verdict | Evidence |
|---|---|---|
| C1-1 fmt | **VERIFIED CLEAN** | `terraform fmt -check -recursive infra/` exit=0; all 5 previously-drifted files corrected. |
| C1-2 IAM comment | **VERIFIED CLEAN** | `infra/modules/iam/main.tf:52-54` lists 7 regions (`eu-central-1, eu-north-1, eu-south-1, eu-south-2, eu-west-1, eu-west-2, eu-west-3`) matching `bedrock-invoke.json:21-27`. |
| C1-3 EIP Component | **VERIFIED CLEAN** | `infra/modules/compute/main.tf:173` reads `Component = "compute"`. README line 183 and `resourcegroups/variables.tf:16` both confirm "compute" is correct. |
| C1-4 compose_yaml Component | **VERIFIED CLEAN** | `infra/envs/prod/main.tf:156` reads `Component = "compute"`. Comment lines 150-155 explain why ("EC2 runtime config"). |
| C1-5 `llm_inference_profile_id` SSM parameter | **INCOMPLETE — see HIGH-NEW-1 below** | Resource created in `infra/modules/secrets/main.tf:102-120`; variable in `infra/modules/secrets/variables.tf:26-30`. Prod wires it at `infra/envs/prod/main.tf:111`. **Localstack does NOT wire it** — `infra/envs/localstack/main.tf:92-111` omits the input, so the module-level default `""` (variables.tf:29) leaves the count=0 and the resource is not created in localstack. The dead bootstrap branch we just fixed is reproduced. |
| C1-6 `null` provider removal | **VERIFIED CLEAN (per scope)** | Removed from `infra/envs/prod/versions.tf` and `infra/envs/localstack/versions.tf`. Both lock files (`infra/envs/prod/.terraform.lock.hcl`, `infra/envs/localstack/.terraform.lock.hcl`) no longer contain `hashicorp/null`. `grep -rn "null_\|null =" infra/` returns only the bootstrap `versions.tf:9` declaration (deliberately out of scope per the FIXES APPLIED list — but flagged as LOW-NEW-1 below for completeness). |
| C1-7 bedrock policy region wildcard | **VERIFIED CLEAN** | `infra/policies/bedrock-invoke.json:16` reads `arn:${partition}:bedrock:*:${account_id}:inference-profile/${inference_profile_id}` (region is now `*`). Foundation-model ARNs (lines 14-15) still keep `${region}` + `*` variants — defensible (gives both the deploy-region exact match and the cross-region wildcard). |
| C1-8 KMS `AllowSns` SourceAccount | **VERIFIED CLEAN** | `infra/modules/kms/main.tf:88-92` carries `Condition = { StringEquals = { "aws:SourceAccount" = var.account_id } }` symmetric with the S3 and Backup branches. |
| C2-1 CloudTrail data-event audit trail | **VERIFIED with HIGH and MEDIUM regressions — see below** | 10 new resources land cleanly in monitoring module; envs/prod and envs/localstack both wire the 3 new ARN inputs (instance_role_arn, secrets_path_prefix_arn, project_cmk_arn). KMS module gains `allow_cloudtrail_service` (default true) and the matching policy statement. **Two issues introduced:** comment-vs-policy drift in KMS (HIGH-NEW-2), and a referenced lifecycle resource that doesn't exist (MED-NEW-1). Plus the destroy.sh gap (HIGH-NEW-3). |
| C2-2 bootstrap IMDS probe + doc block | **VERIFIED CLEAN** | `infra/scripts/bootstrap-ec2.sh:351-498` adds the §8b doc block + IMDSv1 probe. `if curl -sf --max-time 2 ...` is safe under `set -euo pipefail` (the `if` neutralises `-e`). Backslash-escaped backticks in the echo are correct. No array/quoting/$1 hazards. `bash -n` clean. |

---

## New issues found

### HIGH-NEW-1 — `bedrock_inference_profile_id` NOT wired into `module.secrets` in localstack (C1-5 incomplete)

- **File**: `infra/envs/localstack/main.tf:92-111`
- **Diagnosis**: The localstack `module "secrets"` call omits the `bedrock_inference_profile_id` input. The secrets module's `variables.tf:26-30` defaults the variable to `""`, and the new resource at `infra/modules/secrets/main.tf:102-120` is gated by `count = length(var.bedrock_inference_profile_id) > 0 ? 1 : 0`. Result: the `/flowin/ls/llm/inference_profile_id` SSM parameter is **not created in localstack**, so when the bootstrap script's `flowin-load-secrets` (`infra/scripts/bootstrap-ec2.sh:637`) iterates the SSM path it never emits `BEDROCK_INFERENCE_PROFILE_ID` — reproducing exactly the dead-branch problem HIGH-7 was meant to close.
- **Compounding evidence**: `infra/envs/localstack/terraform.tfvars:47` correctly sets `bedrock_inference_profile_id = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"` (non-empty); the value just isn't threaded into the secrets module. Compare with prod (`infra/envs/prod/main.tf:111`) which wires it correctly, and with the localstack IAM call (`infra/envs/localstack/main.tf:74`) which DOES wire the same variable. Cross-env divergence.
- **Severity**: HIGH — the user's mandate was to close the dead-branch problem; the fix is intact in prod but incomplete in localstack.
- **Fix**: add `bedrock_inference_profile_id = var.bedrock_inference_profile_id` to `infra/envs/localstack/main.tf:92-111` (between `bedrock_model_id` line 99 and `app_secret_key` line 100, mirroring prod's column alignment).

### HIGH-NEW-2 — KMS `AllowCloudTrailService` comment claims a `kms:EncryptionContext` defense that isn't in the policy

- **File**: `infra/modules/kms/main.tf:162-164` (the comment) vs `infra/modules/kms/main.tf:178-185` (the actual policy statement).
- **Diagnosis**: The comment reads "`kms:EncryptionContext (aws:cloudtrail:arn) — defence in depth: even an in-account attacker that owned cloudtrail-create rights can't trick the key into encrypting for an unrelated trail`." But the rendered policy at lines 178-185 only contains `aws:SourceAccount` and `aws:SourceArn` (with a wildcard at the end: `arn:...:cloudtrail:...:trail/*`). There is no `kms:EncryptionContext` condition. So the comment describes a control that does not exist. Symmetric with the original HIGH-2 finding (comment-vs-code drift), but on a security-sensitive policy this time.
- **Effect**: any in-account principal with CloudTrail-create rights CAN currently use this key for an unrelated trail — the wildcard SourceArn permits it. The "defense in depth" the comment promises is hollow.
- **Severity**: HIGH — the comment lies. A future operator reading the policy looking for the defense will believe it's there and skip adding it.
- **Fix options (any one of):**
  - Add the actual `kms:EncryptionContext:aws:cloudtrail:arn` condition matching the project's trail ARN under `Condition.StringEquals` — same shape as `kms:EncryptionContext:aws:logs:arn` used in `AllowCloudWatchLogs` (line 66).
  - Or: remove the claim from the comment (lines 162-164) and leave the SourceAccount+SourceArn pair as the documented controls.

### HIGH-NEW-3 — `infra/envs/localstack/destroy.sh` does not state-rm the new `aws_cloudwatch_log_group.audit_trail`

- **File**: `infra/envs/localstack/destroy.sh:49-55` handles `module.monitoring.aws_cloudwatch_log_group.groups[*]` (the `for_each` map) but NOT `module.monitoring.aws_cloudwatch_log_group.audit_trail` (the single resource added by C2-1 with `prevent_destroy = true` at `infra/modules/monitoring/main.tf:1003-1008`).
- **Effect**: `bash destroy.sh` in localstack hits the prevent_destroy lifecycle and fails with "Error: Instance cannot be destroyed". Localstack teardown is broken until the script is amended.
- **Severity**: HIGH — operator-facing localstack workflow is broken by this branch. Cross-env regression introduced by C2-1.
- **Fix**: append `"module.monitoring.aws_cloudwatch_log_group.audit_trail"` to the `protected` array at `destroy.sh:22-35`. Alternatively, broaden the `grep -E` at line 49 to match the audit_trail too:
  ```
  log_group_addrs=$(grep -E '^module\.monitoring\.aws_cloudwatch_log_group\.(groups\[|audit_trail$)' <<<"$state_snapshot" || true)
  ```

---

## Medium issues found

### MED-NEW-1 — Promised `aws_s3_bucket_lifecycle_configuration` on the CloudTrail bucket does not exist

- **File**: `infra/modules/monitoring/main.tf:1100-1102` (the comment) — text says "The `aws_s3_bucket_lifecycle_configuration` below transitions old objects to Glacier and expires them after `audit_trail_log_retention_days` *4 so the S3 record outlives the CW Logs metric-filter window."
- **Diagnosis**: `grep -n aws_s3_bucket_lifecycle_configuration infra/modules/monitoring/main.tf` returns ONLY the comment line. No actual resource exists. CloudTrail JSON.gz deliveries will accumulate in `aws_s3_bucket.audit_trail` indefinitely.
- **Effect**: storage cost grows linearly with time. The 90-day default for `audit_trail_log_retention_days` is enforced on the CW Logs side (good), but the S3-side parallel control is missing. Comment overpromises.
- **Severity**: MEDIUM — cost/storage growth over time; not breaking. Comment is wrong about a security-relevant control surface.
- **Fix options**: either (a) add the `aws_s3_bucket_lifecycle_configuration` the comment promises (transition to GLACIER_IR at e.g. 30d, expire at 90d*4=360d), or (b) edit the comment to match reality.

### MED-NEW-2 — `audit_trail` S3 bucket lacks `force_destroy` and localstack destroy.sh has no `aws s3 rm` step

- **Files**: `infra/modules/monitoring/main.tf:1103-1110` (no `force_destroy`); `infra/envs/localstack/destroy.sh` (no s3-empty step).
- **Diagnosis**: Once CloudTrail writes a single delivery into `aws_s3_bucket.audit_trail`, `terraform destroy` will fail with `BucketNotEmpty`. The bucket is deliberately `prevent_destroy = false` per the inline rationale, but without `force_destroy = true` the destroy still fails on a non-empty bucket. The localstack `destroy.sh` doesn't run `aws s3 rm s3://${bucket} --recursive` before `terraform destroy`, so the very first localstack run after C2-1 lands will leave a populated bucket behind.
- **Severity**: MEDIUM — bites only the second destroy attempt; first apply works fine.
- **Fix options**: (a) set `force_destroy = true` on the bucket (acceptable since it's a forensic-grade bucket the operator opts into recycling); or (b) add `aws s3 rm s3://${bucket_name} --recursive` to destroy.sh ahead of `terraform destroy`.

### MED-NEW-3 — `aws_cloudtrail.audit` and `aws_s3_bucket.audit_trail` lack `prevent_destroy` while the log group has it

- **Files**: `infra/modules/monitoring/main.tf:1244` (trail) and `:1103` (bucket).
- **Diagnosis**: The audit_trail CW log group has `prevent_destroy = true`. The trail and bucket do not. An operator who runs `terraform destroy` (or `terraform apply` after deleting the trail from main.tf) loses the trail entirely — the forensic log group survives but new events stop arriving, silently breaking the alarm path. Asymmetric protection.
- **Severity**: MEDIUM — defensive-only. The trail can be recreated, but the forensic value during the gap is lost.
- **Fix**: add `lifecycle { prevent_destroy = true }` to both `aws_cloudtrail.audit` and `aws_s3_bucket.audit_trail`. If you do, also extend the localstack destroy.sh `protected` list accordingly.

---

## Low issues found

### LOW-NEW-1 — Bootstrap's `null` provider still declared but unused

- **File**: `infra/bootstrap/versions.tf:9-12`.
- **Diagnosis**: HIGH-3 from the original audit named three files; the FIXES APPLIED list explicitly scoped C1-6 to `envs/prod/versions.tf` and `envs/localstack/versions.tf`. The bootstrap copy was deliberately deferred. For completeness: `grep -rn "null_" infra/ --include="*.tf"` returns zero usages anywhere. The bootstrap declaration + the `hashicorp/null = 3.2.4` entry in `infra/bootstrap/.terraform.lock.hcl` are pure dead weight.
- **Severity**: LOW — consistent with the original HIGH-3 finding for prod/localstack; scope was deliberate per the audit prompt.
- **Fix (if/when desired)**: delete the `null = { ... }` block from `infra/bootstrap/versions.tf:9-12` and run `terraform init -upgrade` in `infra/bootstrap/` to drop it from the lock file.

### LOW-NEW-2 — New monitoring outputs not surfaced by env compositions

- **Files**: `infra/modules/monitoring/outputs.tf:60-78` exposes `audit_trail_name`, `audit_trail_arn`, `audit_trail_log_group_name`, `audit_trail_bucket_name`. Neither `infra/envs/prod/outputs.tf` nor `infra/envs/localstack/outputs.tf` re-exports them.
- **Diagnosis**: existing pattern (e.g. `output "alerts_topic_arn"` in prod/outputs.tf line 71) re-exports monitoring-module outputs at the env layer for operator/runbook consumption. The four new audit-trail outputs are missing from this pattern.
- **Severity**: LOW — purely a discoverability gap; operators can still hit the trail by name in the AWS console.
- **Fix**: add `output "audit_trail_name" { value = module.monitoring.audit_trail_name }` (and three siblings) to `envs/prod/outputs.tf`. Optional for localstack since the env is throwaway.

---

## Status

**NOT CLEAN.** 3 HIGH regressions introduced by C1-5 incompletion and C2-1; 3 MEDIUM gaps and 2 LOW notes from the same changes.

The branch must not merge until at least the three HIGH items are resolved:
1. HIGH-NEW-1 — wire `bedrock_inference_profile_id` into the localstack secrets module.
2. HIGH-NEW-2 — make the KMS comment match the policy (or add the missing condition).
3. HIGH-NEW-3 — extend the localstack destroy.sh to state-rm the audit_trail log group.

The three MEDIUM items (missing S3 lifecycle resource, missing force_destroy, asymmetric prevent_destroy on the trail/bucket vs log group) are recommended for this PR but defensible to defer. The two LOW items are bookkeeping.

After those three fixes land, re-run this audit. If they're clean, the C1+C2 work is complete.
