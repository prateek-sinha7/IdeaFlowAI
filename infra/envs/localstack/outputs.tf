output "verified_account_id" {
  description = "Account ID confirmed by the guard."
  value       = module.account_guard.account_id
}

output "verified_region" {
  description = "Region confirmed by the guard."
  value       = module.account_guard.region
}

output "kms_key_arn" {
  description = "Project KMS key ARN."
  value       = module.kms.key_arn
}

output "kms_alias" {
  description = "Project KMS alias."
  value       = module.kms.alias_name
}

output "vpc_id" {
  description = "VPC ID."
  value       = module.network.vpc_id
}

output "public_subnet_id" {
  description = "Public subnet ID."
  value       = module.network.public_subnet_id
}

output "app_security_group_id" {
  description = "Application security group ID."
  value       = module.network.app_security_group_id
}

output "vpc_endpoint_ids" {
  description = "Map of service -> interface endpoint ID."
  value       = module.network.interface_endpoint_ids
}

output "instance_id" {
  description = "EC2 instance ID."
  value       = module.compute.instance_id
}

output "instance_public_ip" {
  description = "EIP address."
  value       = module.compute.public_ip
}

output "instance_role_arn" {
  description = "ARN of the EC2 instance role."
  value       = module.iam.instance_role_arn
}

output "data_volume_id" {
  description = "EBS data volume ID."
  value       = module.compute.data_volume_id
}

output "backup_bucket_name" {
  description = "S3 backup bucket name."
  value       = module.backups.backup_bucket_name
}

output "backup_vault_name" {
  description = "AWS Backup vault name."
  value       = module.backups.backup_vault_name
}

output "alerts_topic_arn" {
  description = "SNS alerts topic ARN."
  value       = module.monitoring.alerts_topic_arn
}

output "log_group_names" {
  description = "Map of CloudWatch log groups."
  value       = module.monitoring.log_group_names
}

output "fqdn" {
  description = "Public FQDN."
  value       = module.dns.fqdn
}

output "parameter_path_prefix" {
  description = "SSM Parameter Store prefix."
  value       = module.secrets.parameter_path_prefix
}

output "resource_group_all" {
  description = "Top-level Resource Group."
  value       = module.resourcegroups.all_group_name
}

output "resource_groups_per_component" {
  description = "Map of component -> Resource Group name."
  value       = module.resourcegroups.per_component_group_names
}

output "ecr_backend_repository_url" {
  description = "ECR pull URL for the backend image."
  value       = module.ecr.backend_repository_url
}

output "ecr_frontend_repository_url" {
  description = "ECR pull URL for the frontend image."
  value       = module.ecr.frontend_repository_url
}
