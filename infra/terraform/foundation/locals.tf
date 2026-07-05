locals {
  # Reference naming convention: prod is bare, non-prod carries a suffix.
  #   prod  -> velocityai
  #   stage -> velocityai-stage
  #   dev   -> velocityai-dev
  name_suffix = var.environment == "prod" ? "" : "-${var.environment}"
  name_prefix = "velocityai${local.name_suffix}"

  # The model ID the application actually invokes. When using an EU-wide
  # inference profile, the SDK passes the profile ID as modelId; IAM still
  # scopes to both the foundation-model ARN and the profile ARN.
  effective_model_id = var.use_inference_profile_for_app ? var.bedrock_inference_profile_id : var.bedrock_model_id
}
