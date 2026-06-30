# Remote state backend (partial config supplied at `terraform init`).
#
# Per-env, per-layer state key:
#
#   terraform init \
#     -backend-config="bucket=$TF_STATE_BUCKET" \
#     -backend-config="key=velocityai/$ENVIRONMENT/foundation.tfstate" \
#     -backend-config="region=$AWS_REGION" \
#     -backend-config="dynamodb_table=$TF_STATE_LOCK_TABLE" \
#     -backend-config="encrypt=true"
#
# Each environment (dev|stage|prod) gets its own state object under
# velocityai/<env>/foundation.tfstate so blast radius stays per-environment.
#
# Local validate without remote state:
#   terraform init -backend=false
terraform {
  backend "s3" {}
}
