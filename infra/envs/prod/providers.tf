provider "aws" {
  region = var.aws_region

  dynamic "assume_role" {
    for_each = var.assume_role_arn != "" ? [1] : []
    content {
      role_arn     = var.assume_role_arn
      session_name = "flowin-terraform-${var.environment}"
      external_id  = var.assume_role_external_id != "" ? var.assume_role_external_id : null
    }
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

# us-east-1 alias for resources that must live there (Billing alarms, etc.).
provider "aws" {
  alias  = "useast1"
  region = "us-east-1"

  dynamic "assume_role" {
    for_each = var.assume_role_arn != "" ? [1] : []
    content {
      role_arn     = var.assume_role_arn
      session_name = "flowin-terraform-${var.environment}-useast1"
      external_id  = var.assume_role_external_id != "" ? var.assume_role_external_id : null
    }
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
