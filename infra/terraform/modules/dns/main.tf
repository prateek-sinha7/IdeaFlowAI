# DNS module — two paths.
#
# var.use_nip_io = false  (default, preserves the original behaviour)
#   • Look up the existing Route 53 hosted zone by name.
#   • Create an A-record at ${app_subdomain}.${route53_zone_name} (or the
#     zone apex when apex_record=true) pointing at var.eip_address.
#
# var.use_nip_io = true  (no-real-DNS path)
#   • Skip the Route 53 lookup AND the A-record entirely.
#   • The FQDN is computed deterministically as `<dashed-eip>.nip.io`
#     (e.g. 1-2-3-4.nip.io for EIP 1.2.3.4). nip.io is a magic-DNS service
#     whose wildcard A record resolves any subdomain like 1-2-3-4.nip.io
#     to the IP 1.2.3.4 — no DNS provisioning required.
#   • nip.io is on the Public Suffix List, so Let's Encrypt issues real
#     certs against the computed hostname (HTTP-01 against the EIP).
#
# This means the module produces zero Terraform-managed AWS resources in
# the nip.io path. The output `fqdn` is still defined and is the only
# external contract callers should rely on.

data "aws_route53_zone" "this" {
  count = var.use_nip_io ? 0 : 1

  name         = var.route53_zone_name
  private_zone = false
}

locals {
  # Computed FQDN. For the nip.io path: dashes replace dots in the EIP, so
  # 1.2.3.4 becomes 1-2-3-4.nip.io. For the Route 53 path: the data-source
  # zone name (which has a trailing dot from AWS) is trimmed and joined
  # with the chosen subdomain, or returned bare when apex_record=true.
  fqdn = var.use_nip_io ? (
    "${replace(var.eip_address, ".", "-")}.nip.io"
    ) : (
    var.apex_record
    ? trim(data.aws_route53_zone.this[0].name, ".")
    : "${var.app_subdomain}.${trim(data.aws_route53_zone.this[0].name, ".")}"
  )

  # The zone's `name` field comes back FQDN-style with a trailing dot (e.g.
  # "example.com."). For the record's own name field that's fine — Route 53
  # accepts both forms — but we keep the local consistent with what the
  # module's output exposes.
  record_name = var.use_nip_io ? "" : (
    var.apex_record ? data.aws_route53_zone.this[0].name : "${var.app_subdomain}.${trim(data.aws_route53_zone.this[0].name, ".")}"
  )
}

resource "aws_route53_record" "app_a" {
  count = var.use_nip_io ? 0 : 1

  zone_id = data.aws_route53_zone.this[0].zone_id
  name    = local.record_name
  type    = "A"
  ttl     = var.ttl_seconds
  records = [var.eip_address]
}
