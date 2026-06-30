# =============================================================================
# CI/CD bootstrap: shared GitLab connection + per-ENVIRONMENT CodeBuild projects.
# =============================================================================
# WHY THIS LIVES IN bootstrap/ (and not in the app pipeline):
#
#   The pipeline (shared -> foundation -> app) runs Terraform *inside*
#   CodeBuild. To do that, CodeBuild must already hold an IAM role with
#   permission to create the AWS resources. That role therefore cannot be
#   created by the very pipeline that depends on it — it is a chicken-and-egg,
#   like the S3 state bucket in main.tf. So it is bootstrapped ONCE, by a human
#   with elevated credentials, and every later pipeline run assumes it.
#
# ISOLATION MODEL (Option B — one build project per environment):
#
#   SHARED (created once):   GitLab connection, default GitLab source
#                            credential (AWS allows only one per account/region),
#                            the S3 state bucket + DynamoDB lock table (main.tf),
#                            and the ECR repositories (../shared). Images are
#                            built once and promoted by tag.
#
#   PER ENVIRONMENT (one each, via for_each over var.runners):
#                            an IAM deploy role, a CodeBuild build project with
#                            its own build env vars, a webhook with its own
#                            branch/tag/release filter, and a CloudWatch log group.
#
#   In a SINGLE AWS ACCOUNT this gives strong *logical* isolation: separate
#   identities/trust, separate triggers, separate audit trail, and per-env
#   scoping of everything AWS lets us scope by name (IAM app roles + instance
#   profiles, remote-state keys, build logs, SSM parameter paths, the env's
#   buckets). It is NOT hard isolation: the broad ProvisionStack permissions
#   (ec2/kms/route53/... can't be resource-scoped) and prod's bare "velocityai"
#   name prefix is a SUPERSET that also matches "velocityai-stage-*". True hard
#   isolation requires separate AWS accounts.
#
# RECOMMENDED HARDENING: attach an IAM permissions boundary scoped to
#   velocityai-* to each deploy role (var.deploy_permissions_boundary_arn) so
#   even the broad ProvisionStack statement cannot touch non-project resources.
#
# ONE-TIME MANUAL STEP (cannot be automated):
#   The GitLab CodeConnections connection is created here in PENDING state.
#   Finish the OAuth handshake once in the AWS console: Developer Tools >
#   Settings > Connections > select it > "Update pending connection". Until
#   then, the webhooks will not fire.
# =============================================================================

locals {
  cicd_tags = { Component = "cicd" }

  # Per-environment runners. Empty (no CI/CD resources) unless enabled — keeps a
  # "state backend only" bootstrap possible. Each key is an environment name
  # (dev|stage|prod); the whole runner stack is created per entry.
  runners = var.create_gitlab_runner ? var.runners : {}

  # Resource name prefix the foundation/app layers use per environment
  # (locals.tf: name_suffix = prod ? "" : "-<env>"). prod's bare "velocityai"
  # prefix is a SUPERSET that also matches "velocityai-stage-*"; hard exclusion
  # needs separate accounts (see the isolation note above / README).
  env_prefix = { for env in keys(local.runners) : env => env == "prod" ? "velocityai" : "velocityai-${env}" }

  # Project name kept in a stable velocityai-gitlab-runner-<branch> form so a
  # branch<->env remap doesn't destroy+recreate the project / webhook / log
  # group. Branch->env routing is done by the webhook filter, not this name;
  # the project injects ENVIRONMENT (= env key) itself.
  runner_project_name = { for env, cfg in local.runners : env => "velocityai-gitlab-runner-${cfg.branch}" }

  # HEAD_REF pattern for "tag" runners. GitLab webhooks have no TAG_NAME filter;
  # a tag push arrives as a PUSH whose head ref is refs/tags/<name>. Empty
  # tag_pattern = any tag (.*).
  runner_tag_ref_pattern = { for env, cfg in local.runners : env => "^refs/tags/${cfg.tag_pattern != "" ? cfg.tag_pattern : ".*"}$" }

  # Webhook filter group per runner, keyed by trigger_type (filters are AND-ed):
  #   branch  -> EVENT=PUSH     AND HEAD_REF ^refs/heads/<branch>$
  #   tag     -> EVENT=PUSH     AND HEAD_REF ^refs/tags/<pattern>$
  #   release -> EVENT=RELEASED (a GitLab Release create/update; any release).
  runner_filters = {
    for env, cfg in local.runners : env => (
      cfg.trigger_type == "release" ? [
        { type = "EVENT", pattern = "RELEASED" },
        ] : cfg.trigger_type == "tag" ? [
        { type = "EVENT", pattern = "PUSH" },
        { type = "HEAD_REF", pattern = local.runner_tag_ref_pattern[env] },
        ] : [
        { type = "EVENT", pattern = "PUSH" },
        { type = "HEAD_REF", pattern = "^refs/heads/${cfg.branch}$" },
      ]
    )
  }
}

# --- SHARED: GitLab connection (token-free; OAuth via CodeConnections) -------
# Preferred over a personal-access-token: no long-lived secret to store. One
# connection serves every per-env build project.
resource "aws_codestarconnections_connection" "gitlab" {
  count         = var.create_gitlab_runner ? 1 : 0
  name          = "velocityai-gitlab"
  provider_type = "GitLab"
  tags          = local.cicd_tags
}

# --- SHARED: default GitLab source credential (one per account/region) -------
# Registers the connection as CodeBuild's DEFAULT GitLab credential. AWS permits
# only one default credential per (auth_type, server_type), so it is inherently
# shared. The connection MUST be AVAILABLE (authorized once in the console)
# before this can be created.
resource "aws_codebuild_source_credential" "gitlab" {
  count       = var.create_gitlab_runner ? 1 : 0
  auth_type   = "CODECONNECTIONS"
  server_type = "GITLAB"
  token       = aws_codestarconnections_connection.gitlab[0].arn
}

# --- PER-ENV: trust policy — only THIS env's build project may assume --------
data "aws_iam_policy_document" "codebuild_assume" {
  for_each = local.runners

  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["codebuild.amazonaws.com"]
    }
    # Confused-deputy guard: only CodeBuild in THIS account.
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
    # Cross-env guard: only this environment's build project ARN may assume this
    # role, so the stage runner can never assume the prod role (and vice versa).
    # Built as a STRING (not a resource reference) to avoid a cycle with the
    # project's service_role.
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:${data.aws_partition.current.partition}:codebuild:${var.aws_region}:${data.aws_caller_identity.current.account_id}:project/${local.runner_project_name[each.key]}"]
    }
  }
}

resource "aws_iam_role" "codebuild_deploy" {
  for_each             = local.runners
  name                 = "velocityai-codebuild-deploy-${each.key}"
  description          = "Role the ${each.key} CodeBuild runner assumes to run the VelocityAI Terraform pipeline."
  assume_role_policy   = data.aws_iam_policy_document.codebuild_assume[each.key].json
  permissions_boundary = var.deploy_permissions_boundary_arn != "" ? var.deploy_permissions_boundary_arn : null
  tags                 = merge(local.cicd_tags, { Environment = each.key })
}

# --- PER-ENV: deploy permissions (scoped to this env wherever AWS allows) ----
# A DEPLOY role for a full-stack Terraform pipeline, so it is broad across the
# services the stack manages. It deliberately does NOT grant AdministratorAccess.
# Everything name-scopable to one environment is scoped (IAM app roles +
# instance profiles, remote-state keys, build logs, SSM parameter paths, the
# env's buckets); the rest stays broad and is the documented residual blast
# radius in a single account.
data "aws_iam_policy_document" "codebuild_deploy" {
  # checkov:skip=CKV_AWS_356:Full-stack IaC deploy role. Only the documented "ProvisionStack" statement uses Resource="*" (ec2/kms/logs/cloudwatch/sns/route53/backup/cloudtrail — actions that do not support meaningful resource scoping for Terraform's create/describe churn, or are global like Route 53). Everything name-scopable IS env-scoped. Residual blast radius is constrained via var.deploy_permissions_boundary_arn. Reviewed and accepted.
  # checkov:skip=CKV_AWS_111:Same as CKV_AWS_356 — write access on the broad ProvisionStack actions cannot be resource-constrained; mitigated by the permissions boundary. Reviewed and accepted.
  # checkov:skip=CKV_AWS_109:Same as CKV_AWS_356 — permissions-management/resource churn for a deploy role; env-scoped where possible, boundary-constrained otherwise. Reviewed and accepted.
  # checkov:skip=CKV_AWS_107:Deploy role reads SSM parameters under /velocityai/<env>/* (env-scoped) to manage app config; not a credentials-exposure path. Reviewed and accepted.
  for_each = local.runners

  # Remote state: this env's own keys + the SHARED layer's state key. Object
  # actions are env-scoped, so a stage pipeline cannot read or write prod state.
  statement {
    sid     = "TerraformStateObjects"
    actions = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = [
      "${aws_s3_bucket.tfstate.arn}/velocityai/${each.key}/*",
      "${aws_s3_bucket.tfstate.arn}/velocityai/shared.tfstate",
    ]
  }
  # ListBucket is required by the S3 backend; it only reveals key names (not
  # contents), so it stays at bucket scope while object reads stay env-scoped.
  statement {
    sid       = "TerraformStateList"
    actions   = ["s3:ListBucket", "s3:GetBucketVersioning"]
    resources = [aws_s3_bucket.tfstate.arn]
  }
  statement {
    sid       = "TerraformLocks"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem"]
    resources = [aws_dynamodb_table.tflock.arn]
  }

  # This env's own build logs only.
  statement {
    sid       = "BuildLogs"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:${data.aws_partition.current.partition}:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/codebuild/${local.runner_project_name[each.key]}*"]
  }

  # Use the shared GitLab connection for source checkout.
  statement {
    sid       = "UseConnection"
    actions   = ["codestar-connections:GetConnectionToken", "codestar-connections:GetConnection", "codestar-connections:UseConnection"]
    resources = [aws_codestarconnections_connection.gitlab[0].arn]
  }

  # ECR is SHARED (built once, promoted by tag) — every env's pipeline manages
  # the velocityai/* repositories. The auth token is account-level (no scope).
  statement {
    sid       = "EcrAuth"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    sid       = "EcrManageRepos"
    actions   = ["ecr:*"]
    resources = ["arn:${data.aws_partition.current.partition}:ecr:${var.aws_region}:${data.aws_caller_identity.current.account_id}:repository/velocityai/*"]
  }

  # SSM Parameter Store: this env's parameter tree only (/velocityai/<env>/*).
  statement {
    sid = "SsmParameters"
    actions = [
      "ssm:PutParameter", "ssm:GetParameter", "ssm:GetParameters",
      "ssm:GetParametersByPath", "ssm:DeleteParameter", "ssm:DeleteParameters",
      "ssm:AddTagsToResource", "ssm:RemoveTagsFromResource", "ssm:ListTagsForResource",
    ]
    resources = ["arn:${data.aws_partition.current.partition}:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/velocityai/${each.key}/*"]
  }

  # Provisioning the EC2/compose stack: networking, EIP, EBS, the EC2 instance,
  # KMS CMK, CloudWatch logs/alarms, SNS, Route 53, AWS Backup, Resource Groups,
  # CloudTrail (audit trail), and SSM RunCommand (the post-build redeploy).
  # Stays broad/`*`: these do not support meaningful resource scoping for the
  # create/describe churn Terraform performs, or (Route 53) are global. This is
  # the residual shared blast radius in a single account (see the isolation
  # note above). Tighten with var.deploy_permissions_boundary_arn.
  statement {
    sid = "ProvisionStack"
    actions = [
      "ec2:*", "kms:*", "logs:*", "cloudwatch:*", "sns:*",
      "route53:*", "backup:*", "backup-storage:*",
      "resource-groups:*", "tag:GetResources", "cloudtrail:*",
      "ssm:SendCommand", "ssm:GetCommandInvocation", "ssm:ListCommandInvocations",
      "ssm:DescribeInstanceInformation", "ssm:DescribeParameters",
      "ssm:StartSession", "ssm:TerminateSession",
    ]
    resources = ["*"]
  }

  # IAM: manage ONLY this environment's application roles + instance profiles,
  # name-prefix scoped, and PassRole only for those roles. A stage pipeline
  # cannot create or pass roles outside velocityai-stage-*.
  statement {
    sid = "ManageAppRoles"
    actions = [
      "iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:TagRole", "iam:UntagRole",
      "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:GetRolePolicy",
      "iam:AttachRolePolicy", "iam:DetachRolePolicy", "iam:ListRolePolicies",
      "iam:ListAttachedRolePolicies", "iam:CreateServiceLinkedRole", "iam:UpdateAssumeRolePolicy",
    ]
    resources = ["arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:role/${local.env_prefix[each.key]}-*"]
  }
  statement {
    sid = "ManageInstanceProfiles"
    actions = [
      "iam:CreateInstanceProfile", "iam:DeleteInstanceProfile", "iam:GetInstanceProfile",
      "iam:AddRoleToInstanceProfile", "iam:RemoveRoleFromInstanceProfile",
      "iam:TagInstanceProfile", "iam:ListInstanceProfilesForRole",
    ]
    resources = ["arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:instance-profile/${local.env_prefix[each.key]}-*"]
  }
  statement {
    sid       = "PassAppRoles"
    actions   = ["iam:PassRole"]
    resources = ["arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:role/${local.env_prefix[each.key]}-*"]
  }

  # S3 buckets the stack manages: this env's own velocityai(-<env>)-* buckets
  # (the pg-dumps backup bucket + the CloudTrail audit-trail bucket). Sub-resource
  # config actions are listed explicitly because their IAM action names are not
  # covered by s3:GetBucket*/s3:PutBucket* wildcards, and the aws_s3_bucket
  # provider reads them on every refresh.
  statement {
    sid = "StackBuckets"
    actions = [
      "s3:CreateBucket", "s3:DeleteBucket",
      "s3:PutBucket*", "s3:GetBucket*", "s3:ListBucket",
      "s3:PutEncryptionConfiguration", "s3:GetEncryptionConfiguration",
      "s3:GetLifecycleConfiguration", "s3:PutLifecycleConfiguration",
      "s3:GetReplicationConfiguration", "s3:GetAccelerateConfiguration",
      "s3:PutObject", "s3:GetObject", "s3:DeleteObject", "s3:GetObjectTagging", "s3:PutObjectTagging",
      "s3:GetObjectVersion", "s3:DeleteObjectVersion",
      "s3:GetBucketObjectLockConfiguration", "s3:PutBucketObjectLockConfiguration",
    ]
    resources = [
      "arn:${data.aws_partition.current.partition}:s3:::${local.env_prefix[each.key]}-*",
      "arn:${data.aws_partition.current.partition}:s3:::${local.env_prefix[each.key]}-*/*",
    ]
  }

  # Read the deploy-time identity (the buildspec calls sts:GetCallerIdentity).
  statement {
    sid       = "WhoAmI"
    actions   = ["sts:GetCallerIdentity"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "codebuild_deploy" {
  for_each = local.runners
  name     = "velocityai-codebuild-deploy-${each.key}"
  role     = aws_iam_role.codebuild_deploy[each.key].id
  policy   = data.aws_iam_policy_document.codebuild_deploy[each.key].json
}

# --- PER-ENV: build log group (retention is a per-env knob) ------------------
resource "aws_cloudwatch_log_group" "gitlab_runner" {
  for_each          = local.runners
  name              = "/aws/codebuild/${local.runner_project_name[each.key]}"
  retention_in_days = each.value.log_retention_days
  tags              = merge(local.cicd_tags, { Environment = each.key })
}

# --- PER-ENV: CodeBuild build project ----------------------------------------
# A GitLab webhook (below) triggers this project; it then runs
# infra/buildspec.yml end to end (validate -> security scan -> shared+foundation
# apply -> build/push backend+frontend images -> app apply -> SSM redeploy ->
# in-container Alembic migrations). ENVIRONMENT is injected here as the single
# source of truth and drives the buildspec's per-env tfvars / state key.
resource "aws_codebuild_project" "gitlab_runner" {
  for_each     = local.runners
  name         = local.runner_project_name[each.key]
  description  = each.value.trigger_type == "release" ? "VelocityAI CI/CD build for ${each.key} — a GitLab Release runs infra/buildspec.yml." : each.value.trigger_type == "tag" ? "VelocityAI CI/CD build for ${each.key} — a matching git TAG push runs infra/buildspec.yml." : "VelocityAI CI/CD build for ${each.key} — PUSH on ${each.value.branch} runs infra/buildspec.yml."
  service_role = aws_iam_role.codebuild_deploy[each.key].arn
  tags         = merge(local.cicd_tags, { Environment = each.key })

  artifacts {
    type = "NO_ARTIFACTS"
  }

  environment {
    compute_type    = each.value.compute_type
    image           = "aws/codebuild/amazonlinux2-x86_64-standard:5.0"
    type            = "LINUX_CONTAINER"
    privileged_mode = true # docker daemon for image builds

    # Variables consumed by infra/buildspec.yml, managed in Terraform so
    # `terraform apply` is the single source of truth (no console edits). The
    # base set merges with runners[<env>].extra_env. None are secrets — model
    # ids / origins / email only; real secrets (SECRET_KEY, DB password) are
    # auto-generated by the foundation secrets module into SSM SecureStrings.
    dynamic "environment_variable" {
      for_each = merge(
        {
          ENVIRONMENT                         = each.key
          TF_STATE_BUCKET                     = var.state_bucket_name
          TF_STATE_LOCK_TABLE                 = var.lock_table_name
          TF_VAR_cors_origins                 = each.value.cors_origins
          TF_VAR_bedrock_model_id             = each.value.bedrock_model_id
          TF_VAR_bedrock_inference_profile_id = each.value.bedrock_inference_profile_id
          TF_VAR_alert_email                  = each.value.alert_email
        },
        each.value.extra_env,
      )
      content {
        name  = environment_variable.key
        value = environment_variable.value
        type  = "PLAINTEXT"
      }
    }
  }

  source {
    type            = "GITLAB"
    location        = var.gitlab_repo_url
    git_clone_depth = 1
    # The buildspec lives under infra/, so the path must be explicit — otherwise
    # CodeBuild looks for ./buildspec.yml at the repo root and fails.
    buildspec = "infra/buildspec.yml"
  }

  logs_config {
    cloudwatch_logs {
      group_name = aws_cloudwatch_log_group.gitlab_runner[each.key].name
    }
  }
}

# --- PER-ENV: webhook — triggers this env's build (branch push, tag, or Release)
resource "aws_codebuild_webhook" "gitlab_runner" {
  for_each     = local.runners
  project_name = aws_codebuild_project.gitlab_runner[each.key].name
  build_type   = "BUILD"

  # The webhook binds to the shared GitLab connection via the default source
  # credential, so that must exist (and be authorized) first.
  depends_on = [aws_codebuild_source_credential.gitlab]

  filter_group {
    dynamic "filter" {
      for_each = local.runner_filters[each.key]
      content {
        type    = filter.value.type
        pattern = filter.value.pattern
      }
    }
  }
}
