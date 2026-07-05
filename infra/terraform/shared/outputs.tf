output "verified_account_id" {
  description = "Account ID confirmed by the guard."
  value       = module.account_guard.account_id
}

output "verified_region" {
  description = "Region confirmed by the guard."
  value       = module.account_guard.region
}

output "ecr_repository_urls" {
  description = "Map of ECR repository name -> pull/push URL. The app layer reads these to compose image URIs; CI uses them for docker push."
  value       = module.ecr.repository_urls
}

output "ecr_repository_arns" {
  description = "Map of ECR repository name -> ARN. The foundation IAM module scopes the instance role's pull policy to these (reconstructed from naming to stay cycle-free)."
  value       = module.ecr.repository_arns
}

output "ecr_registry_url" {
  description = "Registry hostname (<acct>.dkr.ecr.<region>.amazonaws.com). Consumed by the app layer for `docker login` and image URI composition."
  value       = module.ecr.registry_url
}
