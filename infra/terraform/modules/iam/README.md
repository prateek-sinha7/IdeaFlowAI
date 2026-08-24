# Module: `iam`

Creates the EC2 **instance role** and instance profile the application host
runs under, with least-privilege inline policies rendered from JSON templates
in `infra/terraform/policies/`. The role grants exactly what the box needs:
read its SSM parameter tree, decrypt with the project CMK, push pg_dumps to the
backup bucket, invoke the specific Bedrock model/inference profile, and (by
default) SSM Session Manager access.

## Resources created

- `aws_iam_role.instance` — the EC2 instance role (assumed by `ec2.amazonaws.com`).
- `aws_iam_role_policy.*` — inline policies from `policies/*.json` (SSM read,
  KMS decrypt, S3 backup write, Bedrock invoke, …).
- `aws_iam_instance_profile.instance` — wraps the role for `aws_instance`.
- Optional attachment of the AWS-managed `AmazonSSMManagedInstanceCore`.

## Usage

```hcl
module "iam" {
  source = "../../modules/iam"

  name_prefix       = local.name_prefix
  environment       = var.environment
  account_id        = module.account_guard.account_id
  region            = var.aws_region
  kms_key_arn       = module.kms.key_arn
  backup_bucket_arn = module.backups.backup_bucket_arn

  bedrock_model_id             = var.bedrock_model_id
  bedrock_inference_profile_id = var.bedrock_inference_profile_id
}
```

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|----------|
| `name_prefix` | Resource name prefix, e.g. `velocityai-prod`. | `string` | — | yes |
| `environment` | Environment short name (used in policy ARNs). | `string` | — | yes |
| `account_id` | AWS account ID. | `string` | — | yes |
| `region` | AWS region. | `string` | — | yes |
| `kms_key_arn` | Project CMK the instance role may decrypt with. | `string` | — | yes |
| `backup_bucket_arn` | S3 backup bucket the instance writes pg_dumps into. | `string` | — | yes |
| `bedrock_model_id` | Foundation model ID the invoke policy is scoped to. | `string` | — | yes |
| `bedrock_inference_profile_id` | Cross-region inference profile ID the invoke policy is scoped to. | `string` | — | yes |
| `policies_dir` | Path (relative to this module) to the policy JSON templates. | `string` | `"../../policies"` | no |
| `attach_ssm_managed_policy` | Attach `AmazonSSMManagedInstanceCore` (enables Session Manager). | `bool` | `true` | no |
| `cognito_user_pool_arn` | Cognito User Pool ARN the instance role may administer (Admin* actions, scoped to exactly this pool). Empty (default) creates no Cognito policy. | `string` | `""` | no |

## Outputs

| Name | Description |
|------|-------------|
| `instance_role_name` / `instance_role_arn` | The EC2 instance role. |
| `instance_profile_name` | Name to pass to `aws_instance.iam_instance_profile`. |
| `instance_profile_arn` | ARN of the instance profile. |

## Notes

- The Bedrock invoke policy is scoped to the exact model + inference-profile
  ARNs (and the EU regions the profile fans out to) — see
  `policies/bedrock-invoke.json`.
- Day-to-day host access is SSM Session Manager (no SSH key needed); the SSM
  managed policy is what enables it.
