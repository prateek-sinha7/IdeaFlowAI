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

# --- C2-1: CloudTrail data-event audit trail --------------------------------
#
# Audit C/TF-Security HIGH #9: there is no actionable signal when an
# unauthorized identity calls `ssm:GetParameter*` against the SECRET_KEY (or
# any other /flowin/${env}/* SecureString) or `kms:Decrypt` against the
# project CMK. CloudTrail's default management-event capture records those
# calls but CloudTrail data events (Put/Get on individual SSM parameters,
# Decrypt against individual KMS keys) are OFF BY DEFAULT and not captured
# by the AWS account-default trail.
#
# This trail captures data events specifically for:
#   - SSM Put/Get* on the /flowin/${var.environment}/* parameter prefix
#     (the namespace containing SECRET_KEY, DATABASE_PASSWORD, LANGSMITH_API_KEY,
#     and every other application secret).
#   - KMS Decrypt against the project CMK (used by the EC2 instance role's
#     boto3 calls to read SecureStrings).
#
# Trail delivers to S3 (CloudTrail's mandatory durable sink) AND mirrors
# events into a KMS-encrypted CloudWatch Logs group so two
# `aws_cloudwatch_log_metric_filter` resources can derive metrics:
#   - UnexpectedSecretRead   — any Get* on /flowin/${env}/* from a principal
#                              that is NOT the EC2 instance role.
#   - UnexpectedKmsDecrypt   — any Decrypt against the project CMK from a
#                              principal that is NOT the EC2 instance role.
#
# Two `aws_cloudwatch_metric_alarm` resources fire on SUM > 0 over a 5-min
# window (period=300s, evaluation_periods=1; both well inside the
# `period × evaluation_periods ≤ 604_800s (7d)` cap CloudWatch enforces on
# alarms whose Period >= 60s).
#
# Cost estimate (eu-central-1 Sept-2025 list):
#   - CloudTrail data events: $0.10 per 100,000 events.
#   - Project workload generates ~5-10 data events per backend restart
#     (flowin-load-secrets runs `aws ssm get-parameters-by-path` once on
#     each app boot — 1 SSM Get + N KMS Decrypt + ~2 cwagent SSM reads),
#     and ~tens per deploy (`terraform apply` writes the SecureStrings).
#   - Steady-state: ~100-200 data events/day. Worst case 200/day × 30 =
#     6_000 events/mo → $0.006/mo for data events.
#   - S3 storage: trail JSON GZ-compressed ~1KB/event × 6_000/mo = ~6MB →
#     <$0.001/mo.
#   - CloudWatch Logs ingest: $0.50/GB ingest + $0.03/GB storage. 6_000
#     events × ~2KB JSON = ~12MB ingest = $0.006/mo.
#   - Grand total: well under $1/month for the audit trail. (Compare to
#     SECRET_KEY rotation cost if it's exfiltrated and not detected: 1 PR
#     to rotate + an unknown incident-response budget.)
#
# Deliberately NOT a multi-region trail: the project is single-region
# (eu-central-1); a multi-region trail captures KMS Decrypt + SSM
# data-events in every region but the project CMK exists only here and
# /flowin/${env}/* SSM parameters live only here. Multi-region would
# double-count for $0 benefit. is_multi_region_trail = false.
#
# Multi-trail check: no other aws_cloudtrail resources exist in this TF
# tree. Grep confirmed `aws_cloudtrail` is absent from every modules/* and
# envs/* main.tf. So this is the project's first trail; no need to fold
# the data-event selectors into an existing trail's event_selector list.
# The LocalStack endpoints map already registers `cloudtrail`, so plan/
# apply works in both envs.

# CloudWatch Log group the trail mirrors into for metric-filter
# derivation. Lives outside the for_each-managed `log_groups` set above so
# the retention (var.audit_trail_log_retention_days, default 90) can
# diverge from operational logs. KMS-encrypted with the project CMK —
# the existing AllowCloudWatchLogs grant covers any log group under
# /flowin/${env}/* (see modules/kms/main.tf).
resource "aws_cloudwatch_log_group" "audit_trail" {
  name              = "/flowin/${var.environment}/cloudtrail-audit"
  retention_in_days = var.audit_trail_log_retention_days
  kms_key_id        = var.kms_key_arn

  tags = {
    Name      = "/flowin/${var.environment}/cloudtrail-audit"
    Component = "monitoring"
  }

  lifecycle {
    # Same rationale as the operational log groups: forensic capture, must
    # not vanish on a stray `terraform destroy`. Operator must
    # `terraform state rm` deliberately to recycle.
    #
    # Cross-resource asymmetry — DELIBERATE:
    #   - This log group:      prevent_destroy = true
    #   - aws_cloudtrail.audit: prevent_destroy = false (see below)
    #   - aws_s3_bucket.audit_trail: prevent_destroy = false (see below)
    #
    # Why protect ONLY the log group and not the trail/bucket:
    # (a) The log group is where the metric filters + alarms read from;
    #     losing it silently breaks the SECRET_KEY-exfil alarm path with no
    #     visible signal. The trail can be reconstructed from `var.name_prefix`
    #     and the bucket from CloudTrail's standard delivery shape, but the
    #     log-stream history (CW Logs is the durable forensic record between
    #     trail apply cycles) cannot be retroactively reconstructed.
    # (b) The trail topology is operationally fluid: switching to a multi-
    #     region trail, moving to event-data-store, or adding more advanced
    #     event selectors all require destroying + recreating the trail. A
    #     prevent_destroy on the trail would block those legitimate
    #     refactors and force state-surgery on every change.
    # (c) The bucket is the trail's own delivery sink — it MUST be replaced
    #     together with the trail (the trail name is encoded in the
    #     AWSCloudTrailWrite bucket-policy condition's SourceArn). Pinning
    #     prevent_destroy on the bucket but not the trail would create
    #     a perpetual drift between the two.
    # See infra/envs/localstack/destroy.sh: this log group is in the
    # protected state-rm list precisely because of prevent_destroy = true.
    prevent_destroy = true
  }
}

# IAM role CloudTrail assumes to put events into the CW Logs log group.
# CloudTrail can only write to a log group via this delivery role (not via
# the trail's own service principal); this role is therefore narrow:
# logs:CreateLogStream + logs:PutLogEvents on exactly one log group.
data "aws_iam_policy_document" "audit_trail_assume" {
  statement {
    sid     = "CloudTrailAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }

    # Confused-deputy guard — pin to trails in this account+region.
    # The SourceArn pins to the EXACT trail name (`${var.name_prefix}-audit`)
    # rather than a wildcard: the trail name is derived independently from
    # `var.name_prefix` on both sides of this string boundary (string-level
    # coupling, not resource-attribute coupling), so there's no resource-
    # graph cycle. Same pattern as the bucket-policy SourceArn pins below.
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values = [
        "arn:${data.aws_partition.current.partition}:cloudtrail:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:trail/${var.name_prefix}-audit",
      ]
    }
  }
}

resource "aws_iam_role" "audit_trail_to_logs" {
  name               = "${var.name_prefix}-cloudtrail-to-logs"
  assume_role_policy = data.aws_iam_policy_document.audit_trail_assume.json

  tags = {
    Name      = "${var.name_prefix}-cloudtrail-to-logs"
    Component = "monitoring"
  }
}

data "aws_iam_policy_document" "audit_trail_to_logs" {
  statement {
    sid    = "WriteAuditTrailLogStream"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    # Trail-delivery streams are named by AWS as `<acct>_CloudTrail_<region>`
    # under the log group. We can't predict the stream name at TF plan
    # time, so scope to log-stream:* under the audit-trail group ARN.
    resources = ["${aws_cloudwatch_log_group.audit_trail.arn}:*"]
  }
}

resource "aws_iam_role_policy" "audit_trail_to_logs" {
  name   = "${var.name_prefix}-cloudtrail-to-logs"
  role   = aws_iam_role.audit_trail_to_logs.id
  policy = data.aws_iam_policy_document.audit_trail_to_logs.json
}

# Mirror the discipline used by modules/iam: lock the role's inline-policy
# set to exactly this one document, so any out-of-band addition gets
# reverted on the next `terraform apply`. The role exists ONLY to let
# CloudTrail write to one log group; an out-of-band PutRolePolicy could
# in principle add `s3:*` (the role has no resource-policy constraint),
# and that would be invisible without this exclusive guard.
resource "aws_iam_role_policies_exclusive" "audit_trail_to_logs" {
  role_name    = aws_iam_role.audit_trail_to_logs.name
  policy_names = [aws_iam_role_policy.audit_trail_to_logs.name]
}

# S3 bucket CloudTrail uses as its durable sink. CloudTrail REQUIRES an
# S3 bucket — there is no S3-less trail. Kept separate from the project
# backup bucket (modules/backups) for two reasons: (a) bucket policy shape
# is CloudTrail-specific (`AWSCloudTrailAclCheck` + `AWSCloudTrailWrite`
# statements with `aws:SourceArn` pinning to the trail ARN); (b) the
# backup bucket has `prevent_destroy=true` and forcing a CloudTrail
# topology change later would be awkward against that. A separate bucket
# gives operational independence.
#
# Bucket carries `prevent_destroy = false` DELIBERATELY (cross-resource
# asymmetry — see the matching note on aws_cloudwatch_log_group.audit_trail):
# forensic CloudTrail logs are far less load-bearing than the database/skills
# backups in modules/backups, and an operator must be able to roll the trail
# topology (e.g. switching to a multi-region trail, moving to event-data-
# store) without state-surgery on a `prevent_destroy = true` bucket. The
# trail name is encoded in this bucket's policy via SourceArn, so the bucket
# MUST move together with the trail when topology changes.
#
# Tamper-evidence:
#   - Versioning is ENABLED on the bucket below (`aws_s3_bucket_versioning`).
#     With CloudTrail's `enable_log_file_validation = true`, an attacker with
#     `s3:DeleteObject` who tries to wipe BOTH the log files AND the digest
#     files in the same window now leaves delete-markers; the underlying
#     versions survive for forensic recovery.
#   - Lifecycle below transitions objects to GLACIER at 30d and expires at
#     `var.audit_trail_log_retention_s3_days` (default 365) so the S3 record
#     outlives the CW Logs metric-filter window (default 90d) by ~4x.
#
# force_destroy gating: `var.audit_trail_bucket_force_destroy` (default false
# in prod, true in localstack tfvars) makes `terraform destroy` empty the
# bucket before deletion. Mirrors the backups-bucket pattern.
resource "aws_s3_bucket" "audit_trail" {
  bucket        = "${var.name_prefix}-cloudtrail-${data.aws_caller_identity.current.account_id}"
  force_destroy = var.audit_trail_bucket_force_destroy

  tags = {
    Name      = "${var.name_prefix}-cloudtrail"
    Component = "monitoring"
  }
}

# Versioning — enables tamper-evidence: an attacker who deletes log + digest
# files in the same window still leaves delete-markers; the underlying
# versions remain recoverable via S3's version API. The backups bucket uses
# the same pattern (modules/backups/main.tf::aws_s3_bucket_versioning).
resource "aws_s3_bucket_versioning" "audit_trail" {
  bucket = aws_s3_bucket.audit_trail.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_ownership_controls" "audit_trail" {
  bucket = aws_s3_bucket.audit_trail.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "audit_trail" {
  bucket = aws_s3_bucket.audit_trail.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# SSE-KMS with the project CMK — the CloudTrail trail itself sets
# kms_key_id, but the bucket-level encryption is independent of trail
# encryption and aligns the storage encryption shape with the backup
# bucket (modules/backups/main.tf).
resource "aws_s3_bucket_server_side_encryption_configuration" "audit_trail" {
  bucket = aws_s3_bucket.audit_trail.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true
  }
}

# Lifecycle — keep S3 storage cost bounded over time. CloudTrail JSON.gz
# objects are ~1KB/event and accumulate forever without an explicit policy.
# Pattern matches modules/backups/main.tf::aws_s3_bucket_lifecycle_configuration:
#   - Current objects transition to GLACIER at 30d (cheap cold storage; the
#     last 30 days are still in STANDARD for quick forensic access).
#   - Current objects expire at var.audit_trail_log_retention_s3_days (365d
#     default — ~4x the CW Logs 90d window, so the S3 record outlives the
#     metric-filter / alarm replay window).
#   - Noncurrent versions (from delete-marker scenarios — see versioning
#     resource above) expire 30 days after they become noncurrent. This
#     preserves the tamper-evidence forensic window without paying storage
#     for ancient noncurrent-version churn.
#   - Incomplete multipart uploads abort at 7d (matches backups bucket).
resource "aws_s3_bucket_lifecycle_configuration" "audit_trail" {
  bucket = aws_s3_bucket.audit_trail.id

  # Versioning must be enabled before noncurrent_version_expiration is
  # legal in a lifecycle rule. Same constraint as the backups bucket.
  depends_on = [aws_s3_bucket_versioning.audit_trail]

  rule {
    id     = "expire-cloudtrail-deliveries"
    status = "Enabled"

    filter {} # apply to whole bucket

    transition {
      days          = 30
      storage_class = "GLACIER"
    }

    expiration {
      days = var.audit_trail_log_retention_s3_days
    }

    noncurrent_version_expiration {
      noncurrent_days = 30
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# Bucket-policy statements CloudTrail requires to write deliveries:
#   - AWSCloudTrailAclCheck   — the trail's pre-write GetBucketAcl
#   - AWSCloudTrailWrite      — the trail's PutObject delivery, scoped to
#                               AWSLogs/<acct>/ prefix and bucket-owner-
#                               full-control as required by CT.
# Both pin `aws:SourceArn` to the EXACT trail name (string-level coupling
# via `var.name_prefix`, no resource-graph cycle — same pattern as the
# trust-policy SourceArn above). This is the confused-deputy guard: without
# it any CloudTrail in any account that knew this bucket name could target
# it.
#
# Defense-in-depth Deny statements (symmetric with modules/backups bucket
# policy):
#   - DenyInsecureTransport   — requires TLS for any access
#   - DenyUnencryptedPuts     — requires aws:kms SSE on every PutObject
#   - DenyWrongKmsKey         — pins SSE-KMS key id to the project CMK
# Today only the cloudtrail.amazonaws.com service principal CAN write (the
# default S3 deny implicitly blocks everything else), so the two
# encryption-related Denies are belt-and-braces against a future change
# that opens additional writers (e.g. an accidentally-added backup-style
# `Allow s3:PutObject` for the instance role). CloudTrail itself always
# sets aws:kms SSE via the trail's kms_key_id, so the Denies don't block
# legitimate deliveries.
data "aws_iam_policy_document" "audit_trail_bucket" {
  statement {
    sid     = "AWSCloudTrailAclCheck"
    effect  = "Allow"
    actions = ["s3:GetBucketAcl"]

    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }

    resources = [aws_s3_bucket.audit_trail.arn]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceArn"
      values = [
        "arn:${data.aws_partition.current.partition}:cloudtrail:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:trail/${var.name_prefix}-audit",
      ]
    }
  }

  statement {
    sid     = "AWSCloudTrailWrite"
    effect  = "Allow"
    actions = ["s3:PutObject"]

    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }

    resources = [
      "${aws_s3_bucket.audit_trail.arn}/AWSLogs/${data.aws_caller_identity.current.account_id}/*",
    ]

    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-acl"
      values   = ["bucket-owner-full-control"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceArn"
      values = [
        "arn:${data.aws_partition.current.partition}:cloudtrail:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:trail/${var.name_prefix}-audit",
      ]
    }
  }

  # Deny insecure transport — same shape as modules/backups' bucket policy.
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    resources = [
      aws_s3_bucket.audit_trail.arn,
      "${aws_s3_bucket.audit_trail.arn}/*",
    ]
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }

  # Deny PutObject without aws:kms SSE — defense in depth in case future
  # changes open additional writers beyond the cloudtrail.amazonaws.com
  # principal. Modeled on modules/backups/main.tf::DenyUnencryptedPuts.
  statement {
    sid     = "DenyUnencryptedPuts"
    effect  = "Deny"
    actions = ["s3:PutObject"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    resources = ["${aws_s3_bucket.audit_trail.arn}/*"]
    condition {
      test     = "StringNotEquals"
      variable = "s3:x-amz-server-side-encryption"
      values   = ["aws:kms"]
    }
  }

  # Deny PutObject when SSE-KMS key id is NOT the project CMK — pins
  # encryption to a key we control. Uses StringNotEqualsIfExists so a
  # genuinely-missing header (caught by DenyUnencryptedPuts) doesn't double-
  # fire here. Modeled on modules/backups/main.tf::DenyWrongKmsKey.
  statement {
    sid     = "DenyWrongKmsKey"
    effect  = "Deny"
    actions = ["s3:PutObject"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    resources = ["${aws_s3_bucket.audit_trail.arn}/*"]
    condition {
      test     = "StringNotEqualsIfExists"
      variable = "s3:x-amz-server-side-encryption-aws-kms-key-id"
      values   = [var.kms_key_arn]
    }
  }
}

resource "aws_s3_bucket_policy" "audit_trail" {
  bucket = aws_s3_bucket.audit_trail.id
  policy = data.aws_iam_policy_document.audit_trail_bucket.json
}

# The trail itself.
#
# Cross-resource asymmetry — DELIBERATE: this resource has no
# `lifecycle.prevent_destroy = true` while aws_cloudwatch_log_group.audit_trail
# does. See the matching note on the log group above for the full rationale:
# the trail topology must remain operationally fluid (multi-region switch,
# event-data-store migration, additional event selectors), while the log
# group is the durable forensic record between trail apply cycles.
#
# We use `advanced_event_selector` rather than the classic `event_selector`
# because the classic schema only supports `AWS::S3::Object`,
# `AWS::Lambda::Function`, and `AWS::DynamoDB::Table` as data-resource
# types. SSM Parameter Store and KMS Key resource types are ONLY available
# under advanced event selectors (eventCategory = "Data" + resources.type
# = "AWS::SSM::ManagedParameter" / "AWS::KMS::Key"). The two schemas are
# mutually exclusive on a single trail; we get one shot at picking one.
#
# Reference: https://docs.aws.amazon.com/awscloudtrail/latest/userguide/logging-data-events-with-cloudtrail.html
# (the resource-types matrix lists every type usable in advanced event
# selectors; the classic event_selector matrix is much narrower).
#
# Management events are NOT included — the AWS account default trail
# captures them; we don't want to double-count or double-charge.
resource "aws_cloudtrail" "audit" {
  name           = "${var.name_prefix}-audit"
  s3_bucket_name = aws_s3_bucket.audit_trail.bucket

  cloud_watch_logs_group_arn = "${aws_cloudwatch_log_group.audit_trail.arn}:*"
  cloud_watch_logs_role_arn  = aws_iam_role.audit_trail_to_logs.arn

  # Trail log files in S3 are encrypted with the project CMK. The
  # AllowCloudTrailService grant in modules/kms/main.tf enables this.
  kms_key_id = var.kms_key_arn

  # Detects tampering with delivered log files (sigfile per-hour).
  enable_log_file_validation = true

  # Single-region: project is eu-central-1 only; the SSM parameters and
  # CMK exist only here. Multi-region would double-capture for zero
  # additional signal. See module header.
  is_multi_region_trail         = false
  include_global_service_events = false

  # Advanced selector 1: SSM data events on /flowin/${env}/* parameters.
  #
  # `eventCategory = "Data"` is mandatory on every advanced selector that
  # captures data events. `resources.type = "AWS::SSM::ManagedParameter"`
  # restricts to SSM Parameter Store data events; `resources.ARN
  # starts_with` narrows further to our env's parameter namespace. The
  # trailing slash on the prefix is intentional — `starts_with` would
  # otherwise match a hypothetical sibling parameter like
  # `/flowin/prod-other-tenant/...`.
  advanced_event_selector {
    name = "${var.name_prefix} SSM SecureString data events"

    field_selector {
      field  = "eventCategory"
      equals = ["Data"]
    }
    field_selector {
      field  = "resources.type"
      equals = ["AWS::SSM::ManagedParameter"]
    }
    field_selector {
      field       = "resources.ARN"
      starts_with = ["${var.secrets_path_prefix_arn}/"]
    }
  }

  # Advanced selector 2: KMS data events on the project CMK only.
  #
  # CloudTrail KMS data events include Decrypt, Encrypt, GenerateDataKey,
  # ReEncrypt, Sign, Verify. The metric filter (below) further narrows to
  # Decrypt-by-unexpected-identity, which is the SECRET_KEY-leak path.
  # `resources.ARN` is `equals` (exact match) so we don't capture decrypts
  # against unrelated keys.
  advanced_event_selector {
    name = "${var.name_prefix} project CMK data events"

    field_selector {
      field  = "eventCategory"
      equals = ["Data"]
    }
    field_selector {
      field  = "resources.type"
      equals = ["AWS::KMS::Key"]
    }
    field_selector {
      field  = "resources.ARN"
      equals = [var.project_cmk_arn]
    }
  }

  tags = {
    Name      = "${var.name_prefix}-audit"
    Component = "monitoring"
  }

  # CloudTrail validates the bucket policy + CW Logs role at create-time.
  # Without the explicit depends_on the create call can race the policy
  # attach and fail with "InsufficientS3BucketPolicyException".
  depends_on = [
    aws_s3_bucket_policy.audit_trail,
    aws_iam_role_policy.audit_trail_to_logs,
  ]
}

# Metric filter 1: any SSM Get*/Put* against /flowin/${env}/* from a
# principal that is NOT the EC2 instance role.
#
# CloudTrail data-event records arrive as JSON (one event per log entry
# in the CW Logs group). The metric-filter pattern uses CloudWatch's JSON
# filter syntax:
#   - `$.field = "value"`            exact-match string
#   - `$.field != "value"`           exclusion (the load-bearing piece)
#   - `*` wildcard inside the quoted string
#   - whitespace = logical AND, `||` = logical OR
#
# `$.userIdentity.sessionContext.sessionIssuer.arn` is the FIELD CloudTrail
# populates for assumed-role calls (every EC2-role-mediated call lands as
# AssumedRole; sessionIssuer.arn is the underlying role ARN — which IS
# var.instance_role_arn for legitimate traffic). We exclude that.
#
# `$.eventName` matches `GetParameter`, `GetParameters`, `GetParametersByPath`,
# and `PutParameter` via the wildcard prefix (`Get*` OR `Put*`). The
# wildcard at the END of the quoted value works in JSON filters.
#
# Why NOT use a `OR` on the wildcard parts: CloudWatch's JSON filter
# wildcards do support the prefix shape `"GetParameter*"`, and that single
# token covers all three Get* variants. We need a separate `||` branch for
# Put*. Test pattern locally with
#   aws logs filter-log-events --filter-pattern '...'
# before tweaking.
resource "aws_cloudwatch_log_metric_filter" "unexpected_secret_read" {
  name           = "${var.name_prefix}-unexpected-secret-read"
  log_group_name = aws_cloudwatch_log_group.audit_trail.name

  # JSON filter, parenthesised for clarity:
  #   eventSource is ssm AND eventName is Get*/Put* on a parameter
  #   AND the assuming role ARN is NOT the instance role.
  pattern = "{ ($.eventSource = \"ssm.amazonaws.com\") && (($.eventName = \"GetParameter*\") || ($.eventName = \"PutParameter\")) && ($.userIdentity.sessionContext.sessionIssuer.arn != \"${var.instance_role_arn}\") }"

  metric_transformation {
    name          = "UnexpectedSecretRead"
    namespace     = var.cw_metric_namespace
    value         = "1"
    default_value = "0"
  }
}

# Metric filter 2: KMS Decrypt against the project CMK from any identity
# OTHER than the EC2 instance role.
#
# CloudTrail KMS data-events surface the key ARN under `$.resources[0].ARN`.
# We DON'T match on resources[0].ARN here because the trail's
# event_selector already pre-filters to the project CMK only (so 100% of
# events delivered to this log group concern the project CMK already);
# the metric filter only adds the identity exclusion.
#
# Match Decrypt only — Encrypt / GenerateDataKey by external identities
# is a separate (and less acute) concern; if needed, broaden the eventName
# wildcard later. Same identity-exclusion shape as filter 1.
resource "aws_cloudwatch_log_metric_filter" "unexpected_kms_decrypt" {
  name           = "${var.name_prefix}-unexpected-kms-decrypt"
  log_group_name = aws_cloudwatch_log_group.audit_trail.name

  pattern = "{ ($.eventSource = \"kms.amazonaws.com\") && ($.eventName = \"Decrypt\") && ($.userIdentity.sessionContext.sessionIssuer.arn != \"${var.instance_role_arn}\") }"

  metric_transformation {
    name          = "UnexpectedKmsDecrypt"
    namespace     = var.cw_metric_namespace
    value         = "1"
    default_value = "0"
  }
}

# Alarm 1: any UnexpectedSecretRead in 5 minutes pages on-call.
#
# Threshold 0 / GreaterThanThreshold means "any event in the window
# triggers". period × evaluation_periods = 300 × 1 = 300s, well inside
# the CloudWatch 7-day cap. treat_missing_data = "notBreaching" — absence
# of unexpected reads IS the desired state (the legitimate traffic is
# excluded by the filter and doesn't bump the metric).
resource "aws_cloudwatch_metric_alarm" "unexpected_secret_read" {
  alarm_name          = "${var.name_prefix}-unexpected-secret-read"
  alarm_description   = "An SSM GetParameter*/PutParameter on /flowin/${var.environment}/* was issued by a principal OTHER than the EC2 instance role. Investigate immediately — this is the SECRET_KEY exfiltration page."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "UnexpectedSecretRead"
  namespace           = var.cw_metric_namespace
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = {
    Component = "monitoring"
  }
}

# Alarm 2: any UnexpectedKmsDecrypt in 5 minutes pages on-call. Same
# threshold/period rationale as filter 1.
resource "aws_cloudwatch_metric_alarm" "unexpected_kms_decrypt" {
  alarm_name          = "${var.name_prefix}-unexpected-kms-decrypt"
  alarm_description   = "kms:Decrypt against the project CMK was issued by a principal OTHER than the EC2 instance role. Investigate immediately — possible SecureString-decrypt or EBS-snapshot-read attempt."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "UnexpectedKmsDecrypt"
  namespace           = var.cw_metric_namespace
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

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
