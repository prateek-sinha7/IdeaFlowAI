terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
    # random.app_secret_key / random.db_password — strong defaults so the
    # operator doesn't have to pre-seed TF_VAR_*. Generated ONCE on first
    # apply; never regenerated (no keepers). Manual rotation works
    # out-of-band because the aws_ssm_parameter lifecycle ignores `value`.
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}
