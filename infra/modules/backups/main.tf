data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_region" "current" {}

# --- S3 backup bucket -------------------------------------------------------

resource "aws_s3_bucket" "backups" {
  bucket = var.bucket_name

  tags = {
    Name      = var.bucket_name
    Component = "storage"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_ownership_controls" "backups" {
  bucket = aws_s3_bucket.backups.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "backups" {
  bucket = aws_s3_bucket.backups.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Bucket-scoped public-access block (NOT the account-level one — forbidden).
resource "aws_s3_bucket_public_access_block" "backups" {
  bucket = aws_s3_bucket.backups.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "backups" {
  bucket = aws_s3_bucket.backups.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "backups" {
  bucket = aws_s3_bucket.backups.id

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"

    filter {} # apply to whole bucket

    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_version_expiration_days
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  rule {
    id     = "transition-pg-dumps-to-glacier-ir"
    status = "Enabled"

    filter {
      prefix = "postgres/"
    }

    transition {
      days          = var.transition_to_glacier_ir_days
      storage_class = "GLACIER_IR"
    }
  }
}

resource "aws_s3_bucket_policy" "backups" {
  bucket = aws_s3_bucket.backups.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.backups.arn,
          "${aws_s3_bucket.backups.arn}/*"
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      },
      {
        Sid       = "DenyUnencryptedPuts"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.backups.arn}/*"
        Condition = {
          StringNotEquals = {
            "s3:x-amz-server-side-encryption" = "aws:kms"
          }
        }
      },
      {
        Sid       = "DenyWrongKmsKey"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.backups.arn}/*"
        Condition = {
          StringNotEqualsIfExists = {
            "s3:x-amz-server-side-encryption-aws-kms-key-id" = var.kms_key_arn
          }
        }
      }
    ]
  })

  depends_on = [aws_s3_bucket_public_access_block.backups]
}

# --- AWS Backup service role -----------------------------------------------

data "aws_iam_policy_document" "backup_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["backup.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "backup" {
  name        = "${var.name_prefix}-backup-service"
  description = "AWS Backup service role for the Flowin backup vault."

  assume_role_policy = data.aws_iam_policy_document.backup_assume.json

  tags = {
    Name      = "${var.name_prefix}-backup-service"
    Component = "iam"
  }
}

resource "aws_iam_role_policy_attachment" "backup_managed" {
  role       = aws_iam_role.backup.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AWSBackupServiceRolePolicyForBackup"
}

resource "aws_iam_role_policy_attachment" "backup_managed_restore" {
  role       = aws_iam_role.backup.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AWSBackupServiceRolePolicyForRestores"
}

# --- Backup vault -----------------------------------------------------------

resource "aws_backup_vault" "this" {
  name        = "${var.name_prefix}-vault"
  kms_key_arn = var.kms_key_arn

  tags = {
    Name      = "${var.name_prefix}-vault"
    Component = "storage"
  }

  lifecycle {
    prevent_destroy = true
  }
}

# --- Backup plan ------------------------------------------------------------

resource "aws_backup_plan" "daily" {
  name = "${var.name_prefix}-daily"

  rule {
    rule_name           = "DailyAt03UTC"
    target_vault_name   = aws_backup_vault.this.name
    schedule            = var.backup_schedule_cron
    start_window        = 60
    completion_window   = 240
    enable_continuous_backup = false

    lifecycle {
      delete_after = var.daily_backup_retention_days
    }

    recovery_point_tags = {
      Project     = "flowin"
      Environment = var.environment
      Component   = "storage"
    }
  }

  tags = {
    Name      = "${var.name_prefix}-daily"
    Component = "storage"
  }
}

# --- Backup selection: tag-based -------------------------------------------

resource "aws_backup_selection" "by_tag" {
  name         = "${var.name_prefix}-by-tag"
  iam_role_arn = aws_iam_role.backup.arn
  plan_id      = aws_backup_plan.daily.id

  selection_tag {
    type  = "STRINGEQUALS"
    key   = var.backup_selection_tag_key
    value = var.backup_selection_tag_value
  }
}
