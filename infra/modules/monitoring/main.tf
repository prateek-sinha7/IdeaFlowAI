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
  #  - letsencrypt  : /var/log/letsencrypt/letsencrypt.log — Phase 3 item 21
  #                   (cert-renew failures + renewal-heartbeat alarms watch this).
  log_groups = [
    "/flowin/${var.environment}/nginx-access",
    "/flowin/${var.environment}/nginx-error",
    "/flowin/${var.environment}/app",
    "/flowin/${var.environment}/postgres",
    "/flowin/${var.environment}/system",
    "/flowin/${var.environment}/auth",
    "/flowin/${var.environment}/letsencrypt",
  ]

  # Path -> alarm-name-friendly slug for the inode_low for_each. "/" maps
  # to "root"; everything else strips the leading "/" and replaces inner
  # "/" with "-". Avoids trailing dashes from a naive replace().
  # Used by aws_cloudwatch_metric_alarm.inode_low (Audit D P3-4) below.
  inode_path_slug = {
    (var.root_disk_path) = var.root_disk_path == "/" ? "root" : trim(replace(var.root_disk_path, "/", "-"), "-")
    (var.data_disk_path) = var.data_disk_path == "/" ? "root" : trim(replace(var.data_disk_path, "/", "-"), "-")
  }
}

# --- Log groups -------------------------------------------------------------

resource "aws_cloudwatch_log_group" "groups" {
  for_each = toset(local.log_groups)

  name = each.value
  # Per-group retention overrides take precedence over the default. This lets
  # nginx-access (high churn, lowest forensic value) age out faster than
  # auth/auditd (which we want for incident-response forensics). Keys in the
  # map are full log-group names — value validation is in variables.tf.
  retention_in_days = lookup(var.log_retention_overrides, each.value, var.log_retention_days)
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
#  - `alerts`           in eu-central-1 (project region) — fans out every regional
#    alarm. Encrypted with the project CMK.
#
#  - `alerts_useast1`   in us-east-1 — required ONLY for the billing alarm
#    because CloudWatch alarms can publish only to a same-region SNS topic and
#    `EstimatedCharges` is emitted exclusively in us-east-1. We use the
#    AWS-managed `alias/aws/sns` key here (deliberate deviation): the project
#    CMK is region-pinned to eu-central-1, and this topic carries only billing
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
  # Owner has full control. SNS's resource-policy validator rejects the
  # `sns:*` wildcard ("action out of service scope") because the wildcard
  # expansion includes service-level actions (sns:CreateTopic, sns:ListTopics,
  # etc.) that only work via IAM identity policies, not resource policies.
  # Enumerate the resource-scoped actions explicitly.
  # Ref: https://docs.aws.amazon.com/sns/latest/dg/sns-access-policy-language-api-permissions-reference.html
  statement {
    sid    = "OwnerFullControl"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = ["arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root"]
    }

    actions = [
      "sns:AddPermission",
      "sns:DeleteTopic",
      "sns:GetDataProtectionPolicy",
      "sns:GetTopicAttributes",
      "sns:ListSubscriptionsByTopic",
      "sns:ListTagsForResource",
      "sns:Publish",
      "sns:PutDataProtectionPolicy",
      "sns:RemovePermission",
      "sns:SetTopicAttributes",
      "sns:Subscribe",
      "sns:TagResource",
      "sns:UntagResource",
    ]
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

    actions   = ["sns:Publish"]
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
  #
  # aws:SourceArn is constrained to alarms named `flowin-${env}-*` in this
  # account+region. Audit A P3 (23): without this constraint, any CloudWatch
  # alarm in the account that listed this topic in alarm_actions could
  # publish — the Service principal is the *service*, not the alarm. The
  # name-prefix scope mirrors the project's name_prefix discipline.
  statement {
    sid    = "AllowCloudWatchAlarmsPublish"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com"]
    }

    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values = [
        "arn:${data.aws_partition.current.partition}:cloudwatch:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:alarm:${var.name_prefix}-*",
      ]
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

# Topic policy mirror for the us-east-1 billing topic. Audit A P3 (23):
# without an explicit policy, the default SNS topic policy depends on the
# topic owner's principal — fine until a future operator adds a service-
# principal binding (e.g. EventBridge cross-region) at which point we'd
# rather have the constraint already in place. Only the billing alarm ARN
# is allowed; the topic carries no other publishers in this region.
data "aws_iam_policy_document" "alerts_useast1_topic" {
  provider = aws.useast1

  # See note on alerts_topic above — `sns:*` is rejected by SNS's resource-
  # policy validator. Same enumerated action list.
  statement {
    sid    = "OwnerFullControl"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = ["arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root"]
    }

    actions = [
      "sns:AddPermission",
      "sns:DeleteTopic",
      "sns:GetDataProtectionPolicy",
      "sns:GetTopicAttributes",
      "sns:ListSubscriptionsByTopic",
      "sns:ListTagsForResource",
      "sns:Publish",
      "sns:PutDataProtectionPolicy",
      "sns:RemovePermission",
      "sns:SetTopicAttributes",
      "sns:Subscribe",
      "sns:TagResource",
      "sns:UntagResource",
    ]
    resources = [aws_sns_topic.alerts_useast1.arn]
  }

  # CloudWatch billing alarm publishing on its behalf. SourceArn pinned to
  # the single billing alarm in us-east-1 — no other alarms in that region
  # should ever target this topic.
  statement {
    sid    = "AllowCloudWatchAlarmsPublish"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com"]
    }

    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alerts_useast1.arn]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values = [
        "arn:${data.aws_partition.current.partition}:cloudwatch:us-east-1:${data.aws_caller_identity.current.account_id}:alarm:${var.name_prefix}-*",
      ]
    }
  }
}

resource "aws_sns_topic_policy" "alerts_useast1" {
  provider = aws.useast1

  arn    = aws_sns_topic.alerts_useast1.arn
  policy = data.aws_iam_policy_document.alerts_useast1_topic.json
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
#
# Audit D P3-12: the original threshold=0 / evaluation_periods=1 was
# hair-trigger — any single throttle in 5 min paged on-call. Bursty quota
# pressure (which auto-recovers after backoff) is normal at the edges of
# Bedrock's regional quota; sustained pressure is the real signal worth
# paging for. Both threshold and evaluation_periods are now tunable so the
# operator can absorb short bursts without losing the page on actual quota
# exhaustion. Defaults: threshold=5 (any 5 throttles in 5 min), 2 windows
# (i.e. ~10 minutes of sustained pressure).
resource "aws_cloudwatch_metric_alarm" "bedrock_throttles" {
  alarm_name          = "${var.name_prefix}-bedrock-throttles"
  alarm_description   = "Bedrock InvocationThrottles for ${var.bedrock_model_id} > ${var.bedrock_throttles_threshold} per 5-min window for ${var.bedrock_throttles_evaluation_periods} consecutive windows — request a quota increase."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = var.bedrock_throttles_evaluation_periods
  metric_name         = "InvocationThrottles"
  namespace           = "AWS/Bedrock"
  period              = 300
  statistic           = "Sum"
  threshold           = var.bedrock_throttles_threshold
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
# (defined above), not the project's eu-central-1 alerts topic.
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
#
# Audit D P2-4 verification (JWT revocation surge / 4001 storm): the four
# `close code 4001` sites in websocket.py (lines 145, 168, 171, 285) all
# go through FastAPI/uvicorn's standard WS close handler, which emits
# `connection closed (code=4001, ...)` at INFO. The `?"close code 4001"`
# substring catches it. No separate alarm needed for JWT revocation surge
# — this filter already covers it.
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
  statistic = "Sum"
  threshold = var.ws_disconnect_threshold
  # Traffic-dependent: legitimately zero in low-traffic windows. notBreaching
  # is correct here — we don't want to page when the app is just idle.
  treat_missing_data = "notBreaching"

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
  statistic          = "SampleCount"
  threshold          = 1
  treat_missing_data = "breaching"

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = {
    Component = "monitoring"
  }
}

# 12a. Cert renewal failure — Phase 3 item 21.
#
# certbot.timer renews automatically (twice daily, randomised), but a stuck
# renewal (network blip, ACME server flake, validation failure) silently
# leaves a soon-expiring cert. The CW Agent ships /var/log/letsencrypt/*
# into the letsencrypt log group; certbot logs the literal string
# "Failed to renew certificate" on a renewal failure. Any such line in any
# 1-hour window is a page.
resource "aws_cloudwatch_log_metric_filter" "cert_renew_failure" {
  name           = "${var.name_prefix}-cert-renew-failure"
  log_group_name = aws_cloudwatch_log_group.groups["/flowin/${var.environment}/letsencrypt"].name
  # Substring match — `?` in CloudWatch's JSON-less filter syntax is "any
  # event containing this phrase".
  pattern = "?\"Failed to renew\" ?\"All renewals failed\""

  metric_transformation {
    name          = "CertRenewFailure"
    namespace     = var.cw_metric_namespace
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_metric_alarm" "cert_renew_failure" {
  alarm_name          = "${var.name_prefix}-cert-renew-failure"
  alarm_description   = "certbot logged a renewal failure in the last hour. Cert may expire — investigate /var/log/letsencrypt/letsencrypt.log on the host."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "CertRenewFailure"
  namespace           = var.cw_metric_namespace
  period              = 3600 # 1 hour
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = {
    Component = "monitoring"
  }
}

# 12b. Cert renewal heartbeat — covers the "stuck silent" case the failure
# alarm above misses. If certbot.timer is dead, *neither* "Failed to renew"
# nor "Cert not yet due" / "successfully renewed" will appear in the log,
# so the failure-only alarm stays OK while the cert silently approaches
# expiry. This heartbeat alarm fires when the success-side filter sees
# fewer than 1 sample in 30 days. Cert lifetime is 90 days; 30 days of
# silence is a strong signal that something is wrong.
#
# treat_missing_data = "breaching" — absence IS the alert (same pattern as
# pg_dump_heartbeat).
resource "aws_cloudwatch_log_metric_filter" "cert_renew_success" {
  name           = "${var.name_prefix}-cert-renew-success"
  log_group_name = aws_cloudwatch_log_group.groups["/flowin/${var.environment}/letsencrypt"].name
  # certbot logs "Cert not yet due for renewal" on a no-op run, and
  # "successfully renewed" / "renewed" on a real renewal.
  pattern = "?\"Cert not yet due for renewal\" ?\"successfully renewed\" ?\"Renewing\""

  metric_transformation {
    name          = "CertRenewSuccess"
    namespace     = var.cw_metric_namespace
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_metric_alarm" "cert_renew_heartbeat" {
  alarm_name = "${var.name_prefix}-cert-renew-heartbeat-stale"
  # CloudWatch caps EvaluationPeriods * Period at 604_800s (7 days) when
  # Period >= 3600. The original design (period=30d, eval=1) violated that.
  # We're at the inclusive boundary: 86_400 * 7 = 604_800 = 7 days, which
  # is the longest single-alarm window CloudWatch will accept here. Cert
  # lifetime is 90 days, so 7 days of timer silence is still well inside
  # the renewal headroom (cert renewal triggers at T-30d).
  alarm_description   = "certbot has not logged any renewal activity in 7 days — the renew timer may be stuck. Cert lifetime is 90 days; investigate before the cert expires."
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 7
  metric_name         = "CertRenewSuccess"
  namespace           = var.cw_metric_namespace
  period              = 86400 # 1 day
  # SampleCount: absence of any matching log line across 7 consecutive
  # daily windows fires.
  statistic          = "SampleCount"
  threshold          = 1
  treat_missing_data = "breaching"

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = {
    Component = "monitoring"
  }
}

# 13. Agent error rate — Audit D P2-2.
#
# The pipeline executor logs `AGENT [%d/%d] FAILED — %s: %s` at error level
# (backend/app/agents/pipeline.py:178) when an agent invocation raises;
# upstream that becomes an `agent_error` event in the WS stream
# (pipeline.py:181). Sustained high agent_error rate is meaningful:
# Bedrock throttling spillover, prompt-engineering regressions, post-A3
# cancel storms, etc. The pattern below ORs three substrings so we catch
# both the logger line and the JSON event payload.
resource "aws_cloudwatch_log_metric_filter" "agent_error_rate" {
  name           = "${var.name_prefix}-agent-error-rate"
  log_group_name = aws_cloudwatch_log_group.groups["/flowin/${var.environment}/app"].name
  # Any of: the emoji-free FAILED log line, the CONFIG ERROR variant, or the
  # `agent_error` event-type field. CONFIG ERROR is included because A1
  # config errors break the pipeline harder than a recoverable runtime
  # failure but emit the same operational concern (re: prompt regressions).
  pattern = "?\"AGENT [\" ?\"FAILED\" ?\"CONFIG ERROR\" ?\"agent_error\""

  metric_transformation {
    name          = "AgentErrorCount"
    namespace     = var.cw_metric_namespace
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_metric_alarm" "agent_error_high" {
  alarm_name          = "${var.name_prefix}-agent-error-high"
  alarm_description   = "Sustained agent_error rate (>${var.agent_error_rate_threshold} per 5-min window for 2 consecutive windows). Possible Bedrock throttling, prompt regression, or upstream LLM degradation."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "AgentErrorCount"
  namespace           = var.cw_metric_namespace
  period              = 300
  statistic           = "Sum"
  threshold           = var.agent_error_rate_threshold
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = {
    Component = "monitoring"
  }
}

# 14. Stuck running WorkflowRun rows — Audit D P2-3.
#
# A4 fixed cancel-pipeline so cancelled rows reach a terminal state. But a
# row that is genuinely stuck (orchestrator crashed without cancellation,
# DB connection dropped between status updates, etc.) still goes unnoticed.
#
# Approach: a small SQL-driven custom metric. The on-host
# `flowin-stuck-workflows-check.timer` (docs/SIMPLE_AWS_DEPLOYMENT.md
# Appendix B / Appendix D) runs every 15 min, queries Postgres for
# WorkflowRun rows in `running` for >60 min, and pushes the count as
# `Flowin/App::StuckRunningWorkflows`. Alarm fires when the count > 0
# for the whole evaluation window (period covers ~2 publishes).
#
# treat_missing_data = "missing" rather than "breaching" — absence is
# benign in low-traffic windows and we already alarm separately on a
# dead host (cpu_high, mem_high — both treat_missing_data="breaching").
resource "aws_cloudwatch_metric_alarm" "stuck_workflows" {
  alarm_name          = "${var.name_prefix}-stuck-running-workflows"
  alarm_description   = "WorkflowRun rows stuck in `running` state for >60 min. Likely an orchestrator crash, DB drop, or A4 regression. Investigate immediately."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "StuckRunningWorkflows"
  namespace           = var.cw_metric_namespace
  period              = var.stuck_workflows_check_period
  statistic           = "Maximum"
  threshold           = var.stuck_workflows_threshold
  treat_missing_data  = "missing"

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = {
    Component = "monitoring"
  }
}

# 15. Inode usage low — Audit D P3-4.
#
# disk_used_percent (the alarm above on root and data) measures bytes used
# only — a partition can run out of inodes long before it runs out of
# bytes, and the kernel will refuse new file creates with ENOSPC even
# though `df -h` shows free space. Many small files (logs, journald
# fragments, npm/pip caches, postgres temp) are the typical cause.
#
# CW Agent's disk plugin only emits absolute inode counts — `disk_inodes_free`,
# `disk_inodes_total`, `disk_inodes_used`. There's no `_percent` variant
# (the agent rejects it as an invalid measurement name); CloudWatch Metric
# Math would be needed to derive a percentage, and the added fragility isn't
# worth it for a single-EC2 deploy. Use an absolute-count threshold instead.
#
# Threshold 1_000_000: xfs on 50-100 GB volumes typically reports millions
# of inodes free; this fires when something is creating files at runaway
# rate (broken log rotation, runaway test artifacts, etc.) and free inodes
# drop into 6-figure territory. Well before ENOSPC kicks in. Adjust if a
# different filesystem or volume size makes 1M unreasonable.
#
# (Slug map for the alarm name lives in the top `locals` block.)
resource "aws_cloudwatch_metric_alarm" "inode_low" {
  for_each = toset([var.root_disk_path, var.data_disk_path])

  alarm_name          = "${var.name_prefix}-inode-low-${local.inode_path_slug[each.key]}"
  alarm_description   = "Free inodes < 1_000_000 on ${each.key}. Many small files (or runaway logs) — investigate before file creates start failing with ENOSPC."
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 2
  metric_name         = "disk_inodes_free"
  namespace           = var.cw_metric_namespace
  period              = 300
  statistic           = "Average"
  threshold           = 1000000
  treat_missing_data  = "breaching"

  # Match the disk_used_percent alarm dimensions: InstanceId + path. The CW
  # Agent also emits device + fstype but those add fragility (a remount
  # changes them) for no extra precision in our single-instance design.
  dimensions = {
    InstanceId = var.instance_id
    path       = each.key
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = {
    Component = "monitoring"
  }
}
