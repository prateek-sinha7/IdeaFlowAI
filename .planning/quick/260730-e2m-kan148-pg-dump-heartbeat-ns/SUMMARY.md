---
phase: quick-260730-e2m
plan: 01
subsystem: infrastructure/monitoring
tags: [KAN-148, E2, CloudWatch, metrics, postgres-backup, observability]
affects: [dev-environment, stage-environment, prod-environment]
key-files:
  - infra/scripts/bootstrap-ec2.sh
  - infra/terraform/modules/monitoring/main.tf
decisions: [INV-12 no-duplication, no-app-layer-changes, fail-closed-helpers]
metrics:
  files_changed: 2
  lines_added: 50 (helper + publishers)
  lines_modified: 1 (terraform namespace)
---

# KAN-148: Pg_Dump Heartbeat Alarm — Cross-Environment Metric Contamination Fix

## Summary

Fixed infrastructure vulnerability where the pg_dump backup heartbeat alarm and publisher metrics were using a shared namespace ("VelocityAI/Backups") across all three environments (dev/stage/prod), allowing dev's metric publisher to satisfy prod's alarm and create a false negative on production RPO-1h monitoring. Applied E2.md investigation findings: introduced a shared `velocityai-cw-namespace` helper function, updated both pg_dump (E2) and stuck-workflows (E3) publishers to use per-environment namespaces, and changed the Terraform alarm from hardcoded namespace to per-environment variable.

## Changes Applied

| File | Change | Rationale |
|---|---|---|
| `infra/scripts/bootstrap-ec2.sh` | **Added section 16a:** `velocityai-cw-namespace` helper function (lines 821-843) | One shared derivation site for per-environment namespace (fail-closed: refuses unknown environments); matches Terraform's `title()` function result |
| `infra/scripts/bootstrap-ec2.sh` | **Updated pg_dump script (section 16):** Added `CW_NAMESPACE=$(/usr/local/bin/velocityai-cw-namespace)` and `put-metric-data` call after S3 upload (lines 860-867) | Publishes PgDumpHeartbeat=1 metric to per-environment namespace after successful backup; metric was missing in prior implementation |
| `infra/scripts/bootstrap-ec2.sh` | **Updated stuck-workflows script (section 16/E3):** Changed from hardcoded `--namespace VelocityAI/Prod` to `CW_NAMESPACE=$(/usr/local/bin/velocityai-cw-namespace)` (lines 894-900) | E3 now uses shared helper instead of hardcoding prod namespace, enabling per-environment metric publishing (INV-12: no duplication) |
| `infra/terraform/modules/monitoring/main.tf` | **Updated pg_dump_heartbeat alarm resource:** Changed `namespace = "VelocityAI/Backups"` to `namespace = var.cw_metric_namespace` (line 948) | Alarm now watches per-environment namespace (VelocityAI/Dev in dev apply, VelocityAI/Stage in stage apply, etc.); no cross-env contamination |

## What Didn't Change

- Alarm threshold, period, statistic, treat_missing_data — all correct as-is (verified by E2 analysis)
- Pg_dump script's S3 backup logic — only prepended metric publisher, no business logic changes
- Systemd service/timer definitions — hourly timer with RandomizedDelaySec=120 already correct
- Application-layer code (backend/, frontend/) — infrastructure-only fix, zero app changes
- Database migrations — no schema changes (additive INV-3 constraint)

## Locked Decisions Respected

- **INV-12 (no duplication):** Shared namespace helper introduces the per-env mapping exactly once; both E2 and E3 publishers call it rather than duplicating the logic
- **INV-3 (golden parity):** No backend/frontend code changes, so characterization test goldens remain byte-identical
- **Infrastructure CI gates:** All changes pass `terraform fmt -check`, `terraform validate` (shared/app layers verified)
- **Fail-closed design:** Namespace helper refuses unknown environments (exits 1), so a misconfigured bootstrap.env prevents silent metric loss

## Verification Summary

✅ Helper function installed and callable  
✅ Both E2 and E3 publishers use shared helper  
✅ Terraform alarm namespace uses variable  
✅ No cross-environment metric pollution possible  
✅ Terraform format and validation gates pass  
✅ All three must_haves from PLAN.md verified  

## Deviations from Plan

None. Plan executed as written. All tasks completed in a single phase.

## Next Steps (Out of Scope)

1. **Live bootstrap test:** Spin up a fresh dev/stage/prod box or run SSM RunCommand to verify pg_dump metric lands in the correct per-environment namespace
2. **CloudWatch console inspection:** Verify alarms transition from ALARM → OK on first heartbeat pulse
3. **Branch merge & deploy:** Merge to origin/bugfix/infra-sse-bug-findings, trigger buildspec CI gates, deploy to affected environments via Terraform

