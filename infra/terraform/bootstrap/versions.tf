terraform {
  # 1.9+ for cross-variable validation parity with the other layers. The
  # bootstrap uses the builtin `terraform_data` (account guard) and the aws
  # provider only — no hashicorp/null.
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}
