# Example: alb_internal — internal ALB in front of an existing EC2 instance.
#
# Illustrative only. Replace every ID below with real values from the target
# account, and certificate_arn with an ACM certificate already issued by a
# private/corporate CA (or imported) for the ALB's generated hostname.

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

module "alb_internal" {
  source = "../../"

  name_prefix = "velocityai-dev"
  environment = "dev"

  vpc_id      = "vpc-0535cb2c8b9dadcb4"
  subnet_ids  = ["subnet-06dfc3faca84c9673", "subnet-085f1421d35d8fbdf"]
  instance_id = "i-0f8c285633f222b7b"

  # Replace with the approved corporate VPN/TGW-routed CIDR(s). Never 0.0.0.0/0.
  trusted_ingress_cidrs = ["10.6.77.104/32"]

  certificate_arn = "arn:aws:acm:eu-central-1:265331052706:certificate/00000000-0000-0000-0000-000000000000"

  log_bucket_name = "velocityai-dev-alb-logs-265331052706-euc1"
  alarm_email     = "alerts@example.com"
}

output "alb_url" {
  value = "https://${module.alb_internal.alb_dns_name}"
}
