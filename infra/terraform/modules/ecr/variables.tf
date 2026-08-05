# =============================================================================
# Module: ecr
# Container image repositories for VelocityAI (backend + frontend). These are
# SHARED across environments: an image is built once and promoted dev -> stage
# -> prod by tag, so repo names are NOT environment-suffixed and this module is
# instantiated once, in the shared layer (velocityai/shared.tfstate).
# =============================================================================

variable "repository_names" {
  description = "ECR repository names to create. Namespaced as velocityai/<image> so images are addressed as velocityai/<image>:<tag>."
  type        = list(string)

  validation {
    condition     = length(var.repository_names) > 0
    error_message = "Provide at least one repository name."
  }
}

variable "image_tag_mutability" {
  description = "ECR tag mutability. IMMUTABLE (default) means a pushed tag can NEVER be overwritten by any caller — a release tag always denotes the same bytes. This closes the failure mode where a dev-triggered build re-points an existing tag (including a v* release tag) at different content, because ECR IAM cannot restrict PutImage per tag. Build retries of an already-pushed tag stay green: .github/workflows/deploy.yml probes ECR first (ecr:DescribeImages) and reuses the existing digest instead of re-pushing. Set MUTABLE only if you accept overwritable tags. NOTE: with IMMUTABLE, floating aliases such as <env>-latest CANNOT be re-pushed either — mutability is a repository-wide setting on aws provider ~> 5.x (per-tag exclusion filters need provider >= 6.4), which is why the workflow no longer publishes them."
  type        = string
  default     = "IMMUTABLE"

  validation {
    condition     = contains(["MUTABLE", "IMMUTABLE"], var.image_tag_mutability)
    error_message = "image_tag_mutability must be MUTABLE or IMMUTABLE."
  }
}

variable "kms_key_arn" {
  description = "Optional KMS CMK ARN for at-rest encryption of the registry. EMPTY DEFAULT: AES256 (S3-managed) encryption, which is the right choice for the shared layer because it is applied BEFORE the per-environment CMKs (modules/kms, foundation layer) exist — there is no project CMK to point at yet. Supply a key only if you have a dedicated shared CMK."
  type        = string
  default     = ""
}

variable "keep_last_images" {
  description = "Number of most-recent branch-build images to retain per repo, per environment tag prefix (older ones expire). Release-tagged images (no env prefix) are never expired by this policy, so a previous release is always available to roll back to."
  type        = number
  default     = 10

  validation {
    condition     = var.keep_last_images >= 1
    error_message = "keep_last_images must be at least 1."
  }
}

variable "env_tag_prefixes" {
  description = "Per-environment image tag prefixes for branch builds (e.g. dev-/stage-/prod-<sha>). Each gets its own 'keep last N' expiry rule so heavy dev churn never evicts a stage/prod image. RESERVED: do not use these as release tag prefixes, or release images would be expired by count. Release tags carry no prefix and are retained indefinitely."
  type        = list(string)
  default     = ["dev-", "stage-", "prod-"]
}

variable "untagged_expire_days" {
  description = "Expire untagged images (e.g. layers orphaned by a re-pushed tag) this many days after push."
  type        = number
  default     = 14
}

variable "scan_on_push" {
  description = "Enable image vulnerability scanning on push."
  type        = bool
  default     = true
}
