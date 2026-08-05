provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "velocityai"
      Environment = "bootstrap"
      ManagedBy   = "terraform"
      Repo        = "github.com/Hexaware-HnI/velocityai"
      Owner       = var.owner
      CostCenter  = var.cost_center
      Component   = "tfstate"
    }
  }
}
