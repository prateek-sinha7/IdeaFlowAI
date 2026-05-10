variable "expected_account_id" {
  description = "AWS account ID this stack must run against. Plan/apply abort on mismatch."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_account_id))
    error_message = "expected_account_id must be a 12-digit AWS account ID."
  }
}

variable "aws_region" {
  description = "AWS region."
  type        = string
  default     = "eu-central-1"

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9]$", var.aws_region))
    error_message = "aws_region must look like e.g. eu-central-1."
  }
}

variable "availability_zone" {
  description = "Single AZ inside aws_region (e.g. eu-central-1a)."
  type        = string
  default     = "eu-central-1a"

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9][a-z]$", var.availability_zone))
    error_message = "availability_zone must look like e.g. eu-central-1a."
  }

  # Audit B P2-9: cross-var validation. AZs are scoped to a region — passing
  # `eu-central-1a` while aws_region=`us-east-1` would deploy into an AZ
  # that doesn't exist in that region (or worse, deploy into the wrong region
  # silently). Cross-var validation requires Terraform 1.9+; the version pin
  # in versions.tf is `>= 1.7.0`. Bumping the floor to 1.9 is safe for this
  # repo (CI uses 1.15+; local dev follows). See ADR comment in versions.tf.
  validation {
    condition     = startswith(var.availability_zone, var.aws_region)
    error_message = "availability_zone must be in aws_region (e.g. eu-central-1a for aws_region=eu-central-1)."
  }
}

variable "environment" {
  description = "Environment short name; appears in name_prefix and parameter paths."
  type        = string
  default     = "prod"

  validation {
    condition     = can(regex("^[a-z][a-z0-9]{1,15}$", var.environment))
    error_message = "environment must be lowercase, start with a letter, max 16 chars."
  }
}

variable "owner" {
  description = "Tag value for Owner (team contact)."
  type        = string
}

variable "cost_center" {
  description = "Tag value for CostCenter (finance code)."
  type        = string
}

variable "assume_role_arn" {
  description = "Optional IAM role ARN the AWS provider assumes. Empty = use the caller's identity directly."
  type        = string
  default     = ""
}

variable "assume_role_external_id" {
  description = "Optional external ID for the assume-role call."
  type        = string
  default     = ""
}

# --- Network ----------------------------------------------------------------

variable "vpc_cidr" {
  description = "CIDR for the project VPC."
  type        = string
  default     = "10.20.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR for the public subnet."
  type        = string
  default     = "10.20.1.0/24"
}

variable "ssh_allowed_cidrs" {
  description = "List of CIDRs permitted SSH ingress. Leave empty to use only SSM Session Manager (recommended)."
  type        = list(string)
  default     = []
}

# --- Compute ----------------------------------------------------------------

variable "instance_type" {
  description = "EC2 instance type."
  type        = string
  default     = "m6i.2xlarge"
}

variable "root_volume_size_gb" {
  description = "Root EBS volume size."
  type        = number
  default     = 100
}

variable "data_volume_size_gb" {
  description = "Postgres data EBS volume size."
  type        = number
  default     = 50
}

variable "ssh_key_name" {
  description = "Existing EC2 keypair name. Empty disables --key-name (use SSM Session Manager)."
  type        = string
  default     = ""
}

# --- DNS --------------------------------------------------------------------

variable "use_nip_io" {
  description = <<-EOT
    If true, derive the public hostname from the EIP via nip.io
    (e.g. 1-2-3-4.nip.io for EIP 1.2.3.4) instead of creating a Route 53
    A record under route53_zone_name + app_subdomain. nip.io is on the
    Public Suffix List so Let's Encrypt issues real certs. Use this for
    sandbox / no-DNS deployments. Set to false (default) for prod with
    a real domain.

    When true, route53_zone_name and app_subdomain are ignored.
  EOT
  type        = bool
  default     = false
}

variable "route53_zone_name" {
  description = "Existing Route 53 hosted zone name (e.g. example.com). MUST already exist in this account. Bare DNS name only — no http://, no leading or trailing dots. Ignored when use_nip_io = true; supply an empty string in that case."
  type        = string
  default     = ""

  validation {
    # Audit B P2-9: catch the common operator mistake of pasting a URL
    # ("https://example.com") or a fully-qualified absolute name (".example.com.")
    # into a hosted-zone field. The DNS module looks up via data source on
    # the bare name; with a protocol prefix the lookup silently returns an
    # empty result and the A-record creation then fails far downstream.
    # Empty is permitted for the use_nip_io = true path.
    condition     = var.route53_zone_name == "" || (!startswith(var.route53_zone_name, "http") && !startswith(var.route53_zone_name, ".") && !endswith(var.route53_zone_name, "."))
    error_message = "route53_zone_name must be a bare DNS name (no http://, no leading or trailing dots), or empty when use_nip_io = true."
  }
}

variable "app_subdomain" {
  description = "Subdomain (without zone) the app answers on, e.g. 'flowin'. Ignored when use_nip_io = true."
  type        = string
  default     = "flowin"
}

variable "dns_ttl_seconds" {
  description = "TTL for the A record. Ignored when use_nip_io = true (no record is created)."
  type        = number
  default     = 60
}

# --- Bedrock / LLM ----------------------------------------------------------

variable "bedrock_model_id" {
  description = "Bedrock foundation-model ID Flowin invokes. Must start with `anthropic.` (foundation-model), `eu.anthropic.` (EU inference profile), or `us.anthropic.` (US inference profile) — anything else won't match the IAM scope in modules/iam/policies/bedrock-invoke.json."
  type        = string
  default     = "anthropic.claude-haiku-4-5-20251001-v1:0"

  validation {
    # Audit B P2-9: the IAM Bedrock policy scopes invoke to ARNs with these
    # exact prefixes. A typo here (e.g. `claude-haiku-4-5...` without the
    # vendor prefix) would deploy clean, then every InvokeModel call would
    # 403 in production. Cheap pre-flight check.
    condition     = startswith(var.bedrock_model_id, "anthropic.") || startswith(var.bedrock_model_id, "eu.anthropic.") || startswith(var.bedrock_model_id, "us.anthropic.")
    error_message = "bedrock_model_id must start with `anthropic.`, `eu.anthropic.`, or `us.anthropic.`."
  }
}

variable "bedrock_inference_profile_id" {
  description = "Cross-region inference profile ID, used in IAM and as the active model_id when traffic must span regions."
  type        = string
  default     = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "use_inference_profile_for_app" {
  description = "If true, the app's /flowin/$${env}/llm/model_id parameter is the inference profile ID rather than the foundation-model ID."
  type        = bool
  default     = true
}

# --- Secrets / app config ---------------------------------------------------

variable "app_secret_key" {
  description = "Application JWT signing key (>= 32 chars, generate via `openssl rand -hex 64`). NEVER commit. Set via env var TF_VAR_app_secret_key or terraform.tfvars (which is gitignored)."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.app_secret_key) >= 32
    error_message = "app_secret_key must be at least 32 characters."
  }
}

variable "db_password" {
  description = "Postgres password for the application user. Generate via `openssl rand -hex 32`. NEVER commit."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.db_password) >= 16
    error_message = "db_password must be at least 16 characters."
  }
}

variable "anthropic_api_key" {
  description = "Optional fallback Anthropic API key. Empty = no parameter created."
  type        = string
  sensitive   = true
  default     = ""
}

variable "langsmith_tracing" {
  description = "Optional LangSmith tracing toggle (e.g. \"true\"). Empty = no parameter created (tracing off)."
  type        = string
  default     = ""
}

variable "langsmith_api_key" {
  description = "Optional LangSmith API key. Empty = no parameter created."
  type        = string
  sensitive   = true
  default     = ""
}

variable "langsmith_project" {
  description = "Optional LangSmith project name. Empty = no parameter created."
  type        = string
  default     = ""
}

variable "cors_origins" {
  description = "JSON-encoded list of CORS origins, e.g. '[\"https://flowin.example.com\"]'. Each entry must be a fully-qualified URL (http:// or https://). The on-host loader pushes this verbatim into CORS_ORIGINS env, which Settings parses as JSON."
  type        = string

  validation {
    # Audit B P2-9: trip on a bare string ("flowin.example.com") or comma-
    # separated list ("a,b") rather than JSON. Both common operator mistakes;
    # both deploy clean and break at app startup when Settings.cors_origins
    # JSON-parses the value.
    condition     = can(jsondecode(var.cors_origins))
    error_message = "cors_origins must be valid JSON (a list of URL strings, e.g. '[\"https://flowin.example.com\"]')."
  }

  validation {
    # Element-level shape check: each origin must be a fully-qualified URL.
    # FastAPI's CORSMiddleware also validates this, but failing fast at
    # `terraform plan` time is cheaper than failing at app startup.
    condition     = can(jsondecode(var.cors_origins)) ? alltrue([for o in jsondecode(var.cors_origins) : startswith(o, "https://") || startswith(o, "http://")]) : false
    error_message = "cors_origins entries must each start with http:// or https://."
  }
}

variable "access_token_expire_hours" {
  description = "JWT lifetime in hours."
  type        = number
  default     = 12
}

# --- Backups ----------------------------------------------------------------

variable "backup_bucket_name" {
  description = "Globally-unique name for the pg_dump backup bucket. Suggested: flowin-prod-pg-dumps-<account-id>."
  type        = string
}

variable "daily_backup_retention_days" {
  description = "How long AWS Backup keeps each daily snapshot. Default 365d matches docs/SIMPLE_AWS_DEPLOYMENT.md §11. Module enforces (delete_after - cold_storage_after) >= 90 — see modules/backups/variables.tf for the validation."
  type        = number
  default     = 365
}

variable "cold_storage_after_days" {
  description = "Days after which a recovery point transitions to cold storage. AWS Backup requires (delete_after - cold_storage_after) >= 90."
  type        = number
  default     = 30
}

variable "pg_dump_expiry_days" {
  description = "Days after which current versions of pg_dump archives expire from the S3 backup bucket. Default 365 matches docs/SIMPLE_AWS_DEPLOYMENT.md §11.2."
  type        = number
  default     = 365
}

# --- Backup Vault Lock (opt-in, ONE-WAY) -----------------------------------
# Default false. Enabling these flags should follow validation drills — see
# modules/backups/variables.tf::enable_vault_lock for the full rationale.

variable "enable_vault_lock" {
  description = "If true, applies AWS Backup Vault Lock in compliance mode. ONE-WAY: once on, recovery points cannot be deleted before delete_after, and the lock itself becomes immutable after a 3-day cooling-off window. Recommended for production AFTER you've validated daily_backup_retention_days and cold_storage_after_days against real recovery drills."
  type        = bool
  default     = false
}

variable "vault_lock_min_retention_days" {
  description = "Minimum retention enforced by Vault Lock (compliance mode). Should be >= the operator's expected mistake-recovery window."
  type        = number
  default     = 7
}

variable "vault_lock_max_retention_days" {
  description = "Maximum retention enforced by Vault Lock. Should be >= daily_backup_retention_days."
  type        = number
  default     = 365
}

# --- S3 Object Lock (opt-in, creation-time-only) ---------------------------
# Default false. CANNOT be retrofitted to an existing bucket — see
# modules/backups/variables.tf::enable_object_lock for the full caveat.

variable "enable_object_lock" {
  description = "If true, the backup bucket is created with Object Lock enabled (governance mode by default). MUST BE SET AT BUCKET CREATION — cannot be retrofitted. Flipping this against an already-created bucket has no effect (Terraform plans bucket replacement, which prevent_destroy correctly blocks). Recommended for new deployments only."
  type        = bool
  default     = false
}

variable "object_lock_retention_days" {
  description = "Default retention period (days) for Object Lock in Governance mode. An IAM principal with s3:BypassGovernanceRetention can override."
  type        = number
  default     = 35
}

# --- Monitoring -------------------------------------------------------------

variable "alert_email" {
  description = "Email address subscribed to the SNS alerts topic."
  type        = string

  validation {
    condition     = can(regex("^[^@]+@[^@]+\\.[^@]+$", var.alert_email))
    error_message = "alert_email must look like a valid email address."
  }
}

variable "log_retention_days" {
  description = "Default CloudWatch Log retention in days for any group not in log_retention_overrides. Audit D P2-5: prefer setting this conservatively (30d) and overriding the high-volume groups (nginx-access) and forensic groups (auth) explicitly."
  type        = number
  default     = 30

  validation {
    condition = contains(
      [1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 3653],
      var.log_retention_days
    )
    error_message = "log_retention_days must be one of CloudWatch's allowed values."
  }
}

variable "log_retention_overrides" {
  description = "Audit D P2-5: per-log-group retention overrides. Keys are full log group names (e.g. /flowin/prod/auth), values are retention days from the AWS-allowed set. Empty map preserves the previous one-size-fits-all behaviour. Recommended: shorten /flowin/prod/nginx-access to 7d (high churn, lowest forensic value) and lengthen /flowin/prod/auth to 90-180d (forensics)."
  type        = map(number)
  default     = {}
}

variable "billing_alarm_threshold_usd" {
  description = "USD threshold for the EstimatedCharges alarm (us-east-1)."
  type        = number
  default     = 500
}

variable "bedrock_daily_token_threshold" {
  description = "Daily Bedrock InputTokenCount threshold (Sum over 24h). Default 5,000,000 input tokens — see modules/monitoring/variables.tf for the cost model."
  type        = number
  default     = 5000000
}

# --- Phase 3 Audit D additions ---------------------------------------------

variable "bedrock_throttles_threshold" {
  description = "Audit D P3-12: Sum threshold for Bedrock InvocationThrottles over 5 min. 0 (the original default) was hair-trigger; 5 absorbs short bursts but still pages on sustained quota pressure. Tune up after a week of baseline."
  type        = number
  default     = 5
}

variable "bedrock_throttles_evaluation_periods" {
  description = "Audit D P3-12: number of consecutive 5-minute windows the Bedrock throttle threshold must be exceeded before paging. 2 = ~10 min of sustained pressure."
  type        = number
  default     = 2
}

variable "agent_error_rate_threshold" {
  description = "Audit D P2-2: AgentErrorCount threshold above which the agent-error-high alarm fires (over 5-min Sum, 2 consecutive windows). 20 = sustained, not a burst."
  type        = number
  default     = 20
}

variable "stuck_workflows_threshold" {
  description = "Audit D P2-3: count of WorkflowRun rows in `running` for >60 min above which the stuck-workflows alarm fires."
  type        = number
  default     = 0
}

variable "stuck_workflows_check_period" {
  description = "Audit D P2-3: alarm period in seconds. The on-host probe runs every 15 min; 1800s (30 min) gives two publishes per evaluation window."
  type        = number
  default     = 1800
}
