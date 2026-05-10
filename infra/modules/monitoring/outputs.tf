output "log_group_names" {
  description = "Map of friendly suffix -> CloudWatch Log Group name."
  value       = { for k, v in aws_cloudwatch_log_group.groups : k => v.name }
}

output "log_group_arns" {
  description = "Map of friendly suffix -> CloudWatch Log Group ARN."
  value       = { for k, v in aws_cloudwatch_log_group.groups : k => v.arn }
}

output "alerts_topic_arn" {
  description = "SNS topic ARN for alarm fan-out (eu-west-2)."
  value       = aws_sns_topic.alerts.arn
}

output "alerts_topic_name" {
  description = "SNS topic name (eu-west-2)."
  value       = aws_sns_topic.alerts.name
}

output "alerts_useast1_topic_arn" {
  description = "SNS topic ARN in us-east-1 used by the billing alarm (alarms can only publish to a same-region SNS topic)."
  value       = aws_sns_topic.alerts_useast1.arn
}

output "alarm_names" {
  description = "Names of every alarm this module manages."
  value = [
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
  ]
}
