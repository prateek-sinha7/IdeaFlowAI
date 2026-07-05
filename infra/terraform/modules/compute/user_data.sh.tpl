#!/bin/bash
# VelocityAI EC2 user-data — minimal bootstrap.
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
#   bootstrap_log           : /var/log/velocityai-bootstrap.log

set -euo pipefail
exec > >(tee -a /var/log/velocityai-bootstrap.log) 2>&1

echo "[user-data] $(date -u +%FT%TZ) — VelocityAI first-boot start"
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
mkdir -p /etc/velocityai
cat >/etc/velocityai/bootstrap.env <<EOF
VELOCITYAI_ENVIRONMENT=${environment}
VELOCITYAI_REGION=${region}
VELOCITYAI_PARAM_PREFIX=${parameter_path_prefix}
VELOCITYAI_DATA_DEVICE=${data_device_hint}
EOF
chmod 0644 /etc/velocityai/bootstrap.env

%{ for k, v in extra_env ~}
echo "${k}=${v}" >> /etc/velocityai/bootstrap.env
%{ endfor ~}

# --- First-boot full host bootstrap (async, self-provisioning) -------------
# We do NOT run infra/scripts/bootstrap-ec2.sh inline here: that script waits
# on `cloud-init status --wait`, and this user-data IS cloud-init's final
# stage — calling it synchronously would deadlock (the wait can never finish
# because it's waiting for the script that's calling it). Instead we install a
# systemd oneshot unit and start it with `--no-block` so it runs INDEPENDENTLY
# of cloud-init. Once user-data returns, cloud-init reports done and the
# script's internal wait unblocks. The unit is guarded by a sentinel so it
# runs exactly once per instance; bootstrap-ec2.sh writes that sentinel on
# successful completion.
install -d -m 0755 /opt/velocityai

cat >/opt/velocityai/run-firstboot-bootstrap.sh <<'WRAP'
#!/usr/bin/env bash
set -euo pipefail
exec > >(tee -a /var/log/velocityai-firstboot.log) 2>&1
echo "[firstboot] $(date -u +%FT%TZ) fetching bootstrap-ec2.sh from S3"
# shellcheck source=/dev/null
. /etc/velocityai/bootstrap.env
: "$${VELOCITYAI_BACKUP_BUCKET:?VELOCITYAI_BACKUP_BUCKET missing}"
REGION="$${VELOCITYAI_REGION:-eu-central-1}"
for i in $(seq 1 30); do
  if aws s3 cp "s3://$${VELOCITYAI_BACKUP_BUCKET}/config/bootstrap-ec2.sh" \
       /opt/velocityai/bootstrap-ec2.sh --region "$${REGION}"; then
    break
  fi
  echo "[firstboot] bootstrap-ec2.sh not available yet (attempt $i) — retrying"
  sleep 10
done
chmod 0755 /opt/velocityai/bootstrap-ec2.sh
echo "[firstboot] running bootstrap-ec2.sh"
bash /opt/velocityai/bootstrap-ec2.sh
WRAP
chmod 0755 /opt/velocityai/run-firstboot-bootstrap.sh

cat >/etc/systemd/system/velocityai-firstboot.service <<'UNIT'
[Unit]
Description=VelocityAI first-boot full host bootstrap (Postgres, nginx, Docker, app)
After=cloud-init.target network-online.target
Wants=network-online.target
ConditionPathExists=!/var/lib/velocityai/.bootstrap-done

[Service]
Type=oneshot
RemainAfterExit=yes
TimeoutStartSec=1800
ExecStart=/opt/velocityai/run-firstboot-bootstrap.sh

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable velocityai-firstboot.service
# --no-block: start it now but do NOT wait (avoids the cloud-init deadlock).
systemctl start --no-block velocityai-firstboot.service

echo "[user-data] minimal bootstrap complete; velocityai-firstboot.service started (async full install)"
