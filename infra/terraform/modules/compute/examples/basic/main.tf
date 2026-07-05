# Example: compute — EC2 host + encrypted EBS + EIP.
#
# Illustrative only. subnet_id / security_group_id / iam_instance_profile_name
# / kms_key_arn come from the network, iam, and kms modules in the real suite.

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

module "compute" {
  source = "../../"

  name_prefix       = "velocityai-dev"
  environment       = "dev"
  region            = "eu-central-1"
  availability_zone = "eu-central-1a"

  subnet_id                 = "subnet-0123456789abcdef0"
  security_group_id         = "sg-0123456789abcdef0"
  iam_instance_profile_name = "velocityai-dev-instance-profile"
  kms_key_arn               = "arn:aws:kms:eu-central-1:123456789012:key/00000000-0000-0000-0000-000000000000"

  instance_type       = "t3.large" # smaller for a dev box
  data_volume_size_gb = 20
}

output "public_ip" {
  value = module.compute.public_ip
}
