# Module: `secrets`

Owns the environment's runtime configuration in SSM Parameter Store under
`/velocityai/<environment>/`. Secret values (`SECRET_KEY`, `DATABASE_PASSWORD`,
optional `LANGSMITH_API_KEY`) are stored as KMS-encrypted **SecureStrings**;
non-secret config (CORS origins, JWT lifetime, Bedrock model/region) as plain
`String` parameters. The on-host `velocityai-load-secrets` loader reads this
tree and composes `/etc/velocityai/app.env` at every app start.

## Auto-generated secrets

If `app_secret_key` / `db_password` are left empty (the default), the module
generates strong `random_password` values (64-char / 32-char, alphanumeric) on
first apply and stores them. They are generated **once** and reused on
subsequent plans; the parameters use `lifecycle.ignore_changes = [value]` so an
operator can rotate them out-of-band without Terraform reverting. Override the
inputs only to import a known existing value (e.g. restoring a snapshot).

## Resources created

- `random_password.app_secret_key` / `random_password.db_password`.
- `aws_ssm_parameter.*` — `SECRET_KEY`, `DATABASE_PASSWORD` (SecureString);
  `CORS_ORIGINS`, `ACCESS_TOKEN_EXPIRE_HOURS`, `llm/region`, `llm/model_id`,
  `llm/inference_profile_id` (String); optional `LANGSMITH_*` (count-guarded).

## Usage

```hcl
module "secrets" {
  source = "../../modules/secrets"

  name_prefix = local.name_prefix
  environment = var.environment
  region      = var.aws_region
  kms_key_id  = module.kms.key_id

  bedrock_model_id             = var.bedrock_model_id
  bedrock_inference_profile_id = var.bedrock_inference_profile_id
  # app_secret_key / db_password omitted -> auto-generated
}
```

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|----------|
| `name_prefix` | Resource name prefix (used in tags). | `string` | — | yes |
| `environment` | Environment short name; drives the `/velocityai/<env>/...` parameter paths. | `string` | — | yes |
| `region` | AWS region (written as the LLM region parameter). | `string` | — | yes |
| `kms_key_id` | KMS key ID/ARN that encrypts the SecureString parameters. | `string` | — | yes |
| `bedrock_model_id` | Bedrock foundation model ID the app invokes. | `string` | — | yes |
| `bedrock_inference_profile_id` | Cross-region inference profile ID (preferred over model id). | `string` | `""` | no |
| `app_secret_key` | JWT signing key. Empty → 64-char auto-generated. **Sensitive.** | `string` | `""` | no |
| `db_password` | Postgres app-user password. Empty → 32-char auto-generated. **Sensitive.** | `string` | `""` | no |
| `langsmith_tracing` / `langsmith_api_key` / `langsmith_project` | Optional LangSmith config; empty disables creation of each parameter. | `string` | `""` | no |
| `cors_origins` | JSON list of CORS origins. Empty → loader falls back to `["https://<fqdn>"]`. | `string` | `""` | no |
| `access_token_expire_hours` | JWT lifetime in hours (1–168). | `number` | `12` | no |

## Outputs

| Name | Description |
|------|-------------|
| `parameter_path_prefix` | `/velocityai/<environment>` — the path the on-host loader reads. |
| `app_secret_key_parameter_arn` | ARN of the `SECRET_KEY` SecureString parameter. |
| `db_password_parameter_arn` | ARN of the `DATABASE_PASSWORD` SecureString parameter. |

## Notes

- `app_secret_key`, `db_password`, and `langsmith_api_key` are marked
  `sensitive = true` so they never appear in `plan`/`apply` output. Supply
  overrides via `TF_VAR_*`, never committed tfvars.
- `DATABASE_URL` and `ENV` are intentionally **not** written here — the loader
  composes `DATABASE_URL` from `DATABASE_PASSWORD` on the host, and `ENV` lives
  in the systemd unit so an SSM rotation can't misconfigure it.
