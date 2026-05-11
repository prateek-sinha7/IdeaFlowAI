data "aws_ami" "ubuntu" {
  count = var.ami_id == "" ? 1 : 0

  most_recent = true
  owners      = [var.ami_owner]

  filter {
    name   = "name"
    values = [var.ami_name_pattern]
  }

  filter {
    name   = "state"
    values = ["available"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "root-device-type"
    values = ["ebs"]
  }
}

locals {
  parameter_path_prefix = "/flowin/${var.environment}"

  # Either the explicit override (LocalStack et al.) or the data-source lookup.
  effective_ami_id = var.ami_id != "" ? var.ami_id : data.aws_ami.ubuntu[0].id

  user_data = templatefile("${path.module}/user_data.sh.tpl", {
    environment           = var.environment
    region                = var.region
    parameter_path_prefix = local.parameter_path_prefix
    data_device_hint      = var.data_volume_device_name
    extra_env             = var.user_data_extra_env
  })
}

# --- Data volume ------------------------------------------------------------

resource "aws_ebs_volume" "data" {
  availability_zone = var.availability_zone
  size              = var.data_volume_size_gb
  type              = "gp3"
  iops              = 3000
  throughput        = 125
  encrypted         = true
  kms_key_id        = var.kms_key_arn

  tags = {
    Name      = "${var.name_prefix}-data"
    Component = "storage"
    Backup    = "true" # picked up by AWS Backup tag-based selection
  }

  lifecycle {
    prevent_destroy = true
  }
}

# --- EC2 instance -----------------------------------------------------------

resource "aws_instance" "app" {
  ami                    = local.effective_ami_id
  instance_type          = var.instance_type
  subnet_id              = var.subnet_id
  vpc_security_group_ids = [var.security_group_id]
  iam_instance_profile   = var.iam_instance_profile_name != "" ? var.iam_instance_profile_name : null
  key_name               = var.ssh_key_name != "" ? var.ssh_key_name : null

  user_data                   = base64encode(local.user_data)
  user_data_replace_on_change = false

  associate_public_ip_address = false # EIP is associated explicitly

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required" # IMDSv2-only
    # hop_limit = 2 is required for containerized workloads on EC2. The
    # IMDS responds on 169.254.169.254 and the EC2 IAM role's temporary
    # credentials are only fetchable through IMDS. From inside a Docker
    # container the request travels container → bridge → IMDS = 2 hops,
    # so a response capped at 1 hop is dropped before reaching the
    # container. Symptom is `boto3.NoCredentialsError: Unable to locate
    # credentials` — exactly what the backend hit when calling Bedrock.
    # AWS's own docs explicitly recommend hop_limit=2 for ECS/EKS/Docker-
    # on-EC2 deployments. Still IMDSv2-only (http_tokens=required), so
    # SSRF protection is preserved.
    http_put_response_hop_limit = 2
    instance_metadata_tags      = "enabled"
  }

  monitoring                           = var.detailed_monitoring
  ebs_optimized                        = var.ebs_optimized
  instance_initiated_shutdown_behavior = "stop"

  # Console + API guard against an accidental `aws ec2 terminate-instances`
  # or `aws ec2 stop-instances` (a deliberate operator unset is an explicit
  # `terraform apply` away). The data EBS survives termination because it's a
  # separate aws_ebs_volume with prevent_destroy=true, but reattaching it is
  # manual — we'd rather make the destructive verb a hard no by default.
  disable_api_termination = var.disable_api_termination
  disable_api_stop        = var.disable_api_stop

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_size_gb
    iops                  = 3000
    throughput            = 125
    encrypted             = true
    kms_key_id            = var.kms_key_arn
    delete_on_termination = true

    tags = {
      Name      = "${var.name_prefix}-root"
      Component = "compute"
    }
  }

  tags = {
    Name      = "${var.name_prefix}-app"
    Component = "compute"
  }

  lifecycle {
    ignore_changes = [
      # AMI rolls forward as Canonical publishes new images; we want to
      # control instance refresh through a deliberate `terraform taint`,
      # not on every plan.
      ami,
      user_data,
      # AWS provider drift: after `aws_eip_association` attaches an EIP, the
      # describe-instances API starts reporting `associate_public_ip_address`
      # as `true` regardless of the launch-time setting. Without this ignore,
      # every subsequent `terraform plan` marks the instance for replacement
      # (true -> false # forces replacement) — which then cascades into
      # destroying the data EBS volume_attachment, which requires stopping
      # the instance, which is blocked by `disable_api_stop = true`. See
      # hashicorp/terraform-provider-aws#14149 for the upstream issue.
      associate_public_ip_address,
    ]
  }
}

# --- Volume attachment ------------------------------------------------------

resource "aws_volume_attachment" "data" {
  device_name = var.data_volume_device_name
  volume_id   = aws_ebs_volume.data.id
  instance_id = aws_instance.app.id

  # Don't accidentally detach if the instance is replaced; an operator must
  # explicitly run `terraform apply -replace=...` to recycle this.
  stop_instance_before_detaching = true
}

# --- Elastic IP -------------------------------------------------------------

resource "aws_eip" "this" {
  domain = "vpc"

  tags = {
    Name      = "${var.name_prefix}-eip"
    Component = "compute"
  }

  lifecycle {
    # EIPs are address-bearing identity — releasing one frees the IPv4
    # address back to the AWS pool, after which the same /32 cannot be
    # reclaimed. The DNS A-record + any TLS-cert allowlists external
    # parties hold for the IP would all break on re-allocation, so this
    # is hard-coded `true` — Terraform 1.x rejects variable references
    # in `prevent_destroy` (the field is evaluated when the dependency
    # graph is built, before any variable is resolved; verified on TF
    # 1.15.1 in May 2026). Ephemeral envs (LocalStack) state-rm the EIP
    # before `terraform destroy` instead — see
    # envs/localstack/destroy.sh. The `var.protect_eip` input is kept
    # for documentation and forward-compatibility: when (if) Terraform
    # ever loosens this restriction, the wiring change is one line.
    prevent_destroy = true
  }
}

resource "aws_eip_association" "this" {
  instance_id   = aws_instance.app.id
  allocation_id = aws_eip.this.id
}
