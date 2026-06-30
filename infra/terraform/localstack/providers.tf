# LocalStack-targeted provider blocks.
#
# Every aws-service endpoint is rewritten to the LocalStack Pro listener on
# http://localhost:4666 (NB: NOT the standard 4566 — another team container
# may occupy 4566). Credentials are dummy; LocalStack accepts any. Path-style
# S3 + the skip flags stop the provider doing real DNS / IMDS / STS checks.
locals {
  localstack_endpoint = "http://localhost:4666"
}

provider "aws" {
  region                      = var.aws_region
  access_key                  = "test"
  secret_key                  = "test"
  s3_use_path_style           = true
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    acm            = local.localstack_endpoint
    backup         = local.localstack_endpoint
    bedrock        = local.localstack_endpoint
    cloudtrail     = local.localstack_endpoint
    cloudwatch     = local.localstack_endpoint
    dynamodb       = local.localstack_endpoint
    ec2            = local.localstack_endpoint
    ecr            = local.localstack_endpoint
    events         = local.localstack_endpoint
    iam            = local.localstack_endpoint
    kms            = local.localstack_endpoint
    logs           = local.localstack_endpoint
    resourcegroups = local.localstack_endpoint
    route53        = local.localstack_endpoint
    s3             = local.localstack_endpoint
    sns            = local.localstack_endpoint
    sqs            = local.localstack_endpoint
    ssm            = local.localstack_endpoint
    sts            = local.localstack_endpoint
  }

  default_tags {
    tags = {
      Project     = "velocityai"
      Environment = var.environment
      ManagedBy   = "terraform"
      Repo        = "gitlab.com/hexaware-uki/velocityai"
      Owner       = var.owner
      CostCenter  = var.cost_center
    }
  }
}

# us-east-1 alias — pointed at the same LocalStack listener; the billing alarm
# specifies provider = aws.useast1 explicitly.
provider "aws" {
  alias                       = "useast1"
  region                      = "us-east-1"
  access_key                  = "test"
  secret_key                  = "test"
  s3_use_path_style           = true
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    cloudwatch = local.localstack_endpoint
    sns        = local.localstack_endpoint
    sts        = local.localstack_endpoint
    iam        = local.localstack_endpoint
  }

  default_tags {
    tags = {
      Project     = "velocityai"
      Environment = var.environment
      ManagedBy   = "terraform"
      Repo        = "gitlab.com/hexaware-uki/velocityai"
      Owner       = var.owner
      CostCenter  = var.cost_center
    }
  }
}
