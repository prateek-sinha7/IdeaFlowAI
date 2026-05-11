data "aws_partition" "current" {}

locals {
  partition = data.aws_partition.current.partition
}

# Customer-managed CMK used for: EBS data volume, S3 backup bucket SSE,
# AWS Backup vault, and SSM Parameter Store SecureStrings.
resource "aws_kms_key" "this" {
  description              = "${var.name_prefix} project key (EBS data, S3 backups, SSM SecureStrings, Backup vault)"
  deletion_window_in_days  = var.deletion_window_in_days
  enable_key_rotation      = true
  key_usage                = "ENCRYPT_DECRYPT"
  customer_master_key_spec = "SYMMETRIC_DEFAULT"
  multi_region             = false

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
          # Confused-deputy guard — symmetric with the S3 and Backup
          # statements below. Without aws:SourceAccount, any AWS account's
          # SNS topic could (in principle) ask this KMS key to decrypt or
          # generate-data-key on its behalf; the SourceAccount pin forces
          # the caller to be in our own account.
          Condition = {
            StringEquals = {
              "aws:SourceAccount" = var.account_id
            }
          }
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
          # Confused-deputy defence:
          #   - aws:SourceAccount   pins to *our* account (cross-account
          #     attacker can't trick AWS Backup into using this grant).
          #   - aws:SourceArn       narrows further to backup vaults in our
          #     account+region. Wildcard at the vault-name end is intentional:
          #     the kms module doesn't know the vault name (and pinning it
          #     would close a circular dependency: kms -> backups -> kms).
          #     aws:SourceAccount already restricts to our account; the ArnLike
          #     adds defence-in-depth on the service+region pair.
          Condition = {
            StringEquals = {
              "aws:SourceAccount" = var.account_id
            }
            ArnLike = {
              "aws:SourceArn" = "arn:${local.partition}:backup:${var.region}:${var.account_id}:backup-vault:*"
            }
          }
        }
      ] : [],
      # CloudTrail service grant — required so the security-audit trail
      # (modules/monitoring) can configure `kms_key_id = this CMK` and have
      # CloudTrail encrypt the S3-stored log files with our CMK rather than
      # the AWS-managed s3 key. Audit C2-1: the trail captures data events
      # for SECRET_KEY reads + KMS Decrypt; encrypting those records with our
      # own key keeps the cryptographic boundary inside the project.
      #
      # Confused-deputy guards (layered):
      #   - aws:SourceAccount   pins to our account.
      #   - aws:SourceArn       pins to the EXACT trail in this account/region
      #                         (`${var.name_prefix}-audit`). Both sides derive
      #                         the trail name independently from
      #                         `var.name_prefix` — string-level coupling only,
      #                         no resource-graph cycle (the monitoring module
      #                         doesn't read kms module outputs to compute the
      #                         trail name; the kms module doesn't read
      #                         monitoring outputs to compute this ARN).
      #   - kms:EncryptionContext (aws:cloudtrail:arn) — defence in depth.
      #                         CloudTrail sets this encryption context
      #                         automatically on every encryption operation
      #                         with the trail's own ARN; pinning it here
      #                         means even an in-account attacker that owned
      #                         cloudtrail-create rights can't trick the key
      #                         into encrypting for an unrelated trail.
      #                         Modeled on the AllowCloudWatchLogs grant
      #                         (lines 64-67) which uses the analogous
      #                         kms:EncryptionContext:aws:logs:arn.
      var.allow_cloudtrail_service ? [
        {
          Sid    = "AllowCloudTrailService"
          Effect = "Allow"
          Principal = {
            Service = "cloudtrail.amazonaws.com"
          }
          Action = [
            "kms:Decrypt",
            "kms:GenerateDataKey*",
            "kms:DescribeKey"
          ]
          Resource = "*"
          Condition = {
            StringEquals = {
              "aws:SourceAccount"                        = var.account_id
              "kms:EncryptionContext:aws:cloudtrail:arn" = "arn:${local.partition}:cloudtrail:${var.region}:${var.account_id}:trail/${var.name_prefix}-audit"
            }
            ArnLike = {
              "aws:SourceArn" = "arn:${local.partition}:cloudtrail:${var.region}:${var.account_id}:trail/${var.name_prefix}-audit"
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
