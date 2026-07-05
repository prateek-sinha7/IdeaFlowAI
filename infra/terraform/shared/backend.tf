# Remote state backend (partial config supplied at `terraform init`).
#
# This layer holds resources SHARED across all environments (the ECR
# repositories), so it uses a single, env-independent state key:
#
#   terraform init \
#     -backend-config="bucket=$TF_STATE_BUCKET" \
#     -backend-config="key=velocityai/shared.tfstate" \
#     -backend-config="region=$AWS_REGION" \
#     -backend-config="dynamodb_table=$TF_STATE_LOCK_TABLE" \
#     -backend-config="encrypt=true"
#
# Local validate without remote state:
#   terraform init -backend=false
terraform {
  backend "s3" {}
}
