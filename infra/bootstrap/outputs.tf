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
