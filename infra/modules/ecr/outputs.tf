output "backend_repository_url" {
  description = "Pull URL for the backend image (e.g. <ACCOUNT>.dkr.ecr.<REGION>.amazonaws.com/flowin-prod-backend). Bootstrap reads this to drive `docker compose pull`."
  value       = aws_ecr_repository.this["backend"].repository_url
}

output "frontend_repository_url" {
  description = "Pull URL for the frontend image."
  value       = aws_ecr_repository.this["frontend"].repository_url
}

output "repository_arns" {
  description = "List of repository ARNs. Currently informational; the IAM ecr-pull policy reconstructs ARNs from name_prefix to avoid an iam<->ecr graph cycle (IAM scopes Resource via ARN, ECR scopes Principal via instance_role_arn)."
  value       = [for r in aws_ecr_repository.this : r.arn]
}

output "repository_names" {
  description = "Map of logical key (backend/frontend) -> repo name."
  value       = { for k, r in aws_ecr_repository.this : k => r.name }
}

output "registry_url" {
  description = "Registry hostname (everything before the repo name in repository_url). Bootstrap consumes this as FLOWIN_ECR_REGISTRY for `docker login` and for composing image URIs in /etc/flowin/app.env."
  value       = split("/", aws_ecr_repository.this["backend"].repository_url)[0]
}

# TODO: These URLs feed into a CI snippet documented in
# docs/SIMPLE_AWS_DEPLOYMENT.md (ECR push/pull section). When that section
# lands, link it here. The host portion is constant per env+region; the path
# is just the repo name (= name_prefix-backend / name_prefix-frontend).
