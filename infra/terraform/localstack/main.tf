# =============================================================================
# VelocityAI — LocalStack module test fixture (NON-CICD, all-in-one root)
# =============================================================================
# A hermetic harness that applies the WHOLE module set (foundation + app
# modules) against a local LocalStack Pro container, with local state. It is
# NOT part of the bootstrap -> shared -> foundation -> app deploy path; it
# exists so module changes can be smoke-tested end-to-end without an AWS
# account. Quirk overrides (stub AMI, no detailed monitoring / EBS-optimized,
# no instance profile attach, ephemeral EIP) are confined to this directory.
# =============================================================================

module "account_guard" {
  source = "../modules/account_guard"

  expected_account_id = var.expected_account_id
  expected_region     = var.aws_region
}

module "kms" {
  source = "../modules/kms"

  name_prefix = local.name_prefix
  account_id  = module.account_guard.account_id
  region      = module.account_guard.region
}

module "backups" {
  source = "../modules/backups"

  name_prefix                 = local.name_prefix
  environment                 = var.environment
  kms_key_arn                 = module.kms.key_arn
  bucket_name                 = "${local.name_prefix}-pg-dumps-${module.account_guard.account_id}"
  daily_backup_retention_days = var.daily_backup_retention_days

  # LocalStack does not enforce Vault Lock / Object Lock — hardcode off so a
  # tfvars override can't produce lock state in a throwaway env.
  enable_vault_lock  = false
  enable_object_lock = false
}

module "network" {
  source = "../modules/network"

  name_prefix        = local.name_prefix
  vpc_cidr           = var.vpc_cidr
  public_subnet_cidr = var.public_subnet_cidr
  availability_zone  = var.availability_zone
  ssh_allowed_cidrs  = var.ssh_allowed_cidrs
  region             = module.account_guard.region
  environment        = var.environment
  account_id         = module.account_guard.account_id
  kms_key_arn        = module.kms.key_arn
  log_retention_days = var.log_retention_days
  backup_bucket_arn  = module.backups.backup_bucket_arn
}

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
}

# ECR — shared model (single instantiation). LocalStack Pro needs `ecr` in its
# SERVICES list (see README).
module "ecr" {
  source = "../modules/ecr"

  repository_names     = var.ecr_repository_names
  image_tag_mutability = "MUTABLE"
  scan_on_push         = true

  depends_on = [module.account_guard]
}

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

  langsmith_tracing = ""
  langsmith_api_key = ""
  langsmith_project = ""
}

# Compute — LocalStack limitations: EC2 can't see the IAM instance profile
# (moto backend split), no MonitorInstances / EbsOptimized, ephemeral EIP.
module "compute" {
  source = "../modules/compute"

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

  detailed_monitoring     = false
  ebs_optimized           = false
  protect_eip             = false
  disable_api_termination = false
  disable_api_stop        = false

  user_data_extra_env = {
    VELOCITYAI_BACKUP_BUCKET = module.backups.backup_bucket_name
    VELOCITYAI_PARAM_PREFIX  = module.secrets.parameter_path_prefix
    VELOCITYAI_KMS_KEY_ID    = module.kms.key_arn
    # Force module.iam into the graph so its resources are exercised even
    # though the EC2 doesn't attach the profile under LocalStack.
    _IAM_PROFILE_HOOK       = module.iam.instance_profile_name
    VELOCITYAI_ECR_REGISTRY = module.ecr.registry_url
    VELOCITYAI_GIT_REF      = "main"
  }
}

module "dns" {
  source = "../modules/dns"

  name_prefix       = local.name_prefix
  route53_zone_name = var.route53_zone_name
  app_subdomain     = var.app_subdomain
  eip_address       = module.compute.public_ip
  ttl_seconds       = var.dns_ttl_seconds
}

module "monitoring" {
  source = "../modules/monitoring"

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
  bedrock_model_id            = local.effective_model_id
  cw_metric_namespace         = "VelocityAI/${title(var.environment)}"
  # Empty vault name skips aws_backup_vault_notifications (LocalStack API gap).
  backup_vault_name = ""

  instance_role_arn = module.iam.instance_role_arn
  secrets_path_prefix_arn = format(
    "arn:%s:ssm:%s:%s:parameter%s",
    module.account_guard.partition,
    module.account_guard.region,
    module.account_guard.account_id,
    module.secrets.parameter_path_prefix,
  )
  project_cmk_arn = module.kms.key_arn

  # Let `terraform destroy` empty the CloudTrail bucket in this throwaway env.
  audit_trail_bucket_force_destroy = var.audit_trail_bucket_force_destroy
}

module "resourcegroups" {
  source = "../modules/resourcegroups"

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
    ecr        = "ECR-repositories backend frontend lifecycle-policies"
  }
}
