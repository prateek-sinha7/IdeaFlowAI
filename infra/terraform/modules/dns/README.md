# Module: `dns`

Publishes the public hostname the application is reachable at. It has two
mutually exclusive paths selected by `use_nip_io`:

- **Route 53 (`use_nip_io = false`, default).** Looks up an *existing* hosted
  zone by name (it does **not** create one) and creates an `A` record at
  `<app_subdomain>.<route53_zone_name>` (or the zone apex when
  `apex_record = true`) pointing at `eip_address`.
- **nip.io (`use_nip_io = true`).** Creates **no AWS resources at all**. The
  FQDN is computed deterministically as `<dashed-eip>.nip.io` (e.g.
  `1-2-3-4.nip.io`). nip.io is on the Public Suffix List, so Let's Encrypt
  issues real certs against it — handy for go-live before real DNS exists.

Either way, the only contract callers should depend on is the `fqdn` output.

## Resources created

- Route 53 path: `data.aws_route53_zone.this` (lookup) + `aws_route53_record.app_a`.
- nip.io path: none.

## Usage

```hcl
# nip.io (zero DNS config)
module "dns" {
  source      = "../../modules/dns"
  name_prefix = local.name_prefix
  use_nip_io  = true
  eip_address = module.compute.public_ip
}

# Route 53
module "dns" {
  source            = "../../modules/dns"
  name_prefix       = local.name_prefix
  route53_zone_name = "example.com"
  app_subdomain     = "velocityai"
  eip_address       = module.compute.public_ip
}
```

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|----------|
| `name_prefix` | Resource name prefix (used in tags). | `string` | — | yes |
| `eip_address` | Elastic IP (string). Target of the A record, or source of the nip.io hostname. | `string` | — | yes |
| `use_nip_io` | Derive the hostname from `eip_address` via nip.io and create no Route 53 resources. | `bool` | `false` | no |
| `route53_zone_name` | Existing hosted zone name to look up (ignored when `use_nip_io`). | `string` | `""` | no |
| `app_subdomain` | Subdomain under the zone, e.g. `velocityai` (ignored when `use_nip_io` or `apex_record`). | `string` | `"velocityai"` | no |
| `apex_record` | Create the A record at the zone apex (ignores `app_subdomain`). | `bool` | `false` | no |
| `ttl_seconds` | TTL on the A record (30–86400). Ignored when `use_nip_io`. | `number` | `60` | no |

## Outputs

| Name | Description |
|------|-------------|
| `fqdn` | The hostname the app is reachable at (Route 53 or nip.io). The only output callers should rely on. |
| `zone_id` | Hosted zone ID (empty when `use_nip_io`). |
| `record_name` | Name of the created A record (empty when `use_nip_io`). |

## Notes

- This module never creates a hosted zone — the zone must already exist in the
  account when `use_nip_io = false`.
- DNS + EIP live in the `app` layer (not `foundation`) so the record can read
  the live EIP address without a cross-layer state cycle.
