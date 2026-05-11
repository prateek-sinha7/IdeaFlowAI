# Phase C TF Security Re-Audit

Branch: `infra-agent-integration`.
Scope: verification of the Group C1 + C2 fixes applied in this round, plus a fresh sweep for NEW issues introduced by those fixes. Group C3 architectural debt items remain deferred per the triage decision and are NOT re-flagged here.

---

## Fix verification (C1 + C2 items)

### C1-1 — `terraform fmt -recursive infra/` — VERIFIED CLEAN
`terraform fmt -check -recursive infra/` exits 0 with no diff. Every `.tf` file in the tree (modules, envs, bootstrap, policies) is canonically formatted.

### C1-2 — IAM comment drift — VERIFIED CLEAN
`infra/modules/iam/main.tf:50-55` now says "7 regions" and enumerates `eu-central-1, eu-north-1, eu-south-1, eu-south-2, eu-west-1, eu-west-2, eu-west-3` — exact match with `infra/policies/bedrock-invoke.json:20-28`. Comment-vs-JSON sync is restored.

### C1-3 — EIP `Component` tag — VERIFIED CLEAN
`infra/modules/compute/main.tf:168-174` now tags the EIP with `Component = "compute"`. The resourcegroups module's `compute` group (per `infra/modules/resourcegroups/variables.tf:16` — "EC2 instance root EBS volume EIP") includes EIPs, so the EIP now lands in the right per-component view.

### C1-4 — `aws_s3_object.compose_yaml` Component tag — VERIFIED CLEAN
`infra/envs/prod/main.tf:148-157` carries `Component = "compute"` with the explanatory comment lines 150-155 documenting why config was renamed to compute. The 7-component resourcegroups schema is satisfied; the object now appears in the `flowin-prod-compute` resource group instead of being orphaned.

### C1-5 — `aws_ssm_parameter.llm_inference_profile_id` — VERIFIED CLEAN (with one consistency gap)
- Resource present at `infra/modules/secrets/main.tf:102-120` with `count = length(var.bedrock_inference_profile_id) > 0 ? 1 : 0`, correct KMS encryption (`key_id = var.kms_key_id`), correct `lifecycle.ignore_changes` was NOT applied — but neither do the sibling plain-string params (`llm_region`, `llm_model_id`, `cors_origins`, `access_token_expire_hours`). The SecureString params (`app_secret_key`, `db_password`, `langsmith_*`) do have `ignore_changes`. The new param is a plain `String` (inference profile ID is non-secret config), so omitting `ignore_changes` is consistent with the other plain-string params. **Verified clean.**
- Variable declared at `infra/modules/secrets/variables.tf:26-30` with `default = ""`.
- Wired through `infra/envs/prod/main.tf:111` (`bedrock_inference_profile_id = var.bedrock_inference_profile_id`).
- Tags `Component = "secrets"` consistent with other params in the module.
- Bootstrap script case label at `infra/scripts/bootstrap-ec2.sh:637` reads `llm/inference_profile_id) emit BEDROCK_INFERENCE_PROFILE_ID "$value" ;;` — exact match with the SSM key path `${prefix}/llm/inference_profile_id` (the bash strips `${PREFIX}/` first). **Phase C-corr HIGH-7 closed.**
- See LOW-1 below for the localstack-side wiring consistency gap (minor; not security-impacting).

### C1-6 — Unused `null` provider removed — VERIFIED CLEAN
- `infra/envs/prod/versions.tf:11-16` no longer declares `null`. Only `aws` (~> 5.70).
- `infra/envs/localstack/versions.tf:6-11` ditto.
- `.terraform.lock.hcl` in both envs no longer references `null` (verified by grep).
- No `null_resource` exists anywhere in `infra/modules/` or `infra/envs/` (grep clean).
- Note: `infra/bootstrap/versions.tf:9-12` still declares the `null` provider unused — this was out of scope for C1-6 (which targeted `envs/`) and is acceptable per the triage decision, but is worth a future cleanup pass.

### C1-7 — Bedrock inference-profile ARN region wildcard — VERIFIED CLEAN
`infra/policies/bedrock-invoke.json:16` now reads `"arn:${partition}:bedrock:*:${account_id}:inference-profile/${inference_profile_id}"`. The wildcard at the region segment is correct for cross-region inference profiles which span multiple regions by design. Scope remains tightly bounded by: (a) `${account_id}` pinning to our account, (b) the specific `${inference_profile_id}` pinning to our profile, and (c) the existing `aws:RequestedRegion` condition pinning to the 7 EU regions in the same JSON file. Net change: appropriately wider for cross-region calls; not a privilege escalation. **Verified clean.**

### C1-8 — KMS `AllowSns` `aws:SourceAccount` condition — VERIFIED CLEAN
`infra/modules/kms/main.tf:71-93` now has:
```
Condition = {
  StringEquals = {
    "aws:SourceAccount" = var.account_id
  }
}
```
Symmetric with `AllowS3WithinAccount` (lines 95-113) and `AllowAwsBackup` (lines 114-147). Confused-deputy defense-in-depth gap closed. **Verified clean.**

### C2-1 — CloudTrail data-event audit trail — VERIFIED CLEAN (with new issues found — see below)
Single contiguous block in `infra/modules/monitoring/main.tf:928-1444`. All ~10 resources present:
- `aws_cloudwatch_log_group.audit_trail` (line 993) — KMS-encrypted, 90d default retention, `prevent_destroy = true`.
- `aws_iam_role.audit_trail_to_logs` + trust + inline policy + `aws_iam_role_policies_exclusive` (lines 1015-1083).
- `aws_s3_bucket.audit_trail` + ownership controls + public-access block + SSE-KMS + bucket policy (lines 1103-1226).
- `aws_cloudtrail.audit` (line 1244) with `enable_log_file_validation = true`, KMS-encrypted, single-region, advanced event selectors for SSM and KMS.
- Two metric filters + two alarms (lines 1354-1444).

Module input wiring verified in both `envs/prod/main.tf:281-289` and `envs/localstack/main.tf:216-224` (both pass `instance_role_arn`, `secrets_path_prefix_arn`, `project_cmk_arn`). The new KMS policy statement `AllowCloudTrailService` is present in `infra/modules/kms/main.tf:165-187` with confused-deputy guards (`aws:SourceAccount` + `aws:SourceArn` pinning to `trail/*` in our account+region). LocalStack `providers.tf:40` registers the `cloudtrail` endpoint.

CloudTrail metric filter pattern correctness:
- Field path `$.userIdentity.sessionContext.sessionIssuer.arn` is the correct path for assumed-role calls in CloudTrail (verified vs AWS docs).
- The `!=` operator matches when the field is missing (e.g. IAM-user direct calls, root account calls), so coverage is broader than just other assumed-role principals.
- `eventName = "GetParameter*"` covers `GetParameter`, `GetParameters`, and `GetParametersByPath` via CW Logs wildcard.
- `eventSource = "ssm.amazonaws.com"` is the correct CloudTrail event source for Parameter Store APIs.
- Pattern is 222 chars, well under the 1024-char CW Logs filter limit.
- Trail's advanced event selectors use `eventCategory = "Data"` + `resources.type = "AWS::SSM::ManagedParameter"` / `AWS::KMS::Key` — both are valid types per AWS CloudTrail advanced-event-selector schema.
- `resources.ARN starts_with = ["${var.secrets_path_prefix_arn}/"]` — the trailing `/` is correctly present (prevents matching a hypothetical sibling like `/flowin/prod-other-tenant/...`).

**Verified clean.** See MEDIUM-1, MEDIUM-2, MEDIUM-3, HIGH-1 below for new issues found IN this block.

### C2-2 — IMDS netfilter documentation + IMDSv1 drift detection — VERIFIED CLEAN
`infra/scripts/bootstrap-ec2.sh:351-498` contains the ~150-line documentation block explaining:
- Why each of 5 candidate iptables/unshare approaches was rejected with concrete reasoning.
- What layered controls DO exist today (env scrubbing, rlimits, concurrency cap, VPC egress SG, CloudTrail alarm from C2-1).
- The real fix (sidecar `pptx-renderer` with `network_mode: none`) is documented as a TODO and deliberately deferred.

The IMDSv1 drift probe at lines 481-490 uses `curl -sf --max-time 2 http://169.254.169.254/latest/meta-data/`:
- No shell injection vector (URL hardcoded, no user input).
- Wrapped in `if`/`else`, so a non-zero exit doesn't trigger `set -e` abort.
- The CRITICAL log line is shipped to `/flowin/${env}/system` via cwagent for operator visibility.
- Does NOT block bootstrap completion (deliberate — boot must complete; the CloudTrail alarm from C2-1 is the safety net).
- Minor caveat: if `curl` binary were missing, the else-branch would falsely report "OK". curl is in the bootstrap install set so this is theoretical.

**Verified clean.**

---

## New issues found

### HIGH-1 — `aws_cloudwatch_log_group.audit_trail` has `prevent_destroy = true` but is NOT in `destroy.sh` protected list
- **Files:**
  - `infra/modules/monitoring/main.tf:993-1009` (resource with `prevent_destroy = true` at line 1007)
  - `infra/envs/localstack/destroy.sh:22-43` (protected list — missing this resource)
  - `infra/envs/localstack/destroy.sh:45-55` (for_each log-group state-rm loop — only matches `module.monitoring.aws_cloudwatch_log_group.groups[*]`, NOT `.audit_trail`)
- **Impact:** Running `bash destroy.sh` in LocalStack will fail at `terraform destroy` with an error like "Instance cannot be destroyed: Resource module.monitoring.aws_cloudwatch_log_group.audit_trail has lifecycle.prevent_destroy set." The destroy ritual breaks; operators have to manually `terraform state rm module.monitoring.aws_cloudwatch_log_group.audit_trail` before each tear-down.
- **Fix:** Add `"module.monitoring.aws_cloudwatch_log_group.audit_trail"` to the `protected` array at `destroy.sh:22-35`. Alternative: change the for_each regex at line 49 from `^module\.monitoring\.aws_cloudwatch_log_group\.groups\[` to `^module\.monitoring\.aws_cloudwatch_log_group\.(groups\[|audit_trail$)` so both singleton + for_each variants are caught.

### HIGH-2 — CloudTrail audit-trail S3 bucket has NO versioning — tamper-evidence is weakened
- **Files:**
  - `infra/modules/monitoring/main.tf:1103-1142` (audit_trail bucket + ownership + public-access + SSE-KMS — but no `aws_s3_bucket_versioning`)
  - Compare to `infra/modules/backups/main.tf:35-41` (backups bucket DOES enable versioning)
- **Impact:** CloudTrail's `enable_log_file_validation = true` creates digest files for tamper detection, but an attacker with `s3:DeleteObject` permission (the bucket policy doesn't restrict deletes — only PutObject is constrained via `aws:SourceArn`) can delete BOTH the log files AND the digest files in the same window, leaving no trace. With versioning enabled, deletes become delete-markers and the underlying versions survive — recoverable forensics. This is the canonical tamper-resistance posture for audit log buckets per the AWS Security Reference Architecture.
- **Fix:** Add `aws_s3_bucket_versioning.audit_trail { versioning_configuration { status = "Enabled" } }` modeled on `modules/backups/main.tf:35-41`. Optionally add MFA-Delete on top, though that has operational friction in CI contexts.

### MEDIUM-1 — Audit-trail S3 bucket lifecycle configuration promised in comment but NOT created
- **Files:**
  - `infra/modules/monitoring/main.tf:1094-1102` (comment promises "The `aws_s3_bucket_lifecycle_configuration` below transitions old objects to Glacier and expires them after `audit_trail_log_retention_days` *4...")
  - No `aws_s3_bucket_lifecycle_configuration` resource anywhere in the file (grep confirmed: only the COMMENT references this resource).
- **Impact:** CloudTrail JSON.gz objects accumulate in S3 forever with no Glacier transition and no expiration. At ~6 MB/month (per the cost estimate in the C2-1 module header) that's ~$0.001/mo storage growth — operationally trivial but is documentation drift and the comment makes a load-bearing claim about retention that the operator may rely on for compliance evidence. Also: the CW Logs retention is 90d but the S3 record is unbounded; without lifecycle config, the S3 record + CW Logs window diverge in ways that make forensic windows hard to reason about.
- **Fix:** Add an `aws_s3_bucket_lifecycle_configuration.audit_trail` resource matching the comment's promise (e.g. transition to GLACIER at 90d, expire at `var.audit_trail_log_retention_days * 4` = 360d default). Pattern available at `modules/backups/main.tf:65-119`.

### MEDIUM-2 — KMS `AllowCloudTrailService` comment + variable description promise an `kms:EncryptionContext` condition but the actual policy doesn't include it
- **Files:**
  - `infra/modules/kms/main.tf:162-164` (comment lists `kms:EncryptionContext (aws:cloudtrail:arn) — defence in depth`)
  - `infra/modules/kms/variables.tf:58` (variable description: "...a kms:EncryptionContext of the calling AWS account")
  - `infra/modules/kms/main.tf:178-185` (actual `Condition` block has only `aws:SourceAccount` + `aws:SourceArn`, no `kms:EncryptionContext`)
- **Impact:** Comment-vs-code drift in a security-relevant statement. The promised defense-in-depth control (`kms:EncryptionContext:aws:cloudtrail:arn` matching the trail ARN) would prevent an in-account attacker who had `cloudtrail:CreateTrail` from creating a rogue trail and tricking this CMK into encrypting for it. As-is, the `aws:SourceArn = .../trail/*` constraint provides similar coverage (the SourceArn is server-asserted by CloudTrail), so the practical security gap is small. But the comment + variable description set an operator expectation that the code doesn't deliver. Symmetric with the C1-2 fix shape — same class of drift, just in a fresh-laid statement.
- **Fix:** Either (a) ADD the condition:
  ```
  StringEquals = {
    "aws:SourceAccount"                = var.account_id
    "kms:EncryptionContext:aws:cloudtrail:arn" = "arn:${local.partition}:cloudtrail:${var.region}:${var.account_id}:trail/${var.name_prefix}-audit"
  }
  ```
  but note this hard-codes the trail name and closes the dependency loop the comment at lines 158-161 was explicitly trying to avoid. OR (b) REMOVE the comment lines 162-164 and trim the variable description at variables.tf:58 to match the actual policy. Recommend (a) only if the dependency loop concern can be resolved by passing the trail name as a kms-module input; (b) is the conservative path.

### MEDIUM-3 — Audit-trail S3 bucket policy lacks `DenyUnencryptedPuts` / `DenyWrongKmsKey` / `DenyInsecureTransport-for-Get` symmetric to backups bucket
- **Files:**
  - `infra/modules/monitoring/main.tf:1152-1221` (audit_trail bucket policy — three statements: ACLCheck, Write, DenyInsecureTransport)
  - Compare to `infra/modules/backups/main.tf:115-152` (backups bucket has `DenyUnencryptedPuts` + `DenyWrongKmsKey` additionally)
- **Impact:** The audit-trail bucket policy currently only allows CloudTrail-service writes (everything else is implicitly denied by the default S3 evaluation). So in practice no other principal CAN write — but if a future change introduces another writer (e.g. accidentally adding a backup-bucket-style "Allow s3:PutObject for instance role" statement), there's no second-layer guarantee that the write happens with our KMS key. The defense-in-depth posture differs from the backups bucket without a stated reason.
- **Fix:** Add `DenyUnencryptedPuts` (s3:PutObject without `s3:x-amz-server-side-encryption = aws:kms`) and `DenyWrongKmsKey` (s3:PutObject with a different `s3:x-amz-server-side-encryption-aws-kms-key-id`) statements modeled on `modules/backups/main.tf:128-152`. Or document explicitly in the bucket-policy comment why this bucket deliberately omits them (e.g. "only the cloudtrail.amazonaws.com principal can write, and CT always sets aws:kms encryption via the trail's kms_key_id"). Either path makes the operator's reading match the intent.

### LOW-1 — `bedrock_inference_profile_id` not wired into `module.secrets` in localstack env
- **Files:**
  - `infra/envs/localstack/main.tf:92-111` (`module "secrets"` block — does NOT pass `bedrock_inference_profile_id`)
  - `infra/envs/localstack/terraform.tfvars:47` (`bedrock_inference_profile_id = "eu.anthropic.claude-haiku-4-5-..."` IS set)
  - `infra/envs/prod/main.tf:111` (prod DOES wire it: `bedrock_inference_profile_id = var.bedrock_inference_profile_id`)
- **Impact:** In localstack, `var.bedrock_inference_profile_id` is set in tfvars but unused by `module.secrets` — the secrets module sees the default empty string and the new `aws_ssm_parameter.llm_inference_profile_id` resource isn't created (count guard returns 0). LocalStack-side smoke tests therefore don't exercise the new C1-5 resource end-to-end. The `iam` module IS wired (line 74), so the bedrock-invoke IAM policy DOES include the profile ID — just not the SSM param creation. This is a coverage gap (not a security gap): a bug in the new SSM param resource would only surface at prod apply, not in localstack smoke.
- **Fix:** Add `bedrock_inference_profile_id = var.bedrock_inference_profile_id` to the `module "secrets"` block in `infra/envs/localstack/main.tf` between lines 99-103. Trivial one-line edit. The localstack apply will then exercise the new resource.

### LOW-2 — Comment vs code drift in CloudTrail trust policy (and bucket policy): comment promises "Wildcard at the trail-name end" but code pins to exact trail name
- **Files:**
  - `infra/modules/monitoring/main.tf:1026-1028` (trust-policy comment: "Wildcard at the trail-name end is intentional: the role is defined before the trail and pinning by name would create a cycle")
  - `infra/modules/monitoring/main.tf:1038` (actual `values` has the FULL trail name `trail/${var.name_prefix}-audit`, no wildcard)
  - Same pattern in the bucket-policy at `infra/modules/monitoring/main.tf:1169` and `:1197` (also pins by full name, no wildcard)
- **Impact:** The actual code is MORE restrictive than the comment promises (pinned to exact trail vs wildcard) — so the security posture is TIGHTER than documented, opposite of MEDIUM-2. There's no resource-graph cycle because both sides derive from `var.name_prefix` independently (string-level coupling, not resource-attribute coupling). The comment is simply misleading about why the pin is by-name.
- **Fix:** Update the comment to explain the actual rationale: "Pin to the exact trail name (derived independently from `var.name_prefix`, no resource-graph cycle). Same pattern as the bucket-policy SourceArn pins." OR if a wildcard was actually intended, change `trail/${var.name_prefix}-audit` to `trail/*` or `trail/${var.name_prefix}-*`.

### LOW-3 — `var.protect_eip` still unused (C1-9 from triage was not part of this round's fix list)
- **Files:**
  - `infra/modules/compute/variables.tf` (declares `protect_eip`)
  - `infra/modules/compute/main.tf:186-188` (comment says "kept for documentation and forward-compatibility")
  - `infra/envs/localstack/main.tf:149` (sets `protect_eip = false`)
  - `infra/envs/localstack/destroy.sh:60` ("The `var.protect_eip` input on the compute module is currently advisory.")
- **Impact:** The variable is plumbed through but unused. The triage allowed this as long as the comment documents the intent — the comment at main.tf:186-188 does this. Acceptable today but the operator-visibility cost stays until either Terraform loosens the prevent_destroy variable-reference restriction (then this can be wired up) OR the variable is deleted.
- **Fix:** Not required this round. Backlog for the next sweep: either delete or wire when possible.

---

## Group C3 deferred items (NOT re-flagged)

Per the user mandate, these are NOT considered findings in this re-audit. They remain known architectural debt with their own future PR scope:

- **C3-1** — `SECRET_KEY` plaintext via SSM Session Manager (TF-sec CRITICAL-1). Reaches the on-disk `/etc/flowin/app.env` (0640 root:flowin). Mitigation requires either boot-time boto3 fetch (no on-disk plaintext) or RS256/KMS-sign for JWTs. The C2-1 CloudTrail alarm provides detection coverage in the interim.
- **C3-2** — `SECRET_KEY` plaintext in Terraform state (TF-sec CRITICAL-3). The `random_password` + `aws_ssm_parameter.value` serialize to the prod tfstate. Mitigation requires TF 1.11+ `ephemeral` blocks or moving secret lifecycle out of TF entirely.
- **C3-3** — JWT HS256 → RS256 + claim validation (Phase B Group 2). Separate security PR.
- bcrypt 72-byte truncation, login rate limiting, password policy — Phase B Group 2, separate PR.

---

## Verification commands run

### `terraform fmt -check -recursive infra/`
```
$ terraform fmt -check -recursive infra/
$ echo "Exit: $?"
Exit: 0
```
Clean — no files require reformatting.

### `terraform validate` per env

**`infra/envs/prod`:**
```
$ terraform init -backend=false -input=false
[...] Terraform has been successfully initialized!
$ terraform validate
Success! The configuration is valid.
```

**`infra/envs/localstack`:**
```
$ terraform init -backend=false -input=false
[...] Terraform has been successfully initialized!
$ terraform validate
Success! The configuration is valid.
```

**`infra/bootstrap`:**
```
$ terraform init -backend=false -input=false
[...] Terraform has been successfully initialized!
$ terraform validate
Success! The configuration is valid.
```

All three envs validate cleanly.

### Orphaned `null_resource` check
```
$ grep -rn "null_resource\|provider \"null\"" infra/modules/ infra/envs/
(no output)
```
No orphaned `null_resource` left. `infra/bootstrap/versions.tf:9-12` still declares the `null` provider but it's unused; this is outside the C1-6 scope (envs only).

### Case-statement / SSM-param contract check
`infra/scripts/bootstrap-ec2.sh:637` reads:
```
llm/inference_profile_id) emit BEDROCK_INFERENCE_PROFILE_ID "$value" ;;
```
`infra/modules/secrets/main.tf:111` writes parameter named `"${local.prefix}/llm/inference_profile_id"` where `local.prefix = "/flowin/${var.environment}"`. The bootstrap's `rel="${name#${PREFIX}/}"` strip yields `llm/inference_profile_id` — exact match. **Phase C-corr HIGH-7 dead-branch is now live.**

### Filter pattern length
```
$ echo -n 'pattern content' | wc -c
   222
```
Under the 1024-char CW Logs filter pattern limit. No truncation risk.

---

## Verdict

All eight C1 fixes + both C2 fixes are correctly applied and the Terraform tree validates cleanly. However, the C2-1 CloudTrail block introduces SEVEN new issues:
- 2 HIGH (destroy.sh breakage, audit-trail bucket missing versioning)
- 3 MEDIUM (lifecycle config missing, KMS encryption-context drift, bucket policy DenyUnencryptedPuts/DenyWrongKmsKey gap)
- 3 LOW (localstack wiring asymmetry, trust-policy comment drift, pre-existing `protect_eip` plumbing)

The user mandate ("repeat until clean") is NOT yet satisfied — another fix pass is needed for at least the HIGH and MEDIUM findings.

The findings cluster tightly: HIGH-1 is the operational footgun (localstack destroy breaks), HIGH-2 + MEDIUM-1 + MEDIUM-3 are all S3-side defenses-in-depth on the new audit-trail bucket, MEDIUM-2 + LOW-2 are the same comment-drift class that C1-2 already cleaned up — just on freshly-introduced statements. Fixing the HIGH+MEDIUM tier is mechanical (~30-45 min of TF + a destroy.sh tweak); the LOW items can ride along or be deferred.
