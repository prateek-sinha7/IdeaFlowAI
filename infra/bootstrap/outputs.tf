output "state_bucket_name" {
  description = "Name of the S3 bucket holding Terraform state. Wire into envs/*/backend.tf."
  value       = aws_s3_bucket.tfstate.id
}

output "state_bucket_arn" {
  description = "ARN of the state bucket."
  value       = aws_s3_bucket.tfstate.arn
}

output "lock_table_name" {
  description = "DynamoDB table for state locking."
  value       = aws_dynamodb_table.tflock.name
}

output "verified_account_id" {
  description = "Account ID confirmed by the guard."
  value       = data.aws_caller_identity.current.account_id
}

output "verified_region" {
  description = "Region confirmed by the guard."
  value       = data.aws_region.current.name
}

output "kms_key_arn" {
  description = "Bootstrap CMK ARN. State bucket and lock table encrypt with this key."
  value       = aws_kms_key.bootstrap.arn
}

output "kms_key_alias" {
  description = "Alias of the bootstrap CMK (alias/flowin-tfstate)."
  value       = aws_kms_alias.bootstrap.name
}
