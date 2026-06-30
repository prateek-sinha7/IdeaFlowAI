output "state_bucket_name" {
  description = "Name of the S3 bucket holding Terraform state. Pass as TF_STATE_BUCKET / -backend-config=\"bucket=...\" to the shared, foundation, and app layers."
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
  description = "Alias of the bootstrap CMK (alias/velocityai-tfstate)."
  value       = aws_kms_alias.bootstrap.name
}

# --- CI/CD runner outputs ---------------------------------------------------

output "codebuild_deploy_role_arns" {
  description = "Per-environment ARNs of the IAM roles CodeBuild assumes to run the pipeline, keyed by environment."
  value       = { for env, role in aws_iam_role.codebuild_deploy : env => role.arn }
}

output "gitlab_connection_arn" {
  description = "ARN of the shared GitLab CodeConnections connection. PENDING until authorized once in the AWS console."
  value       = var.create_gitlab_runner ? aws_codestarconnections_connection.gitlab[0].arn : null
}

output "gitlab_runner_project_names" {
  description = "Per-environment CodeBuild project names, keyed by environment (named after the branch each serves; triggered by their webhooks)."
  value       = { for env, proj in aws_codebuild_project.gitlab_runner : env => proj.name }
}
