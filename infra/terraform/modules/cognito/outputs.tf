output "user_pool_id" {
  description = "Cognito User Pool ID (e.g. eu-central-1_xxxxxxxxx). Written to SSM as COGNITO_USER_POOL_ID."
  value       = aws_cognito_user_pool.this.id
}

output "user_pool_arn" {
  description = "User Pool ARN — used to scope the pool-restricted IAM policy for the EC2 instance role."
  value       = aws_cognito_user_pool.this.arn
}

output "user_pool_endpoint" {
  description = "The user pool's endpoint domain (issuer host), used to build the `iss` claim the backend verifies: https://<endpoint>."
  value       = aws_cognito_user_pool.this.endpoint
}

output "client_id" {
  description = "App client ID. Written to SSM as COGNITO_CLIENT_ID."
  value       = aws_cognito_user_pool_client.backend.id
}

output "client_secret" {
  description = "App client secret. Written to SSM as COGNITO_CLIENT_SECRET (SecureString). Sensitive — never appears in plan/apply output."
  value       = aws_cognito_user_pool_client.backend.client_secret
  sensitive   = true
}

output "group_names" {
  description = "The four fixed group names created, for reference by callers/tests."
  value       = var.group_names
}
