# Remote state backend (partial config supplied at `terraform init`).
#
# Per-env, per-layer state key:
#
#   terraform init \
#     -backend-config="bucket=$TF_STATE_BUCKET" \
#     -backend-config="key=velocityai/$ENVIRONMENT/app.tfstate" \
#     -backend-config="region=$AWS_REGION" \
#     -backend-config="dynamodb_table=$TF_STATE_LOCK_TABLE" \
#     -backend-config="encrypt=true"
#
# This layer reads the foundation layer's outputs via terraform_remote_state
# (see data.tf), so the same state bucket must also be passed as
# TF_VAR_state_bucket (see variables.tf).
#
# Local validate without remote state:
#   terraform init -backend=false
terraform {
  backend "s3" {}
}
