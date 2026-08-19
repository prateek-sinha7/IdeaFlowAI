# =============================================================================
# Module: alb_internal
# =============================================================================
# Internal Application Load Balancer fronting an EXISTING EC2 instance that
# this Terraform tree does not create (it was provisioned by another process
# — see var.instance_id). The ALB gets AWS's auto-assigned DNS name
# (internal-<name>-<id>.<region>.elb.amazonaws.com); no Route 53 zone, EIP, or
# custom domain is created or required.
#
# Security model:
#   - ALB SG: 443/tcp inbound ONLY from var.trusted_ingress_cidrs (validated
#     to reject 0.0.0.0/0). No port 80.
#   - Target SG: 443/tcp inbound ONLY from the ALB SG. Attached to the
#     existing instance's primary ENI via aws_network_interface_sg_attachment
#     — this ADDS a security group to the ENI without touching the
#     instance's existing security group(s) or requiring an aws_instance
#     resource in this module (the instance is looked up, not managed).
#   - The ALB never terminates a self-signed/private cert without an
#     explicit, out-of-band-provisioned var.certificate_arn (see
#     variables.tf) — this module does not create ACM certificates or key
#     material.
# =============================================================================

data "aws_caller_identity" "current" {}

data "aws_instance" "target" {
  instance_id = var.instance_id
}

locals {
  tags = merge(
    {
      Project     = "velocityai"
      Environment = var.environment
      ManagedBy   = "terraform"
      Owner       = var.owner
      CostCenter  = var.cost_center
      Component   = "alb-internal"
    },
    var.extra_tags,
  )
}

# --- Security groups ---------------------------------------------------------

resource "aws_security_group" "alb" {
  name        = "${var.name_prefix}-alb-sg"
  description = "Internal ALB — HTTPS from approved corporate VPN/TGW CIDRs only"
  vpc_id      = var.vpc_id

  tags = merge(local.tags, { Name = "${var.name_prefix}-alb-sg" })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_ingress_rule" "alb_https" {
  for_each = toset(var.trusted_ingress_cidrs)

  security_group_id = aws_security_group.alb.id
  description       = "HTTPS from approved corporate CIDR ${each.value}"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = each.value

  tags = { Name = "${var.name_prefix}-alb-ingress-https-${replace(each.value, "/", "-")}" }
}

resource "aws_security_group" "alb_target" {
  name        = "${var.name_prefix}-alb-target-sg"
  description = "Target-side SG attached to the existing instance's ENI — HTTPS from the ALB SG only"
  vpc_id      = var.vpc_id

  tags = merge(local.tags, { Name = "${var.name_prefix}-alb-target-sg" })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_egress_rule" "alb_to_target" {
  security_group_id            = aws_security_group.alb.id
  description                  = "HTTPS to the registered target"
  ip_protocol                  = "tcp"
  from_port                    = var.target_port
  to_port                      = var.target_port
  referenced_security_group_id = aws_security_group.alb_target.id

  tags = { Name = "${var.name_prefix}-alb-egress-to-target" }
}

resource "aws_vpc_security_group_ingress_rule" "target_from_alb" {
  security_group_id            = aws_security_group.alb_target.id
  description                  = "HTTPS from the ALB SG"
  ip_protocol                  = "tcp"
  from_port                    = var.target_port
  to_port                      = var.target_port
  referenced_security_group_id = aws_security_group.alb.id

  tags = { Name = "${var.name_prefix}-alb-target-ingress-from-alb" }
}

# Attaches the target SG to the existing instance's primary ENI WITHOUT
# modifying the instance's own security-group list (the instance is not an
# aws_instance resource in this module — it's a data source lookup only, so
# there is no inline security_groups/vpc_security_group_ids to conflict with).
resource "aws_network_interface_sg_attachment" "target" {
  security_group_id    = aws_security_group.alb_target.id
  network_interface_id = data.aws_instance.target.network_interface_id
}

# --- Access/connection log bucket --------------------------------------------
# ALB access logs support ONLY SSE-S3 (AWS-managed keys) — a customer CMK is
# rejected by the ELB log-delivery service. See AWS ELB access-log docs.

resource "aws_s3_bucket" "logs" {
  bucket        = var.log_bucket_name
  force_destroy = var.log_bucket_force_destroy

  tags = merge(local.tags, { Name = var.log_bucket_name })
}

resource "aws_s3_bucket_public_access_block" "logs" {
  bucket = aws_s3_bucket.logs.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "logs" {
  bucket = aws_s3_bucket.logs.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256" # SSE-S3 — the only option ELB log delivery supports
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id

  rule {
    id     = "expire-alb-logs"
    status = "Enabled"

    filter {}

    expiration {
      days = var.log_retention_days
    }

    noncurrent_version_expiration {
      noncurrent_days = var.log_retention_days
    }
  }
}

data "aws_iam_policy_document" "logs_bucket" {
  statement {
    sid    = "AllowElbLogDelivery"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["logdelivery.elasticloadbalancing.amazonaws.com"]
    }

    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.logs.arn}/AWSLogs/${data.aws_caller_identity.current.account_id}/*"]

    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-acl"
      values   = ["bucket-owner-full-control"]
    }
  }
}

resource "aws_s3_bucket_policy" "logs" {
  bucket = aws_s3_bucket.logs.id
  policy = data.aws_iam_policy_document.logs_bucket.json
}

# --- ALB ----------------------------------------------------------------------

resource "aws_lb" "this" {
  name               = "${var.name_prefix}-internal"
  internal           = true
  load_balancer_type = "application"
  ip_address_type    = "ipv4"
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.subnet_ids

  enable_deletion_protection = var.enable_deletion_protection
  drop_invalid_header_fields = true
  enable_http2               = true
  desync_mitigation_mode     = "strictest"
  idle_timeout               = var.idle_timeout_seconds

  access_logs {
    bucket  = aws_s3_bucket.logs.id
    prefix  = "access"
    enabled = true
  }

  connection_logs {
    bucket  = aws_s3_bucket.logs.id
    prefix  = "connection"
    enabled = true
  }

  depends_on = [aws_s3_bucket_policy.logs]

  tags = merge(local.tags, { Name = "${var.name_prefix}-internal-alb" })
}

resource "aws_lb_target_group" "https" {
  name        = "${var.name_prefix}-https-tg"
  vpc_id      = var.vpc_id
  port        = var.target_port
  protocol    = "HTTPS"
  target_type = "instance"

  health_check {
    protocol            = "HTTPS"
    path                = var.health_check_path
    matcher             = var.health_check_matcher
    interval            = var.health_check_interval_seconds
    timeout             = var.health_check_timeout_seconds
    healthy_threshold   = var.healthy_threshold
    unhealthy_threshold = var.unhealthy_threshold
  }

  tags = merge(local.tags, { Name = "${var.name_prefix}-https-tg" })
}

resource "aws_lb_target_group_attachment" "instance" {
  target_group_arn = aws_lb_target_group.https.arn
  target_id        = var.instance_id
  port             = var.target_port
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = var.ssl_policy
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.https.arn
  }

  tags = merge(local.tags, { Name = "${var.name_prefix}-https-listener" })
}

# --- Alarms -------------------------------------------------------------------

resource "aws_sns_topic" "alerts" {
  count = var.create_sns_topic ? 1 : 0

  name              = "${var.name_prefix}-alb-alerts"
  kms_master_key_id = var.kms_key_arn != "" ? var.kms_key_arn : null

  tags = merge(local.tags, { Name = "${var.name_prefix}-alb-alerts" })
}

resource "aws_sns_topic_subscription" "email" {
  count = var.create_sns_topic && length(var.alarm_email) > 0 ? 1 : 0

  topic_arn = aws_sns_topic.alerts[0].arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

locals {
  alarm_topic_arn = var.create_sns_topic ? aws_sns_topic.alerts[0].arn : var.alarm_sns_topic_arn
}

resource "aws_cloudwatch_metric_alarm" "unhealthy_host_count" {
  alarm_name          = "${var.name_prefix}-alb-unhealthy-hosts"
  alarm_description   = "One or more targets behind ${aws_lb.this.name} are unhealthy."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "UnHealthyHostCount"
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.unhealthy_host_alarm_threshold
  # notBreaching: UnHealthyHostCount reports no datapoints until the ALB has
  # actually evaluated a target at least once. "breaching" would put this
  # alarm into ALARM immediately after creation/apply, before the target
  # group ever gets its first health check.
  treat_missing_data = "notBreaching"

  dimensions = {
    LoadBalancer = aws_lb.this.arn_suffix
    TargetGroup  = aws_lb_target_group.https.arn_suffix
  }

  alarm_actions = [local.alarm_topic_arn]
  ok_actions    = [local.alarm_topic_arn]

  tags = local.tags
}

resource "aws_cloudwatch_metric_alarm" "target_5xx" {
  alarm_name          = "${var.name_prefix}-alb-target-5xx"
  alarm_description   = "Elevated 5xx responses from the target behind ${aws_lb.this.name}."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_Target_5XX_Count"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.target_5xx_alarm_threshold
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = aws_lb.this.arn_suffix
  }

  alarm_actions = [local.alarm_topic_arn]
  ok_actions    = [local.alarm_topic_arn]

  tags = local.tags
}

resource "aws_cloudwatch_metric_alarm" "elb_5xx" {
  alarm_name          = "${var.name_prefix}-alb-elb-5xx"
  alarm_description   = "Elevated ALB-generated 5xx responses on ${aws_lb.this.name}."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_ELB_5XX_Count"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.elb_5xx_alarm_threshold
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = aws_lb.this.arn_suffix
  }

  alarm_actions = [local.alarm_topic_arn]
  ok_actions    = [local.alarm_topic_arn]

  tags = local.tags
}

resource "aws_cloudwatch_metric_alarm" "target_response_time" {
  alarm_name          = "${var.name_prefix}-alb-target-response-time"
  alarm_description   = "Average target response time behind ${aws_lb.this.name} is elevated."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "TargetResponseTime"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.target_response_time_alarm_threshold_seconds
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = aws_lb.this.arn_suffix
  }

  alarm_actions = [local.alarm_topic_arn]
  ok_actions    = [local.alarm_topic_arn]

  tags = local.tags
}
