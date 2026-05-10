locals {
  # Log group names match the destinations the on-host CloudWatch Agent ships to
  # (see docs/SIMPLE_AWS_DEPLOYMENT.md §10.1). Keeping these in lock-step is
  # load-bearing: a name drift means alarms watch a group nothing writes to.
  #
  #  - nginx-access : /var/log/nginx/access.log (target of the 5xx metric filter)
  #  - nginx-error  : /var/log/nginx/error.log
  #  - app          : journald-shipped uvicorn + Next.js combined log group
  #                   (filterable per unit via _SYSTEMD_UNIT)
  #  - postgres     : /var/log/postgresql/postgresql-16-main.log
  #  - system       : journald system slice
  #  - auth         : /var/log/auth.log (sshd / sudo)
  log_groups = [
    "/flowin/${var.environment}/nginx-access",
    "/flowin/${var.environment}/nginx-error",
    "/flowin/${var.environment}/app",
    "/flowin/${var.environment}/postgres",
    "/flowin/${var.environment}/system",
    "/flowin/${var.environment}/auth",
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

  lifecycle {
    # Log groups carry forensic and audit data. Recreating them after an
    # accidental destroy loses the historical stream and breaks every
    # metric-filter that points at them. Operators should `terraform state
    # rm` deliberately if a rename is required. Note: `dynamic` blocks are
    # disallowed inside `lifecycle`, but a static block alongside `for_each`
    # works — every key in the map gets the same protection.
    prevent_destroy = true
  }
}

# --- SNS topics -------------------------------------------------------------
#
# We need two topics:
#
#  - `alerts`           in eu-west-2 (project region) — fans out every regional
#    alarm. Encrypted with the project CMK.
#
#  - `alerts_useast1`   in us-east-1 — required ONLY for the billing alarm
#    because CloudWatch alarms can publish only to a same-region SNS topic and
#    `EstimatedCharges` is emitted exclusively in us-east-1. We use the
#    AWS-managed `alias/aws/sns` key here (deliberate deviation): the project
#    CMK is region-pinned to eu-west-2, and this topic carries only billing
#    alarm payloads (account ID + USD threshold) — no PII, no application
#    secrets, no log content. The added-managed-key risk is small; the
#    additional-region CMK cost and operational surface are not worth it for
#    one alarm whose payload is operational metadata.

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

# Topic policy: lets the AWS Backup service principal publish job-state
# notifications, and lets CloudWatch Events / EventBridge publish on behalf
# of CloudWatch alarms. The default SNS topic policy restricts Publish to
# the topic owner — without this, aws_backup_vault_notifications gets no
# events into the topic.
#
# The Confused-Deputy guards are aws:SourceAccount (and aws:SourceArn for
# the EventBridge case where ARN shape is well-defined). Backup events come
# from the vault itself, so we constrain the SourceArn to vault + plan ARNs
# in this account+region.
data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_region" "current" {}

data "aws_iam_policy_document" "alerts_topic" {
  # Owner has full control (canonical default).
  statement {
    sid    = "OwnerFullControl"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = ["arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root"]
    }

    actions   = ["SNS:*"]
    resources = [aws_sns_topic.alerts.arn]
  }

  # AWS Backup vault notifications — required so aws_backup_vault_notifications
  # can deliver BACKUP_JOB_FAILED / RESTORE_JOB_FAILED into this topic.
  statement {
    sid    = "AllowBackupServicePublish"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["backup.amazonaws.com"]
    }

    actions   = ["SNS:Publish"]
    resources = [aws_sns_topic.alerts.arn]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    # Vault ARNs only — narrows further than the account check.
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values = [
        "arn:${data.aws_partition.current.partition}:backup:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:backup-vault:*",
      ]
    }
  }

  # CloudWatch alarms publishing into this same topic — the alarms in this
  # module specify SNS:Publish via alarm_actions, which in CloudWatch lingo
  # means "the cloudwatch service publishes on the alarm's behalf".
  statement {
    sid    = "AllowCloudWatchAlarmsPublish"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com"]
    }

    actions   = ["SNS:Publish"]
    resources = [aws_sns_topic.alerts.arn]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_sns_topic_policy" "alerts" {
  arn    = aws_sns_topic.alerts.arn
  policy = data.aws_iam_policy_document.alerts_topic.json
}

# --- AWS Backup job-state notifications ------------------------------------
#
# Hooks the alerts SNS topic into the project's AWS Backup vault so AWS
# Backup itself fires on job-state changes (FAILED / EXPIRED / RESTORE
# FAILED). Cleaner than an EventBridge rule + target since the binding is
# on the vault.
#
# Lives here rather than in modules/backups to break a module-output cycle:
# compute consumes backups.backup_bucket_name; monitoring consumes
# compute.instance_id; placing this resource in backups would close the
# triangle. The vault name is a one-way input (backups -> monitoring), so
# it doesn't reintroduce the cycle.
#
# Empty `var.backup_vault_name` disables the resource — used in LocalStack
# and useful as an escape hatch when bootstrap order matters.
resource "aws_backup_vault_notifications" "alerts" {
  count = length(var.backup_vault_name) > 0 ? 1 : 0

  backup_vault_name = var.backup_vault_name
  sns_topic_arn     = aws_sns_topic.alerts.arn

  # Three states cover the failure surface: FAILED is the routine error,
  # EXPIRED means the backup job ran out of its completion window without
  # finishing. RESTORE_JOB_FAILED ties in the test-restore drill workflow.
  backup_vault_events = [
    "BACKUP_JOB_FAILED",
    "BACKUP_JOB_EXPIRED",
    "RESTORE_JOB_FAILED",
  ]

  # The notifications API requires the SNS topic policy to allow
  # backup.amazonaws.com to publish — see aws_sns_topic_policy.alerts.
  depends_on = [aws_sns_topic_policy.alerts]
}

# Billing-alarm topic in us-east-1.
resource "aws_sns_topic" "alerts_useast1" {
  provider = aws.useast1

  name = "${var.name_prefix}-alerts-useast1"
  # AWS-managed key — see header comment above for the deviation rationale.
  kms_master_key_id = "alias/aws/sns"

  tags = {
    Name      = "${var.name_prefix}-alerts-useast1"
    Component = "monitoring"
  }
}

resource "aws_sns_topic_subscription" "email_useast1" {
  count    = length(var.alert_email) > 0 ? 1 : 0
  provider = aws.useast1

  topic_arn = aws_sns_topic.alerts_useast1.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# --- CloudWatch alarms ------------------------------------------------------

# Host alarms 1-3b (CPU / memory / root-disk / data-disk) all use
# `treat_missing_data = "breaching"`. Rationale: the metrics are
# CloudWatch-Agent-emitted. When the agent dies, the metrics go absent —
# they don't go to zero. With `notBreaching`, a dead agent leaves every
# host alarm in OK state while the disk fills, OOM-killer fires, etc. With
# `breaching`, missing data pages on-call (which is what we want — "I
# can't see the host" *is* the alert).

# 1. CPU sustained high
resource "aws_cloudwatch_metric_alarm" "cpu_high" {
  alarm_name          = "${var.name_prefix}-cpu-high"
  alarm_description   = "Sustained host CPU above ${var.cpu_threshold_percent}% for 15 minutes (breaching on missing data — covers a dead CloudWatch Agent)"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 3
  metric_name         = "cpu_usage_user"
  namespace           = var.cw_metric_namespace
  period              = 300
  statistic           = "Average"
  threshold           = var.cpu_threshold_percent
  treat_missing_data  = "breaching"

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
  alarm_description   = "Memory above ${var.memory_threshold_percent}% for 10 minutes (breaching on missing data — covers a dead CloudWatch Agent)"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "mem_used_percent"
  namespace           = var.cw_metric_namespace
  period              = 300
  statistic           = "Average"
  threshold           = var.memory_threshold_percent
  treat_missing_data  = "breaching"

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
  alarm_description   = "Root filesystem disk usage above ${var.disk_threshold_percent}% (breaching on missing data — covers a dead CloudWatch Agent)"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "disk_used_percent"
  namespace           = var.cw_metric_namespace
  period              = 300
  statistic           = "Maximum"
  threshold           = var.disk_threshold_percent
  treat_missing_data  = "breaching"

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
  alarm_description   = "Postgres data filesystem disk usage above ${var.disk_threshold_percent}% (breaching on missing data — covers a dead CloudWatch Agent)"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "disk_used_percent"
  namespace           = var.cw_metric_namespace
  period              = 300
  statistic           = "Maximum"
  threshold           = var.disk_threshold_percent
  treat_missing_data  = "breaching"

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
  log_group_name = aws_cloudwatch_log_group.groups["/flowin/${var.environment}/nginx-access"].name
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

# 5. Postgres connection failures observed in the unified backend log (journald)
resource "aws_cloudwatch_log_metric_filter" "db_conn_error" {
  name           = "${var.name_prefix}-db-conn-error"
  log_group_name = aws_cloudwatch_log_group.groups["/flowin/${var.environment}/app"].name
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
#
# The alarm and its target SNS topic must live in the same region — alarms
# cannot publish across regions. So this alarm fans out to alerts_useast1
# (defined above), not the project's eu-west-2 alerts topic.
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

  alarm_actions = [aws_sns_topic.alerts_useast1.arn]
  ok_actions    = [aws_sns_topic.alerts_useast1.arn]

  tags = {
    Component = "monitoring"
  }
}

# 9. WebSocket disconnect spike — derived from the unified backend log group.
#
# The backend logs disconnects at info level: `WebSocket disconnected: user=…`
# (backend/app/api/websocket.py:439) when WebSocketDisconnect propagates up;
# the FastAPI close path also issues `code=4001` for auth failures and
# `code=1011` for internal errors. We catch all four shapes via the OR'd
# pattern; CloudWatch's syntax for "any of these phrases anywhere in the
# event" is `?phrase1 ?phrase2 ?phrase3` (each ? token is a substring match).
resource "aws_cloudwatch_log_metric_filter" "ws_disconnect" {
  name           = "${var.name_prefix}-ws-disconnect"
  log_group_name = aws_cloudwatch_log_group.groups["/flowin/${var.environment}/app"].name
  pattern        = "?\"WebSocket disconnected\" ?\"WebSocketDisconnect\" ?\"close code 4001\" ?\"close code 1011\""

  metric_transformation {
    name          = "WSDisconnect"
    namespace     = var.cw_metric_namespace
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_metric_alarm" "ws_disconnect_spike" {
  alarm_name          = "${var.name_prefix}-ws-disconnect-spike"
  alarm_description   = "Spike in WebSocket disconnects — possible JWT-revocation surge, frontend bug, or upstream failure."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "WSDisconnect"
  namespace           = var.cw_metric_namespace
  period              = 300
  # Sum is the canonical statistic for a count-style metric filter.
  statistic           = "Sum"
  threshold           = var.ws_disconnect_threshold
  # Traffic-dependent: legitimately zero in low-traffic windows. notBreaching
  # is correct here — we don't want to page when the app is just idle.
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = {
    Component = "monitoring"
  }
}

# 10. Bedrock InputTokenCount daily total — cost-runaway detector.
#
# Covers: cancel-pipeline failures still streaming, frontend retry storms,
# accidental long-context fan-out. Threshold expressed as a daily input-
# token cap. Haiku 4.5 list price ~$4 input + ~$20 output per 1M tokens at
# the time of writing, so 5M input ≈ ~$20 input + variable output. Tunable
# in tfvars.
#
# Dimensions on whichever ModelId the SDK actually invokes — for the EU
# inference profile that's the profile ID, NOT the foundation-model ID.
# `var.bedrock_model_id` is the post-P0 fix value (effective_model_id from
# envs/prod/locals.tf).
resource "aws_cloudwatch_metric_alarm" "bedrock_tokens_daily" {
  alarm_name          = "${var.name_prefix}-bedrock-tokens-daily"
  alarm_description   = "Bedrock input-token consumption above the daily cap. Cost-runaway detector — covers the cancel-pipeline failure mode and any unexpected traffic surge."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "InputTokenCount"
  namespace           = "AWS/Bedrock"
  period              = 86400 # 24 hours
  statistic           = "Sum"
  threshold           = var.bedrock_daily_token_threshold
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

# 11. pg_dump heartbeat — RPO 1h backstop.
#
# The `flowin-pg-dump` systemd timer (docs/SIMPLE_AWS_DEPLOYMENT.md
# §11.2 / Appendix B.3) runs hourly and PUTs to s3://.../postgres/<TS>/
# under SSE-KMS. After a successful upload, the script publishes a
# CloudWatch custom metric `Flowin/Backups::PgDumpHeartbeat = 1` —
# absence of that metric for >2h means the timer is stuck or the host is
# unreachable, both of which jeopardise the documented RPO 1h.
#
# treat_missing_data = "breaching" is the *correct* setting here — the
# whole point is that absence IS the alert signal.
#
# (The IAM instance role already grants cloudwatch:PutMetricData on
# Resource: "*" — see infra/modules/iam/main.tf::cw_agent_describes —
# because that API doesn't support resource-level scoping.)
resource "aws_cloudwatch_metric_alarm" "pg_dump_heartbeat" {
  alarm_name          = "${var.name_prefix}-pg-dump-heartbeat-stale"
  alarm_description   = "No successful pg_dump in the last 2 hours. RPO 1h is at risk — check the flowin-pg-dump.timer / instance health."
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "PgDumpHeartbeat"
  namespace           = "Flowin/Backups"
  period              = 7200 # 2 hours
  # SampleCount on a count metric — number of put-metric-data calls in
  # the period. Less than 1 in two hours means at least two hourly runs
  # have failed (or the host is dead).
  statistic           = "SampleCount"
  threshold           = 1
  treat_missing_data  = "breaching"

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = {
    Component = "monitoring"
  }
}
