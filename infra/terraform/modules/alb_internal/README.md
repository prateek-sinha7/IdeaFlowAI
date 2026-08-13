# Module: `alb_internal`

Internal Application Load Balancer fronting an **existing** EC2 instance that
this module does not create — the instance, VPC, and subnets are looked up by
ID (`data "aws_instance"`), never managed. Built for the case where compute
was provisioned outside this Terraform tree and a private, VPN/TGW-reachable
HTTPS endpoint needs to be added in front of it without opening the instance
itself to any inbound traffic.

The ALB uses AWS's auto-assigned DNS name
(`internal-<name>-<id>.<region>.elb.amazonaws.com`). This module creates **no**
Route 53 zone, record, or Elastic IP.

## Security model

- **ALB security group:** `443/tcp` inbound **only** from
  `var.trusted_ingress_cidrs` (validated to reject `0.0.0.0/0` — an internal
  ALB with open ingress defeats the point). No port 80 listener or rule.
- **Target security group:** `443/tcp` inbound **only** from the ALB security
  group. Attached to the existing instance's primary ENI via
  `aws_network_interface_sg_attachment`, which **adds** a security group to
  the ENI without touching the instance's existing security group(s) — the
  instance keeps whatever SGs it already had.
- **TLS:** the module takes `var.certificate_arn` and never creates a
  certificate or private key. AWS cannot issue a public ACM certificate for
  an `amazonaws.com`-owned name, so the certificate for the ALB's generated
  hostname must come from a corporate/private CA (or be a dev-only
  certificate manually trusted on client devices) and be imported into ACM
  out-of-band — see `.local/velocityai-dev-alb/` for a helper script.
- **Target TLS:** the ALB connects to the target over HTTPS on
  `var.target_port` without validating the target's certificate (this is
  standard ALB target-group behavior — see
  [AWS docs](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-target-groups.html)),
  so the instance's existing self-signed nginx certificate works unmodified.
- **Access/connection logs:** delivered to a dedicated, versioned,
  `SSE-S3`-encrypted (the only encryption ELB log delivery supports), public-access-blocked
  S3 bucket with a lifecycle expiration.
- **Alarms:** `UnHealthyHostCount`, target/ALB 5xx, and `TargetResponseTime`,
  published to a dedicated SNS topic (or an existing one, see
  `create_sns_topic`).

## Usage

```hcl
module "alb_internal" {
  source = "../../modules/alb_internal"

  name_prefix = "velocityai-dev"
  environment = "dev"

  vpc_id      = "vpc-0535cb2c8b9dadcb4"
  subnet_ids  = ["subnet-06dfc3faca84c9673", "subnet-085f1421d35d8fbdf"]
  instance_id = "i-0f8c285633f222b7b"

  trusted_ingress_cidrs = ["10.6.77.104/32"] # replace with the approved corporate VPN CIDR

  certificate_arn = "arn:aws:acm:eu-central-1:265331052706:certificate/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

  log_bucket_name = "velocityai-dev-alb-logs-265331052706-euc1"
  alarm_email     = "alerts@example.com"
}

output "alb_url" {
  value = "https://${module.alb_internal.alb_dns_name}"
}
```

## Inputs (selected)

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|----------|
| `name_prefix` | Resource name prefix, e.g. `velocityai-dev`. | `string` | — | yes |
| `environment` | `dev` \| `stage` \| `prod`. | `string` | — | yes |
| `vpc_id` | Existing VPC ID. | `string` | — | yes |
| `subnet_ids` | >= 2 subnet IDs in different AZs, each with >= 8 free IPs. Not TGW-attachment subnets. | `list(string)` | — | yes |
| `instance_id` | Existing EC2 instance ID to register as the target. | `string` | — | yes |
| `trusted_ingress_cidrs` | Approved corporate VPN/TGW CIDR(s). Must NOT contain `0.0.0.0/0`. | `list(string)` | — | yes |
| `certificate_arn` | ACM certificate ARN for the ALB's generated DNS name (private CA or imported). | `string` | — | yes |
| `log_bucket_name` | Globally-unique S3 bucket name for ALB logs. | `string` | — | yes |
| `target_port` | Port nginx listens on. | `number` | `443` | no |
| `health_check_path` | ALB health-check path. | `string` | `"/"` | no |
| `enable_deletion_protection` | Guard against accidental ALB delete. | `bool` | `true` | no |
| `idle_timeout_seconds` | Must exceed the app's SSE heartbeat interval. | `number` | `300` | no |
| `create_sns_topic` / `alarm_sns_topic_arn` | Create a dedicated topic, or publish to an existing one. | `bool` / `string` | `true` / `""` | no |
| `alarm_email` | Subscribes to the created topic. Ignored when `create_sns_topic = false`. | `string` | `""` | no |

See `variables.tf` for the full list (health-check tuning, alarm thresholds,
tagging).

## Outputs

| Name | Description |
|------|-------------|
| `alb_dns_name` | The URL to browse to: `https://<alb_dns_name>`. |
| `alb_security_group_id` / `target_security_group_id` | The two SGs this module creates. |
| `target_group_arn` / `listener_arn` | For further wiring if needed. |
| `log_bucket_name` / `log_bucket_arn` | ALB log destination. |
| `alarm_topic_arn` | SNS topic alarms publish to. |

## Notes

- This module never touches the target instance's own security group(s),
  route tables, or NACLs. It also never modifies the instance resource
  itself — it is read via `data "aws_instance"`, so `terraform destroy` on
  a composition using this module removes only the ALB, its two SGs, the
  ENI attachment, target group, listener, log bucket, and alarms. The
  instance is unaffected.
- Direct access to the instance's private IP remains whatever it was before
  applying this module — this module does not change the instance's
  existing ingress rules, so verify separately that nothing else grants
  broader access.
- Pass a **narrow** `trusted_ingress_cidrs` (the approved corporate VPN/TGW
  range). A `/32` for a single tester's current VPN IP is fine for initial
  validation but is not a durable team-wide rule.
