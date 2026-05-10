variable "name_prefix" {
  description = "Project + env prefix, e.g. flowin-prod or flowin-ls."
  type        = string
}

variable "kms_key_arn" {
  description = "KMS CMK ARN for at-rest encryption of the registry."
  type        = string
}

variable "instance_role_arn" {
  description = "ARN of the EC2 instance role that needs pull access. Used as the sole Principal in the per-repo aws_ecr_repository_policy. The IAM-side counterpart (an inline policy on the same role) lives in the iam module and is rendered from policies/ecr-pull.json."
  type        = string
}

variable "environment" {
  description = "Environment short name (e.g. prod, ls). Used in the Environment tag for Resource Group filtering."
  type        = string
}
