locals {
  log_groups = [
    "/flowin/${var.environment}/nginx",
    "/flowin/${var.environment}/uvicorn",
    "/flowin/${var.environment}/next",
    "/flowin/${var.environment}/postgres",
    "/flowin/${var.environment}/system",
  ]
}

# --- Log groups -------------------------------------------------------------

resource "aws_cloudwatch_log_group" "groups" {
  for_each = toset(local.log_groups)

  name              = each.value
  retention_in_days = var.log_retention_days
  kms_key_id        = var.kms_key_arn

  tags = {
    Name      = each.value
    Component = "monitoring"
  }
}

# --- SNS topic --------------------------------------------------------------

resource "aws_sns_topic" "alerts" {
  name              = "${var.name_prefix}-alerts"
  kms_master_key_id = var.kms_key_arn

  tags = {
    Name      = "${var.name_prefix}-alerts"
    Component = "monitoring"
  }
}

resource "aws_sns_topic_subscription" "email" {
  count = length(var.alert_email) > 0 ? 1 : 0

  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# --- CloudWatch alarms ------------------------------------------------------

# 1. CPU sustained high
resource "aws_cloudwatch_metric_alarm" "cpu_high" {
  alarm_name          = "${var.name_prefix}-cpu-high"
  alarm_description   = "Sustained host CPU above ${var.cpu_threshold_percent}% for 15 minutes"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 3
  metric_name         = "cpu_usage_user"
  namespace           = var.cw_metric_namespace
  period              = 300
  statistic           = "Average"
  threshold           = var.cpu_threshold_percent
  treat_missing_data  = "notBreaching"

  dimensions = {
    InstanceId = var.instance_id
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = {
    Component = "monitoring"
  }
}

# 2. Memory pressure
resource "aws_cloudwatch_metric_alarm" "mem_high" {
  alarm_name          = "${var.name_prefix}-mem-high"
  alarm_description   = "Memory above ${var.memory_threshold_percent}% for 10 minutes"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "mem_used_percent"
  namespace           = var.cw_metric_namespace
  period              = 300
  statistic           = "Average"
  threshold           = var.memory_threshold_percent
  treat_missing_data  = "notBreaching"

  dimensions = {
    InstanceId = var.instance_id
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = {
    Component = "monitoring"
  }
}

# 3a. Root disk near full
resource "aws_cloudwatch_metric_alarm" "disk_root_high" {
  alarm_name          = "${var.name_prefix}-disk-root-high"
  alarm_description   = "Root filesystem disk usage above ${var.disk_threshold_percent}%"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "disk_used_percent"
  namespace           = var.cw_metric_namespace
  period              = 300
  statistic           = "Maximum"
  threshold           = var.disk_threshold_percent
  treat_missing_data  = "notBreaching"

  dimensions = {
    InstanceId = var.instance_id
    path       = "/"
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = {
    Component = "monitoring"
  }
}

# 3b. Data disk near full (Postgres)
resource "aws_cloudwatch_metric_alarm" "disk_data_high" {
  alarm_name          = "${var.name_prefix}-disk-data-high"
  alarm_description   = "Postgres data filesystem disk usage above ${var.disk_threshold_percent}%"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "disk_used_percent"
  namespace           = var.cw_metric_namespace
  period              = 300
  statistic           = "Maximum"
  threshold           = var.disk_threshold_percent
  treat_missing_data  = "notBreaching"

  dimensions = {
    InstanceId = var.instance_id
    path       = "/var/lib/postgresql"
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = {
    Component = "monitoring"
  }
}

# 4. nginx 5xx spike — derived metric from a log filter
resource "aws_cloudwatch_log_metric_filter" "nginx_5xx" {
  name           = "${var.name_prefix}-nginx-5xx"
  log_group_name = aws_cloudwatch_log_group.groups["/flowin/${var.environment}/nginx"].name
  pattern        = "[ip, id, user, ts, request, status_code=5*, ...]"

  metric_transformation {
    name          = "Nginx5xx"
    namespace     = var.cw_metric_namespace
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_metric_alarm" "nginx_5xx_spike" {
  alarm_name          = "${var.name_prefix}-nginx-5xx-spike"
  alarm_description   = "More than 10 nginx 5xx responses per minute for 5 minutes"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 5
  metric_name         = "Nginx5xx"
  namespace           = var.cw_metric_namespace
  period              = 60
  statistic           = "Sum"
  threshold           = 10
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = {
    Component = "monitoring"
  }
}

# 5. Postgres connection failures observed in uvicorn log
resource "aws_cloudwatch_log_metric_filter" "db_conn_error" {
  name           = "${var.name_prefix}-db-conn-error"
  log_group_name = aws_cloudwatch_log_group.groups["/flowin/${var.environment}/uvicorn"].name
  pattern        = "OperationalError ?could not connect"

  metric_transformation {
    name          = "DBConnError"
    namespace     = var.cw_metric_namespace
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_metric_alarm" "db_conn_error" {
  alarm_name          = "${var.name_prefix}-db-conn-error"
  alarm_description   = "Postgres connection failures observed in the uvicorn log"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "DBConnError"
  namespace           = var.cw_metric_namespace
  period              = 60
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = {
    Component = "monitoring"
  }
}

# 6. Bedrock throttles
resource "aws_cloudwatch_metric_alarm" "bedrock_throttles" {
  alarm_name          = "${var.name_prefix}-bedrock-throttles"
  alarm_description   = "Bedrock InvocationThrottles for ${var.bedrock_model_id} > 0 over 5 minutes — request a quota increase."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "InvocationThrottles"
  namespace           = "AWS/Bedrock"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    ModelId = var.bedrock_model_id
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = {
    Component = "monitoring"
  }
}

# 7. Bedrock server errors
resource "aws_cloudwatch_metric_alarm" "bedrock_server_errors" {
  alarm_name          = "${var.name_prefix}-bedrock-server-errors"
  alarm_description   = "Bedrock InvocationServerErrors > 5 over 5 minutes — likely Bedrock incident."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "InvocationServerErrors"
  namespace           = "AWS/Bedrock"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  treat_missing_data  = "notBreaching"

  dimensions = {
    ModelId = var.bedrock_model_id
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = {
    Component = "monitoring"
  }
}

# 8. Estimated charges — must be authored against us-east-1.
# The AWS/Billing namespace publishes EstimatedCharges only in us-east-1; an
# alarm in any other region will be permanently INSUFFICIENT_DATA.
resource "aws_cloudwatch_metric_alarm" "billing" {
  provider = aws.useast1

  alarm_name          = "${var.name_prefix}-billing-monthly"
  alarm_description   = "Account-wide AWS estimated charges above $${var.billing_alarm_threshold_usd}. NOTE: this is the account total, not Flowin-only."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "EstimatedCharges"
  namespace           = "AWS/Billing"
  period              = 21600
  statistic           = "Maximum"
  threshold           = var.billing_alarm_threshold_usd
  treat_missing_data  = "notBreaching"

  dimensions = {
    Currency = "USD"
  }

  alarm_actions = [aws_sns_topic.alerts.arn]

  tags = {
    Component = "monitoring"
  }
}
