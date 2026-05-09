output "account_id" {
  description = "Account ID confirmed by the guard. Wire downstream resources to depend on this value to ensure the precondition runs first."
  value       = data.aws_caller_identity.current.account_id

  depends_on = [terraform_data.guard]
}

output "region" {
  description = "Region confirmed by the guard."
  value       = data.aws_region.current.name

  depends_on = [terraform_data.guard]
}

output "partition" {
  description = "AWS partition (aws, aws-us-gov, aws-cn). For ARN construction."
  value       = data.aws_partition.current.partition
}
