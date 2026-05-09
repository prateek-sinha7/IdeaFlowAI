data "aws_route53_zone" "this" {
  name         = var.route53_zone_name
  private_zone = false
}

locals {
  record_name = var.apex_record ? data.aws_route53_zone.this.name : "${var.app_subdomain}.${trim(data.aws_route53_zone.this.name, ".")}"
}

resource "aws_route53_record" "app_a" {
  zone_id = data.aws_route53_zone.this.zone_id
  name    = local.record_name
  type    = "A"
  ttl     = var.ttl_seconds
  records = [var.eip_address]
}
