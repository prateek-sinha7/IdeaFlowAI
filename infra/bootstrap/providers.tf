provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "flowin"
      Environment = "bootstrap"
      ManagedBy   = "terraform"
      Repo        = "gitlab.com/hexaware-uki/flowin"
      Owner       = var.owner
      CostCenter  = var.cost_center
      Component   = "tfstate"
    }
  }
}
