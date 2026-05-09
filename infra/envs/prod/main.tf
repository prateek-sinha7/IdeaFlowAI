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
}

# --- Backups (storage bucket + Backup vault) -------------------------------
module "backups" {
  source = "../../modules/backups"

  name_prefix                 = local.name_prefix
  environment                 = var.environment
  kms_key_arn                 = module.kms.key_arn
  bucket_name                 = var.backup_bucket_name
  daily_backup_retention_days = var.daily_backup_retention_days
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

# --- Secrets (SSM Parameter Store) -----------------------------------------
module "secrets" {
  source = "../../modules/secrets"

  name_prefix                = local.name_prefix
  environment                = var.environment
  region                     = module.account_guard.region
  kms_key_id                 = module.kms.key_id
  bedrock_model_id           = local.effective_model_id
  app_secret_key             = var.app_secret_key
  db_password                = var.db_password
  anthropic_api_key          = var.anthropic_api_key
  cors_origins               = var.cors_origins
  access_token_expire_hours  = var.access_token_expire_hours
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

  user_data_extra_env = {
    FLOWIN_BACKUP_BUCKET = module.backups.backup_bucket_name
    FLOWIN_PARAM_PREFIX  = module.secrets.parameter_path_prefix
  }
}

# --- DNS --------------------------------------------------------------------
module "dns" {
  source = "../../modules/dns"

  name_prefix       = local.name_prefix
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
  billing_alarm_threshold_usd = var.billing_alarm_threshold_usd
  bedrock_model_id            = var.bedrock_model_id
  cw_metric_namespace         = "Flowin/${title(var.environment)}"
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
