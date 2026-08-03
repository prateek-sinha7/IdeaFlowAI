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

# --- GitHub Actions CI/CD outputs (github_oidc.tf) --------------------------
# The retired GitLab/CodeBuild outputs (codebuild_deploy_role_arns,
# gitlab_connection_arn, gitlab_runner_project_names) lived here.
#
# The single `github_cicd_role_arn` output is GONE: there is no single shared
# role any more. github_oidc.tf now creates one ECR-only build role plus one
# deploy role per environment, so GitHub needs TWO variables per Environment:
#   AWS_BUILD_ROLE_ARN  <- github_build_role_arn      (same in every env)
#   AWS_DEPLOY_ROLE_ARN <- github_deploy_role_arns[e] (env-specific)
# See docs/GITHUB_CICD_SETUP.md §3.2 and infra/terraform/RUNBOOK.md §1a.

output "github_build_role_arn" {
  description = "ARN of the GitHub Actions OIDC build role (ECR push/pull only). Set as the AWS_BUILD_ROLE_ARN variable in EVERY GitHub Environment — the same value in each. Null when create_github_oidc = false."
  value       = var.create_github_oidc ? aws_iam_role.github_build[0].arn : null
}

output "github_deploy_role_arns" {
  description = "Map of environment name -> per-environment GitHub Actions OIDC deploy role ARN. Set each value as the AWS_DEPLOY_ROLE_ARN variable in the MATCHING GitHub Environment; crossing them over will fail at STS, which is the intended behaviour. Empty when create_github_oidc = false."
  value       = { for env, role in aws_iam_role.github_deploy : env => role.arn }
}

output "github_oidc_provider_arn" {
  description = "ARN of the GitHub Actions OIDC identity provider (created here, or adopted from an existing one — see github_oidc_create_provider). Null when create_github_oidc = false."
  value       = var.create_github_oidc ? local.github_oidc_provider_arn : null
}
