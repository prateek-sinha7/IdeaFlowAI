output "log_group_names" {
  description = "Map of friendly suffix -> CloudWatch Log Group name."
  value       = { for k, v in aws_cloudwatch_log_group.groups : k => v.name }
}

output "log_group_arns" {
  description = "Map of friendly suffix -> CloudWatch Log Group ARN."
  value       = { for k, v in aws_cloudwatch_log_group.groups : k => v.arn }
}

output "alerts_topic_arn" {
  description = "SNS topic ARN for alarm fan-out (eu-central-1)."
  value       = aws_sns_topic.alerts.arn
}

output "alerts_topic_name" {
  description = "SNS topic name (eu-central-1)."
  value       = aws_sns_topic.alerts.name
}

output "alerts_useast1_topic_arn" {
  description = "SNS topic ARN in us-east-1 used by the billing alarm (alarms can only publish to a same-region SNS topic)."
  value       = aws_sns_topic.alerts_useast1.arn
}

output "alarm_names" {
  description = "Names of every alarm this module manages. Used by docs/runbooks and downstream PagerDuty/Slack integrations."
  value = concat(
    [
      aws_cloudwatch_metric_alarm.cpu_high.alarm_name,
      aws_cloudwatch_metric_alarm.mem_high.alarm_name,
      aws_cloudwatch_metric_alarm.disk_root_high.alarm_name,
      aws_cloudwatch_metric_alarm.disk_data_high.alarm_name,
      aws_cloudwatch_metric_alarm.nginx_5xx_spike.alarm_name,
      aws_cloudwatch_metric_alarm.db_conn_error.alarm_name,
      aws_cloudwatch_metric_alarm.bedrock_throttles.alarm_name,
      aws_cloudwatch_metric_alarm.bedrock_server_errors.alarm_name,
      aws_cloudwatch_metric_alarm.billing.alarm_name,
      aws_cloudwatch_metric_alarm.ws_disconnect_spike.alarm_name,
      aws_cloudwatch_metric_alarm.bedrock_tokens_daily.alarm_name,
      aws_cloudwatch_metric_alarm.pg_dump_heartbeat.alarm_name,
      # Phase 3 additions:
      aws_cloudwatch_metric_alarm.cert_renew_failure.alarm_name,   # 21
      aws_cloudwatch_metric_alarm.cert_renew_heartbeat.alarm_name, # 21
      aws_cloudwatch_metric_alarm.agent_error_high.alarm_name,     # D P2-2
      aws_cloudwatch_metric_alarm.stuck_workflows.alarm_name,      # D P2-3
      # Phase C additions:
      aws_cloudwatch_metric_alarm.unexpected_secret_read.alarm_name, # C2-1
      aws_cloudwatch_metric_alarm.unexpected_kms_decrypt.alarm_name, # C2-1
    ],
    # for_each over [root, data] disk paths — one alarm per path.
    [for k, a in aws_cloudwatch_metric_alarm.inode_low : a.alarm_name],
  )
}

# C2-1: CloudTrail audit-trail diagnostics. The trail name + log group are
# documented surfaces (operators ack the alarms via the runbook by hitting
# the log group in the console; the trail ARN is the canonical handle for
# Cloud Custodian / Security Hub integrations).
output "audit_trail_name" {
  description = "Name of the CloudTrail trail that captures SSM/KMS data events (C2-1)."
  value       = aws_cloudtrail.audit.name
}

output "audit_trail_arn" {
  description = "ARN of the CloudTrail trail (C2-1)."
  value       = aws_cloudtrail.audit.arn
}

output "audit_trail_log_group_name" {
  description = "CloudWatch Logs group name the audit trail delivers into (C2-1). Metric filters UnexpectedSecretRead / UnexpectedKmsDecrypt read from this group."
  value       = aws_cloudwatch_log_group.audit_trail.name
}

output "audit_trail_bucket_name" {
  description = "Name of the S3 bucket the CloudTrail trail writes durable JSON GZ deliveries to (C2-1)."
  value       = aws_s3_bucket.audit_trail.bucket
}
