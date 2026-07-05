# Module: `network`

Builds the single-AZ VPC the application runs in: VPC, Internet Gateway, one
public subnet, route table, the application security group, a separate
security group for VPC interface endpoints, the endpoints themselves
(Bedrock/SSM/Logs over PrivateLink + an S3 gateway endpoint), and VPC flow logs
to a KMS-encrypted CloudWatch log group.

## Network exposure

The only world-open ingress is the public web surface, which a public SaaS must
expose:

- `80/tcp` from `0.0.0.0/0` — HTTP redirect + ACME http-01 challenge.
- `443/tcp` from `0.0.0.0/0` — HTTPS / WSS (nginx terminates TLS on the host).
- `22/tcp` — **only** from `ssh_allowed_cidrs` (validated to never contain
  `0.0.0.0/0`); empty by default, relying on SSM Session Manager instead.

The VPC's default security group and default route table are adopted and
emptied so an accidentally-unscoped ENI/subnet fails closed rather than getting
AWS's permissive defaults. Interface/gateway endpoint policies pin
`aws:PrincipalAccount` to this account as defence-in-depth.

## Resources created

`aws_vpc`, `aws_internet_gateway`, `aws_subnet.public`, `aws_route_table` +
route + association, `aws_default_security_group`/`aws_default_route_table`
(locked empty), `aws_security_group.app` + ingress/egress rules,
`aws_security_group.endpoints`, `aws_vpc_endpoint.interface` (bedrock,
bedrock-runtime, ssm, ssmmessages, ec2messages, logs), `aws_vpc_endpoint.s3`,
and the VPC flow-logs role + log group + `aws_flow_log`.

## Usage

```hcl
module "network" {
  source = "../../modules/network"

  name_prefix        = local.name_prefix
  environment        = var.environment
  region             = var.aws_region
  account_id         = module.account_guard.account_id
  availability_zone  = var.availability_zone
  vpc_cidr           = "10.20.0.0/16"
  public_subnet_cidr = "10.20.1.0/24"
  kms_key_arn        = module.kms.key_arn
  backup_bucket_arn  = module.backups.backup_bucket_arn
  ssh_allowed_cidrs  = [] # rely on SSM Session Manager
}
```

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|----------|
| `name_prefix` | Resource name prefix. | `string` | — | yes |
| `region` | Region (used to build endpoint service names). | `string` | — | yes |
| `account_id` | AWS account ID (flow-logs trust + endpoint-policy `aws:PrincipalAccount`). | `string` | — | yes |
| `availability_zone` | Single AZ to deploy into, e.g. `eu-central-1a`. | `string` | — | yes |
| `kms_key_arn` | CMK that encrypts the flow-logs CloudWatch group. | `string` | — | yes |
| `environment` | Env short name; appears in the flow-logs log-group path. | `string` | `"prod"` | no |
| `vpc_cidr` | Primary VPC CIDR. | `string` | `"10.20.0.0/16"` | no |
| `public_subnet_cidr` | CIDR for the single public subnet. | `string` | `"10.20.1.0/24"` | no |
| `ssh_allowed_cidrs` | CIDRs permitted to reach `22/tcp`. Must not contain `0.0.0.0/0`. | `list(string)` | `[]` | no |
| `log_retention_days` | Retention for the flow-logs group. | `number` | `30` | no |
| `backup_bucket_arn` | Scopes the S3 gateway endpoint policy. Empty → `Resource:*` fallback. | `string` | `""` | no |

## Outputs

| Name | Description |
|------|-------------|
| `vpc_id` / `vpc_cidr` | The project VPC. |
| `public_subnet_id` | The single public subnet. |
| `public_route_table_id` | The public route table. |
| `app_security_group_id` | SG to attach to the EC2 instance. |
| `endpoints_security_group_id` | SG attached to the interface endpoints. |
| `interface_endpoint_ids` | Map of service name → interface endpoint ID. |
| `s3_gateway_endpoint_id` | The S3 gateway endpoint ID. |
| `internet_gateway_id` | The IGW ID. |
| `flow_logs_log_group_name` / `_arn` / `flow_logs_iam_role_arn` | VPC flow-logs destination + role. |

## Notes

- Single-AZ by design (see `docs/SIMPLE_AWS_DEPLOYMENT.md`); per-env CIDRs are
  non-overlapping (prod `10.20`, stage `10.30`, dev `10.40`).
- `ssh_allowed_cidrs` has a validation that rejects `0.0.0.0/0` outright.
