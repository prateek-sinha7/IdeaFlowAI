variable "name_prefix" {
  description = "Resource name prefix, e.g. flowin-prod."
  type        = string
}

variable "environment" {
  description = "Environment short name (matches the Environment tag value)."
  type        = string
}

variable "components" {
  description = "Per-component group definitions. Map of component_name -> human description. Each becomes a Resource Group filtering on Component=<name>."
  type        = map(string)
  default = {
    network    = "VPC, subnets, route tables, security groups, VPC endpoints"
    compute    = "EC2 instance, root EBS volume, EIP"
    storage    = "Data EBS volume, S3 backup bucket, AWS Backup vault"
    monitoring = "CloudWatch log groups, alarms, SNS"
    iam        = "IAM role, KMS key, instance profile"
    secrets    = "SSM Parameter Store entries"
  }
}

variable "description_separator" {
  description = "Glyph between the component-name prefix and the human description in each per-component group. Defaults to em-dash; LocalStack validates description against a stricter ASCII regex than real AWS, so test envs override this with '-'."
  type        = string
  default     = "—"
}
