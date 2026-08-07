# =============================================================================
# VelocityAI Foundation Layer (per environment)
# =============================================================================
# Long-lived, slow-changing base for one environment: the account/region guard,
# the project KMS CMK, the VPC + endpoints, the S3 backup bucket + AWS Backup
# vault, the EC2 instance role, and the SSM Parameter Store secrets.
#
# The app layer (compute, DNS, monitoring, compose object) reads this layer's
# outputs via terraform_remote_state and never re-declares these inputs.
#
# State key: velocityai/<env>/foundation.tfstate
# Apply order: bootstrap -> shared -> foundation(<env>) -> app(<env>)
# =============================================================================

# --- Account / region guard -------------------------------------------------
# Runs first; refuses plan/apply against the wrong account or region.
module "account_guard" {
  source = "../modules/account_guard"

  expected_account_id = var.expected_account_id
  expected_region     = var.aws_region
}

# --- KMS --------------------------------------------------------------------
module "kms" {
  source = "../modules/kms"

  name_prefix = local.name_prefix
  account_id  = module.account_guard.account_id
  region      = module.account_guard.region
}

# --- Backups (storage bucket + Backup vault) -------------------------------
# Before network because the network module scopes the S3 gateway VPC endpoint
# to this bucket's ARN.
module "backups" {
  source = "../modules/backups"

  name_prefix = local.name_prefix
  environment = var.environment
  kms_key_arn = module.kms.key_arn
  # Derived deterministically (no committed name / account ID): the live
  # account ID from the guard makes it globally unique per account+env.
  bucket_name                 = "${local.name_prefix}-pg-dumps-${module.account_guard.account_id}"
  daily_backup_retention_days = var.daily_backup_retention_days
  cold_storage_after_days     = var.cold_storage_after_days
  pg_dump_expiry_days         = var.pg_dump_expiry_days

  # Vault Lock — opt-in, ONE-WAY. Default false. Enable only after retention
  # drills (see modules/backups/variables.tf for the full irreversibility note).
  enable_vault_lock             = var.enable_vault_lock
  vault_lock_min_retention_days = var.vault_lock_min_retention_days
  vault_lock_max_retention_days = var.vault_lock_max_retention_days

  # S3 Object Lock — opt-in, CREATION-TIME-ONLY. Default false.
  enable_object_lock         = var.enable_object_lock
  object_lock_retention_days = var.object_lock_retention_days
}

# --- Network ----------------------------------------------------------------
module "network" {
  source = "../modules/network"

  name_prefix        = local.name_prefix
  vpc_cidr           = var.vpc_cidr
  public_subnet_cidr = var.public_subnet_cidr
  availability_zone  = var.availability_zone
  ssh_allowed_cidrs  = var.ssh_allowed_cidrs
  region             = module.account_guard.region

  # VPC flow logs (project-owned, KMS-encrypted CW log group) + endpoint
  # policies (aws:PrincipalAccount pin; S3 gateway scoped to the backup bucket).
  environment        = var.environment
  account_id         = module.account_guard.account_id
  kms_key_arn        = module.kms.key_arn
  log_retention_days = var.log_retention_days
  backup_bucket_arn  = module.backups.backup_bucket_arn
}

# --- IAM (instance role + policies) ----------------------------------------
# The instance role's ecr-pull policy is scoped to the SHARED ECR repos
# (velocityai/backend, velocityai/frontend) — reconstructed from ARNs inside
# the module to stay free of a cross-layer dependency on the shared layer.
module "iam" {
  source = "../modules/iam"

  name_prefix                  = local.name_prefix
  environment                  = var.environment
  account_id                   = module.account_guard.account_id
  region                       = module.account_guard.region
  kms_key_arn                  = module.kms.key_arn
  backup_bucket_arn            = module.backups.backup_bucket_arn
  bedrock_model_id             = var.bedrock_model_id
  bedrock_inference_profile_id = var.bedrock_inference_profile_id
  attach_ssm_managed_policy    = true

  # Cognito — pool-scoped admin permissions. The policy's `count` keys off the
  # boolean, not the ARN (which is unknown until apply).
  cognito_enabled       = var.cognito_enabled
  cognito_user_pool_arn = var.cognito_enabled ? module.cognito[0].user_pool_arn : ""
}

# --- Cognito (COGNITO-MIGRATION-PLAN Phase 1) -------------------------------
# One User Pool + backend app client + tier/role groups per environment.
# Gated on var.cognito_enabled (default false) so existing environments are
# unaffected until an operator explicitly opts in per-environment — creating
# a pool is a one-way step this module deliberately does not do by accident.
module "cognito" {
  count  = var.cognito_enabled ? 1 : 0
  source = "../modules/cognito"

  name_prefix = local.name_prefix
  environment = var.environment

  deletion_protection = var.environment == "prod" ? "ACTIVE" : "INACTIVE"
  mfa_configuration   = var.cognito_mfa_configuration

  # Email OTP second factor. Requires SES (below) — the module validates that
  # rather than silently producing a pool without the factor. Turning this on
  # switches account recovery to admin_only and therefore SURRENDERS
  # self-service password reset; see the module's variable documentation.
  email_mfa_enabled = var.cognito_email_mfa_enabled

  ses_source_arn             = var.cognito_ses_source_arn
  ses_from_email_address     = var.cognito_ses_from_email_address
  ses_reply_to_email_address = var.cognito_ses_reply_to_email_address

  auth_session_validity_minutes = var.cognito_auth_session_validity_minutes

  access_token_validity_minutes = var.cognito_access_token_validity_minutes
  id_token_validity_minutes     = var.cognito_access_token_validity_minutes
  refresh_token_validity_days   = var.cognito_refresh_token_validity_days
}

# --- Secrets (SSM Parameter Store) -----------------------------------------
module "secrets" {
  source = "../modules/secrets"

  name_prefix                  = local.name_prefix
  environment                  = var.environment
  region                       = module.account_guard.region
  kms_key_id                   = module.kms.key_id
  bedrock_model_id             = local.effective_model_id
  bedrock_inference_profile_id = var.bedrock_inference_profile_id
  app_secret_key               = var.app_secret_key
  db_password                  = var.db_password
  cors_origins                 = var.cors_origins
  access_token_expire_hours    = var.access_token_expire_hours

  # LangSmith — empty defaults; opt-in via tfvars / TF_VAR_*.
  langsmith_tracing = var.langsmith_tracing
  langsmith_api_key = var.langsmith_api_key
  langsmith_project = var.langsmith_project

  # Cognito — the module's `count` keys off this boolean (NOT off the string
  # values below), because those come from module.cognito outputs that are
  # unknown until apply and cannot legally drive a count.
  cognito_enabled       = var.cognito_enabled
  cognito_user_pool_id  = var.cognito_enabled ? module.cognito[0].user_pool_id : ""
  cognito_client_id     = var.cognito_enabled ? module.cognito[0].client_id : ""
  cognito_client_secret = var.cognito_enabled ? module.cognito[0].client_secret : ""
  cognito_region        = var.cognito_enabled ? module.account_guard.region : ""

  # Auth cutover flags (Phase 5). Only published once Cognito exists for this
  # environment — publishing AUTH_PROVIDER=cognito without a pool would trip
  # the application's own boot guard.
  auth_provider         = var.cognito_enabled ? var.auth_provider : ""
  auth_allow_legacy_jwt = var.cognito_enabled ? tostring(var.auth_allow_legacy_jwt) : ""
  break_glass_enabled   = var.cognito_enabled ? tostring(var.break_glass_enabled) : ""

  # Sourced from the module's DERIVED output, not from var.cognito_email_mfa_enabled:
  # if the flag is set but SES isn't configured, the pool ends up without email
  # MFA and the backend must be told `false` so it doesn't disable self-service
  # password reset for a factor that was never actually configured.
  auth_email_mfa_enabled = var.cognito_enabled ? tostring(module.cognito[0].email_mfa_active) : ""
}
