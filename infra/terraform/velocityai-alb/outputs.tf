output "environment" {
  description = "Environment this apply targeted."
  value       = var.environment
}

output "alb_url" {
  description = "The URL to browse to over the corporate VPN/TGW path."
  value       = "https://${module.alb_internal.alb_dns_name}"
}

output "alb_dns_name" {
  description = "AWS-assigned internal ALB DNS name."
  value       = module.alb_internal.alb_dns_name
}

output "alb_security_group_id" {
  description = "Security group attached to the ALB (443/tcp from trusted_ingress_cidrs only)."
  value       = module.alb_internal.alb_security_group_id
}

output "target_security_group_id" {
  description = "Security group attached to the EC2 instance's ENI (443/tcp from the ALB SG only)."
  value       = module.alb_internal.target_security_group_id
}

output "log_bucket_name" {
  description = "S3 bucket receiving ALB access/connection logs."
  value       = module.alb_internal.log_bucket_name
}
