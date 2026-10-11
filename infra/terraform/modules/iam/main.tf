# Partition lookup so AWS-managed policy ARNs are portable across `aws`,
# `aws-cn`, `aws-us-gov`. Other modules (kms, backups, monitoring) already
# follow this idiom; the IAM module had a hardcoded `arn:aws:...` string for
# the SSM managed policy, fixed below. No functional change in `aws`.
data "aws_partition" "current" {}

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    sid     = "AllowEC2Assume"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "instance" {
  name        = "${var.name_prefix}-instance"
  description = "VelocityAI EC2 instance profile role (Bedrock invoke, SSM read, KMS decrypt, CW logs, S3 backup)."

  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json

  tags = {
    Name      = "${var.name_prefix}-instance"
    Component = "iam"
  }

  lifecycle {
    # Recreating the instance role detaches the running EC2 instance from its
    # IAM identity (the AmazonSSMManagedInstanceCore + bedrock-invoke + ssm-read
    # paths all break) and operators have to roll the instance to recover.
    # The literal `true` is fine — there's no env-specific override path. If
    # an operator genuinely needs to delete in localstack they can
    # `terraform state rm` first, but in practice destroy.sh tears the whole
    # stack down without going through `terraform destroy` for the role
    # alone, so the question never comes up.
    prevent_destroy = true
  }
}

# --- Inline policies, rendered from templates -------------------------------

# --- Bedrock invoke scope ---------------------------------------------------
#
# The role may invoke EVERY model the application can select, not just the
# default one: `model_catalog.py` lets a run pick any catalogued model, and a
# model that is not in this grant fails at runtime with AccessDeniedException.
# The allow-list is expressed as inference-profile IDs only — the underlying
# foundation-model IDs are DERIVED by stripping the CRIS geography prefix, so
# there is no second hand-maintained list to drift.
#
# Why both resource shapes are needed for one call: the SDK passes the profile
# ID as `modelId`, and Bedrock authorizes the profile ARN *and* the foundation
# model in each destination region the profile can route to. Granting only one
# of the two yields a 403 that names the other.
locals {
  # Profiles the role may name as `modelId`. The scalar var is the app's active
  # profile (SSM `llm/inference_profile_id`); the list is everything else the
  # catalog can select.
  bedrock_profile_ids = distinct(compact(concat(
    [var.bedrock_inference_profile_id],
    var.bedrock_allowed_inference_profile_ids,
  )))

  # `eu.anthropic.claude-opus-4-5-…` -> `anthropic.claude-opus-4-5-…`,
  # `global.openai.gpt-6-sol`        -> `openai.gpt-6-sol`.
  # Foundation-model ARNs never carry the geography prefix; inference-profile
  # ARNs always do.
  bedrock_foundation_model_ids = distinct(compact(concat(
    [var.bedrock_model_id],
    [
      for profile_id in local.bedrock_profile_ids :
      replace(profile_id, "/^(eu|us|apac|global)\\./", "")
    ],
  )))

  # Region segment is `*`, not `${var.region}`: a cross-region profile routes to
  # destination regions the caller never names, and authorization happens
  # against the foundation model in THOSE regions. The previous region-pinned
  # duplicate of this ARN was a strict subset of the wildcard form and is
  # dropped. Blast radius stays bounded by the `aws:RequestedRegion` condition
  # (the regions the principal may CALL) plus the exact model-ID list.
  bedrock_foundation_model_arns = [
    for model_id in local.bedrock_foundation_model_ids :
    "arn:${data.aws_partition.current.partition}:bedrock:*::foundation-model/${model_id}"
  ]

  bedrock_inference_profile_arns = [
    for profile_id in local.bedrock_profile_ids :
    "arn:${data.aws_partition.current.partition}:bedrock:*:${var.account_id}:inference-profile/${profile_id}"
  ]

  # OpenAI (GPT) models on the bedrock-runtime endpoint additionally authorize
  # against the account's default project — `bedrock:InvokeModel` must be
  # allowed on `project/default` in the calling region or the request is denied
  # even when the profile and foundation model are both granted. Only added when
  # an `openai.` model is actually in scope, so a Claude-only deployment keeps
  # the exact grant it has today.
  #   https://docs.aws.amazon.com/bedrock/latest/userguide/projects.html
  bedrock_openai_in_scope = length([
    for profile_id in local.bedrock_profile_ids :
    profile_id if can(regex("(^|\\.)openai\\.", profile_id))
  ]) > 0

  bedrock_project_arns = (
    local.bedrock_openai_in_scope
    ? ["arn:${data.aws_partition.current.partition}:bedrock:${var.region}:${var.account_id}:project/default"]
    : []
  )
}

resource "aws_iam_role_policy" "bedrock_invoke" {
  name = "${var.name_prefix}-bedrock-invoke"
  role = aws_iam_role.instance.id

  # The `aws:RequestedRegion` condition pins invocation to the regions the role
  # may call Bedrock FROM (default: the 7 EU regions — see
  # `bedrock_allowed_request_regions`). It does NOT bound where a cross-region
  # profile may route to; that is a property of the profile itself. See:
  #   https://docs.aws.amazon.com/bedrock/latest/userguide/cross-region-inference.html
  policy = templatefile("${path.module}/${var.policies_dir}/bedrock-invoke.json", {
    invoke_resources = jsonencode(concat(
      local.bedrock_foundation_model_arns,
      local.bedrock_inference_profile_arns,
      local.bedrock_project_arns,
    ))
    inference_profile_arns  = jsonencode(local.bedrock_inference_profile_arns)
    allowed_request_regions = jsonencode(var.bedrock_allowed_request_regions)
  })
}

resource "aws_iam_role_policy" "ssm_read" {
  name = "${var.name_prefix}-ssm-read"
  role = aws_iam_role.instance.id

  policy = templatefile("${path.module}/${var.policies_dir}/ssm-read.json", {
    partition   = data.aws_partition.current.partition
    region      = var.region
    account_id  = var.account_id
    environment = var.environment
  })
}

resource "aws_iam_role_policy" "kms_decrypt" {
  name = "${var.name_prefix}-kms-decrypt"
  role = aws_iam_role.instance.id

  # kms-decrypt.json is split into four narrowly-scoped statements
  # (SSM SecureStrings via PARAMETER_ARN encryption context; EBS via
  # ec2.<region>.amazonaws.com ViaService; S3 backup via s3.<region>.amazonaws.com
  # ViaService; CloudWatch Logs via logs.<region>.amazonaws.com ViaService and
  # the aws:logs:arn encryption context). All four statements need
  # region/account_id/environment for ARN composition.
  policy = templatefile("${path.module}/${var.policies_dir}/kms-decrypt.json", {
    partition   = data.aws_partition.current.partition
    kms_key_arn = var.kms_key_arn
    region      = var.region
    account_id  = var.account_id
    environment = var.environment
  })
}

# The CloudWatch Agent's log delivery needs CreateLogStream + PutLogEvents
# (both scoped to log-stream ARNs and matched by the log-group prefix wildcard),
# plus DescribeLogStreams (scoped to log-group, not used by the modern agent).
#
# Deliberately NOT granted (do not re-add without re-reading this):
#
#   logs:DescribeLogGroups — the action has NO resource type in AWS IAM Service
#     Reference (no "Resources" entry), so it can only ever be granted with
#     Resource "*". Previously present here scoped to /velocityai/<env>/* ARN,
#     which made it a silent no-op (IAM accepts it but never matches). Agent
#     only calls it if target.Retention > 0 (pusher/target.go:79), and no
#     collect_list entry in bootstrap-ec2.sh sets retention_in_days — Terraform
#     owns retention (modules/monitoring/main.tf:44). If that ever changes, BOTH
#     DescribeLogGroups AND PutRetentionPolicy become needed, both on Resource
#     "*". See B3 (prevents retention in collect_list) and B4 (agent log
#     visibility) for the safety net. Deleted per FIX-144 least-privilege fix.
#
#   logs:CreateLogGroup — Terraform pre-creates all seven log groups with
#     prevent_destroy (modules/monitoring/main.tf:15-23). Agent only calls
#     CreateLogGroup on ResourceNotFoundException from CreateLogStream, which
#     cannot happen while Terraform owns the groups.
#
# The metric/describe half of the agent (CloudWatch PutMetricData + EC2
# Describe*) lives in the separate cwagent-describe policy below (line 157)
# — see that comment for the same rule applied to actions with no resource types.
resource "aws_iam_role_policy" "cloudwatch_write" {
  name = "${var.name_prefix}-cloudwatch-write"
  role = aws_iam_role.instance.id

  policy = templatefile("${path.module}/${var.policies_dir}/cloudwatch-write.json", {
    partition   = data.aws_partition.current.partition
    region      = var.region
    account_id  = var.account_id
    environment = var.environment
  })
}

resource "aws_iam_role_policy" "s3_backup_rw" {
  name = "${var.name_prefix}-s3-backup-rw"
  role = aws_iam_role.instance.id

  policy = templatefile("${path.module}/${var.policies_dir}/s3-backup-rw.json", {
    bucket_arn = var.backup_bucket_arn
  })
}

# Read-only on `config/*` of the same bucket. Bootstrap script downloads
# /opt/velocityai/docker-compose.yml from s3://<bucket>/config/docker-compose.yml,
# uploaded by Terraform (envs/prod/main.tf aws_s3_object.compose_yaml).
# Kept distinct from s3_backup_rw so that policy can stay strictly write-only.
resource "aws_iam_role_policy" "s3_config_read" {
  name = "${var.name_prefix}-s3-config-read"
  role = aws_iam_role.instance.id

  policy = templatefile("${path.module}/${var.policies_dir}/s3-config-read.json", {
    bucket_arn = var.backup_bucket_arn
  })
}

# ECR pull. Two statements:
#   1) ecr:GetAuthorizationToken on Resource "*" — required by AWS, the API
#      doesn't accept a scoped Resource. This grants a short-lived token
#      usable against any registry in the account; we accept that.
#   2) Pull-action verbs scoped to exactly two repository ARNs derived from
#      name_prefix (NOT from the ecr module outputs — that would close a
#      cycle: iam reads ecr.repository_arns AND ecr reads iam.instance_role_arn
#      for its repo policy Principal). name_prefix is known statically at
#      plan time so reconstructing the ARNs here is safe.
resource "aws_iam_role_policy" "ecr_pull" {
  name = "${var.name_prefix}-ecr-pull"
  role = aws_iam_role.instance.id

  policy = templatefile("${path.module}/${var.policies_dir}/ecr-pull.json", {
    partition   = data.aws_partition.current.partition
    region      = var.region
    account_id  = var.account_id
    name_prefix = var.name_prefix
  })
}

# --- The CloudWatch Agent needs a couple of describe + metric-put actions ---
# These cannot be scoped down by Resource (per AWS docs — the APIs don't
# accept resource-level scoping). Kept as a small, separate policy so they're
# easy to audit on their own. The `aws:RequestedRegion` condition bounds the
# blast radius to the deploy region so a stolen instance credential can't
# be replayed against another region's CloudWatch / EC2 metadata.
data "aws_iam_policy_document" "cw_agent_describes" {
  statement {
    sid    = "CloudWatchAgentMetricPut"
    effect = "Allow"
    actions = [
      "cloudwatch:PutMetricData",
      "ec2:DescribeTags",
      "ec2:DescribeVolumes"
    ]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.region]
    }
  }
}

resource "aws_iam_role_policy" "cw_agent" {
  name   = "${var.name_prefix}-cwagent-describe"
  role   = aws_iam_role.instance.id
  policy = data.aws_iam_policy_document.cw_agent_describes.json
}

# --- Host capacity matrix + admission gate (specs/014) ----------------------
# The background poller (app/services/host_metrics.py) needs to read the
# CloudWatch Agent's own custom metrics back (cloudwatch:GetMetricData) and
# discover the fleet by tag (ec2:DescribeInstances) when
# HOST_CAPACITY_INSTANCE_IDS is not set. Same shape as cw_agent_describes
# above: neither action supports resource-level ARNs (Resource "*" is the
# only form IAM accepts for them), so the `aws:RequestedRegion` condition is
# the only blast-radius control available — bounds a stolen instance
# credential to this deploy region, same as the agent's own describe policy.
data "aws_iam_policy_document" "capacity_read" {
  statement {
    sid    = "HostCapacityRead"
    effect = "Allow"
    actions = [
      "cloudwatch:GetMetricData",
      "ec2:DescribeInstances"
    ]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.region]
    }
  }
}

resource "aws_iam_role_policy" "capacity_read" {
  name   = "${var.name_prefix}-capacity-read"
  role   = aws_iam_role.instance.id
  policy = data.aws_iam_policy_document.capacity_read.json
}

# --- Cognito admin (Cognito-only auth migration Phase 3) -------------------
# Scoped to exactly one pool ARN (least privilege — never Resource "*").
#
# UNCONDITIONAL as of Phase 3 (".kiro/specs/login/prompt.md": "remove the
# count gate (Cognito is mandatory)"). Cognito is the sole authentication
# authority now — every environment that runs this application needs this
# policy, so a plan-time opt-out no longer describes a real deployment
# topology; every dev/stage/prod.tfvars already sets `cognito_enabled = true`.
# The `cognito_enabled`/`cognito_user_pool_arn` VARIABLES stay for now (Phase 4
# removes them at the foundation level, per the brief's own phase split) —
# only the count gate on THIS resource is removed here, so the ARN plumbing
# one layer up does not have to change in the same commit that fixes the
# grant list.
resource "aws_iam_role_policy" "cognito_admin" {
  name = "${var.name_prefix}-cognito-admin"
  role = aws_iam_role.instance.id

  policy = templatefile("${path.module}/${var.policies_dir}/cognito-admin.json", {
    user_pool_arn = var.cognito_user_pool_arn
  })
}

# --- Optional: AWS-managed SSM core for Session Manager --------------------

resource "aws_iam_role_policy_attachment" "ssm_managed" {
  count = var.attach_ssm_managed_policy ? 1 : 0

  role       = aws_iam_role.instance.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# --- Instance profile -------------------------------------------------------

resource "aws_iam_instance_profile" "instance" {
  name = "${var.name_prefix}-instance"
  role = aws_iam_role.instance.name

  tags = {
    Name      = "${var.name_prefix}-instance"
    Component = "iam"
  }

  lifecycle {
    # Same reasoning as aws_iam_role.instance — the instance profile is the
    # actual handle EC2 holds. Recreating it forces a stop/start of the EC2
    # instance (the profile name on the EC2 is a hard identity, not a
    # reference) and breaks every credentials path until the new profile
    # propagates. Hard-coded `true`; localstack lifecycle is destroy.sh.
    prevent_destroy = true
  }
}

# --- Exclusive lists: drift detection on policy attachments ----------------
#
# Provider 5.62+ supplies `aws_iam_role_policies_exclusive` (inline policies)
# and `aws_iam_role_policy_attachments_exclusive` (managed-policy
# attachments). Both lock the set: an out-of-band attachment by an operator
# (or another stack) shows up as drift on next plan, and the next apply will
# REMOVE it. That's the trade-off: we get sealed-set guarantees, but anyone
# adding a new aws_iam_role_policy.X to this module MUST add its name to the
# inline list below or apply will silently delete it. Same hazard for
# managed policies. Treat both lists as "the source of truth" for what hangs
# off this role.
#
# Provider versions: see modules/iam/versions.tf (`~> 5.70`).

resource "aws_iam_role_policies_exclusive" "instance" {
  role_name = aws_iam_role.instance.name
  policy_names = [
    aws_iam_role_policy.bedrock_invoke.name,
    aws_iam_role_policy.ssm_read.name,
    aws_iam_role_policy.kms_decrypt.name,
    aws_iam_role_policy.cloudwatch_write.name,
    aws_iam_role_policy.s3_backup_rw.name,
    aws_iam_role_policy.s3_config_read.name,
    aws_iam_role_policy.ecr_pull.name,
    aws_iam_role_policy.cw_agent.name,
    aws_iam_role_policy.capacity_read.name,
    # cognito_admin is unconditional as of Phase 3 (no longer count-guarded).
    aws_iam_role_policy.cognito_admin.name,
  ]
}

resource "aws_iam_role_policy_attachments_exclusive" "instance" {
  role_name = aws_iam_role.instance.name
  # When attach_ssm_managed_policy is false the role has no managed
  # attachments — supply an empty list. Provider accepts this and enforces
  # "exactly zero managed-policy attachments allowed".
  policy_arns = (
    var.attach_ssm_managed_policy
    ? ["arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonSSMManagedInstanceCore"]
    : []
  )
}
