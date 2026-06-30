provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "velocityai"
      Environment = "bootstrap"
      ManagedBy   = "terraform"
      Repo        = "gitlab.com/hexaware-uki/velocityai"
      Owner       = var.owner
      CostCenter  = var.cost_center
      Component   = "tfstate"
    }
  }
}
