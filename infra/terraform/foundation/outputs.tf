# =============================================================================
# Foundation outputs — the contract the app layer reads via terraform_remote_state.
# =============================================================================

output "verified_account_id" {
  description = "Account ID confirmed by the guard."
  value       = module.account_guard.account_id
}

output "verified_region" {
  description = "Region confirmed by the guard."
  value       = module.account_guard.region
}

output "name_prefix" {
  description = "Resource name prefix for this environment (velocityai / velocityai-stage / velocityai-dev)."
  value       = local.name_prefix
}

output "availability_zone" {
  description = "AZ the public subnet lives in. The app layer pins the EC2 + data EBS volume to the same AZ."
  value       = var.availability_zone
}

# --- KMS ---------------------------------------------------------------------
output "kms_key_arn" {
  description = "Project KMS CMK ARN. Encrypts EBS, the backup bucket, the SNS topic, SSM SecureStrings, and the compose S3 object."
  value       = module.kms.key_arn
}

output "kms_key_id" {
  description = "Project KMS CMK key ID."
  value       = module.kms.key_id
}

output "kms_alias" {
  description = "Project KMS alias (alias/velocityai[-env])."
  value       = module.kms.alias_name
}

# --- Network -----------------------------------------------------------------
output "vpc_id" {
  description = "VPC ID."
  value       = module.network.vpc_id
}

output "public_subnet_id" {
  description = "Public subnet ID the EC2 instance launches into."
  value       = module.network.public_subnet_id
}

output "app_security_group_id" {
  description = "Security group attached to the EC2 instance ENI."
  value       = module.network.app_security_group_id
}

output "vpc_endpoint_ids" {
  description = "Map of service -> interface endpoint ID."
  value       = module.network.interface_endpoint_ids
}

# --- IAM ---------------------------------------------------------------------
output "instance_profile_name" {
  description = "Instance profile name to attach to the EC2 instance."
  value       = module.iam.instance_profile_name
}

output "instance_role_arn" {
  description = "ARN of the EC2 instance role. The app monitoring module references it (CloudTrail metric filters); compute attaches via the profile."
  value       = module.iam.instance_role_arn
}

# --- Backups -----------------------------------------------------------------
output "backup_bucket_name" {
  description = "S3 backup bucket name. The app layer uploads the compose object here and the on-host scripts write pg_dumps."
  value       = module.backups.backup_bucket_name
}

output "backup_bucket_arn" {
  description = "ARN of the S3 backup bucket."
  value       = module.backups.backup_bucket_arn
}

output "backup_vault_name" {
  description = "AWS Backup vault name. The app monitoring module binds vault notifications onto the alerts topic."
  value       = module.backups.backup_vault_name
}

# --- Secrets -----------------------------------------------------------------
output "parameter_path_prefix" {
  description = "SSM Parameter Store prefix VelocityAI reads from (/velocityai/<env>)."
  value       = module.secrets.parameter_path_prefix
}
