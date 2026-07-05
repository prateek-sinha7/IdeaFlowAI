data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_partition" "current" {}

locals {
  # The account this bootstrap targets. When `expected_account_id` is left
  # blank (the default), we adopt whatever account the AWS CLI / provider is
  # currently authenticated to — i.e. the live `aws sts get-caller-identity`
  # account. Set `expected_account_id` explicitly to turn the guard below into
  # a hard pin that refuses to apply against any other account.
  effective_account_id = var.expected_account_id != "" ? var.expected_account_id : data.aws_caller_identity.current.account_id
}

# Account-id guard. Refuses to operate against the wrong account.
#
# By default (`expected_account_id = ""`) the guard adopts the live caller
# account, so this is a no-op that simply records the account it ran against.
# Pin `expected_account_id` to a concrete 12-digit id to make it abort on any
# mismatch — recommended in shared / multi-account org setups.
resource "terraform_data" "account_guard" {
  input = {
    actual_account_id   = data.aws_caller_identity.current.account_id
    expected_account_id = local.effective_account_id
    actual_region       = data.aws_region.current.name
    expected_region     = var.aws_region
  }

  lifecycle {
    precondition {
      condition     = data.aws_caller_identity.current.account_id == local.effective_account_id
      error_message = "Account mismatch: provider authenticated to ${data.aws_caller_identity.current.account_id}, expected ${local.effective_account_id}. Refusing to apply."
    }

    precondition {
      condition     = data.aws_region.current.name == var.aws_region
      error_message = "Region mismatch: provider region is ${data.aws_region.current.name}, expected ${var.aws_region}. Refusing to apply."
    }
  }
}

# --- Bootstrap CMK ---------------------------------------------------------
#
# A small, bootstrap-local KMS key used to encrypt:
#   - the Terraform state bucket (`aws_s3_bucket_server_side_encryption_configuration.tfstate`)
#   - the DynamoDB state-lock table (`aws_dynamodb_table.tflock.server_side_encryption`)
#
# Why a dedicated key rather than the project CMK that `modules/kms` creates
# downstream of bootstrap? Because bootstrap MUST be runnable against an empty
# account; the project CMK doesn't exist until the foundation layer applies,
# which in turn needs this state backend already present. Chicken-and-egg.
#
# Key policy: AWS-account root principal is the sole grantee — anyone whose
# IAM policy grants `kms:*` on this key (the Terraform operator role(s)) can
# use it. S3 and DynamoDB authorize through the caller's principal, so we
# don't need explicit service grants.
#
# Rotation is enabled; deletion window is 30 days (max) so an accidental
# `terraform destroy` of the key can be recovered.
resource "aws_kms_key" "bootstrap" {
  description             = "VelocityAI Terraform bootstrap CMK (state bucket + DynamoDB lock table)."
  deletion_window_in_days = 30
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "EnableRootAccountAccess"
        Effect    = "Allow"
        Principal = { AWS = "arn:${data.aws_partition.current.partition}:iam::${local.effective_account_id}:root" }
        Action    = "kms:*"
        Resource  = "*"
      }
    ]
  })

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [terraform_data.account_guard]
}

resource "aws_kms_alias" "bootstrap" {
  name          = "alias/velocityai-tfstate"
  target_key_id = aws_kms_key.bootstrap.key_id
}

# --- State bucket -----------------------------------------------------------

resource "aws_s3_bucket" "tfstate" {
  bucket = var.state_bucket_name

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [terraform_data.account_guard]
}

resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.bootstrap.arn
    }
    bucket_key_enabled = true
  }
}

# Bucket-scoped public-access block (NOT the account-level one — that is forbidden).
resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_policy" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.tfstate.arn,
          "${aws_s3_bucket.tfstate.arn}/*"
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })

  depends_on = [aws_s3_bucket_public_access_block.tfstate]
}

# --- Lock table -------------------------------------------------------------

resource "aws_dynamodb_table" "tflock" {
  name         = var.lock_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.bootstrap.arn
  }

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [terraform_data.account_guard]
}
