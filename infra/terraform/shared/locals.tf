locals {
  # The shared layer is NOT environment-specific (single shared.tfstate),
  # so its resources carry the bare project prefix. Per-env naming
  # (velocityai / velocityai-stage / velocityai-dev) lives in
  # foundation/locals.tf and app/locals.tf.
  name_prefix = "velocityai"
}
