provider "aws" {
  region = var.aws_region

  dynamic "assume_role" {
    for_each = var.assume_role_arn != "" ? [1] : []
    content {
      role_arn     = var.assume_role_arn
      session_name = "velocityai-terraform-shared"
      external_id  = var.assume_role_external_id != "" ? var.assume_role_external_id : null
    }
  }

  default_tags {
    tags = {
      Project     = "velocityai"
      Environment = "shared"
      ManagedBy   = "terraform"
      Repo        = "github.com/Hexaware-HnI/velocityai"
      Owner       = var.owner
      CostCenter  = var.cost_center
    }
  }
}
