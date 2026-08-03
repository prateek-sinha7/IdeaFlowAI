# =============================================================================
# ECR repositories — SHARED across environments (build once, promote by DIGEST).
# =============================================================================
# Pull/push access is granted entirely IAM-side:
#   * the per-env EC2 instance roles (foundation/modules/iam, ecr-pull.json)
#     are scoped to these repo ARNs and do the actual image pull on the box;
#   * ONE GitHub Actions build role (bootstrap/github_oidc.tf) holds the push
#     actions on exactly these repos. The per-environment DEPLOY roles hold no
#     ECR permissions at all.
# There is intentionally NO aws_ecr_repository_policy here: a repo policy would
# have to name every per-env consumer role, which lives in a downstream layer
# and would create a cross-layer dependency cycle. IAM-side scoping is the
# single, cycle-free control point.
#
# TAG IMMUTABILITY IS LOAD-BEARING (var.image_tag_mutability, default
# IMMUTABLE). The repositories are shared, and ECR IAM offers no per-tag
# condition for ecr:PutImage — so IAM alone cannot stop a build triggered for
# one environment from re-pointing another environment's tag. Immutability can:
# an existing tag cannot be overwritten by anyone. Deploys then reference the
# resolved digest (repo@sha256:...), so what was scanned is what runs.

locals {
  # Per-environment "keep last N" rules for branch builds, one per tag prefix
  # (dev-/stage-/prod-) so each environment's churn is bounded independently.
  ecr_prefix_rules = [
    for idx, prefix in var.env_tag_prefixes : {
      rulePriority = idx + 1
      description  = "Keep last ${var.keep_last_images} '${prefix}*' branch-build images"
      selection = {
        tagStatus     = "tagged"
        tagPrefixList = [prefix]
        countType     = "imageCountMoreThan"
        countNumber   = var.keep_last_images
      }
      action = { type = "expire" }
    }
  ]

  # Untagged layers (orphaned when a tag is re-pushed) expire by age.
  ecr_untagged_rule = {
    rulePriority = length(var.env_tag_prefixes) + 1
    description  = "Expire untagged images ${var.untagged_expire_days} days after push"
    selection = {
      tagStatus   = "untagged"
      countType   = "sinceImagePushed"
      countUnit   = "days"
      countNumber = var.untagged_expire_days
    }
    action = { type = "expire" }
  }

  ecr_lifecycle_rules = concat(local.ecr_prefix_rules, [local.ecr_untagged_rule])
}

resource "aws_ecr_repository" "this" {
  # checkov:skip=CKV_AWS_136:AES256 (S3-managed) encryption is the default because the shared layer is applied BEFORE the per-env CMKs exist; a CMK can be supplied via var.kms_key_arn when one is available. Reviewed and accepted.
  #
  # CKV_AWS_51 (immutable tags) is NOT skipped any more: var.image_tag_mutability
  # now defaults to IMMUTABLE, so the check passes on the default configuration.
  # An operator who deliberately sets MUTABLE re-opens the finding, which is the
  # correct signal rather than a blanket suppression.
  for_each = toset(var.repository_names)

  name                 = each.value
  image_tag_mutability = var.image_tag_mutability

  encryption_configuration {
    encryption_type = var.kms_key_arn != "" ? "KMS" : "AES256"
    kms_key         = var.kms_key_arn != "" ? var.kms_key_arn : null
  }

  image_scanning_configuration {
    scan_on_push = var.scan_on_push
  }

  # force_delete = false (explicit) so a `terraform destroy` against a registry
  # that still holds images FAILS LOUDLY rather than silently deleting pushed
  # artifacts. To intentionally tear down, empty the repo first.
  force_delete = false

  tags = {
    Name      = each.value
    Component = "ecr"
  }
}

resource "aws_ecr_lifecycle_policy" "this" {
  for_each = aws_ecr_repository.this

  repository = each.value.name

  policy = jsonencode({
    rules = local.ecr_lifecycle_rules
  })
}
