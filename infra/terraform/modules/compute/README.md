# Module: `compute`

Provisions the application host: the EC2 instance, its KMS-encrypted root and
data EBS volumes, the Elastic IP, and the data-volume attachment. Postgres data
lives on the separate `prevent_destroy` data volume mounted at
`/var/lib/postgresql`, so it survives instance replacement; the EIP is likewise
`prevent_destroy` so the public address (and any DNS/cert bound to it) is
stable.

## Security defaults

- **IMDSv2 required** (`http_tokens = "required"`), hop limit 2 for
  Docker-on-EC2.
- Root + data EBS volumes encrypted with the project CMK.
- No auto-assigned public IP (`associate_public_ip_address = false`); the EIP is
  attached explicitly.
- `disable_api_termination` / `disable_api_stop` default `true`.

## Resources created

`aws_ebs_volume.data` (gp3, encrypted, `prevent_destroy`), `aws_instance.app`
(IMDSv2, encrypted root, user-data templated), `aws_volume_attachment.data`,
`aws_eip.this` (`prevent_destroy`), `aws_eip_association.this`. The Ubuntu AMI
is resolved via a data source unless `ami_id` is set.

## Usage

```hcl
module "compute" {
  source = "../../modules/compute"

  name_prefix               = local.name_prefix
  environment               = var.environment
  region                    = var.aws_region
  subnet_id                 = module.network.public_subnet_id
  availability_zone         = var.availability_zone
  security_group_id         = module.network.app_security_group_id
  iam_instance_profile_name = module.iam.instance_profile_name
  kms_key_arn               = module.kms.key_arn
}
```

## Inputs (selected)

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|----------|
| `name_prefix` | Resource name prefix. | `string` | — | yes |
| `environment` | Environment short name (user-data template). | `string` | — | yes |
| `region` | AWS region (user-data template). | `string` | — | yes |
| `subnet_id` | Subnet to launch into. | `string` | — | yes |
| `availability_zone` | AZ for the data EBS volume — must match the subnet's AZ. | `string` | — | yes |
| `security_group_id` | SG to attach to the primary ENI. | `string` | — | yes |
| `iam_instance_profile_name` | Instance profile to attach. | `string` | — | yes |
| `kms_key_arn` | CMK encrypting root + data EBS. | `string` | — | yes |
| `instance_type` | EC2 instance type. | `string` | `"m6i.2xlarge"` | no |
| `root_volume_size_gb` / `data_volume_size_gb` | EBS sizes (min 30 / 20 GiB). | `number` | `100` / `50` | no |
| `ssh_key_name` | Existing keypair for emergency SSH; empty disables `--key-name`. | `string` | `""` | no |
| `ami_id` | Override the Ubuntu AMI lookup (e.g. LocalStack). | `string` | `""` | no |
| `detailed_monitoring` / `ebs_optimized` | Toggles (set `false` where unsupported). | `bool` | `true` | no |
| `disable_api_termination` / `disable_api_stop` | Termination/stop guards. | `bool` | `true` | no |
| `user_data_extra_env` | Extra key/values injected into the user-data template. | `map(string)` | `{}` | no |

## Outputs

| Name | Description |
|------|-------------|
| `instance_id` / `instance_arn` | The EC2 instance. |
| `private_ip` / `public_ip` | Primary private IP / EIP public IP. |
| `eip_allocation_id` | EIP allocation ID. |
| `data_volume_id` / `data_volume_arn` | Data EBS volume (feed the ARN to AWS Backup selection). |
| `ami_id` | AMI ID resolved at apply time. |

## Notes

- `prevent_destroy` on the data volume and EIP is hard-coded `true` (Terraform
  forbids variables there). Ephemeral envs (LocalStack) `state rm` them before
  `terraform destroy` — see `localstack/destroy.sh`.
- The instance ignores `ami`/`user_data`/`associate_public_ip_address` changes
  to avoid spurious replacement; refresh the AMI with a deliberate
  `terraform taint`.
