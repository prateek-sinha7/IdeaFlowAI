locals {
  # Reference naming convention: prod is bare, non-prod carries a suffix.
  #   prod  -> velocityai
  #   stage -> velocityai-stage
  #   dev   -> velocityai-dev
  name_suffix = var.environment == "prod" ? "" : "-${var.environment}"
  name_prefix = "velocityai${local.name_suffix}"

  # Foundation outputs (read via remote state in data.tf).
  fnd = data.terraform_remote_state.foundation.outputs

  # ECR is SHARED (built once, promoted by tag). The registry hostname is
  # reconstructed from the live account + region rather than read from the
  # shared layer's state — no cross-layer dependency, same value either way.
  registry       = "${module.account_guard.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com"
  backend_image  = "${local.registry}/velocityai/backend:${var.image_tag}"
  frontend_image = "${local.registry}/velocityai/frontend:${var.image_tag}"

  # Model ID the app actually invokes (profile ID when using cross-region
  # inference). Drives the Bedrock CloudWatch alarm dimension.
  effective_model_id = var.use_inference_profile_for_app ? var.bedrock_inference_profile_id : var.bedrock_model_id

  # SSM parameter ARN prefix for the monitoring module's CloudTrail metric
  # filters. Built from the guard's partition/region/account + the foundation
  # parameter prefix (no trailing slash, no wildcard).
  secrets_path_prefix_arn = "arn:${module.account_guard.partition}:ssm:${module.account_guard.region}:${module.account_guard.account_id}:parameter${local.fnd.parameter_path_prefix}"
}
