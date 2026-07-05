# VelocityAI — app layer (per environment)

The deployable unit for one environment. Reads the `foundation` layer's
outputs via `terraform_remote_state` (see `data.tf`) and composes `compute`
(EC2 + data EBS + EIP), `dns`, the `docker-compose.yml` + `deploy.env` S3
objects (driven by `var.image_tag`), `monitoring`, and `resourcegroups`. It
runs its own `account_guard`.

- **State key:** `velocityai/<env>/app.tfstate`
- **Required vars:** `state_bucket` (to read foundation state), `image_tag`
  (the container tag to deploy), `expected_account_id`, `alert_email`.
- **Apply:** `terraform init -backend-config=... && terraform apply -var-file=<env>.tfvars -var="state_bucket=$B" -var="image_tag=<tag>" -var="expected_account_id=<account>" -var="alert_email=<email>"`

### Deploy model

`app apply` writes two objects to the backup bucket (KMS-encrypted):
`config/docker-compose.yml` (static) and `config/deploy.env`
(`IMAGE_TAG`/`BACKEND_IMAGE`/`FRONTEND_IMAGE`, regenerated when `image_tag`
changes). The on-host bootstrap and the CI post-build SSM RunCommand both read
those, then `docker compose pull && up -d`. The image tag is **not** baked into
the EC2 user-data (it has `ignore_changes`), so a tag bump never replaces the
instance.

`alert_email`, `cors_origins`, and the Bedrock model are injected as `TF_VAR_*`
by the CI runner; `image_tag` / `state_bucket` / `expected_account_id` come on
the CLI from the pipeline.
