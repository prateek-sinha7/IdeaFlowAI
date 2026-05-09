variable "name_prefix" {
  description = "Resource name prefix, e.g. flowin-prod."
  type        = string
}

variable "environment" {
  description = "Environment short name (e.g. prod). Used in policy ARNs."
  type        = string
}

variable "account_id" {
  description = "AWS account ID."
  type        = string
}

variable "region" {
  description = "AWS region."
  type        = string
}

variable "kms_key_arn" {
  description = "ARN of the project CMK the instance role may decrypt with."
  type        = string
}

variable "backup_bucket_arn" {
  description = "ARN of the S3 bucket the instance writes pg_dumps into."
  type        = string
}

variable "bedrock_model_id" {
  description = "Foundation model ID, e.g. anthropic.claude-haiku-4-5-20251001-v1:0."
  type        = string
}

variable "bedrock_inference_profile_id" {
  description = "Cross-region inference profile ID, e.g. eu.anthropic.claude-haiku-4-5-20251001-v1:0."
  type        = string
}

variable "policies_dir" {
  description = "Path (relative to this module) to the policies/ directory holding policy JSON templates."
  type        = string
  default     = "../../policies"
}

variable "attach_ssm_managed_policy" {
  description = "Whether to attach the AWS-managed AmazonSSMManagedInstanceCore policy to the role (enables Session Manager)."
  type        = bool
  default     = true
}
