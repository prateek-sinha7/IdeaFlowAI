# Remote state backend (partial config supplied at `terraform init`).
#
# Each environment gets its OWN state key — always pass a per-environment
# key so applying dev can never touch stage/prod state:
#
#   terraform init \
#     -backend-config="bucket=$TF_STATE_BUCKET" \
#     -backend-config="key=velocityai/$ENVIRONMENT/alb.tfstate" \
#     -backend-config="region=$AWS_REGION" \
#     -backend-config="dynamodb_table=$TF_STATE_LOCK_TABLE" \
#     -backend-config="encrypt=true"
#
# e.g. key=velocityai/dev/alb.tfstate, velocityai/stage/alb.tfstate,
# velocityai/prod/alb.tfstate.
#
# This is a standalone layer: the EC2 instances/VPC/subnets it targets were
# NOT created by infra/terraform/foundation or infra/terraform/app (they were
# provisioned by another process — see main.tf). It gets its own state object
# per environment so its blast radius never overlaps foundation/app state or
# another environment's ALB.
#
# Local validate without remote state:
#   terraform init -backend=false
terraform {
  backend "s3" {}
}
