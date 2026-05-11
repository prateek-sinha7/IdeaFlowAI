variable "name_prefix" {
  description = "Resource name prefix, e.g. flowin-prod."
  type        = string
}

variable "environment" {
  description = "Environment short name (e.g. prod). Used in log-group paths."
  type        = string
}

variable "instance_id" {
  description = "EC2 instance ID alarms reference via the InstanceId dimension."
  type        = string
}

variable "kms_key_arn" {
  description = "ARN of the project CMK used to encrypt log groups and the SNS topic."
  type        = string
}

variable "alert_email" {
  description = "Email address subscribed to the alerts SNS topic. Empty disables the subscription."
  type        = string
  default     = ""
}

variable "log_retention_days" {
  description = "Default CloudWatch Log retention in days. Applied to any log group not present in log_retention_overrides. Audit D P2-5: groups with materially different operational profile (nginx-access high-volume vs auth/auditd long-forensics) should override via log_retention_overrides rather than push this default to one global compromise number."
  type        = number
  default     = 30

  validation {
    condition = contains(
      [1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 3653],
      var.log_retention_days
    )
    error_message = "log_retention_days must be one of CloudWatch's allowed values (1,3,5,7,14,30,60,90,120,150,180,365,400,545,731,1827,3653)."
  }
}

variable "log_retention_overrides" {
  description = "Per-log-group retention overrides. Keys are full log group names (e.g. /flowin/prod/auth, /flowin/prod/nginx-access), values are retention days from the AWS-allowed set. Backward-compatible: empty map preserves the previous one-size-fits-all behaviour where every group used log_retention_days."
  type        = map(number)
  default     = {}

  validation {
    condition = alltrue([
      for v in values(var.log_retention_overrides) :
      contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 3653], v)
    ])
    error_message = "log_retention_overrides values must be one of CloudWatch's allowed retention periods (1,3,5,7,14,30,60,90,120,150,180,365,400,545,731,1827,3653)."
  }
}

variable "cpu_threshold_percent" {
  description = "Alarm threshold for sustained CPU."
  type        = number
  default     = 80
}

variable "memory_threshold_percent" {
  description = "Alarm threshold for memory."
  type        = number
  default     = 85
}

variable "disk_threshold_percent" {
  description = "Alarm threshold for disk usage (root and data)."
  type        = number
  default     = 80
}

variable "billing_alarm_threshold_usd" {
  description = "USD threshold for the EstimatedCharges alarm (us-east-1)."
  type        = number
  default     = 500
}

variable "bedrock_model_id" {
  description = "The model ID the app actually invokes — typically the cross-region inference profile (e.g. eu.anthropic.claude-haiku-4-5-20251001-v1:0), NOT the foundation-model ID. Used as the ModelId dimension on Bedrock alarms; CloudWatch dimensions metrics by whichever string the SDK passed as modelId."
  type        = string
}

variable "cw_metric_namespace" {
  description = "Namespace under which the CloudWatch agent emits host metrics."
  type        = string
  default     = "Flowin/Prod"
}

variable "bedrock_daily_token_threshold" {
  description = "Daily Bedrock InputTokenCount threshold (Sum over 24h). 5,000,000 input tokens at Haiku 4.5 list (~$4 / 1M input + ~$20 / 1M output) is roughly a $20-input + variable-output budget — the alarm catches token-runaway from cancel-pipeline failures, retry storms, and runaway long-context fan-out before they show up on the monthly bill. Tune after a week of baseline data."
  type        = number
  default     = 5000000

  validation {
    condition     = var.bedrock_daily_token_threshold > 0
    error_message = "bedrock_daily_token_threshold must be > 0."
  }
}

variable "ws_disconnect_threshold" {
  description = "WebSocket disconnect count over a 5-minute window above which the alarm fires. >50/5min is a reasonable starting threshold for a single-instance deployment serving ~150 concurrent sessions; tune up if traffic grows."
  type        = number
  default     = 50

  validation {
    condition     = var.ws_disconnect_threshold > 0
    error_message = "ws_disconnect_threshold must be > 0."
  }
}

variable "backup_vault_name" {
  description = "Name of the AWS Backup vault to wire job-state notifications onto. Empty disables aws_backup_vault_notifications (LocalStack and during bootstrap before the vault exists)."
  type        = string
  default     = ""
}

variable "bedrock_throttles_threshold" {
  description = "Sum threshold for the Bedrock InvocationThrottles alarm over a 5-minute window. Audit D P3-12: 0 is hair-trigger (any single throttle in 5 min pages); 5 absorbs short bursts of quota pressure that auto-recover after backoff but still pages on sustained pressure. Tune up if Bedrock quota gets bumped and the baseline noise floor changes."
  type        = number
  default     = 5

  validation {
    condition     = var.bedrock_throttles_threshold >= 0
    error_message = "bedrock_throttles_threshold must be >= 0."
  }
}

variable "bedrock_throttles_evaluation_periods" {
  description = "Number of consecutive 5-minute windows the Bedrock throttle threshold must be exceeded before the alarm fires. 1 = pages on the first window over threshold; 2 = requires sustained pressure across two windows (~10 min) before paging."
  type        = number
  default     = 2

  validation {
    condition     = var.bedrock_throttles_evaluation_periods >= 1
    error_message = "bedrock_throttles_evaluation_periods must be >= 1."
  }
}

variable "agent_error_rate_threshold" {
  description = "Sum threshold for the agent-error rate alarm. Audit D P2-2: triggers when the AgentErrorCount metric exceeds this in any 5-minute window for two consecutive windows. Default 20 = 'sustained, not a burst' — at ~150 concurrent sessions the natural burst-rate from transient Bedrock blips is well under 20/5min, so 20 cleanly separates a normal blip from a real degradation."
  type        = number
  default     = 20

  validation {
    condition     = var.agent_error_rate_threshold >= 0
    error_message = "agent_error_rate_threshold must be >= 0."
  }
}

variable "stuck_workflows_threshold" {
  description = "Audit D P2-3: WorkflowRun rows in `running` for >60 min above this count fires the stuck-workflows alarm. Default 0 — the on-host SQL probe pushes the literal count and any non-zero value is a finding."
  type        = number
  default     = 0

  validation {
    condition     = var.stuck_workflows_threshold >= 0
    error_message = "stuck_workflows_threshold must be >= 0."
  }
}

variable "stuck_workflows_check_period" {
  description = "Audit D P2-3: alarm period in seconds. The on-host probe runs every 15 min (900s); 1800s (30 min) gives the alarm two publishes per evaluation window so a single missed probe doesn't auto-clear the alarm."
  type        = number
  default     = 1800

  validation {
    condition     = var.stuck_workflows_check_period >= 60
    error_message = "stuck_workflows_check_period must be >= 60s (CloudWatch alarm period minimum)."
  }
}

variable "root_disk_path" {
  description = "Mount path of the root filesystem for the inode_low alarm dimensions. Must match what the CW Agent emits as the `path` dimension on `disk_inodes_free`."
  type        = string
  default     = "/"
}

variable "data_disk_path" {
  description = "Mount path of the data (Postgres) filesystem for the inode_low alarm dimensions. Must match what the CW Agent emits as the `path` dimension on `disk_inodes_free`."
  type        = string
  default     = "/var/lib/postgresql"
}
