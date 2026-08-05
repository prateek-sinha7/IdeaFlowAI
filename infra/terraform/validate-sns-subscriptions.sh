#!/bin/bash
# M-13: Validate SNS email subscriptions are confirmed before considering
# the deployment complete. An unconfirmed PendingConfirmation subscription
# means no alerts are being delivered — catch this early.
#
# Usage: bash infra/terraform/validate-sns-subscriptions.sh <environment>
#   e.g. bash infra/terraform/validate-sns-subscriptions.sh dev
#
# Prerequisites:
#   - AWS CLI v2 with credentials for the project account
#   - jq for JSON parsing
#   - The SNS topics created by the app Terraform layer
#
# Exit codes:
#   0 = all subscriptions confirmed
#   1 = one or more subscriptions pending
#   2 = error (missing topic, AWS API failure, etc.)

set -euo pipefail

ENV="${1:-dev}"
REGION="${REGION:-eu-central-1}"

# SNS topics created by modules/monitoring/main.tf
ALERTS_TOPIC="velocityai-${ENV}-alerts"
CRITICAL_TOPIC="velocityai-${ENV}-critical"

echo "[M-13] Validating SNS email subscriptions for environment: $ENV"
echo ""

check_topic_subscriptions() {
    local topic_name="$1"
    local topic_arn

    # Resolve topic ARN
    topic_arn=$(aws sns list-topics --region "$REGION" --query "Topics[?contains(TopicArn, '${topic_name}')].TopicArn" --output text 2>/dev/null) || {
        echo "❌ ERROR: Could not list SNS topics (AWS API failure or credentials missing)"
        return 2
    }

    if [[ -z "$topic_arn" ]]; then
        echo "❌ ERROR: Topic '${topic_name}' not found (Terraform app layer may not have been applied yet)"
        return 2
    fi

    echo "Topic: $topic_arn"

    # List subscriptions
    local subscriptions
    subscriptions=$(aws sns list-subscriptions-by-topic --topic-arn "$topic_arn" --region "$REGION" --query "Subscriptions[].[Endpoint,SubscriptionArn]" --output json)

    # Parse and check each subscription
    local pending_count=0
    local confirmed_count=0
    local total=0

    while IFS= read -r line; do
        if [[ -z "$line" ]]; then continue; fi

        local endpoint
        local status
        endpoint=$(echo "$line" | jq -r '.[0]')
        status=$(echo "$line" | jq -r '.[1]')
        total=$((total + 1))

        if [[ "$status" == "PendingConfirmation" ]]; then
            echo "  ⏳ PENDING: $endpoint"
            pending_count=$((pending_count + 1))
        else
            echo "  ✅ CONFIRMED: $endpoint"
            confirmed_count=$((confirmed_count + 1))
        fi
    done < <(echo "$subscriptions" | jq -c '.[]')

    echo "  Summary: $confirmed_count confirmed, $pending_count pending, $total total"
    echo ""

    return "$pending_count"
}

# Check both topics
exit_code=0
check_topic_subscriptions "$ALERTS_TOPIC" || exit_code=$?
check_topic_subscriptions "$CRITICAL_TOPIC" || exit_code=$?

if [[ $exit_code -eq 0 ]]; then
    echo "✅ All SNS subscriptions are confirmed. Alerts will be delivered."
    exit 0
else
    echo "❌ One or more SNS subscriptions are PENDING. Operators must confirm via email."
    echo ""
    echo "Recovery steps:"
    echo "  1. Check your email (including spam folder) for AWS SNS confirmation links"
    echo "  2. Click the 'Confirm subscription' link in the email"
    echo "  3. Re-run this script to verify: bash infra/terraform/validate-sns-subscriptions.sh $ENV"
    echo ""
    echo "If no email arrived:"
    echo "  1. Check alert_email in the tfvars file is correct"
    echo "  2. Run the app Terraform apply again (it will update the topic email)"
    echo "  3. Re-check your email"
    exit 1
fi
