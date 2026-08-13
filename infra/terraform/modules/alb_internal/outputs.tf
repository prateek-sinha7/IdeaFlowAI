output "alb_arn" {
  description = "ARN of the internal ALB."
  value       = aws_lb.this.arn
}

output "alb_dns_name" {
  description = "AWS-assigned DNS name of the internal ALB (internal-<name>-<id>.<region>.elb.amazonaws.com). This is the URL to browse to over the VPN/TGW path — no Route 53 record is created."
  value       = aws_lb.this.dns_name
}

output "alb_zone_id" {
  description = "Route 53 hosted zone ID of the ALB (only needed if a caller later chooses to alias a private hosted zone record at it; not used by this module)."
  value       = aws_lb.this.zone_id
}

output "alb_security_group_id" {
  description = "Security group attached to the ALB. Ingress is restricted to var.trusted_ingress_cidrs on 443/tcp only."
  value       = aws_security_group.alb.id
}

output "target_security_group_id" {
  description = "Security group attached to the target instance's ENI. Ingress is restricted to the ALB security group on var.target_port only."
  value       = aws_security_group.alb_target.id
}

output "target_group_arn" {
  description = "ARN of the HTTPS target group the instance is registered in."
  value       = aws_lb_target_group.https.arn
}

output "listener_arn" {
  description = "ARN of the HTTPS listener."
  value       = aws_lb_listener.https.arn
}

output "log_bucket_name" {
  description = "S3 bucket receiving ALB access + connection logs."
  value       = aws_s3_bucket.logs.id
}

output "log_bucket_arn" {
  description = "ARN of the ALB log bucket."
  value       = aws_s3_bucket.logs.arn
}

output "alarm_topic_arn" {
  description = "SNS topic ARN alarms publish to (either the topic this module created, or var.alarm_sns_topic_arn when create_sns_topic = false)."
  value       = local.alarm_topic_arn
}
