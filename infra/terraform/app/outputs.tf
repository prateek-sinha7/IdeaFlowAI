output "verified_account_id" {
  description = "Account ID confirmed by the guard."
  value       = module.account_guard.account_id
}

output "verified_region" {
  description = "Region confirmed by the guard."
  value       = module.account_guard.region
}

output "instance_id" {
  description = "EC2 instance ID."
  value       = module.compute.instance_id
}

output "instance_public_ip" {
  description = "EIP address attached to the instance."
  value       = module.compute.public_ip
}

output "fqdn" {
  description = "Public FQDN the app is reachable on (nip.io or Route 53)."
  value       = module.dns.fqdn
}

output "config_bucket" {
  description = "S3 bucket holding the deploy artifacts (config/docker-compose.yml + config/deploy.env). The CI post-build SSM redeploy reads these to `docker compose pull` the new image tag."
  value       = local.fnd.backup_bucket_name
}

output "image_tag" {
  description = "Container image tag this app state deployed."
  value       = var.image_tag
}

output "backend_image" {
  description = "Fully-qualified backend image URI for this deploy."
  value       = local.backend_image
}

output "frontend_image" {
  description = "Fully-qualified frontend image URI for this deploy."
  value       = local.frontend_image
}

output "alerts_topic_arn" {
  description = "SNS alerts topic ARN."
  value       = module.monitoring.alerts_topic_arn
}

output "log_group_names" {
  description = "Map of CloudWatch log groups."
  value       = module.monitoring.log_group_names
}

output "resource_group_all" {
  description = "Top-level Resource Group covering every VelocityAI resource in this environment."
  value       = module.resourcegroups.all_group_name
}

output "resource_groups_per_component" {
  description = "Map of component -> Resource Group name."
  value       = module.resourcegroups.per_component_group_names
}
