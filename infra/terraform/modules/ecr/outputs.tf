output "repository_urls" {
  description = "Map of repository name -> pull/push URL (e.g. velocityai/backend -> <acct>.dkr.ecr.<region>.amazonaws.com/velocityai/backend)."
  value       = { for k, v in aws_ecr_repository.this : k => v.repository_url }
}

output "repository_arns" {
  description = "Map of repository name -> repository ARN."
  value       = { for k, v in aws_ecr_repository.this : k => v.arn }
}

output "registry_url" {
  description = "Registry hostname (everything before the repo path), e.g. <acct>.dkr.ecr.<region>.amazonaws.com. The app layer consumes this for `docker login` and to compose image URIs; identical for every repo in this account+region."
  value       = split("/", values(aws_ecr_repository.this)[0].repository_url)[0]
}
