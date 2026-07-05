# Example: backups — S3 pg_dump bucket + AWS Backup vault/plan.
#
# Illustrative only. kms_key_arn comes from the kms module in the real suite.
# Compliance locks (Vault Lock / Object Lock) are left at their safe defaults
# (off) here.

terraform {
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}

provider "aws" {
  region = "eu-central-1"
}

module "backups" {
  source = "../../"

  name_prefix = "velocityai-dev"
  environment = "dev"
  kms_key_arn = "arn:aws:kms:eu-central-1:123456789012:key/00000000-0000-0000-0000-000000000000"
  bucket_name = "velocityai-dev-pg-dumps-123456789012"

  # retention - cold_storage must be >= 90 (AWS Backup rule), and cold >= 1.
  daily_backup_retention_days = 180
  cold_storage_after_days     = 30
}

output "backup_bucket_arn" {
  value = module.backups.backup_bucket_arn
}
