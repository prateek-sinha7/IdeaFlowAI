# =============================================================================
# GitHub Actions CI/CD — OIDC provider + single shared deploy role.
# =============================================================================
# Terraform form of docs/GITHUB_CICD_SETUP.md Appendix A (the shared-role
# pattern) + §2.1 (the least-privilege scoping). Replaces the retired
# GitLab/CodeBuild IAM in cicd.tf.
#
# What this creates (all gated on var.create_github_oidc):
#   1. aws_iam_openid_connect_provider.github  — GitHub's OIDC IdP in this
#      account (or reuse an existing one via var.github_oidc_create_provider).
#   2. aws_iam_role.github_cicd                — ONE shared role whose trust
#      policy admits all of var.github_environments (dev/stage/prod).
#   3. aws_iam_role_policy.github_cicd         — inline least-privilege policy.
#
# OIDC-only: no static AWS keys ever live in GitHub. GitHub Actions requests a
# short-lived JWT (sub=repo:<org>/<repo>:environment:<env>), STS validates it
# against the provider + this role's trust policy, and hands back ~1h creds.
#
# Set the role ARN (output github_cicd_role_arn) as the AWS_ROLE_ARN variable
# in each GitHub Environment (GITHUB_CICD_SETUP.md §3.2).
# =============================================================================

locals {
  github_oidc_url  = "token.actions.githubusercontent.com"
  github_oidc_host = "https://token.actions.githubusercontent.com"

  # The provider ARN, whether we created it here or adopted a pre-existing one
  # (a sibling project in a shared account may already own the GitHub IdP —
  # there can be only one per account for a given URL).
  github_oidc_provider_arn = var.create_github_oidc ? (
    var.github_oidc_create_provider
    ? one(aws_iam_openid_connect_provider.github[*].arn)
    : one(data.aws_iam_openid_connect_provider.github[*].arn)
  ) : ""

  github_cicd_tags = { Component = "cicd" }

  # ECR repo ARNs the deploy role may push/pull (built once, promoted by tag).
  github_ecr_repo_arns = [
    for name in var.github_ecr_repository_names :
    "arn:${data.aws_partition.current.partition}:ecr:${var.aws_region}:${data.aws_caller_identity.current.account_id}:repository/${name}"
  ]

  # SSM Parameter Store prefixes the deploy role may write, one per environment
  # (/velocityai/<env>/*). deploy.yml pushes GitHub vars/secrets here on every run.
  github_ssm_param_arns = [
    for env in var.github_environments :
    "arn:${data.aws_partition.current.partition}:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/velocityai/${env}/*"
  ]

  # KMS keys used to encrypt SSM SecureString parameters. Empty var → scope to
  # every key in this account+region (broader, but NOT a bare "*"): the
  # per-env project CMKs are created downstream in the foundation layer and
  # don't exist at bootstrap time, so pinning exact key ARNs here would create
  # a cross-layer dependency. Pass concrete ARNs once they exist to tighten.
  github_kms_key_arns = length(var.github_cicd_kms_key_arns) > 0 ? var.github_cicd_kms_key_arns : [
    "arn:${data.aws_partition.current.partition}:kms:${var.aws_region}:${data.aws_caller_identity.current.account_id}:key/*"
  ]
}

# --- OIDC identity provider -------------------------------------------------
# Created once per account. In a shared account a sibling project may already
# own it — set github_oidc_create_provider = false to adopt the existing one.
resource "aws_iam_openid_connect_provider" "github" {
  count = var.create_github_oidc && var.github_oidc_create_provider ? 1 : 0

  url             = local.github_oidc_host
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = var.github_oidc_thumbprints

  tags = merge(local.github_cicd_tags, {
    Name = "github-actions-oidc"
  })
}

data "aws_iam_openid_connect_provider" "github" {
  count = var.create_github_oidc && !var.github_oidc_create_provider ? 1 : 0

  url = local.github_oidc_host
}

# --- Trust policy: GitHub OIDC, scoped to this repo + our environments ------
# Federated principal is the GitHub IdP; the token must carry
#   aud = sts.amazonaws.com
#   sub = repo:<org>/<repo>:environment:<dev|stage|prod>
# so only workflow jobs that declare `environment: <env>` for THIS repo can
# assume the role — a run in a fork or a different repo cannot.
data "aws_iam_policy_document" "github_cicd_assume" {
  count = var.create_github_oidc ? 1 : 0

  statement {
    sid     = "GitHubActionsOIDC"
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.github_oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.github_oidc_url}:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Bind to exactly this repo + each admitted GitHub Environment name.
    # Wildcards (*) after the org and repo name allow for GitHub org renames,
    # repo forks, or suffixed variants (e.g. flowin-v2) without a trust-policy
    # edit. The environment suffix remains pinned (no wildcard there).
    condition {
      test     = "StringLike"
      variable = "${local.github_oidc_url}:sub"
      values   = [for env in var.github_environments : "repo:${var.github_org_repo}:environment:${env}"]
    }
  }
}

resource "aws_iam_role" "github_cicd" {
  count = var.create_github_oidc ? 1 : 0

  name                 = var.github_cicd_role_name
  description          = "GitHub Actions OIDC deploy role for VelocityAI (dev/stage/prod). See docs/GITHUB_CICD_SETUP.md."
  assume_role_policy   = data.aws_iam_policy_document.github_cicd_assume[0].json
  permissions_boundary = var.deploy_permissions_boundary_arn != "" ? var.deploy_permissions_boundary_arn : null
  max_session_duration = 3600

  tags = merge(local.github_cicd_tags, {
    Name = var.github_cicd_role_name
  })
}

# --- Inline permissions policy (least privilege) ----------------------------
data "aws_iam_policy_document" "github_cicd" {
  count = var.create_github_oidc ? 1 : 0

  # ECR auth token is account-level — the GetAuthorizationToken API rejects a
  # scoped Resource, so "*" is unavoidable here. The token it returns is still
  # only usable against repos the ECRPushPull statement below scopes to.
  # checkov:skip=CKV_AWS_356:ecr:GetAuthorizationToken does not support resource-level scoping (AWS API constraint). Reviewed and accepted.
  statement {
    sid       = "ECRAuth"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  # Push + pull, scoped to exactly the two shared repos (velocityai/backend,
  # velocityai/frontend). deploy.yml builds once and promotes by tag.
  statement {
    sid    = "ECRPushPull"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "ecr:PutImage",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
    ]
    resources = local.github_ecr_repo_arns
  }

  # Push config from GitHub vars/secrets → SSM, scoped to /velocityai/<env>/*
  # for every admitted environment. A dev job can only write dev's tree.
  statement {
    sid       = "SSMPutParameters"
    effect    = "Allow"
    actions   = ["ssm:PutParameter"]
    resources = local.github_ssm_param_arns
  }

  # ── ssm:SendCommand MUST be two statements (GITHUB_CICD_SETUP.md §2.1) ──
  # SendCommand authorizes against BOTH the document AND the target instance.
  # The AWS-RunShellScript document has no Environment tag, so a single
  # tag-conditioned Resource="*" statement can NEVER be satisfied and every
  # deploy fails with AccessDeniedException. Split: document unconditionally,
  # instance with the tag condition.
  statement {
    sid       = "SSMSendCommandDocument"
    effect    = "Allow"
    actions   = ["ssm:SendCommand"]
    resources = ["arn:${data.aws_partition.current.partition}:ssm:${var.aws_region}::document/AWS-RunShellScript"]
  }

  statement {
    sid       = "SSMSendCommandInstance"
    effect    = "Allow"
    actions   = ["ssm:SendCommand"]
    resources = ["arn:${data.aws_partition.current.partition}:ec2:${var.aws_region}:${data.aws_caller_identity.current.account_id}:instance/*"]

    # Only instances tagged with an admitted Environment value — a dev deploy
    # can never reach a prod box. This is the load-bearing isolation control.
    condition {
      test     = "StringEquals"
      variable = "ssm:resourceTag/Environment"
      values   = var.github_environments
    }
  }

  # Poll command status — the invocation APIs don't support resource scoping.
  # checkov:skip=CKV_AWS_356:ssm:GetCommandInvocation/ListCommandInvocations do not support resource-level scoping (AWS API constraint). Reviewed and accepted.
  statement {
    sid    = "SSMCommandStatus"
    effect = "Allow"
    actions = [
      "ssm:GetCommandInvocation",
      "ssm:ListCommandInvocations",
    ]
    resources = ["*"]
  }

  # Encrypt SSM SecureStrings on put; Decrypt/GenerateDataKey for completeness.
  statement {
    sid    = "KMSForSecureString"
    effect = "Allow"
    actions = [
      "kms:Encrypt",
      "kms:Decrypt",
      "kms:GenerateDataKey",
    ]
    resources = local.github_kms_key_arns
  }

  # NOTE: sts:GetCallerIdentity was previously granted here but deploy.yml
  # never calls it. Removed to reduce the role's permission surface. If a
  # future step needs it, re-add with a comment explaining the caller.
}

resource "aws_iam_role_policy" "github_cicd" {
  count = var.create_github_oidc ? 1 : 0

  name   = "${var.github_cicd_role_name}-inline"
  role   = aws_iam_role.github_cicd[0].id
  policy = data.aws_iam_policy_document.github_cicd[0].json
}
