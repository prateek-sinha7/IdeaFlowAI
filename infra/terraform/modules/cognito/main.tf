locals {
  tags = merge(
    {
      Name        = "${var.name_prefix}-cognito"
      Component   = "cognito"
      Environment = var.environment
    },
    var.tags,
  )

  # Email OTP as a second factor. Requires BOTH the opt-in flag and SES-backed
  # delivery: Cognito refuses EmailMfaConfiguration on a pool using the built-in
  # COGNITO_DEFAULT sender, and the built-in sender's rate limit would make the
  # factor unusable even if it were accepted. Deriving the flag here (rather
  # than trusting var.email_mfa_enabled alone) means a caller who sets the flag
  # but forgets SES gets a pool without email MFA instead of a failed apply --
  # and the variable validation below turns that into a loud error anyway.
  email_mfa_active = var.email_mfa_enabled && length(var.ses_source_arn) > 0 && var.mfa_configuration != "OFF"

  # AWS will not let email be BOTH the second factor and the account-recovery
  # channel. Two documented constraints, one root cause:
  #
  #   * CreateUserPool/UpdateUserPool reject `verified_email` as the only
  #     AccountRecoverySetting member while EmailMfaConfiguration is active
  #     ("Cannot set verified_email as the only member of
  #     AccountRecoverySetting when EmailMfaConfiguration is active").
  #   * Even where accepted, AWS documents that email MFA DISQUALIFIES email
  #     for account recovery -- so a mixed setting degrades silently rather
  #     than failing at apply time.
  #
  # The reasoning is sound: one compromised mailbox would otherwise yield both
  # the second factor and the password-reset channel, which is not two factors.
  #
  # This pool has no phone numbers (`username_attributes = ["email"]`, no
  # phone_number attribute collected anywhere), so `verified_phone_number` is
  # not an available fallback. That leaves `admin_only`, which is the recorded
  # decision: with email MFA on, self-service password reset is deliberately
  # surrendered and password resets become an administrator operation
  # (`POST /api/admin/users/{id}/reset-password`). The backend reads the same
  # posture from AUTH_EMAIL_MFA_ENABLED and returns an explicit "contact your
  # administrator" instead of silently accepting a reset request whose email
  # will never arrive.
  account_recovery_mechanism = local.email_mfa_active ? "admin_only" : "verified_email"
}

# =============================================================================
# User Pool
# =============================================================================
# Invitation-only (admin_create_user_config.allow_admin_create_user_only =
# true) — mirrors the deliberate self-registration-disabled posture already
# enforced at the application layer (backend/app/api/auth.py `/register`
# always 403s). No hosted UI / domain (Decision 1: the in-app login form
# stays; the backend talks to Cognito via AdminInitiateAuth, never a browser
# redirect to Cognito's own UI). No IdP attached (Decision 2 — "not now") but
# nothing here blocks adding one later.
resource "aws_cognito_user_pool" "this" {
  name = "${var.name_prefix}-users"

  deletion_protection = var.deletion_protection

  # Decision 8: ESSENTIALS. PLUS unlocks threat protection (Phase 6 item 2) —
  # surfaced as a variable so the upgrade is an explicit decision, not a silent
  # assumption (A-7 / R15).
  user_pool_tier = var.feature_plan

  password_policy {
    minimum_length                   = var.password_minimum_length
    require_lowercase                = var.password_require_lowercase
    require_uppercase                = var.password_require_uppercase
    require_numbers                  = var.password_require_numbers
    require_symbols                  = var.password_require_symbols
    temporary_password_validity_days = var.temp_password_validity_days
  }

  # Email is the sign-in identifier (matches `users.email` on the app side);
  # required + non-mutable-by-self would need a custom flow to change, so we
  # leave it mutable — email changes are an admin operation via AdminUpdateUserAttributes,
  # not exposed anywhere yet.
  username_attributes = ["email"]

  auto_verified_attributes = ["email"]

  admin_create_user_config {
    allow_admin_create_user_only = true

    invite_message_template {
      email_subject = "Your Flowin account"
      email_message = "Your username is {username} and temporary password is {####}. Sign in at the Flowin app and you will be asked to set a new password."
      sms_message   = "Your username is {username} and temporary password is {####}."
    }
  }

  # TOTP software-token MFA. Cutover posture is OPTIONAL (Decision 4); the
  # backend enforces "required for admins" as an app-layer gate (no native
  # per-group MFA requirement exists in Cognito).
  mfa_configuration = var.mfa_configuration

  dynamic "software_token_mfa_configuration" {
    for_each = var.mfa_configuration == "OFF" ? [] : [1]
    content {
      enabled = true
    }
  }

  # Email OTP (EMAIL_OTP challenge) as a second factor. Essentials feature plan
  # or higher is required -- see var.feature_plan, which defaults to ESSENTIALS.
  # Cognito delivers the code through the SES identity configured in
  # email_configuration below; there is no separate enrolment ceremony the way
  # TOTP has one (no AssociateSoftwareToken/VerifySoftwareToken pair), because
  # possession of the mailbox is already established by the invitation flow.
  # Enabling the factor for a user is therefore a single SetUserMFAPreference
  # call with EmailMfaSettings -- see backend/app/core/cognito.py.
  dynamic "email_mfa_configuration" {
    for_each = local.email_mfa_active ? [1] : []
    content {
      subject = var.email_mfa_subject
      message = var.email_mfa_message
    }
  }

  # Exactly one mechanism either way. See local.account_recovery_mechanism for
  # why email MFA forces this to admin_only rather than keeping verified_email.
  account_recovery_setting {
    recovery_mechanism {
      name     = local.account_recovery_mechanism
      priority = 1
    }
  }

  # Email delivery (Phase 6 item 3). Cognito's built-in sender is rate limited
  # to a level unusable for real password-reset volume, so production routes
  # through SES with a verified domain + DKIM. Empty ses_source_arn keeps the
  # built-in sender, which is fine for dev.
  dynamic "email_configuration" {
    for_each = length(var.ses_source_arn) > 0 ? [1] : []
    content {
      email_sending_account  = "DEVELOPER"
      source_arn             = var.ses_source_arn
      from_email_address     = var.ses_from_email_address
      reply_to_email_address = var.ses_reply_to_email_address != "" ? var.ses_reply_to_email_address : null
    }
  }

  lifecycle {
    # A user pool holds every account's credential state. Recreating it
    # deletes every user without warning. The operator must explicitly edit
    # this out (documented in the module README) before a destroy is allowed
    # to proceed — mirrors modules/iam's instance-role precedent.
    prevent_destroy = true
  }

  tags = local.tags
}

# =============================================================================
# App client — confidential (has a secret), backend-mediated auth only
# =============================================================================
# No hosted-UI OAuth flows/scopes configured — the backend talks to Cognito
# server-side via AdminInitiateAuth/AdminRespondToAuthChallenge, never a
# browser redirect (Decision 1). generate_secret = true because this client
# is used only from the backend (never shipped to a browser bundle), so a
# SECRET_HASH can be safely computed server-side on every AdminInitiateAuth
# call.
resource "aws_cognito_user_pool_client" "backend" {
  name         = "${var.name_prefix}-backend"
  user_pool_id = aws_cognito_user_pool.this.id

  generate_secret = true

  explicit_auth_flows = [
    "ALLOW_ADMIN_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true

  # Bounds the lifetime of the `Session` string threaded through
  # AdminInitiateAuth -> AdminRespondToAuthChallenge, and therefore how long an
  # emailed OTP stays usable. Cognito's default is 3 minutes, which is tight
  # once SES queuing and inbox delivery are in the path -- a user who has to
  # open a mail client can plausibly exceed it and get an expired-code error
  # that looks like a wrong code. See var.auth_session_validity_minutes.
  auth_session_validity = var.auth_session_validity_minutes

  access_token_validity  = var.access_token_validity_minutes
  id_token_validity      = var.id_token_validity_minutes
  refresh_token_validity = var.refresh_token_validity_days

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  read_attributes  = ["email", "email_verified"]
  write_attributes = ["email"]
}

# =============================================================================
# Groups — fixed precedence table (Decision 6 / migration plan §5.1)
# =============================================================================
# No IAM role attached to any group (cognito:preferred_role is an Identity
# Pool concept this migration does not use — no Identity Pool is created,
# see the plan's non-goals). Tier/role resolution happens in application code
# (core/entitlements.py resolve_tier_from_groups/resolve_is_admin_from_groups)
# from these exact names + precedences.

# --- Threat protection (Phase 6 item 2) -------------------------------------
# Only meaningful on the PLUS feature plan; the resource is skipped entirely
# otherwise so an ESSENTIALS pool doesn't fail apply on an unsupported setting.
# `client_id` is omitted deliberately: that makes this the POOL-LEVEL default,
# which is what we want with a single app client.
resource "aws_cognito_risk_configuration" "this" {
  count = var.feature_plan == "PLUS" && var.threat_protection_mode != "NO_ACTION" ? 1 : 0

  user_pool_id = aws_cognito_user_pool.this.id

  compromised_credentials_risk_configuration {
    # Cognito checks compromised credentials on sign-in and password changes.
    # AWS documents that these checks apply to ADMIN_USER_PASSWORD_AUTH but not
    # SRP — so the Decision-1 backend-mediated flow is compatible.
    event_filter = ["SIGN_IN", "PASSWORD_CHANGE", "SIGN_UP"]

    actions {
      event_action = var.threat_protection_mode == "ENFORCED" ? "BLOCK" : "NO_ACTION"
    }
  }
}

resource "aws_cognito_user_group" "admins" {
  name         = var.group_names.admins
  user_pool_id = aws_cognito_user_pool.this.id
  precedence   = 0
  description  = "is_admin = true"
}

resource "aws_cognito_user_group" "tier_enterprise" {
  name         = var.group_names.tier_enterprise
  user_pool_id = aws_cognito_user_pool.this.id
  precedence   = 10
  description  = "tier = enterprise"
}

resource "aws_cognito_user_group" "tier_pro" {
  name         = var.group_names.tier_pro
  user_pool_id = aws_cognito_user_pool.this.id
  precedence   = 20
  description  = "tier = pro"
}

resource "aws_cognito_user_group" "tier_basic" {
  name         = var.group_names.tier_basic
  user_pool_id = aws_cognito_user_pool.this.id
  precedence   = 30
  description  = "tier = basic"
}
