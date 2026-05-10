# ECR repositories for the Flowin app images.
#
# Two repos: <name_prefix>-backend and <name_prefix>-frontend. Both are
# KMS-encrypted at rest with the project CMK, scan on push, and use IMMUTABLE
# tags. Pull access is granted to the EC2 instance role two ways:
#   1) An inline IAM policy on the instance role (modules/iam +
#      policies/ecr-pull.json) — primary control.
#   2) A repository policy here scoped to the same role ARN —
#      defence-in-depth.
#
# Push is intentionally NOT granted by this module: pushes come from CI or
# operator workstations using their own IAM credentials, not from the EC2
# instance. If push permissions need locking down, that's a pusher-side
# policy, not a repo policy here. See policies/ecr-pull.json for the read
# path actually used at boot/deploy time.

locals {
  # Map keys (backend/frontend) flow into the Repository tag below so a
  # Resource Group filter on `Component=ecr` + `Repository=backend` can
  # narrow further when an operator wants per-repo scoping.
  repositories = {
    backend  = "${var.name_prefix}-backend"
    frontend = "${var.name_prefix}-frontend"
  }
}

resource "aws_ecr_repository" "this" {
  for_each = local.repositories

  name = each.value

  # IMMUTABLE: once a tag is pushed it cannot be overwritten by a subsequent
  # push of the same tag. This forces semver-ish, push-unique tags
  # (e.g. v20260510-abc1234) and eliminates the "someone re-pushed `latest`
  # and broke prod" failure mode. Rollback is via re-deploying a *previous*
  # tag, NOT via re-tagging a newer image as an older name. If a deploy
  # needs to be reverted, point the EC2 to v20260510-abc1234 instead of
  # v20260511-def5678 — both still exist in the registry until lifecycle
  # policy expires them.
  image_tag_mutability = "IMMUTABLE"

  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = var.kms_key_arn
  }

  image_scanning_configuration {
    scan_on_push = true
  }

  # force_delete = false (default, made explicit) so a `terraform destroy`
  # against a registry that still has images in it FAILS LOUDLY rather than
  # silently nuking pushed artifacts. To intentionally destroy: empty the
  # repo (`aws ecr batch-delete-image ...`) first, or flip this to true in a
  # disposable env. localstack's destroy.sh empties registries before
  # destroy when needed.
  force_delete = false

  tags = {
    Name        = each.value
    Environment = var.environment
    Project     = "flowin"
    Component   = "ecr"
    Repository  = each.key
  }

  # No prevent_destroy — repos are cheap to recreate; CI re-pushes images
  # after a teardown. KMS, S3 backup bucket, EBS data volume, and the IAM
  # role/profile have prevent_destroy because they hold or anchor durable
  # state. ECR repos do not.
  lifecycle {
    prevent_destroy = false
  }
}

# Lifecycle policy: keep the most recent 10 tagged images, expire any
# untagged image older than 14 days. Tagged-retention by count rather than
# age so a quiet weekend doesn't expire the running prod image.
resource "aws_ecr_lifecycle_policy" "this" {
  for_each = aws_ecr_repository.this

  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after 14 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 14
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep last 10 tagged images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = { type = "expire" }
      }
    ]
  })
}

# Repository policy: pull-only, instance-role-only.
#
# This is the second layer (the IAM-side ecr-pull policy on the role is the
# primary). Push permissions are intentionally OMITTED here — pushes come
# from CI runners or operator workstations using their own IAM identities,
# and gating those is a separate, pusher-side concern (an IAM policy on the
# pusher principal, not on this repo). Adding push to the repo policy here
# would force the question "who is the principal?" — and the right answer
# isn't `instance_role_arn`. So: pull only.
resource "aws_ecr_repository_policy" "this" {
  for_each = aws_ecr_repository.this

  repository = each.value.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowInstanceRolePull"
        Effect = "Allow"
        Principal = {
          AWS = var.instance_role_arn
        }
        Action = [
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:BatchCheckLayerAvailability"
        ]
      }
    ]
  })
}
