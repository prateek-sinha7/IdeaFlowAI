locals {
  name_prefix = "flowin-${var.environment}"

  effective_model_id = var.use_inference_profile_for_app ? var.bedrock_inference_profile_id : var.bedrock_model_id
}
