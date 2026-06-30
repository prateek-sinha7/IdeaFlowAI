provider "aws" {
  region = var.aws_region

  dynamic "assume_role" {
    for_each = var.assume_role_arn != "" ? [1] : []
    content {
      role_arn     = var.assume_role_arn
      session_name = "velocityai-terraform-${var.environment}-app"
      external_id  = var.assume_role_external_id != "" ? var.assume_role_external_id : null
    }
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

# us-east-1 alias for resources that must live there (Billing/EstimatedCharges
# alarm consumed by the monitoring module).
provider "aws" {
  alias  = "useast1"
  region = "us-east-1"

  dynamic "assume_role" {
    for_each = var.assume_role_arn != "" ? [1] : []
    content {
      role_arn     = var.assume_role_arn
      session_name = "velocityai-terraform-${var.environment}-app-useast1"
      external_id  = var.assume_role_external_id != "" ? var.assume_role_external_id : null
    }
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
