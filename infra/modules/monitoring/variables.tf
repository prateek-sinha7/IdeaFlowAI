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
  description = "CloudWatch Log retention in days."
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
