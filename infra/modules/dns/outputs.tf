output "fqdn" {
  description = "Fully qualified domain name the application is reachable at."
  value       = aws_route53_record.app_a.fqdn
}

output "zone_id" {
  description = "Route 53 hosted zone ID (looked up, not created)."
  value       = data.aws_route53_zone.this.zone_id
}

output "record_name" {
  description = "Name of the A record."
  value       = aws_route53_record.app_a.name
}
