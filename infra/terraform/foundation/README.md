# VelocityAI — foundation layer (per environment)

Long-lived base for one environment. Composes `account_guard`, `kms`,
`network`, `backups`, `iam`, and `secrets`, and publishes their outputs for the
`app` layer to read via `terraform_remote_state`.

- **State key:** `velocityai/<env>/foundation.tfstate`
- **Apply:** `terraform init -backend-config=... && terraform apply -var-file=<env>.tfvars -var="expected_account_id=<account>"`
- **Per-env config:** `dev.tfvars` / `stage.tfvars` / `prod.tfvars` (non-secret:
  CIDRs, AZ, retention). `environment` is set in the tfvars file.
- **Secrets:** `app_secret_key` / `db_password` default empty and are
  auto-generated into SSM SecureStrings; override only via `TF_VAR_*`.
- **Outputs consumed by `app`:** KMS key, VPC/subnet/SG ids, instance profile +
  role ARN, backup bucket + vault, SSM parameter prefix, AZ.

Inputs the CI runner injects as `TF_VAR_*`: `cors_origins`,
`bedrock_model_id`, `bedrock_inference_profile_id`. `expected_account_id` and
`aws_region` come on the CLI from the pipeline (derived from STS).
