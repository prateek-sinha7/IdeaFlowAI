terraform {
  # Aligned with the layer floor: the consuming layers (shared/foundation/app)
  # pin >= 1.9.0 for cross-variable validation, so modules don't advertise a
  # lower floor they're never instantiated under.
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
      configuration_aliases = [
        aws,
        aws.useast1,
      ]
    }
  }
}
