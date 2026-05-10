# Remote state for envs/prod.
#
# Operators supply ONLY the bucket name at init time:
#   terraform init -backend-config="bucket=flowin-tfstate-<account>-<region>"
#
# Everything else is committed here so the state location is unambiguous —
# preventing the failure mode where two operators init against different
# keys and silently fork state. If the bucket name is sensitive in your
# org (e.g. it embeds the account ID), commit a sample backend.hcl in a
# private channel instead, but the `key`/`region`/`encrypt`/`dynamodb_table`
# values are NOT secrets and belong in version control.
terraform {
  backend "s3" {
    key            = "envs/prod/terraform.tfstate"
    region         = "eu-west-2"
    encrypt        = true
    dynamodb_table = "flowin-tfstate-locks"
    # bucket is operator-supplied via -backend-config
  }
}
