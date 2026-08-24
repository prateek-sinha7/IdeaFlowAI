# VelocityAI foundation — prod environment (NON-SECRET config only).
#
# Consumed by CI as: terraform -chdir=infra/terraform/foundation apply \
#   -var-file=prod.tfvars -var="expected_account_id=$ACCOUNT_ID" -var="aws_region=$AWS_REGION"
#
# Secrets and per-env values are injected via TF_VAR_* from the CI runner / SSM
# — never committed here. Resource names derive from environment: prod ->
# velocityai (bare, no suffix).
#
# COGNITO STATUS (P2 finding, COGNITO-AUTH-QA-BUGS.md "Committed Prod tfvars
# Does Not Enable Cognito") — DELIBERATELY LEFT UNRESOLVED HERE, flagged for an
# operator decision rather than silently flipped:
#
#   `cognito_enabled` is NOT set below, so it resolves to its module default
#   (`false`, foundation/variables.tf). dev.tfvars explicitly sets it `true`;
#   prod does not. This means ONE of the following is true and MUST be
#   confirmed against the live account before treating this file as
#   authoritative:
#
#     (a) Production genuinely has not cut over to Cognito yet and is still on
#         local/break-glass auth for every non-bootstrap user — in which case
#         this file is accurate and cutover is still pending
#         (.planning/COGNITO-MIGRATION-PLAN.md Phase 5).
#     (b) Production HAS been cut over, but via an uncommitted CI/CD
#         TF_VAR_cognito_enabled=true override or a manual `terraform apply
#         -var=...` — in which case this committed file no longer describes
#         production's real state, and every one of `cognito_mfa_configuration`
#         / `cognito_feature_plan` / `cognito_threat_protection_mode` /
#         `auth_provider` / `auth_allow_legacy_jwt` (all default to
#         permissive/off values when omitted, see foundation/variables.tf) is
#         ALSO unaudited and unreviewed here.
#
#   Do not add `cognito_enabled = true` to this file without first running
#   `python3 scripts/verify_cognito_cutover.py --check-pool` against the prod
#   account and confirming which of (a)/(b) is the actual state — this
#   deployment is not something to change through documentation alone.

environment = "prod"

# Network — non-overlapping CIDR per environment (dev 10.40 / stage 10.30 / prod 10.20).
availability_zone  = "eu-central-1a"
vpc_cidr           = "10.20.0.0/16"
public_subnet_cidr = "10.20.1.0/24"

log_retention_days          = 30
daily_backup_retention_days = 365
cold_storage_after_days     = 30
pg_dump_expiry_days         = 365
