terraform {
  # Aligned with the layer floor: the other layers (shared/foundation/app)
  # pin >= 1.9.0 for cross-variable validation.
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}
