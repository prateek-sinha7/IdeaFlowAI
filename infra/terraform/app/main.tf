# =============================================================================
# VelocityAI App Layer (per environment) — the deployable unit
# =============================================================================
# Everything that changes when you ship: the EC2 instance + data EBS volume +
# EIP, the public DNS record, the docker-compose.yml + image-tag deploy object
# in S3 (driven by var.image_tag), the CloudWatch monitoring, and the Resource
# Groups. Long-lived base (network, KMS, IAM, secrets, backups) is read from
# the foundation layer via terraform_remote_state (see data.tf / locals.tf).
#
# State key: velocityai/<env>/app.tfstate
# Apply order: bootstrap -> shared -> foundation(<env>) -> app(<env>)
# =============================================================================

# --- Account / region guard -------------------------------------------------
# The app layer applies independently of foundation, so it runs its own guard
# (and sources account_id/region/partition from it) rather than trusting the
# provider blindly.
module "account_guard" {
  source = "../modules/account_guard"

  expected_account_id = var.expected_account_id
  expected_region     = var.aws_region
}

# --- Compute (EC2, data EBS, EIP) ------------------------------------------
module "compute" {
  source = "../modules/compute"

  # The instance self-provisions on first boot via velocityai-firstboot.service
  # (see modules/compute/user_data.sh.tpl), which pulls these config objects
  # from S3. They must therefore exist BEFORE the instance boots — otherwise a
  # fresh instance races its own bootstrap against the upload. No cycle: these
  # objects only reference foundation outputs + local files, never compute.
  depends_on = [
    aws_s3_object.compose_yaml,
    aws_s3_object.compose_prod_yaml,
    aws_s3_object.deploy_env,
    aws_s3_object.bootstrap_script,
    aws_s3_object.reconcile_script,
  ]

  name_prefix               = local.name_prefix
  environment               = var.environment
  region                    = module.account_guard.region
  instance_type             = var.instance_type
  subnet_id                 = local.fnd.public_subnet_id
  availability_zone         = local.fnd.availability_zone
  security_group_id         = local.fnd.app_security_group_id
  iam_instance_profile_name = local.fnd.instance_profile_name
  kms_key_arn               = local.fnd.kms_key_arn
  ssh_key_name              = var.ssh_key_name
  root_volume_size_gb       = var.root_volume_size_gb
  data_volume_size_gb       = var.data_volume_size_gb

  # Console/API guard against an accidental terminate/stop. Flip to false in
  # tfvars + apply to deliberately roll the instance.
  disable_api_termination = var.disable_api_termination
  disable_api_stop        = var.disable_api_stop

  # Environment threaded into the on-host bootstrap. The image tag is NOT here
  # (it lives in the deploy-env S3 object below, re-read at every redeploy);
  # user_data has ignore_changes so a tag bump never replaces the instance.
  user_data_extra_env = {
    VELOCITYAI_BACKUP_BUCKET = local.fnd.backup_bucket_name
    VELOCITYAI_PARAM_PREFIX  = local.fnd.parameter_path_prefix
    VELOCITYAI_KMS_KEY_ID    = local.fnd.kms_key_arn
    VELOCITYAI_FQDN          = module.dns.fqdn
    VELOCITYAI_ECR_REGISTRY  = local.registry
    VELOCITYAI_GIT_REF       = var.git_ref
    VELOCITYAI_ACME_EMAIL    = var.alert_email
  }
}

# --- On-host bootstrap script hosted in S3 ---------------------------------
# The first-boot systemd unit (velocityai-firstboot.service, written by the
# compute module's user_data) downloads this and runs the full host install
# (Postgres, nginx, Docker, certbot, systemd units, app start). Uploading it
# here — instead of relying on an operator to run it via SSM — is what makes a
# freshly-created instance self-provision. `source_hash` re-uploads whenever
# the local script changes so hosts always fetch the current version.
resource "aws_s3_object" "bootstrap_script" {
  bucket = local.fnd.backup_bucket_name
  key    = "config/bootstrap-ec2.sh"

  source      = "${path.root}/../../scripts/bootstrap-ec2.sh"
  source_hash = filemd5("${path.root}/../../scripts/bootstrap-ec2.sh")

  content_type           = "text/x-shellscript"
  server_side_encryption = "aws:kms"
  kms_key_id             = local.fnd.kms_key_arn

  tags = {
    Name      = "${local.name_prefix}-bootstrap-script"
    Component = "compute"
  }
}

# --- Host-config reconcile script hosted in S3 --------------------------------
# The declarative half of bootstrap-ec2.sh (nginx site + limits + proxy-header
# snippet, CloudWatch agent config + ACLs), extracted so it can be re-applied
# to a RUNNING host. bootstrap-ec2.sh fetches and runs it on first boot; the CI
# deploy fetches and runs it on every deploy. `source_hash` re-uploads whenever
# the local script changes, so a repo edit reaches a live host on the next
# deploy without any pipeline change.
#
# Same category as bootstrap_script: infrastructure that must exist before any
# CI run, not deploy output. Same bucket/prefix/KMS key, so the instance role's
# existing s3-config-read + kms-decrypt grants already cover it.
resource "aws_s3_object" "reconcile_script" {
  bucket = local.fnd.backup_bucket_name
  key    = "config/reconcile-host-config.sh"

  source      = "${path.root}/../../scripts/reconcile-host-config.sh"
  source_hash = filemd5("${path.root}/../../scripts/reconcile-host-config.sh")

  content_type           = "text/x-shellscript"
  server_side_encryption = "aws:kms"
  kms_key_id             = local.fnd.kms_key_arn

  tags = {
    Name      = "${local.name_prefix}-reconcile-script"
    Component = "compute"
  }
}

# --- DNS --------------------------------------------------------------------
module "dns" {
  source = "../modules/dns"

  name_prefix       = local.name_prefix
  use_nip_io        = var.use_nip_io
  route53_zone_name = var.route53_zone_name
  app_subdomain     = var.app_subdomain
  eip_address       = module.compute.public_ip
  ttl_seconds       = var.dns_ttl_seconds
}

# --- docker-compose.yml hosted in S3 ---------------------------------------
# The on-host bootstrap downloads this to run `docker compose pull && up -d`.
# `source_hash` makes Terraform re-upload when the local file changes.
resource "aws_s3_object" "compose_yaml" {
  bucket = local.fnd.backup_bucket_name
  key    = "config/docker-compose.yml"

  source      = "${path.root}/../../../docker-compose.yml"
  source_hash = filemd5("${path.root}/../../../docker-compose.yml")

  content_type           = "text/yaml"
  server_side_encryption = "aws:kms"
  kms_key_id             = local.fnd.kms_key_arn

  tags = {
    Name      = "${local.name_prefix}-compose-yaml"
    Component = "compute"
  }
}

# --- docker-compose.prod.yml (M-01 logging override) hosted in S3 ----------
# Switches backend/frontend to the awslogs driver so each ships to its own
# CloudWatch stream instead of the CloudWatch agent's undifferentiated
# {instance_id}/docker stream. Applied alongside docker-compose.yml via
# `docker compose -f docker-compose.yml -f docker-compose.prod.yml` (both the
# systemd unit in bootstrap-ec2.sh and the CI redeploy in
# .github/workflows/deploy.yml + .github/scripts/remote-deploy.sh pass both
# files). Same delivery mechanism/bucket/KMS key as compose_yaml.
#
# NOTE: CI no longer READS this S3 object (deploy.yml ships docker-compose.yml
# / docker-compose.prod.yml inline from the checkout, gzip+base64, in the SSM
# payload — see remote-deploy.sh's header). This upload stays because
# bootstrap-ec2.sh §10 and velocityai-firstboot.service still fetch it on
# first boot, before any CI deploy has ever run.
resource "aws_s3_object" "compose_prod_yaml" {
  bucket = local.fnd.backup_bucket_name
  key    = "config/docker-compose.prod.yml"

  source      = "${path.root}/../../../docker-compose.prod.yml"
  source_hash = filemd5("${path.root}/../../../docker-compose.prod.yml")

  content_type           = "text/yaml"
  server_side_encryption = "aws:kms"
  kms_key_id             = local.fnd.kms_key_arn

  tags = {
    Name      = "${local.name_prefix}-compose-prod-yaml"
    Component = "compute"
  }
}

# --- Deploy env (image tag) hosted in S3 -----------------------------------
# This is what makes the app layer the "deployable unit": the resolved image
# URIs for var.image_tag. Changing image_tag changes this object's content, so
# `app apply` re-uploads it and bootstrap-ec2.sh §10 reads it on first boot to
# seed BACKEND_IMAGE/FRONTEND_IMAGE before any CI deploy has run. The
# docker-compose.yml interpolates ${BACKEND_IMAGE}/${FRONTEND_IMAGE} from here.
#
# NOTE: steady-state CI redeploys (.github/workflows/deploy.yml) do NOT read
# this object — GitHub Actions computes the image tag itself and pins it
# directly into /etc/velocityai/app.env via remote-deploy.sh, with no
# Terraform apply in the loop. This S3 object is retained purely for the
# first-boot bootstrap path described above.
resource "aws_s3_object" "deploy_env" {
  bucket = local.fnd.backup_bucket_name
  key    = "config/deploy.env"

  content = <<-EOT
    # Generated by Terraform (app layer). Do not edit by hand.
    IMAGE_TAG=${var.image_tag}
    BACKEND_IMAGE=${local.backend_image}
    FRONTEND_IMAGE=${local.frontend_image}
  EOT

  content_type           = "text/plain"
  server_side_encryption = "aws:kms"
  kms_key_id             = local.fnd.kms_key_arn

  tags = {
    Name      = "${local.name_prefix}-deploy-env"
    Component = "compute"
  }
}

# --- Monitoring -------------------------------------------------------------
module "monitoring" {
  source = "../modules/monitoring"

  providers = {
    aws         = aws
    aws.useast1 = aws.useast1
  }

  name_prefix                 = local.name_prefix
  environment                 = var.environment
  instance_id                 = module.compute.instance_id
  kms_key_arn                 = local.fnd.kms_key_arn
  alert_email                 = var.alert_email
  log_retention_days          = var.log_retention_days
  log_retention_overrides     = var.log_retention_overrides
  billing_alarm_threshold_usd = var.billing_alarm_threshold_usd
  bedrock_model_id            = local.effective_model_id
  cw_metric_namespace         = "VelocityAI/${title(var.environment)}"
  backup_vault_name           = local.fnd.backup_vault_name

  bedrock_daily_token_threshold        = var.bedrock_daily_token_threshold
  bedrock_throttles_threshold          = var.bedrock_throttles_threshold
  bedrock_throttles_evaluation_periods = var.bedrock_throttles_evaluation_periods
  agent_error_rate_threshold           = var.agent_error_rate_threshold
  stuck_workflows_threshold            = var.stuck_workflows_threshold
  stuck_workflows_check_period         = var.stuck_workflows_check_period

  # CloudTrail management-event audit-trail wiring (C2-1).
  instance_role_arn       = local.fnd.instance_role_arn
  secrets_path_prefix_arn = local.secrets_path_prefix_arn
  project_cmk_arn         = local.fnd.kms_key_arn
  # M-07: CloudTrail data-event capture for the backup bucket (GetObject/
  # PutObject on the hourly pg_dump backups — the management-event trail
  # above never captured object-level S3 API calls).
  backup_bucket_arn = local.fnd.backup_bucket_arn
}

# --- Resource Groups (tag-query everything in this env) --------------------
module "resourcegroups" {
  source = "../modules/resourcegroups"

  name_prefix = local.name_prefix
  environment = var.environment
}
