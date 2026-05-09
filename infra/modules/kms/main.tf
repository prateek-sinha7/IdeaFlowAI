data "aws_partition" "current" {}

locals {
  partition = data.aws_partition.current.partition
}

# Customer-managed CMK used for: EBS data volume, S3 backup bucket SSE,
# AWS Backup vault, and SSM Parameter Store SecureStrings.
resource "aws_kms_key" "this" {
  description             = "${var.name_prefix} project key (EBS data, S3 backups, SSM SecureStrings, Backup vault)"
  deletion_window_in_days = var.deletion_window_in_days
  enable_key_rotation     = true
  key_usage               = "ENCRYPT_DECRYPT"
  customer_master_key_spec = "SYMMETRIC_DEFAULT"
  multi_region            = false

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [
        {
          Sid    = "EnableRootAccountAdmin"
          Effect = "Allow"
          Principal = {
            AWS = "arn:${local.partition}:iam::${var.account_id}:root"
          }
          Action   = "kms:*"
          Resource = "*"
        },
        {
          Sid    = "AllowEbsAttachmentViaServiceLinkedRole"
          Effect = "Allow"
          Principal = {
            AWS = "arn:${local.partition}:iam::${var.account_id}:root"
          }
          Action = [
            "kms:CreateGrant",
            "kms:ListGrants",
            "kms:RevokeGrant"
          ]
          Resource = "*"
          Condition = {
            Bool = {
              "kms:GrantIsForAWSResource" = "true"
            }
          }
        }
      ],
      var.allow_logs_service ? [
        {
          Sid    = "AllowCloudWatchLogs"
          Effect = "Allow"
          Principal = {
            Service = "logs.${var.region}.amazonaws.com"
          }
          Action = [
            "kms:Encrypt*",
            "kms:Decrypt*",
            "kms:ReEncrypt*",
            "kms:GenerateDataKey*",
            "kms:Describe*"
          ]
          Resource = "*"
          Condition = {
            ArnLike = {
              "kms:EncryptionContext:aws:logs:arn" = "arn:${local.partition}:logs:${var.region}:${var.account_id}:log-group:/flowin/*"
            }
          }
        }
      ] : [],
      var.allow_sns_service ? [
        {
          Sid    = "AllowSns"
          Effect = "Allow"
          Principal = {
            Service = "sns.amazonaws.com"
          }
          Action = [
            "kms:Decrypt",
            "kms:GenerateDataKey"
          ]
          Resource = "*"
        }
      ] : [],
      var.allow_s3_service ? [
        {
          Sid    = "AllowS3WithinAccount"
          Effect = "Allow"
          Principal = {
            Service = "s3.amazonaws.com"
          }
          Action = [
            "kms:Decrypt",
            "kms:GenerateDataKey"
          ]
          Resource = "*"
          Condition = {
            StringEquals = {
              "aws:SourceAccount" = var.account_id
            }
          }
        }
      ] : [],
      var.allow_backup_service ? [
        {
          Sid    = "AllowAwsBackup"
          Effect = "Allow"
          Principal = {
            Service = "backup.amazonaws.com"
          }
          Action = [
            "kms:Decrypt",
            "kms:Encrypt",
            "kms:GenerateDataKey",
            "kms:DescribeKey",
            "kms:CreateGrant"
          ]
          Resource = "*"
          Condition = {
            StringEquals = {
              "aws:SourceAccount" = var.account_id
            }
          }
        }
      ] : [],
      [
        for principal in var.additional_principals : {
          Sid    = "AllowAdditionalPrincipal${replace(replace(replace(principal, ":", ""), "/", ""), "-", "")}"
          Effect = "Allow"
          Principal = {
            AWS = principal
          }
          Action = [
            "kms:Decrypt",
            "kms:Encrypt",
            "kms:GenerateDataKey",
            "kms:GenerateDataKeyWithoutPlaintext",
            "kms:ReEncryptFrom",
            "kms:ReEncryptTo",
            "kms:DescribeKey"
          ]
          Resource = "*"
        }
      ]
    )
  })

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Name      = "${var.name_prefix}-key"
    Component = "iam"
  }
}

resource "aws_kms_alias" "this" {
  name          = "alias/${var.name_prefix}"
  target_key_id = aws_kms_key.this.key_id
}
