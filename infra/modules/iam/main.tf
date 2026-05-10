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
  description = "Flowin EC2 instance profile role (Bedrock invoke, SSM read, KMS decrypt, CW logs, S3 backup)."

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

resource "aws_iam_role_policy" "bedrock_invoke" {
  name = "${var.name_prefix}-bedrock-invoke"
  role = aws_iam_role.instance.id

  # The bedrock-invoke.json policy includes an `aws:RequestedRegion` condition
  # pinning invocation to the EU regions the cross-region inference profile
  # fans to. The list is hardcoded in the JSON (eu-central-1, eu-west-1,
  # eu-west-2). If AWS adds another EU region to the EU profile, update
  # the list there. See:
  #   https://docs.aws.amazon.com/bedrock/latest/userguide/cross-region-inference.html
  policy = templatefile("${path.module}/${var.policies_dir}/bedrock-invoke.json", {
    partition            = data.aws_partition.current.partition
    region               = var.region
    account_id           = var.account_id
    model_id             = var.bedrock_model_id
    inference_profile_id = var.bedrock_inference_profile_id
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
# /opt/flowin/docker-compose.yml from s3://<bucket>/config/docker-compose.yml,
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
