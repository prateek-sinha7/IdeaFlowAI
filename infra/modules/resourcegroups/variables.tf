variable "name_prefix" {
  description = "Resource name prefix, e.g. flowin-prod."
  type        = string
}

variable "environment" {
  description = "Environment short name (matches the Environment tag value)."
  type        = string
}

variable "components" {
  description = "Per-component group definitions. Map of component_name -> human description. Each becomes a Resource Group filtering on Component=<name>. Description values are baked into AWS Resource Groups' `description` field, which is validated against the regex `[\\sa-zA-Z0-9_.-]*` server-side — no commas, parens, slashes, em-dashes, etc. The validation block below enforces this so operators get a fail-at-plan error instead of a fail-at-apply error."
  type        = map(string)
  default = {
    network    = "VPC subnets route tables security groups VPC endpoints"
    compute    = "EC2 instance root EBS volume EIP"
    storage   = "Data EBS volume S3 backup bucket AWS Backup vault"
    monitoring = "CloudWatch log groups alarms SNS"
    iam       = "IAM role KMS key instance profile"
    secrets   = "SSM Parameter Store entries"
    ecr       = "ECR repositories backend frontend lifecycle policies"
  }

  validation {
    condition     = alltrue([for v in values(var.components) : can(regex("^[[:space:]a-zA-Z0-9_.-]*$", v))])
    error_message = "Each components value must match ^[\\sa-zA-Z0-9_.-]*$ — AWS Resource Groups rejects commas, parentheses, colons, em-dashes, slashes, etc. in description fields."
  }
}

variable "description_separator" {
  description = "Glyph between the component-name prefix and the human description in each per-component group. Real AWS Resource Groups validates description against `[\\sa-zA-Z0-9_.-]*` — em-dash (U+2014), en-dash, slash, colon are all rejected. Default is an ASCII hyphen with surrounding spaces; override only if you have a stricter house-style preference that still fits the regex."
  type        = string
  default     = " - "

  validation {
    condition     = can(regex("^[[:space:]a-zA-Z0-9_.-]*$", var.description_separator))
    error_message = "description_separator must only contain whitespace, ASCII letters/digits, underscore, dot, or hyphen — AWS Resource Groups rejects anything else."
  }
}
