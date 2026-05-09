#!/bin/bash
# Flowin EC2 user-data — minimal bootstrap.
#
# This script intentionally does almost nothing. The full bootstrap (apt
# install, postgres init, nginx config, app deploy, systemd units, certbot)
# lives in `docs/SIMPLE_AWS_DEPLOYMENT.md` Appendix D. We pull and run that
# script via SSM RunCommand or a direct fetch from the configured artifact
# location after first boot.
#
# Variables:
#   environment             : ${environment}
#   region                  : ${region}
#   parameter_path_prefix   : ${parameter_path_prefix}
#   data_device_hint        : ${data_device_hint}
#   bootstrap_log           : /var/log/flowin-bootstrap.log

set -euo pipefail
exec > >(tee -a /var/log/flowin-bootstrap.log) 2>&1

echo "[user-data] $(date -u +%FT%TZ) — Flowin first-boot start"
echo "[user-data] env=${environment} region=${region} prefix=${parameter_path_prefix}"

# Make IMDSv2-only and tight
echo "[user-data] tightening IMDS access"
TOKEN=$(curl -fsS -X PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 60" || true)

# Wait for cloud-init's apt-lock to free, then install AWS CLI v2 if missing.
echo "[user-data] waiting for apt lock"
while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1; do sleep 2; done

apt-get update -y
apt-get install -y --no-install-recommends curl unzip ca-certificates jq

if ! command -v aws >/dev/null 2>&1; then
  echo "[user-data] installing aws-cli v2"
  TMP=$(mktemp -d)
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "$TMP/awscliv2.zip"
  unzip -q "$TMP/awscliv2.zip" -d "$TMP"
  "$TMP/aws/install"
  rm -rf "$TMP"
fi

# Self-identify and tag the journal entry for ops searchability.
INSTANCE_ID=$(curl -fsS -H "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/meta-data/instance-id || echo unknown)
echo "[user-data] instance_id=$INSTANCE_ID"

# Mark "ready for ops bootstrap" — the operator (or SSM RunCommand from CI)
# now drives the heavy installation per Appendix D.
mkdir -p /etc/flowin
cat >/etc/flowin/bootstrap.env <<EOF
FLOWIN_ENVIRONMENT=${environment}
FLOWIN_REGION=${region}
FLOWIN_PARAM_PREFIX=${parameter_path_prefix}
FLOWIN_DATA_DEVICE=${data_device_hint}
EOF
chmod 0644 /etc/flowin/bootstrap.env

%{ for k, v in extra_env ~}
echo "${k}=${v}" >> /etc/flowin/bootstrap.env
%{ endfor ~}

echo "[user-data] minimal bootstrap complete; awaiting SSM RunCommand for full install"
