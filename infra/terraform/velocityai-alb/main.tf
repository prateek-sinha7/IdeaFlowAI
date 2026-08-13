# =============================================================================
# VelocityAI — internal ALB layer (dev / stage / prod)
# =============================================================================
# Fronts the EXISTING per-environment EC2 instance (provisioned outside this
# Terraform tree — see .planning / session history) with an internal ALB
# reachable over the existing corporate VPN/Transit Gateway path. Uses AWS's
# auto-assigned ALB DNS name; no Route 53 zone, record, or EIP is created.
#
# One apply = one environment. Select the environment via
# -var-file=<dev|stage|prod>.tfvars (see README.md / dev.tfvars).
#
# State key: velocityai/<environment>/alb.tfstate — each environment gets its
# own state object, so a mistake in one environment's plan can't touch
# another's resources.
#
# Prerequisite: an ACM certificate (private CA or imported) for THIS
# environment's ALB generated hostname must already exist — this layer does
# not create one. The generated hostname is only known AFTER the first
# apply, so plan this as a two-step rollout per environment: (1) apply with
# a placeholder/self-signed cert to get the DNS name, request/import the
# real cert against that name, (2) apply again with var.certificate_arn
# pointed at the real certificate.
# =============================================================================

module "account_guard" {
  source = "../modules/account_guard"

  expected_account_id = var.expected_account_id
  expected_region     = var.aws_region
}

module "alb_internal" {
  source = "../modules/alb_internal"

  name_prefix = local.name_prefix
  environment = var.environment

  vpc_id      = var.vpc_id
  subnet_ids  = var.subnet_ids
  instance_id = var.instance_id

  trusted_ingress_cidrs = var.trusted_ingress_cidrs
  certificate_arn       = var.certificate_arn

  log_bucket_name = local.log_bucket_name
  alarm_email     = var.alarm_email
  kms_key_arn     = var.kms_key_arn

  owner       = var.owner
  cost_center = var.cost_center

  depends_on = [module.account_guard]
}
