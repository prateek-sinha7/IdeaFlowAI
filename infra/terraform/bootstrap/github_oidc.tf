# =============================================================================
# GitHub Actions CI/CD — OIDC provider + ONE BUILD ROLE + PER-ENV DEPLOY ROLES.
# =============================================================================
# Terraform form of docs/GITHUB_CICD_SETUP.md Appendix A + §2.1 (least
# privilege). Replaces the retired GitLab/CodeBuild IAM in cicd.tf.
#
# WHY THIS IS NO LONGER ONE SHARED ROLE
# -------------------------------------
# The previous design created a single role whose trust policy admitted every
# entry in var.github_environments AND whose inline policy listed every
# environment's SSM prefix + every admitted `Environment` tag value. That does
# NOT isolate environments: the OIDC `sub` claim is evaluated exactly once, by
# sts:AssumeRoleWithWebIdentity. It is NOT re-evaluated per API call. So once a
# `dev` job held those credentials it could write /velocityai/prod/* and
# ssm:SendCommand a prod-tagged instance — the old comments claiming otherwise
# were wrong. The tag condition only limited the blast radius to "some admitted
# environment", never to "the environment this job was approved for".
#
# The fix is structural, and the ONLY structural fix available inside one
# account: the environment must be baked into the identity, not into a
# condition the caller has already satisfied.
#
# What this creates (all gated on var.create_github_oidc):
#   1. aws_iam_openid_connect_provider.github   — GitHub's OIDC IdP in this
#      account (or adopt an existing one via var.github_oidc_create_provider).
#   2. aws_iam_role.github_build                — ONE build role. ECR only:
#      auth, layer/manifest push, pull, DescribeImages. No SSM. No KMS. Cannot
#      reach any EC2 instance or parameter tree in any environment.
#   3. aws_iam_role.github_deploy[<env>]        — ONE DEPLOY ROLE PER
#      ENVIRONMENT, each trusting exactly ONE `sub` (StringEquals, no globs)
#      and each scoped to exactly ONE SSM prefix and ONE `Environment` tag
#      value. A dev deploy role cannot name a prod parameter or a prod
#      instance, whatever the job asks for. Deploy roles hold NO ECR
#      permissions at all — the EC2 instance role pulls the images (see
#      .github/scripts/remote-deploy.sh §8), not the CI role.
#
# OIDC-only: no static AWS keys ever live in GitHub. GitHub Actions requests a
# short-lived JWT (sub=repo:<owner>/<repo>:environment:<env>), STS validates it
# against the provider + the role's trust policy, and hands back ~1h creds.
#
# Wire the outputs into GitHub (GITHUB_CICD_SETUP.md §3.2):
#   github_build_role_arn      -> AWS_BUILD_ROLE_ARN  (same value in every env)
#   github_deploy_role_arns[e] -> AWS_DEPLOY_ROLE_ARN (env-specific value)
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

  # Set of environments to build roles for. Empty when the OIDC block is off,
  # so for_each collapses to zero resources without a count/for_each mix.
  github_env_set = var.create_github_oidc ? toset(var.github_environments) : toset([])

  # ECR repo ARNs the BUILD role may push/pull (built once, promoted by digest).
  github_ecr_repo_arns = [
    for name in var.github_ecr_repository_names :
    "arn:${data.aws_partition.current.partition}:ecr:${var.aws_region}:${data.aws_caller_identity.current.account_id}:repository/${name}"
  ]

  # Resource scope for the KMS grant. Explicit ARNs when the operator can
  # supply them; otherwise every key in this account+region (NOT a bare "*"),
  # because the per-env project CMKs are created downstream in the foundation
  # layer and do not exist at bootstrap time — pinning exact key ARNs here
  # would create a cross-layer dependency.
  #
  # The breadth of that fallback is what the kms:ViaService +
  # kms:EncryptionContext:PARAMETER_ARN conditions on the statement exist to
  # close: the grant is usable ONLY through SSM, and ONLY for a parameter under
  # this environment's own prefix. A dev deploy role cannot encrypt a prod
  # parameter even though the prod key ARN is inside its Resource set.
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

# =============================================================================
# BUILD ROLE — ECR only, shared across environments
# =============================================================================
# Trusts every admitted environment because `build` runs under
# `environment: <resolved env>` in deploy.yml and the artifact it produces is
# environment-agnostic (D-4: one image, promoted by digest).
#
# Sharing this role across environments is deliberate and safe in a way the old
# shared DEPLOY role was not: the ECR repositories are themselves shared, so
# there is no per-environment resource to separate here (ECR IAM has no
# tag/tag-prefix condition for PutImage — you cannot express "may push dev-*
# but not v*"). What protects a release artifact is IMMUTABLE tags on the repo
# (infra/terraform/modules/ecr) — an existing tag cannot be overwritten by any
# caller, including this role. Deploy-time integrity comes from deploying the
# digest the build resolved, never a floating tag.
data "aws_iam_policy_document" "github_build_assume" {
  count = var.create_github_oidc ? 1 : 0

  statement {
    sid     = "GitHubActionsOIDCBuild"
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

    # EXACT subjects, one per admitted environment — no wildcards anywhere.
    # A glob such as "repo:my-org*/my-repo*:environment:prod" would also admit
    # any OTHER GitHub owner/repository whose name shares that prefix, in any
    # organisation, which is a repo-impersonation path into this account.
    condition {
      test     = "StringEquals"
      variable = "${local.github_oidc_url}:sub"
      values   = [for env in var.github_environments : "repo:${var.github_org_repo}:environment:${env}"]
    }
  }
}

resource "aws_iam_role" "github_build" {
  count = var.create_github_oidc ? 1 : 0

  name                 = "${var.github_cicd_role_name}-build"
  description          = "GitHub Actions OIDC build role for VelocityAI — ECR push/pull only, no SSM/KMS/EC2 reach. See docs/GITHUB_CICD_SETUP.md."
  assume_role_policy   = data.aws_iam_policy_document.github_build_assume[0].json
  permissions_boundary = var.deploy_permissions_boundary_arn != "" ? var.deploy_permissions_boundary_arn : null
  max_session_duration = 3600

  tags = merge(local.github_cicd_tags, {
    Name = "${var.github_cicd_role_name}-build"
    Role = "build"
  })
}

data "aws_iam_policy_document" "github_build" {
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
  # velocityai/frontend).
  #
  # DescribeImages is what makes a re-run of an already-built commit work
  # against IMMUTABLE tags: deploy.yml probes for the resolved tag first and,
  # when it already exists, reuses that image's digest instead of re-pushing
  # (which ECR would reject with ImagePushNotAllowedException). It is also how
  # the workflow turns a tag into the digest it actually deploys.
  statement {
    sid    = "ECRPushPull"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "ecr:DescribeImages",
      "ecr:PutImage",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
    ]
    resources = local.github_ecr_repo_arns
  }
}

resource "aws_iam_role_policy" "github_build" {
  count = var.create_github_oidc ? 1 : 0

  name   = "${var.github_cicd_role_name}-build-inline"
  role   = aws_iam_role.github_build[0].id
  policy = data.aws_iam_policy_document.github_build[0].json
}

# =============================================================================
# DEPLOY ROLES — one per environment, single-environment blast radius
# =============================================================================
# Trust: exactly ONE subject per role. `repo:<owner>/<repo>:environment:dev`
# cannot assume the stage or prod role, so a dev job holds credentials that
# have no name for a stage/prod parameter or instance in the first place.
data "aws_iam_policy_document" "github_deploy_assume" {
  for_each = local.github_env_set

  statement {
    sid     = "GitHubActionsOIDCDeploy"
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

    # StringEquals + a single value: this role is reachable ONLY from a job in
    # THIS repository running under THIS GitHub Environment (whose reviewer /
    # branch-and-tag protection rules are therefore load-bearing — see
    # docs/GITHUB_CICD_SETUP.md §3.1).
    condition {
      test     = "StringEquals"
      variable = "${local.github_oidc_url}:sub"
      values   = ["repo:${var.github_org_repo}:environment:${each.key}"]
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  for_each = local.github_env_set

  name                 = "${var.github_cicd_role_name}-${each.key}"
  description          = "GitHub Actions OIDC deploy role for VelocityAI ${each.key} — scoped to /velocityai/${each.key}/* and Environment=${each.key} instances only. See docs/GITHUB_CICD_SETUP.md."
  assume_role_policy   = data.aws_iam_policy_document.github_deploy_assume[each.key].json
  permissions_boundary = var.deploy_permissions_boundary_arn != "" ? var.deploy_permissions_boundary_arn : null
  max_session_duration = 3600

  tags = merge(local.github_cicd_tags, {
    Name        = "${var.github_cicd_role_name}-${each.key}"
    Role        = "deploy"
    Environment = each.key
  })
}

data "aws_iam_policy_document" "github_deploy" {
  for_each = local.github_env_set

  # Push config from GitHub vars/secrets → SSM, scoped to THIS environment's
  # prefix only. /velocityai/<other-env>/* is not in the Resource set, so it is
  # denied by default — not by a condition the caller has already satisfied.
  statement {
    sid       = "SSMPutParameters"
    effect    = "Allow"
    actions   = ["ssm:PutParameter"]
    resources = ["arn:${data.aws_partition.current.partition}:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/velocityai/${each.key}/*"]
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

    # Instance IDs are opaque, so the reachable target set is expressed as a
    # tag condition — pinned to THIS environment's single value. Even a wrong
    # EC2_INSTANCE_ID GitHub variable (or a hand-edited one) cannot deliver a
    # command to a box tagged for another environment: STS never issued this
    # session anything broader. Belt-and-braces with remote-deploy.sh §2,
    # which aborts on a host/deploy environment mismatch.
    condition {
      test     = "StringEquals"
      variable = "ssm:resourceTag/Environment"
      values   = [each.key]
    }
  }

  # Poll command status. GetCommandInvocation does not support resource-level
  # scoping. ssm:ListCommandInvocations was previously granted here too but
  # the workflow never calls it — removed to keep the surface minimal.
  # checkov:skip=CKV_AWS_356:ssm:GetCommandInvocation does not support resource-level scoping (AWS API constraint). Reviewed and accepted.
  statement {
    sid       = "SSMCommandStatus"
    effect    = "Allow"
    actions   = ["ssm:GetCommandInvocation"]
    resources = ["*"]
  }

  # Encrypt SSM SecureStrings on put. Encrypt ONLY: the workflow writes
  # parameters and never reads them back (the EC2 instance role decrypts, via
  # velocityai-load-secrets), so kms:Decrypt and kms:GenerateDataKey are not
  # part of this path and are no longer granted.
  #
  # NOTE ON PARAMETER TIER: standard-tier SecureStrings encrypt via kms:Encrypt.
  # ADVANCED-tier parameters use kms:GenerateDataKey instead — if deploy.yml
  # ever passes `--tier Advanced`, add that action here or the put will fail
  # with AccessDeniedException.
  #
  # Both conditions matter, and together they are what makes the broad key/*
  # fallback Resource safe:
  #   kms:ViaService  — the grant is usable only through SSM in this region,
  #                     never by calling KMS directly.
  #   kms:EncryptionContext:PARAMETER_ARN — SSM puts the parameter's own ARN in
  #                     the encryption context of every SecureString operation,
  #                     so pinning it to /velocityai/<this env>/* means a dev
  #                     role cannot encrypt a prod parameter even though the
  #                     prod CMK is inside its Resource set. This is the same
  #                     mechanism the EC2 instance role's decrypt path already
  #                     relies on (infra/terraform/policies/kms-decrypt.json),
  #                     chosen over kms:RequestAlias because the alias is not
  #                     dependably present once SSM resolves the key on the
  #                     caller's behalf, whereas the encryption context is.
  statement {
    sid       = "KMSEncryptSecureStringViaSSM"
    effect    = "Allow"
    actions   = ["kms:Encrypt"]
    resources = local.github_kms_key_arns

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${var.aws_region}.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "kms:EncryptionContext:PARAMETER_ARN"
      values   = ["arn:${data.aws_partition.current.partition}:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/velocityai/${each.key}/*"]
    }
  }
}

resource "aws_iam_role_policy" "github_deploy" {
  for_each = local.github_env_set

  name   = "${var.github_cicd_role_name}-${each.key}-inline"
  role   = aws_iam_role.github_deploy[each.key].id
  policy = data.aws_iam_policy_document.github_deploy[each.key].json
}

# --- Advisory: permissions boundary ----------------------------------------
# A boundary is strongly recommended in a shared AWS Organizations account
# (RUNBOOK.md §0). It is not forced, because a first-time bootstrap in a
# sandbox account legitimately has no boundary policy to point at yet — and
# hard-failing there would block the very apply that creates the roles. A
# `check` block surfaces it as a plan/apply WARNING instead of failing.
check "github_cicd_permissions_boundary" {
  assert {
    condition     = !var.create_github_oidc || var.deploy_permissions_boundary_arn != ""
    error_message = "deploy_permissions_boundary_arn is empty: the GitHub Actions build/deploy roles have no permissions boundary. RECOMMENDED in a shared account — scope a boundary to velocityai-* so these roles cannot touch non-project resources (see infra/terraform/RUNBOOK.md §0)."
  }
}
