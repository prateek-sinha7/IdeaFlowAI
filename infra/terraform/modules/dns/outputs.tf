output "fqdn" {
  description = "Fully qualified domain name the application is reachable at. nip.io path: <dashed-eip>.nip.io (e.g. 1-2-3-4.nip.io). Route 53 path: $${app_subdomain}.$${route53_zone_name} (or zone apex when apex_record=true)."
  value       = local.fqdn
}

output "zone_id" {
  description = "Route 53 hosted zone ID (looked up, not created). Empty string when use_nip_io = true."
  value       = var.use_nip_io ? "" : data.aws_route53_zone.this[0].zone_id
}

output "record_name" {
  description = "Name of the A record created in Route 53. Empty string when use_nip_io = true (no record is created)."
  value       = var.use_nip_io ? "" : aws_route53_record.app_a[0].name
}
