# LocalStack-targeted provider blocks.
#
# - Every aws-service endpoint is rewritten to the LocalStack Pro listener on
#   http://localhost:4666 (NB: NOT the standard 4566 — there's another team
#   container on 4566 we must not interfere with).
# - Credentials are dummy ("test"/"test"); LocalStack accepts any.
# - Path-style S3 + the various skip flags are required so the AWS provider
#   doesn't try real DNS / IMDS / STS account-id checks against AWS.
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
    accessanalyzer           = local.localstack_endpoint
    account                  = local.localstack_endpoint
    acm                      = local.localstack_endpoint
    apigateway               = local.localstack_endpoint
    apigatewayv2             = local.localstack_endpoint
    appautoscaling           = local.localstack_endpoint
    appconfig                = local.localstack_endpoint
    appsync                  = local.localstack_endpoint
    athena                   = local.localstack_endpoint
    autoscaling              = local.localstack_endpoint
    backup                   = local.localstack_endpoint
    batch                    = local.localstack_endpoint
    bedrock                  = local.localstack_endpoint
    bedrockagent             = local.localstack_endpoint
    cloudcontrol             = local.localstack_endpoint
    cloudformation           = local.localstack_endpoint
    cloudfront               = local.localstack_endpoint
    cloudtrail               = local.localstack_endpoint
    cloudwatch               = local.localstack_endpoint
    codebuild                = local.localstack_endpoint
    codecommit               = local.localstack_endpoint
    codedeploy               = local.localstack_endpoint
    codepipeline             = local.localstack_endpoint
    cognitoidentity          = local.localstack_endpoint
    cognitoidp               = local.localstack_endpoint
    configservice            = local.localstack_endpoint
    dynamodb                 = local.localstack_endpoint
    ec2                      = local.localstack_endpoint
    ecr                      = local.localstack_endpoint
    ecs                      = local.localstack_endpoint
    efs                      = local.localstack_endpoint
    eks                      = local.localstack_endpoint
    elasticache              = local.localstack_endpoint
    elasticbeanstalk         = local.localstack_endpoint
    elb                      = local.localstack_endpoint
    elbv2                    = local.localstack_endpoint
    emr                      = local.localstack_endpoint
    es                       = local.localstack_endpoint
    firehose                 = local.localstack_endpoint
    glacier                  = local.localstack_endpoint
    glue                     = local.localstack_endpoint
    iam                      = local.localstack_endpoint
    iot                      = local.localstack_endpoint
    kafka                    = local.localstack_endpoint
    kinesis                  = local.localstack_endpoint
    kinesisanalytics         = local.localstack_endpoint
    kms                      = local.localstack_endpoint
    lakeformation            = local.localstack_endpoint
    lambda                   = local.localstack_endpoint
    logs                     = local.localstack_endpoint
    mediastore               = local.localstack_endpoint
    mq                       = local.localstack_endpoint
    neptune                  = local.localstack_endpoint
    organizations            = local.localstack_endpoint
    qldb                     = local.localstack_endpoint
    rds                      = local.localstack_endpoint
    redshift                 = local.localstack_endpoint
    resourcegroups           = local.localstack_endpoint
    resourcegroupstaggingapi = local.localstack_endpoint
    route53                  = local.localstack_endpoint
    route53resolver          = local.localstack_endpoint
    s3                       = local.localstack_endpoint
    s3control                = local.localstack_endpoint
    sagemaker                = local.localstack_endpoint
    secretsmanager           = local.localstack_endpoint
    serverlessrepo           = local.localstack_endpoint
    servicediscovery         = local.localstack_endpoint
    ses                      = local.localstack_endpoint
    sns                      = local.localstack_endpoint
    sqs                      = local.localstack_endpoint
    ssm                      = local.localstack_endpoint
    stepfunctions            = local.localstack_endpoint
    sts                      = local.localstack_endpoint
    swf                      = local.localstack_endpoint
    transfer                 = local.localstack_endpoint
    waf                      = local.localstack_endpoint
    wafregional              = local.localstack_endpoint
    wafv2                    = local.localstack_endpoint
    xray                     = local.localstack_endpoint
  }

  default_tags {
    tags = {
      Project     = "flowin"
      Environment = var.environment
      ManagedBy   = "terraform"
      Repo        = "gitlab.com/hexaware-uki/flowin"
      Owner       = var.owner
      CostCenter  = var.cost_center
    }
  }
}

# us-east-1 alias — pointed at the same LocalStack listener; the billing alarm
# resource specifies provider = aws.useast1 explicitly.
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
      Project     = "flowin"
      Environment = var.environment
      ManagedBy   = "terraform"
      Repo        = "gitlab.com/hexaware-uki/flowin"
      Owner       = var.owner
      CostCenter  = var.cost_center
    }
  }
}
