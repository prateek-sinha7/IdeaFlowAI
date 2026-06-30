# =============================================================================
# VelocityAI Shared Layer
# =============================================================================
# Resources owned ONCE across all environments. Container images are built a
# single time and promoted dev -> stage -> prod by tag, so the ECR repositories
# are not environment-specific and must be owned by exactly one state file
# (this one) to avoid name collisions between the per-env app layers.
#
# State key: velocityai/shared.tfstate
# Apply order: bootstrap -> shared -> foundation(<env>) -> app(<env>)
# =============================================================================

# Account / region guard — refuses to apply against the wrong account or region
# (the suite shares an AWS Organizations account with other Hexaware tenants).
module "account_guard" {
  source = "../modules/account_guard"

  expected_account_id = var.expected_account_id
  expected_region     = var.aws_region
}

# --- ECR: shared container registries (build once, promote by tag) ----------
module "ecr" {
  source = "../modules/ecr"

  repository_names     = var.ecr_repository_names
  image_tag_mutability = var.ecr_image_tag_mutability
  keep_last_images     = var.ecr_keep_last_images
  scan_on_push         = true

  # Ensure the account/region guard evaluates before any repo is created.
  depends_on = [module.account_guard]
}
