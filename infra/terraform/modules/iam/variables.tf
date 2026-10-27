variable "name_prefix" {
  description = "Resource name prefix, e.g. velocityai-prod."
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
  description = "ARN of the S3 bucket the instance writes pg_dumps and the skills/runs tarballs into."
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

variable "bedrock_allowed_inference_profile_ids" {
  description = "Every cross-Region inference profile the instance role may invoke, in ADDITION to bedrock_inference_profile_id (which is the app's active default). Give profile IDs only — the underlying foundation-model IDs are derived by stripping the geography prefix, so `eu.anthropic.claude-opus-4-5-20251101-v1:0` also grants `anthropic.claude-opus-4-5-20251101-v1:0`. A model the application can select but that is absent here fails at runtime with AccessDeniedException."
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for id in var.bedrock_allowed_inference_profile_ids :
      can(regex("^(eu|us|apac|global)\\.[A-Za-z0-9][A-Za-z0-9.:_-]*$", id))
    ])
    error_message = "Each entry must be an inference-profile ID prefixed with a geography (eu./us./apac./global.), e.g. eu.anthropic.claude-sonnet-4-5-20250929-v1:0 or global.openai.gpt-6-sol. Bare foundation-model IDs are not inference profiles."
  }
}

variable "bedrock_allowed_request_regions" {
  description = "Regions the instance role may CALL Bedrock from (aws:RequestedRegion condition on the invoke policy). Bounds a leaked instance credential to the deployment geography; it does NOT constrain where a cross-Region inference profile routes to. Default is the EU set the eu.* Anthropic profiles are invocable from."
  type        = list(string)
  default = [
    "eu-central-1",
    "eu-north-1",
    "eu-south-1",
    "eu-south-2",
    "eu-west-1",
    "eu-west-2",
    "eu-west-3",
  ]

  validation {
    condition     = length(var.bedrock_allowed_request_regions) > 0
    error_message = "bedrock_allowed_request_regions must list at least one region — an empty list would deny every Bedrock call."
  }
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

# JUSTIFICATION for the suppression below (required before any linter is
# silenced): this variable became genuinely unused inside the module when Phase 3
# removed the `count` gate from `aws_iam_role_policy.cognito_admin` (see the long
# comment at that resource in main.tf). It is retained ON PURPOSE because
# `foundation/main.tf` still passes it; deleting the variable while a caller
# supplies it fails with "An argument named cognito_enabled is not expected
# here". The main.tf comment states the removal is Phase 4 work at the
# foundation level, deliberately not folded into the commit that changed the
# grant. Removing this suppression without also removing the call site will make
# `tflint --recursive` exit 2 and fail the `security[iac]` leg.
# tflint-ignore: terraform_unused_declarations
variable "cognito_enabled" {
  description = "Whether to attach the pool-scoped Cognito admin policy. MUST be a plan-time-known boolean rather than a `length(var.cognito_user_pool_arn) > 0` test — the ARN is a module output that is unknown until apply, and counting on it fails the plan with \"The count value depends on resource attributes that cannot be determined until apply\". Unused inside this module since Phase 3; retained for the caller until Phase 4."
  type        = bool
  default     = false
}

variable "cognito_user_pool_arn" {
  description = "ARN of the Cognito User Pool the instance role may administer (AdminInitiateAuth/AdminCreateUser/etc, scoped to exactly this pool). Only used when cognito_enabled = true."
  type        = string
  default     = ""
}
