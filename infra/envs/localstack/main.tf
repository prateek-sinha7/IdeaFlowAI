# LocalStack composition. Mirrors envs/prod/main.tf with one change: the
# compute module receives an `ami_id` override so it skips the Canonical AMI
# lookup (which doesn't resolve in LocalStack).

# --- Account / region guard -------------------------------------------------
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

# --- Backups ----------------------------------------------------------------
module "backups" {
  source = "../../modules/backups"

  name_prefix                 = local.name_prefix
  environment                 = var.environment
  kms_key_arn                 = module.kms.key_arn
  bucket_name                 = var.backup_bucket_name
  daily_backup_retention_days = var.daily_backup_retention_days
}

# --- IAM --------------------------------------------------------------------
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

# --- Secrets ----------------------------------------------------------------
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
}

# --- Compute ----------------------------------------------------------------
# LocalStack limitation: the EC2 service has its own moto IAM backend cache
# and cannot see instance profiles created via the IAM service, so RunInstances
# returns NoSuchEntity even after the profile is fully visible to `aws iam`.
# We still create the profile via the IAM module (it's exercised by `aws iam`
# call paths) but don't attach it to the EC2 here. Prod is unchanged.
#
# We still keep the `iam_instance_profile_name` reference so module.iam is in
# the dependency graph and runs to completion before module.compute.
module "compute" {
  source = "../../modules/compute"

  name_prefix               = local.name_prefix
  environment               = var.environment
  region                    = module.account_guard.region
  instance_type             = var.instance_type
  subnet_id                 = module.network.public_subnet_id
  availability_zone         = var.availability_zone
  security_group_id         = module.network.app_security_group_id
  iam_instance_profile_name = ""
  kms_key_arn               = module.kms.key_arn
  ssh_key_name              = var.ssh_key_name
  root_volume_size_gb       = var.root_volume_size_gb
  data_volume_size_gb       = var.data_volume_size_gb
  ami_id                    = var.ami_id

  # LocalStack hasn't implemented MonitorInstances or ebs-optimized launches.
  detailed_monitoring = false
  ebs_optimized       = false

  user_data_extra_env = {
    FLOWIN_BACKUP_BUCKET = module.backups.backup_bucket_name
    FLOWIN_PARAM_PREFIX  = module.secrets.parameter_path_prefix
    # See envs/prod: pg_dump and skills-backup scripts read this for `aws s3 cp
    # --sse aws:kms --sse-kms-key-id $FLOWIN_KMS_KEY_ID`.
    FLOWIN_KMS_KEY_ID = module.kms.key_arn
    # Forces module.iam to be in the graph so the IAM resources are still
    # created and exercised in this environment.
    _IAM_PROFILE_HOOK = module.iam.instance_profile_name
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
  # See envs/prod: the alarm must dimension on whatever string the app passes
  # to Bedrock as modelId. local.effective_model_id matches that.
  bedrock_model_id    = local.effective_model_id
  cw_metric_namespace = "Flowin/${title(var.environment)}"
}

# --- Resource Groups --------------------------------------------------------
# LocalStack's resource-groups validator rejects any character outside
# [\sa-zA-Z0-9_\.-] (no commas, no em-dash) where real AWS allows them. We
# substitute an ASCII hyphen for the em-dash and strip commas from the
# per-component descriptions in this env only. Prod is unchanged.
module "resourcegroups" {
  source = "../../modules/resourcegroups"

  name_prefix           = local.name_prefix
  environment           = var.environment
  description_separator = "-"

  components = {
    network    = "VPC subnets route-tables security-groups VPC-endpoints"
    compute    = "EC2 root-EBS-volume EIP"
    storage    = "Data-EBS-volume S3-backup-bucket AWS-Backup-vault"
    monitoring = "CloudWatch log-groups alarms SNS"
    iam        = "IAM-role KMS-key instance-profile"
    secrets    = "SSM-Parameter-Store-entries"
  }
}
