#!/usr/bin/env bash
# Materialize the application environment from the environment-scoped SSM path.
#
# This file is the canonical loader implementation. bootstrap-ec2.sh installs it
# for a first boot, and remote-deploy.sh atomically refreshes it from the exact
# commit being deployed before invoking it. Keep the explicit allowlist below:
# the parameter prefix also contains deploy, bootstrap, and CloudWatch values
# that must not enter the container environment.
set -euo pipefail

# shellcheck source=/dev/null
. /etc/velocityai/bootstrap.env

OUT=/etc/velocityai/app.env
TMP=$(mktemp /etc/velocityai/app.env.XXXXXX)
chmod 0640 "$TMP"
chown root:velocityai "$TMP"

REGION="${VELOCITYAI_REGION:-eu-central-1}"
PREFIX="${VELOCITYAI_PARAM_PREFIX:-/velocityai/prod}"
DOMAIN="${VELOCITYAI_FQDN:-}"

# Preserve host-managed image pins and Compose interpolation values. Everything
# else in app.env is regenerated from SSM on each invocation.
if [[ -f "$OUT" ]]; then
    grep -E '^(BACKEND_IMAGE|FRONTEND_IMAGE|ENV|VELOCITYAI_ENVIRONMENT|VELOCITYAI_CW_LOG_GROUP)=' "$OUT" >> "$TMP" || true
fi

emit() {
    # EnvironmentFile and Docker Compose treat text after the first '=' as the
    # literal value. SSM values cannot contain literal newlines.
    printf '%s=%s\n' "$1" "$2" >> "$TMP"
}

CORS_SET=0
PUBLIC_BASE_URL_SET=0
# Keep each parameter as a compact JSON object. This avoids splitting a
# multi-line value into accidental parameter records.
while IFS= read -r param_json; do
    name="$(jq -r '.Name' <<<"$param_json")"
    value="$(jq -r '.Value' <<<"$param_json")"
    rel="${name#${PREFIX}/}"
    case "$rel" in
        CORS_ORIGINS)
            if [[ -n "$value" ]]; then
                emit CORS_ORIGINS "$value"
                CORS_SET=1
            fi
            ;;
        PUBLIC_BASE_URL)
            if [[ -n "$value" ]]; then
                emit PUBLIC_BASE_URL "$value"
                PUBLIC_BASE_URL_SET=1
            fi
            ;;
        SECRET_KEY|ACCESS_TOKEN_EXPIRE_HOURS|LANGSMITH_TRACING|LANGSMITH_API_KEY|LANGSMITH_PROJECT|HANDOFF_MAX_TRANSCRIPT_BYTES|COGNITO_USER_POOL_ID|COGNITO_CLIENT_ID|COGNITO_CLIENT_SECRET|COGNITO_REGION|ADMIN_MFA_REQUIRED|AUTH_EMAIL_MFA_ENABLED)
            emit "$rel" "$value"
            ;;
        HOST_CAPACITY_*)
            emit "$rel" "$value"
            ;;
        DATABASE_PASSWORD)
            emit DATABASE_URL "postgresql://velocityai:${value}@host.docker.internal:5432/velocityai"
            ;;
        llm/region)               emit AWS_REGION                   "$value" ;;
        llm/model_id)             emit BEDROCK_MODEL_ID             "$value" ;;
        llm/inference_profile_id) emit BEDROCK_INFERENCE_PROFILE_ID "$value" ;;
        llm/coding_model_id)      emit BEDROCK_CODING_MODEL_ID      "$value" ;;
        deploy/*|cloudwatch-agent/*|bootstrap/*)
            # These values belong to host recovery, the CloudWatch agent, or
            # retired bootstrap state. They must not be exposed to containers.
            ;;
        *)
            echo "[velocityai-load-secrets] WARN: ignoring unknown parameter ${name}" >&2
            ;;
    esac
done < <(aws ssm get-parameters-by-path \
            --path "$PREFIX" --recursive --with-decryption \
            --region "$REGION" \
            --query 'Parameters[].{Name:Name,Value:Value}' --output json \
            | jq -c '.[]')

if [[ "$CORS_SET" -eq 0 && -n "$DOMAIN" ]]; then
    emit CORS_ORIGINS "[\"https://${DOMAIN}\"]"
fi

if [[ "$PUBLIC_BASE_URL_SET" -eq 0 && -n "$DOMAIN" ]]; then
    emit PUBLIC_BASE_URL "https://${DOMAIN}"
fi

mv "$TMP" "$OUT"
chmod 0640 "$OUT"
chown root:velocityai "$OUT"
