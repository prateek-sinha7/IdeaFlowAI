output "parameter_path_prefix" {
  description = "Path prefix for all Flowin parameters in this environment."
  value       = "/flowin/${var.environment}"
}

output "llm_provider_parameter_arn" {
  value = aws_ssm_parameter.llm_provider.arn
}

output "app_secret_key_parameter_arn" {
  value = aws_ssm_parameter.app_secret_key.arn
}

output "db_password_parameter_arn" {
  value = aws_ssm_parameter.db_password.arn
}
