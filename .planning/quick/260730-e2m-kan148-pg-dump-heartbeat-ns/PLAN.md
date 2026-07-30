---
phase: quick-260730-e2m
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - infra/scripts/bootstrap-ec2.sh
  - infra/terraform/modules/monitoring/main.tf
autonomous: true
requirements: [KAN-148]

must_haves:
  truths:
    - "A shared velocityai-cw-namespace helper function exists in bootstrap-ec2.sh and derives per-environment namespaces (VelocityAI/Dev, VelocityAI/Stage, VelocityAI/Prod)"
    - "The pg_dump_heartbeat alarm namespace is changed from hardcoded 'VelocityAI/Backups' to var.cw_metric_namespace"
    - "The pg_dump script includes a put-metric-data call with the pg_dump_heartbeat metric into the per-environment namespace"
    - "The stuck-workflows script (E3) is updated to use the shared helper instead of hardcoded VelocityAI/Prod namespace"
    - "No cross-environment metric contamination can occur - each environment publishes to its own namespace"
  artifacts:
    - path: "infra/scripts/bootstrap-ec2.sh"
      provides: "Shared velocityai-cw-namespace helper + pg_dump & stuck-workflows publishers"
      contains: "velocityai-cw-namespace"
    - path: "infra/terraform/modules/monitoring/main.tf"
      provides: "Per-environment pg_dump_heartbeat alarm namespace"
      contains: "var.cw_metric_namespace"
  key_links:
    - from: "pg_dump_heartbeat alarm hardcoded namespace"
      to: "per-environment namespace via var.cw_metric_namespace"
      via: "Terraform variable substitution"
      pattern: "namespace.*=.*var.cw_metric_namespace"
    - from: "missing pg_dump metric publisher"
      to: "CloudWatch put-metric-data call after successful S3 upload"
      via: "Shell script injection into velocityai-pg-dump heredoc"
      pattern: "put-metric-data.*--namespace.*PgDumpHeartbeat"

---

## Objective

Fix the pg_dump heartbeat alarm cross-environment metric contamination and missing metric publisher (KAN-148 / E2.md investigation).

### Current Issues
1. **pg_dump_heartbeat alarm namespace is hardcoded to 'VelocityAI/Backups'** — shared across dev/stage/prod, allowing dev's metric publisher to satisfy prod's alarm (false negative on production RPO-1h control)
2. **pg_dump metric publisher is missing** — no put-metric-data call in velocityai-pg-dump script despite the alarm expecting it
3. **E3's stuck-workflows publisher also has cross-env namespace problem** — hardcoded to VelocityAI/Prod instead of per-environment

### Root Cause
- The alarm's namespace field uses a string literal instead of deriving from the per-environment `var.cw_metric_namespace` variable (line 948 of monitoring/main.tf)
- The pg_dump script was never wired with the metric publisher call (lines 821-836 of bootstrap-ec2.sh)
- Both E2 and E3 need a shared namespace-derivation mechanism to prevent code duplication (INV-12)

### Fixed Behavior
- Each environment (dev/stage/prod) publishes metrics to its own namespace (VelocityAI/Dev, VelocityAI/Stage, VelocityAI/Prod)
- The alarm watches the correct per-environment namespace via Terraform variable
- A shared `velocityai-cw-namespace` helper enforces fail-closed behavior (refuses unknown environments)
- Both pg_dump and stuck-workflows publishers use the same mechanism

---

## Context

@.planning/dev-sse-infra-investigations/E2.md (full investigation, line 1-1299)
@.planning/IMPLEMENTATION-REGISTER.md (INV-12: no duplication; architecture constraints)
@infra/terraform/modules/monitoring/main.tf (pg_dump_heartbeat alarm, line 942-968)
@infra/scripts/bootstrap-ec2.sh (pg_dump script, line 821-836; stuck-workflows script, line 853-869)
@infra/terraform/app/main.tf (cw_metric_namespace per-environment definition)

---

## Facts Verified During Planning

- "pg_dump_heartbeat alarm exists at infra/terraform/modules/monitoring/main.tf:942", verified by grep at line 942
- "pg_dump script exists at infra/scripts/bootstrap-ec2.sh:821-836", verified by grep; contains no put-metric-data call
- "stuck-workflows publisher exists at infra/scripts/bootstrap-ec2.sh:853-869", verified by grep; uses hardcoded VelocityAI/Prod namespace at line 865
- "E2.md analysis is current & verified", confirmed by cross-reference to current code anchors in E2.md I1 section
- "IAM permissions for CloudWatch already exist", confirmed in E2.md I4(i) — instance role grants cloudwatch:PutMetricData with no namespace condition
- "VELOCITYAI_ENVIRONMENT is available in both systemd unit EnvironmentFile paths", confirmed at lines 903 (bootstrap.env) and 967 (app.env)
- "No INV-1/3/12/13 constraints violated", infrastructure edits only, zero kernel changes

---

## Files to Change

1. **infra/scripts/bootstrap-ec2.sh**
   - Add `velocityai-cw-namespace` helper function (section 16a, before pg_dump script)
   - Inject put-metric-data call into velocityai-pg-dump script (after S3 upload, before echo)
   - Update velocityai-stuck-workflows-check script to call the helper instead of hardcoding VelocityAI/Prod

2. **infra/terraform/modules/monitoring/main.tf**
   - Change pg_dump_heartbeat alarm namespace from `"VelocityAI/Backups"` to `var.cw_metric_namespace`

---

## What is NOT Changing

- The alarm's other attributes (threshold, period, statistic, treat_missing_data) — all correct as-is (confirmed in E2.md I3)
- The pg_dump script's S3 backup logic — only adding the metric publisher after successful upload
- The pg_dump systemd service/timer (already correct, hourly with RandomizedDelaySec=120)
- Any application-layer code (backend/, frontend/) — this is infrastructure-only

---

## Deleted Code Check

None. INV-12 compliance achieved by introducing the shared helper exactly once (in bootstrap-ec2.sh, section 16a) rather than duplicating namespace logic in two places. E3's publisher will call the helper; no code is being resurrected.

---

## Locked Decisions Respected

- **IMPLEMENTATION-REGISTER.md §4 "INV-12 (no duplication)"** — the fix introduces the namespace helper once and uses it in both E2 and E3 publishers
- **E2.md I2 "INV-12 / INV-3 ... only the project invariant with real force here"** — respected by design
- **E2.md I2 "dev only. Do not plan changes to stage or prod resources"** — the Terraform change is one-line (alarm namespace), dev-scoped in effect (only affects the dev-deployed alarm when dev apply runs; stage/prod unchanged unless they separately apply)
- **Established infrastructure CI gates** — changes must pass `terraform fmt -check`, `terraform validate`, `checkov`, `trivy`, `gitleaks` (pre-tested in E2.md I4(g))

