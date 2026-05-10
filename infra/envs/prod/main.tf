# --- Account / region guard -------------------------------------------------
# Runs first; refuses plan/apply against the wrong account or region.
module "account_guard" {
  source = "../../modules/account_guard"

  expected_account_id = var.expected_account_id
  expected_region     = var.aws_region
}

# --- KMS --------------------------------------------------------------------
module "kms" {
  source = "../../modules/kms"

  name_prefix = local.name_prefix
  account_id  = module.account_guard.account_id
  region      = module.account_guard.region
}

# --- Network ----------------------------------------------------------------
module "network" {
  source = "../../modules/network"

  name_prefix        = local.name_prefix
  vpc_cidr           = var.vpc_cidr
  public_subnet_cidr = var.public_subnet_cidr
  availability_zone  = var.availability_zone
  ssh_allowed_cidrs  = var.ssh_allowed_cidrs
  region             = module.account_guard.region

  # Inputs for VPC flow logs (Phase 3 item 17) and VPC endpoint policies
  # (Phase 3 item 18). Flow logs deliver into a project-owned, KMS-encrypted
  # CloudWatch log group; endpoint policies pin aws:PrincipalAccount to this
  # account and (for the S3 gateway) scope Resource to the backup bucket.
  environment        = var.environment
  account_id         = module.account_guard.account_id
  kms_key_arn        = module.kms.key_arn
  log_retention_days = var.log_retention_days
  backup_bucket_arn  = module.backups.backup_bucket_arn
}

# --- Backups (storage bucket + Backup vault) -------------------------------
#
# Note: `aws_backup_vault_notifications` (which fans BACKUP_JOB_FAILED /
# RESTORE_JOB_FAILED into the alerts topic) intentionally lives in the
# monitoring module rather than here. Putting it in backups would close a
# cycle (compute -> monitoring -> backups -> compute via the bucket-name
# reference). Monitoring receives the vault name and creates the
# notifications binding there.
module "backups" {
  source = "../../modules/backups"

  name_prefix                 = local.name_prefix
  environment                 = var.environment
  kms_key_arn                 = module.kms.key_arn
  bucket_name                 = var.backup_bucket_name
  daily_backup_retention_days = var.daily_backup_retention_days
  cold_storage_after_days     = var.cold_storage_after_days
  pg_dump_expiry_days         = var.pg_dump_expiry_days

  # Vault Lock — opt-in, ONE-WAY. Default false. See variables.tf for the
  # full irreversibility caveat; enable only after retention drills.
  enable_vault_lock             = var.enable_vault_lock
  vault_lock_min_retention_days = var.vault_lock_min_retention_days
  vault_lock_max_retention_days = var.vault_lock_max_retention_days

  # S3 Object Lock — opt-in, CREATION-TIME-ONLY. Default false. Cannot be
  # retrofitted to an existing bucket; the prevent_destroy on the bucket
  # correctly blocks the replacement Terraform would otherwise plan.
  enable_object_lock         = var.enable_object_lock
  object_lock_retention_days = var.object_lock_retention_days
}

# --- IAM (instance role + policies) ----------------------------------------
module "iam" {
  source = "../../modules/iam"

  name_prefix                  = local.name_prefix
  environment                  = var.environment
  account_id                   = module.account_guard.account_id
  region                       = module.account_guard.region
  kms_key_arn                  = module.kms.key_arn
  backup_bucket_arn            = module.backups.backup_bucket_arn
  bedrock_model_id             = var.bedrock_model_id
  bedrock_inference_profile_id = var.bedrock_inference_profile_id
  attach_ssm_managed_policy    = true
}

# --- ECR (container image registry) ----------------------------------------
# Lives after iam because the per-repo policy's Principal is the instance
# role ARN. The reverse direction (iam policy scoping Resource to repo ARNs)
# does NOT read ecr outputs — it reconstructs ARNs from name_prefix. That
# asymmetry is what breaks the would-be iam<->ecr cycle.
module "ecr" {
  source = "../../modules/ecr"

  name_prefix       = local.name_prefix
  environment       = var.environment
  kms_key_arn       = module.kms.key_arn
  instance_role_arn = module.iam.instance_role_arn
}

# --- Secrets (SSM Parameter Store) -----------------------------------------
module "secrets" {
  source = "../../modules/secrets"

  name_prefix               = local.name_prefix
  environment               = var.environment
  region                    = module.account_guard.region
  kms_key_id                = module.kms.key_id
  bedrock_model_id          = local.effective_model_id
  app_secret_key            = var.app_secret_key
  db_password               = var.db_password
  anthropic_api_key         = var.anthropic_api_key
  cors_origins              = var.cors_origins
  access_token_expire_hours = var.access_token_expire_hours

  # LangSmith — empty defaults; opt-in via tfvars / TF_VAR_*.
  langsmith_tracing = var.langsmith_tracing
  langsmith_api_key = var.langsmith_api_key
  langsmith_project = var.langsmith_project
}

# --- Compute (EC2, EBS, EIP) -----------------------------------------------
module "compute" {
  source = "../../modules/compute"

  name_prefix               = local.name_prefix
  environment               = var.environment
  region                    = module.account_guard.region
  instance_type             = var.instance_type
  subnet_id                 = module.network.public_subnet_id
  availability_zone         = var.availability_zone
  security_group_id         = module.network.app_security_group_id
  iam_instance_profile_name = module.iam.instance_profile_name
  kms_key_arn               = module.kms.key_arn
  ssh_key_name              = var.ssh_key_name
  root_volume_size_gb       = var.root_volume_size_gb
  data_volume_size_gb       = var.data_volume_size_gb

  # Phase 3 item 19. Both default true in the module; explicit here so an
  # operator skimming this composition knows the EC2 is protected from a
  # console mis-click `terminate-instances` / `stop-instances`. To roll the
  # instance deliberately, flip these to false in tfvars + apply, or run
  # `aws ec2 modify-instance-attribute --no-disable-api-termination` first.
  disable_api_termination = true
  disable_api_stop        = true

  user_data_extra_env = {
    FLOWIN_BACKUP_BUCKET = module.backups.backup_bucket_name
    FLOWIN_PARAM_PREFIX  = module.secrets.parameter_path_prefix
    # The pg_dump and skills-backup scripts upload with `--sse aws:kms
    # --sse-kms-key-id $FLOWIN_KMS_KEY_ID`. The bucket policy denies any PUT
    # whose KMS key isn't this one (see modules/backups/main.tf
    # DenyWrongKmsKey), so this var must be present at boot.
    FLOWIN_KMS_KEY_ID = module.kms.key_arn
    # Public hostname the on-host bootstrap (Appendix D) needs for nginx
    # `server_name`, certbot HTTP-01, and the NEXT_PUBLIC_API_URL /
    # NEXT_PUBLIC_WS_URL the Next.js build bakes in. Derived from
    # module.dns.fqdn so the same value drives Route 53 (when configured)
    # OR the nip.io path when var.use_nip_io = true.
    FLOWIN_FQDN = module.dns.fqdn

    # Container deploy: ECR registry the bootstrap logs into and pulls images
    # from. Bootstrap script's `aws ecr get-login-password | docker login
    # $FLOWIN_ECR_REGISTRY` and `/etc/flowin/app.env` BACKEND_IMAGE/
    # FRONTEND_IMAGE both reference this. Derived from module.ecr's repo URL
    # by stripping the trailing /<repo>; see modules/ecr/outputs.tf.
    FLOWIN_ECR_REGISTRY = module.ecr.registry_url

    # Branch/tag the bootstrap fetches docker-compose.yml from. Defaults to
    # main; pin in tfvars to release a specific commit. (The compose file is
    # the only artifact still pulled from git at boot — Dockerfiles and the
    # app code live inside the ECR images.)
    FLOWIN_GIT_REF = var.git_ref
  }
}

# --- DNS --------------------------------------------------------------------
module "dns" {
  source = "../../modules/dns"

  name_prefix       = local.name_prefix
  use_nip_io        = var.use_nip_io
  route53_zone_name = var.route53_zone_name
  app_subdomain     = var.app_subdomain
  eip_address       = module.compute.public_ip
  ttl_seconds       = var.dns_ttl_seconds
}

# --- Monitoring -------------------------------------------------------------
module "monitoring" {
  source = "../../modules/monitoring"

  providers = {
    aws         = aws
    aws.useast1 = aws.useast1
  }

  name_prefix                 = local.name_prefix
  environment                 = var.environment
  instance_id                 = module.compute.instance_id
  kms_key_arn                 = module.kms.key_arn
  alert_email                 = var.alert_email
  log_retention_days          = var.log_retention_days
  log_retention_overrides     = var.log_retention_overrides
  billing_alarm_threshold_usd = var.billing_alarm_threshold_usd
  # CloudWatch Bedrock metrics dimension by the model ID the SDK actually invokes.
  # When the app uses an EU-wide inference profile, that's the profile ID — NOT
  # the foundation-model ID. local.effective_model_id resolves to whichever the
  # app is configured to call (see locals.tf).
  bedrock_model_id    = local.effective_model_id
  cw_metric_namespace = "Flowin/${title(var.environment)}"
  # Wires aws_backup_vault_notifications onto the alerts topic so AWS
  # Backup fires on BACKUP_JOB_FAILED / RESTORE_JOB_FAILED. The resource
  # lives in monitoring (not backups) to avoid a module-output cycle —
  # see backups module main.tf for the full rationale.
  backup_vault_name             = module.backups.backup_vault_name
  bedrock_daily_token_threshold = var.bedrock_daily_token_threshold

  # Phase 3 tunables (audit D P2-2 agent error, P2-3 stuck workflows,
  # P3-12 Bedrock throttle thresholds).
  bedrock_throttles_threshold          = var.bedrock_throttles_threshold
  bedrock_throttles_evaluation_periods = var.bedrock_throttles_evaluation_periods
  agent_error_rate_threshold           = var.agent_error_rate_threshold
  stuck_workflows_threshold            = var.stuck_workflows_threshold
  stuck_workflows_check_period         = var.stuck_workflows_check_period
}

# --- Resource Groups (last; they tag-query everything else) ----------------
module "resourcegroups" {
  source = "../../modules/resourcegroups"

  name_prefix = local.name_prefix
  environment = var.environment

  # Implicit dependency on every other module so the groups appear once
  # there are resources to populate them. Terraform infers this from the
  # output references in module.*; we don't need explicit depends_on here
  # because the per-component groups query by tag at AWS-side runtime.
}
