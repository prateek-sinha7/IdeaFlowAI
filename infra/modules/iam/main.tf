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
}

# --- Inline policies, rendered from templates -------------------------------

resource "aws_iam_role_policy" "bedrock_invoke" {
  name = "${var.name_prefix}-bedrock-invoke"
  role = aws_iam_role.instance.id

  policy = templatefile("${path.module}/${var.policies_dir}/bedrock-invoke.json", {
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
    region      = var.region
    account_id  = var.account_id
    environment = var.environment
  })
}

resource "aws_iam_role_policy" "kms_decrypt" {
  name = "${var.name_prefix}-kms-decrypt"
  role = aws_iam_role.instance.id

  policy = templatefile("${path.module}/${var.policies_dir}/kms-decrypt.json", {
    kms_key_arn = var.kms_key_arn
  })
}

resource "aws_iam_role_policy" "cloudwatch_write" {
  name = "${var.name_prefix}-cloudwatch-write"
  role = aws_iam_role.instance.id

  policy = templatefile("${path.module}/${var.policies_dir}/cloudwatch-write.json", {
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

# --- The CloudWatch Agent needs a couple of describe + metric-put actions ---
# These cannot be scoped down (per AWS docs); kept as a small, separate
# policy so they're easy to audit on their own.
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
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# --- Instance profile -------------------------------------------------------

resource "aws_iam_instance_profile" "instance" {
  name = "${var.name_prefix}-instance"
  role = aws_iam_role.instance.name

  tags = {
    Name      = "${var.name_prefix}-instance"
    Component = "iam"
  }
}
