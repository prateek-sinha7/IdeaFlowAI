set -euo pipefail

# ── Resolve the project CMK alias ─────────────────────────────
# The instance role's kms-decrypt policy grants Decrypt ONLY on this
# key, with a PARAMETER_ARN encryption-context condition, so omitting
# --key-id would let SSM re-key the parameter under alias/aws/ssm and
# the box would lose the ability to read its own secrets.
#
# FIX-KMS-01: the alias used to be DERIVED from the environment name
# (`alias/velocityai` for prod, `alias/velocityai-<env>` otherwise),
# which silently assumed the account's aliases follow that exact
# convention. They do not — the dev key is `velocityai-dev-euc1` (it
# carries a region suffix) — so every deploy failed at the first
# SecureString push with `InvalidKeyId ... alias/velocityai-dev is
# not found`. The alias is now an explicit per-environment INPUT
# (vars.KMS_KEY_ALIAS), with the old derivation kept only as a
# fallback so environments that do match the convention keep working.
if [[ -n "${KMS_KEY_ALIAS:-}" ]]; then
  # Accept both `velocityai-dev-euc1` and `alias/velocityai-dev-euc1`
  # so the variable can be pasted straight from the KMS console,
  # which shows the alias without the prefix.
  KMS_ALIAS="${KMS_KEY_ALIAS#alias/}"
  KMS_ALIAS="alias/${KMS_ALIAS}"
  echo "Using KMS alias from vars.KMS_KEY_ALIAS: ${KMS_ALIAS}"
elif [[ "$DEPLOY_ENV" == "prod" ]]; then
  KMS_ALIAS="alias/velocityai"
  echo "::warning::vars.KMS_KEY_ALIAS is not set on the '${DEPLOY_ENV}' environment — falling back to the derived alias ${KMS_ALIAS}."
else
  KMS_ALIAS="alias/velocityai-${DEPLOY_ENV}"
  echo "::warning::vars.KMS_KEY_ALIAS is not set on the '${DEPLOY_ENV}' environment — falling back to the derived alias ${KMS_ALIAS}."
fi

# Validate the SHAPE only — deliberately NOT `aws kms describe-key`.
# The deploy role is granted exactly one KMS action, kms:Encrypt,
# under a `kms:ViaService = ssm.<region>.amazonaws.com` condition
# (infra/terraform/bootstrap/github_oidc.tf,
# sid=KMSEncryptSecureStringViaSSM). A direct KMS call is therefore
# denied twice over — DescribeKey is not in the policy, and ViaService
# rejects anything that does not arrive through SSM — so a preflight
# probe would fail on a perfectly good alias. The authoritative check
# is the first put-parameter below, whose InvalidKeyId is translated
# into actionable guidance by put_param's error handler.
# KMS alias names allow alphanumerics plus _ - / (and must not use the
# reserved alias/aws/ prefix, which is the AWS-managed key this step
# exists to avoid).
if [[ ! "$KMS_ALIAS" =~ ^alias/[A-Za-z0-9/_-]+$ ]]; then
  echo "::error::Resolved KMS alias '${KMS_ALIAS}' is not a valid alias name."
  echo "::error::Set KMS_KEY_ALIAS on the '${DEPLOY_ENV}' GitHub Environment to the alias shown in the KMS console (e.g. velocityai-dev-euc1)."
  exit 1
fi
if [[ "$KMS_ALIAS" == alias/aws/* ]]; then
  echo "::error::KMS alias '${KMS_ALIAS}' is an AWS-managed key. SecureStrings must use the project CMK so the instance role's scoped kms:Decrypt grant still applies."
  exit 1
fi

# FIX-SSM-01: explicit desired-state semantics per parameter, instead
# of the previous blanket "empty value -> skip (leave whatever SSM
# already has)". A skip silently preserved a STALE value: clearing
# LANGSMITH_API_KEY/LANGSMITH_TRACING in GitHub, for example, did not
# disable tracing if an older SSM value existed, because the host
# loader re-reads the old parameter on every deploy. Semantics now:
#   required        -> empty value FAILS the deploy (never silently
#                      proceed on a missing secret the app needs)
#   delete-if-empty -> empty value DELETES the existing parameter,
#                      so the host loader's own documented fallback
#                      (a default, or the box's FQDN, etc.) applies
#                      instead of a value GitHub no longer sets
# Values are never echoed for either outcome — only key names and
# the action taken (created/updated/deleted/unchanged).
#
# FIX-SSM-05: the delete-if-empty half above was WRITTEN here but not
# in force — it depended on an ssm:GetParameter probe the deploy role
# is not granted, and the denial was indistinguishable from "parameter
# absent". See the long note inside put_param's empty-value branch.
declare -i PARAMS_PUSHED=0 PARAMS_DELETED=0 PARAMS_UNCHANGED=0

put_param() {
  local key="$1" value="$2" type="${3:-String}" policy="${4:-delete-if-empty}"
  if [[ -z "$value" ]]; then
    if [[ "$policy" == "required" ]]; then
      echo "::error::Required config value for '${key}' is empty — refusing to deploy without it."
      exit 1
    fi
    # delete-if-empty: remove any existing parameter so the host's
    # own fallback/default takes effect, rather than leaving a
    # stale value from a previous deploy in place.
    #
    # FIX-SSM-05: this used to PROBE first with
    # `aws ssm get-parameter ... >/dev/null 2>&1` and only delete when
    # the probe succeeded. That made the whole delete-if-empty policy a
    # no-op, because the deploy role has no ssm:GetParameter (and
    # deliberately still doesn't — see the SSMDeleteParameters comment
    # in infra/terraform/bootstrap/github_oidc.tf). The probe returned
    # non-zero on AccessDenied exactly as it does on ParameterNotFound,
    # so every empty value took the `else` branch, logged `unchanged`,
    # and left the stale SSM value serving the box. FIX-SSM-01's stated
    # semantics were never actually in force.
    #
    # Call delete-parameter directly and CLASSIFY the failure instead:
    # ParameterNotFound is the only benign error (nothing to delete);
    # anything else — AccessDenied, throttling, a wrong region — fails
    # the deploy. Silence is no longer an outcome.
    local del_err
    del_err="$(mktemp)"
    if aws ssm delete-parameter \
      --name "${SSM_PREFIX}/${key}" \
      --region "$AWS_REGION" \
      --no-cli-pager >/dev/null 2>"$del_err"; then
      echo "  deleted: ${key} (cleared in GitHub — host default/fallback now applies)"
      PARAMS_DELETED+=1
      rm -f "$del_err"
      return
    fi
    if grep -q 'ParameterNotFound' "$del_err"; then
      rm -f "$del_err"
      echo "  unchanged: ${key} (empty, no existing parameter)"
      PARAMS_UNCHANGED+=1
      return
    fi
    # Any other failure is real. Surface the AWS error verbatim (it
    # names the parameter and the action, never a value) and stop.
    cat "$del_err" >&2
    if grep -q 'AccessDenied' "$del_err"; then
      echo "::error::The deploy role was denied ssm:DeleteParameter on '${SSM_PREFIX}/${key}'."
      echo "::error::Apply the SSMDeleteParameters statement for the '${DEPLOY_ENV}' role (infra/terraform/bootstrap/github_oidc.tf). Without it a value cleared in GitHub silently keeps serving from SSM."
    fi
    rm -f "$del_err"
    echo "::error::Refusing to continue: '${key}' was cleared in GitHub but the stale SSM parameter could not be removed."
    exit 1
  fi
  # An ARRAY, not a word-split string: `--key-id $KMS_ALIAS` inside an
  # unquoted variable only works by accident and breaks the moment an
  # alias contains anything unusual.
  local -a kms_args=()
  local suffix=""
  if [[ "$type" == "SecureString" ]]; then
    kms_args=(--key-id "$KMS_ALIAS")
    suffix=" -> ${KMS_ALIAS}"
  fi
  # --value is passed from a shell variable, never interpolated into a
  # log line, and stdout is discarded: put-parameter echoes back the
  # parameter metadata, and for a SecureString we do not want any of
  # that in the run log.
  #
  # stderr IS captured (not discarded) so an InvalidKeyId can be
  # turned into the one instruction that actually fixes it. It is
  # safe to surface: put-parameter's error messages describe the key
  # and parameter name, never the --value. On any other error the
  # captured stderr is re-emitted verbatim so nothing is swallowed.
  local err_file rc=0
  err_file="$(mktemp)"
  if ! aws ssm put-parameter \
    --name "${SSM_PREFIX}/${key}" \
    --value "$value" \
    --type "$type" \
    --overwrite \
    "${kms_args[@]}" \
    --region "$AWS_REGION" \
    --no-cli-pager >/dev/null 2>"$err_file"; then
    rc=1
  fi
  if [[ "$rc" -ne 0 ]]; then
    cat "$err_file" >&2
    if grep -q 'InvalidKeyId' "$err_file"; then
      echo "::error::SSM rejected the KMS key '${KMS_ALIAS}' while writing '${key}'."
      echo "::error::The alias must exist in ${AWS_REGION} in this account. Copy it from the KMS console (e.g. velocityai-dev-euc1) into the KMS_KEY_ALIAS variable on the '${DEPLOY_ENV}' GitHub Environment."
    elif grep -q 'AccessDenied' "$err_file"; then
      echo "::error::The deploy role was denied writing '${key}'. If this is a SecureString, confirm the '${KMS_ALIAS}' key ARN is included in github_cicd_kms_key_arns for the '${DEPLOY_ENV}' role (infra/terraform/bootstrap/github_oidc.tf)."
    fi
    rm -f "$err_file"
    exit 1
  fi
  rm -f "$err_file"
  echo "  pushed: ${key} (${type}${suffix})"
  PARAMS_PUSHED+=1
}

echo "Pushing config to SSM under ${SSM_PREFIX}/..."

# SecureString params (secrets). DATABASE_PASSWORD is deliberately
# absent (D-5): it is generated on the box by bootstrap-ec2.sh and
# written to SSM from there. So is the app-level ENV (D-6).
# SECRET_KEY is the app's session/JWT signing secret — required,
# never delete-on-empty (an accidental blank GitHub secret must fail
# loudly, not silently wipe the running app's signing key).
put_param "SECRET_KEY"              "$SECRET_KEY"              "SecureString" "required"
put_param "LANGSMITH_API_KEY"       "$LANGSMITH_API_KEY"       "SecureString" "delete-if-empty"
put_param "bootstrap/admin-password" "$BOOTSTRAP_ADMIN_PASSWORD" "SecureString" "delete-if-empty"

# String params (plain config) — all optional/defaulted on the host
# loader, so an empty GitHub value deletes the SSM override and lets
# the host's own documented default/fallback apply.
put_param "CORS_ORIGINS"                 "$CORS_ORIGINS"                 "String" "delete-if-empty"
put_param "PUBLIC_BASE_URL"              "$PUBLIC_BASE_URL"              "String" "delete-if-empty"
put_param "ACCESS_TOKEN_EXPIRE_HOURS"    "$ACCESS_TOKEN_EXPIRE_HOURS"    "String" "delete-if-empty"
put_param "HANDOFF_MAX_TRANSCRIPT_BYTES" "$HANDOFF_MAX_TRANSCRIPT_BYTES" "String" "delete-if-empty"
put_param "LANGSMITH_TRACING"            "$LANGSMITH_TRACING"            "String" "delete-if-empty"
put_param "LANGSMITH_PROJECT"             "$LANGSMITH_PROJECT"            "String" "delete-if-empty"
put_param "bootstrap/admin-email"        "$BOOTSTRAP_ADMIN_EMAIL"        "String" "delete-if-empty"

# specs/014 — host capacity matrix + admission gate. Only these two
# are pushed from GitHub Environment variables; every other
# HOST_CAPACITY_* setting (thresholds, gate on/off, poll interval,
# etc.) is left at its Settings default (app/core/config.py) and
# changed there directly if a non-default value is ever needed.
# Plain config, never secrets.
put_param "HOST_CAPACITY_METRIC_NAMESPACE"       "$HOST_CAPACITY_METRIC_NAMESPACE"       "String" "delete-if-empty"
put_param "HOST_CAPACITY_INSTANCE_IDS"           "$HOST_CAPACITY_INSTANCE_IDS"           "String" "delete-if-empty"

# Bedrock LLM config (under the llm/ sub-prefix the host loader maps
# to AWS_REGION / BEDROCK_* — any other key name is silently dropped).
# llm/region always has a value (the resolved AWS_REGION), so it is
# never empty; the rest follow the same delete-if-empty semantics.
put_param "llm/region"               "$AWS_REGION"                   "String" "required"
put_param "llm/model_id"             "$BEDROCK_MODEL_ID"             "String" "delete-if-empty"
put_param "llm/inference_profile_id" "$BEDROCK_INFERENCE_PROFILE_ID" "String" "delete-if-empty"
put_param "llm/coding_model_id"      "$BEDROCK_CODING_MODEL_ID"      "String" "delete-if-empty"

echo "Config push complete: ${PARAMS_PUSHED} pushed, ${PARAMS_DELETED} deleted, ${PARAMS_UNCHANGED} unchanged."
