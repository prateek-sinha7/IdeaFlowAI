locals {
  name_prefix = "flowin-${var.environment}"

  # The model ID the application actually invokes. When using an EU-wide
  # inference profile, the SDK call passes the profile ID as the modelId;
  # IAM policy still scopes to both the foundation-model ARN and the profile
  # ARN. See SIMPLE_AWS_DEPLOYMENT.md §0.1 + §5.3.
  effective_model_id = var.use_inference_profile_for_app ? var.bedrock_inference_profile_id : var.bedrock_model_id
}
