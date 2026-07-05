# Example: dns — nip.io path (creates zero AWS resources).
#
# Illustrative only. Swap use_nip_io=false + route53_zone_name for the
# Route 53 path.

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

module "dns" {
  source = "../../"

  name_prefix = "velocityai-dev"
  use_nip_io  = true
  eip_address = "203.0.113.10" # normally module.compute.public_ip
}

output "fqdn" {
  value = module.dns.fqdn # => 203-0-113-10.nip.io
}
