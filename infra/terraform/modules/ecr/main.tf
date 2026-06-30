# =============================================================================
# ECR repositories — SHARED across environments (build once, promote by tag).
# =============================================================================
# Pull access is granted entirely IAM-side:
#   * the per-env EC2 instance roles (foundation/modules/iam, ecr-pull.json)
#     are scoped to these repo ARNs;
#   * the per-env CodeBuild deploy roles (bootstrap/cicd.tf) hold ecr:* on
#     velocityai/* so the pipeline can push.
# There is intentionally NO aws_ecr_repository_policy here: a repo policy would
# have to name every per-env consumer role, which lives in a downstream layer
# and would create a cross-layer dependency cycle. IAM-side scoping is the
# single, cycle-free control point.

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
  # checkov:skip=CKV_AWS_51:Tag mutability is operator-configurable via var.image_tag_mutability (default MUTABLE) so a build retry can re-push the same <env>-<sha>/release tag — the reference CI model. Reviewed and accepted.
  # checkov:skip=CKV_AWS_136:AES256 (S3-managed) encryption is the default because the shared layer is applied BEFORE the per-env CMKs exist; a CMK can be supplied via var.kms_key_arn when one is available. Reviewed and accepted.
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
