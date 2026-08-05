terraform {
  # 1.9+ for cross-variable validation. Terraform does not run in CI/CD
  # (GitHub Actions only builds images and redeploys containers — see
  # docs/GITHUB_CICD_SETUP.md); this floor is what operators applying the
  # layer by hand are held to, and is what `terraform validate` checks locally.
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}
