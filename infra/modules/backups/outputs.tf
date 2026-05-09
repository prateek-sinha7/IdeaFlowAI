output "backup_bucket_name" {
  description = "Name of the S3 bucket holding pg_dump archives."
  value       = aws_s3_bucket.backups.id
}

output "backup_bucket_arn" {
  description = "ARN of the S3 backup bucket. Wire into the IAM module's policy template."
  value       = aws_s3_bucket.backups.arn
}

output "backup_vault_name" {
  description = "Name of the AWS Backup vault."
  value       = aws_backup_vault.this.name
}

output "backup_vault_arn" {
  description = "ARN of the AWS Backup vault."
  value       = aws_backup_vault.this.arn
}

output "backup_plan_id" {
  description = "ID of the AWS Backup plan."
  value       = aws_backup_plan.daily.id
}

output "backup_role_arn" {
  description = "ARN of the AWS Backup service role (used in selections)."
  value       = aws_iam_role.backup.arn
}
