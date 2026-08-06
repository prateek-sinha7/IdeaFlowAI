variable "name_prefix" {
  description = "Resource name prefix, e.g. velocityai-prod (used in tags and derived names)."
  type        = string
}

variable "environment" {
  description = "Environment short name (dev/stage/prod). Used only for tagging/naming — never baked into application logic."
  type        = string

  validation {
    condition     = contains(["dev", "stage", "prod"], var.environment)
    error_message = "environment must be one of: dev, stage, prod."
  }
}

# --- Password policy ---------------------------------------------------------

variable "password_minimum_length" {
  description = "Minimum password length enforced by the User Pool (COGNITO-MIGRATION-PLAN A-5: strengthened above the app's legacy 8-char floor)."
  type        = number
  default     = 12

  validation {
    condition     = var.password_minimum_length >= 8 && var.password_minimum_length <= 99
    error_message = "password_minimum_length must be between 8 and 99."
  }
}

variable "password_require_lowercase" {
  type    = bool
  default = true
}

variable "password_require_uppercase" {
  type    = bool
  default = true
}

variable "password_require_numbers" {
  type    = bool
  default = true
}

variable "password_require_symbols" {
  type    = bool
  default = true
}

variable "temp_password_validity_days" {
  description = "Days an admin-set temporary password stays valid before it expires (admin_create_user_config)."
  type        = number
  default     = 7
}

# --- MFA -----------------------------------------------------------------

variable "mfa_configuration" {
  description = "Pool-wide MFA setting. OPTIONAL at cutover (Decision 4); OFF/ON are the other allowed values. There is no native \"required for admins only\" — that is enforced at the application layer (see the migration plan §5.5)."
  type        = string
  default     = "OPTIONAL"

  validation {
    condition     = contains(["OFF", "OPTIONAL", "ON"], var.mfa_configuration)
    error_message = "mfa_configuration must be one of: OFF, OPTIONAL, ON."
  }
}

# --- Feature plan / threat protection (Phase 6 item 2) ----------------------
# Decision 8 selected ESSENTIALS. Threat protection (compromised-credential
# detection, adaptive authentication) requires PLUS. Assumption A-7 / risk R15
# recorded that this was DEFERRED, not assumed present — so it is surfaced as an
# explicit variable rather than left implicit in the resource body.
#
# Worth noting in Plus's favour when this decision is revisited: AWS documents
# that compromised-credential checks apply to ADMIN_USER_PASSWORD_AUTH but NOT
# to SRP. The backend-mediated flow chosen in Decision 1 is therefore compatible
# with threat protection, whereas an SRP-based client-side flow would not have
# been. The architecture does not block the upgrade.

variable "feature_plan" {
  description = "Cognito user pool feature plan: LITE, ESSENTIALS, or PLUS. ESSENTIALS (default, Decision 8) provides TOTP MFA. PLUS additionally enables threat protection — compromised-credential detection and adaptive auth — and costs more per MAU."
  type        = string
  default     = "ESSENTIALS"

  validation {
    condition     = contains(["LITE", "ESSENTIALS", "PLUS"], var.feature_plan)
    error_message = "feature_plan must be one of: LITE, ESSENTIALS, PLUS."
  }
}

variable "threat_protection_mode" {
  description = "Threat-protection enforcement for the standard (non-hosted-UI) auth flow. Requires feature_plan = PLUS; ignored otherwise. AUDIT logs risk assessments without blocking (the safe first step); ENFORCED applies the configured automatic responses; NO_ACTION disables it."
  type        = string
  default     = "NO_ACTION"

  validation {
    condition     = contains(["NO_ACTION", "AUDIT", "ENFORCED"], var.threat_protection_mode)
    error_message = "threat_protection_mode must be one of: NO_ACTION, AUDIT, ENFORCED."
  }
}

# --- Email delivery / SES (Phase 6 item 3) ---------------------------------
# Cognito's built-in COGNITO_DEFAULT sender is capped at a very low daily
# volume and is explicitly not intended for production traffic. Self-service
# password reset (Decision 10) therefore depends on routing pool email through
# SES with a verified domain + DKIM. Left empty = keep COGNITO_DEFAULT, which is
# adequate for dev but NOT for a real reset flow.

variable "ses_source_arn" {
  description = "ARN of a VERIFIED SES identity (domain or email) to send pool email from. Empty (default) keeps Cognito's built-in sender, which is rate limited and unsuitable for production password-reset volume. Setting this switches email_sending_account to DEVELOPER."
  type        = string
  default     = ""
}

variable "ses_from_email_address" {
  description = "From: address for pool email. Must belong to the verified ses_source_arn identity. Required when ses_source_arn is set."
  type        = string
  default     = ""
}

variable "ses_reply_to_email_address" {
  description = "Optional Reply-To: address for pool email."
  type        = string
  default     = ""
}

# --- App client token lifetimes -------------------------------------------

variable "access_token_validity_minutes" {
  description = "Access token lifetime in minutes (A-3: 30-60 min recommended)."
  type        = number
  default     = 60
}

variable "id_token_validity_minutes" {
  description = "ID token lifetime in minutes — matched to the access token by default."
  type        = number
  default     = 60
}

variable "refresh_token_validity_days" {
  description = "Refresh token lifetime in days (A-4: shorter in dev, longer in prod)."
  type        = number
  default     = 30
}

# --- Deletion protection ---------------------------------------------------

variable "deletion_protection" {
  description = "Cognito user pool deletion_protection value. Set ACTIVE in prod so the pool cannot be destroyed without first deactivating protection explicitly."
  type        = string
  default     = "INACTIVE"

  validation {
    condition     = contains(["ACTIVE", "INACTIVE"], var.deletion_protection)
    error_message = "deletion_protection must be ACTIVE or INACTIVE."
  }
}

# --- Groups ------------------------------------------------------------------
# Fixed precedence table per the migration plan §5.1. Not made configurable —
# these four names + precedences are a locked decision (Decision 6), and the
# application's resolve_tier_from_groups/resolve_is_admin_from_groups read
# these exact literal names.

variable "group_names" {
  description = "The four fixed Cognito groups this module creates, keyed by precedence (lower = higher priority). DO NOT change these names without updating backend/app/core/entitlements.py in lockstep."
  type = object({
    admins          = string
    tier_enterprise = string
    tier_pro        = string
    tier_basic      = string
  })
  default = {
    admins          = "flowin-admins"
    tier_enterprise = "flowin-tier-enterprise"
    tier_pro        = "flowin-tier-pro"
    tier_basic      = "flowin-tier-basic"
  }
}

variable "tags" {
  description = "Additional tags merged onto every resource in this module (mandatory-tags locals pattern owned by the caller)."
  type        = map(string)
  default     = {}
}
