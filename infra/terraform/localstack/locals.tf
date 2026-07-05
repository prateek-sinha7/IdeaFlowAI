locals {
  # The fixture is always suffixed (velocityai-ls); it never uses the bare
  # prod prefix, so a stray apply can't collide with real prod resources.
  name_prefix        = "velocityai-${var.environment}"
  effective_model_id = var.use_inference_profile_for_app ? var.bedrock_inference_profile_id : var.bedrock_model_id
}
