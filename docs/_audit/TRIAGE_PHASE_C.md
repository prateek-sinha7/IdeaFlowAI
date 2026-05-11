# Phase C TF Triage

Two audits ran in parallel:
- **TF Security** (`docs/_audit/tf_security.md`): 4 CRITICAL, 10 HIGH, 18 MEDIUM, 12 LOW
- **TF Correctness** (`docs/_audit/tf_correctness.md`): 0 CRITICAL, 9 HIGH, 12 MEDIUM, 7 LOW

After dedupe + origin analysis, findings split into 4 groups:

---

## Group C1 — Quick fixes [should land in this PR, ~30 min total]

Mechanical changes, low blast radius, no architectural decisions needed.

### C1-1 — `terraform fmt -recursive infra/` (5 files)
- `infra/envs/localstack/providers.tf`
- `infra/envs/localstack/terraform.tfvars`
- `infra/modules/backups/main.tf`
- `infra/modules/kms/main.tf`
- `infra/modules/resourcegroups/variables.tf`
- **Fix:** one shell command. Already verified by both Phase A and Phase C agents.

### C1-2 — Comment/code drift in `infra/modules/iam/main.tf:52-54`
- Comment claims 3 EU regions; `infra/policies/bedrock-invoke.json` lists 7.
- **Fix:** update the comment to match the JSON (or vice versa — JSON is authoritative).

### C1-3 — EIP `Component = "network"` should be `"compute"` (`infra/modules/compute/main.tf:173`)
- The EIP belongs in the compute resource group per the README; current tag puts it in network.
- **Fix:** one-line tag change.

### C1-4 — S3 `compose_yaml` undeclared `Component = "config"` (`infra/envs/prod/main.tf:149`)
- The resourcegroups module knows 7 components: `network/compute/storage/monitoring/iam/secrets/ecr`. `"config"` isn't one.
- **Fix:** change to one of the 7 (likely `compute` since the file feeds the app on the EC2). Or add `config` to the resourcegroups module.

### C1-5 — Dead `BEDROCK_INFERENCE_PROFILE_ID` branch in bootstrap (`infra/scripts/bootstrap-ec2.sh:488`)
- The case statement maps `llm/inference_profile_id` → `BEDROCK_INFERENCE_PROFILE_ID`, but the SSM parameter is never created in `infra/modules/secrets/main.tf`.
- **Fix:** either delete the case branch OR add the SSM param (need to know which is intended — likely the param should exist since the cross-region inference profile ID is non-secret config we want to manage).

### C1-6 — Unused `null` provider (`infra/envs/*/versions.tf`)
- Declared and locked but never used.
- **Fix:** remove from all three `versions.tf` files.

### C1-7 — Bedrock inference-profile ARN region pinning (`infra/policies/bedrock-invoke.json:16`)
- ARN uses `${region}` (deploy region), but cross-region inference profiles have a single home region.
- Works in eu-central-1 today; silently breaks if redeployed to another EU region.
- **Fix:** change region segment to `*` (the cross-region inference profile is account-scoped, not region-scoped).

### C1-8 — KMS `AllowSns` lacks `aws:SourceAccount` (`infra/modules/kms/main.tf:71-83`) [CRITICAL-4]
- Confused-deputy defense-in-depth gap. Asymmetric with the S3 and Backup branches which both pin SourceAccount.
- **Fix:** add `"aws:SourceAccount": "${data.aws_caller_identity.current.account_id}"` to the StringEquals condition (single-line edit).

### C1-9 — `var.protect_eip` plumbed but never referenced (`infra/modules/compute/variables.tf`)
- Variable accepted by the module but unused. Misleading to operators who think setting it does something.
- **Fix:** delete the variable + its callsites OR add a comment explaining it's documentation-only for future TF versions.

---

## Group C2 — Medium fixes [worth landing in this PR, ~2-4 hours]

Real new TF resources / non-trivial logic changes.

### C2-1 — CloudTrail data-event alarm on SSM SecureStrings + KMS [TF-sec HIGH#1]
- Currently no alarm fires if an unauthorized identity calls `GetParameter` on `/flowin/${env}/SECRET_KEY` or `kms:Decrypt` on the bootstrap CMK.
- This is the "find out" alarm that closes the detection gap for Group C3 issues.
- **Fix:** add `aws_cloudwatch_log_group` + `aws_cloudtrail` for data events + `aws_cloudwatch_metric_filter` + `aws_cloudwatch_metric_alarm` resources in `infra/modules/monitoring/main.tf`. Single self-contained block.

### C2-2 — IMDS netfilter for the pptx_export Node subprocess [TF-sec CRITICAL-2 partial]
- Our G1-C1 hardening scrubs env vars but the Node subprocess can still reach `169.254.169.254` and get instance-role IAM creds.
- **Fix options:**
  - Easy: iptables OUTPUT DROP rule on 169.254.169.254 inside the backend container — applied in bootstrap-ec2.sh as part of container setup. Doesn't help if attacker uses ICMP/UDP, but blocks the typical IMDS HTTP path.
  - Medium: run the Node subprocess in a network-namespace via `unshare -n` (requires CAP_SYS_ADMIN, which docker grants on default).
  - Hard: separate `pptx-renderer` sidecar container with `network_mode: none` in docker-compose.
- **Recommend:** start with the iptables drop (simplest, biggest payoff), document the residual risk.

---

## Group C3 — Architectural debt [defer to a dedicated security PR, NOT this branch]

These pre-existing issues need product decisions and would balloon the diff. Each is its own multi-day workstream.

### C3-1 — `SECRET_KEY` plaintext via SSM Session Manager [TF-sec CRITICAL-1]
- The bootstrap writes the decrypted SSM SecureString to `/etc/flowin/app.env` (0640 root:flowin). Anyone with `ssm:StartSession` can `cat` it → forge HS256 JWTs for any user.
- **Fix space (pick one):**
  - **A.** Don't persist SECRET_KEY to disk. Have FastAPI fetch it at boot via boto3 SSM GetParameter (instance role can do this without writing the secret to a file). Same for DB_URL, LANGSMITH key.
  - **B.** Remove `ssm:StartSession` from the instance profile, force operator SSH (or KMS-encrypted ssm SendCommand only). Big operator UX hit.
  - **C.** Switch to RS256 JWTs with a private key in AWS KMS (signing via kms:Sign, never exposing the private key material). Best long-term but biggest scope.
- **Cost:** 1-3 days incl. testing across all deploy paths.

### C3-2 — `SECRET_KEY` plaintext in Terraform state [TF-sec CRITICAL-3]
- `random_password` + `aws_ssm_parameter.value` serialize to the prod tfstate in S3.
- **Fix space:**
  - Migrate to TF 1.11+ `ephemeral` blocks + `value_wo` (write-only). Removes the secret from state going forward.
  - OR move secret lifecycle out of TF entirely (manual AWS Secrets Manager, rotation outside TF).
- **Cost:** TF version bump + state migration ritual; ~1 day.

### C3-3 — JWT HS256 → RS256 + claim validation [from Phase B Group 2 + reinforced by Phase C]
- Already deferred in Phase B Group 2. Phase C makes the case stronger because the symmetric secret + state exposure combine into the same threat surface.
- **Cost:** ~1-2 days.

---

## Group C4 — Low-priority / cosmetic [backlog]

Belt-and-suspenders, code style, observability nice-to-haves. Most "verified clean but could be tighter" items from the audits land here.

- Detailed-monitoring enabled vs default
- ECR image lifecycle policy (image grew to 591MB)
- CloudWatch log retention tuning
- Default tags via provider block vs per-resource (we use per-resource consistently — could switch but no functional gain)
- Output sensitivity tags
- VPC flow logs retention
- ~28 other small items across the two audits

---

## Recommendation

- **In this PR**: Group C1 (8-9 quick fixes, 30 min) + Group C2 (2 items, 4 hours). Then re-run the two Phase C agents to verify clean.
- **Separate security PR**: Group C3 (architectural debt — needs design review, separate review/test cycle).
- **Backlog file**: Group C4 (cosmetic).

This keeps PR scope tight while closing every issue **caused or compounded by this branch's work** (the pptx_export RCE attack chain runs through the IMDS surface in C2-2, so closing that completes the G1-C1 story).
