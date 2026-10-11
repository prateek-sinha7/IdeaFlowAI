#!/usr/bin/env bash
# =============================================================================
# Upload host config artifacts to s3://<bucket>/config/.
# =============================================================================
# Usage:
#   upload-host-config.sh <bucket> <kms-key-arn> <region> <file>...
#
# Each <file> is a path in the checkout; it is uploaded to
# s3://<bucket>/config/<basename>. The script stops at the first failed upload.
#
# WHY THIS EXISTS (the bug it fixes)
# ----------------------------------
# Four files are needed by a host at BOOT time, not just at deploy time:
#
#   docker-compose.yml, docker-compose.prod.yml,
#   reconcile-host-config.sh, velocityai-load-secrets.sh
#
# deploy.yml ships them INLINE in the SSM payload, so a running host always gets
# the version from the commit being deployed. But bootstrap-ec2.sh FETCHES them
# from s3://<bucket>/config/ — and only provision.yml ever wrote that prefix.
# So a rebuilt or replaced instance booted on whatever was uploaded by the last
# PROVISION run, which could be many deploys stale: an old compose file, an old
# loader allowlist (silently dropping config keys the app now reads), an old
# nginx/CloudWatch reconcile. The box then looked healthy while running a
# configuration nobody had reviewed in months.
#
# deploy.yml now calls this script after a successful redeploy, so S3 tracks the
# deployed commit and a rebuild lands on the same configuration the running host
# already has.
#
# IAM: the per-environment deploy role already grants what this needs —
# s3:PutObject + s3:GetObject on <bucket>/config/* (github_oidc.tf sid
# ConfigObjectUpload), s3:GetEncryptionConfiguration on the bucket
# (sid ConfigBucketEncryptionRead), and kms:GenerateDataKey + kms:Decrypt via S3
# (sid KMSForConfigUploadViaS3). No IAM change is required to adopt this.
# Note there is deliberately no s3:DeleteObject: this script only ever replaces
# objects, never removes them.
set -euo pipefail

if [ "$#" -lt 4 ]; then
  echo "::error::usage: upload-host-config.sh <bucket> <kms-key-arn> <region> <file>..." >&2
  exit 1
fi

bucket="$1"
kms_key_id="$2"
region="$3"
shift 3

# Fail before the first API call if a path is wrong, rather than uploading a
# partial set and leaving config/ internally inconsistent.
for src in "$@"; do
  if [ ! -s "$src" ]; then
    echo "::error::'${src}' does not exist or is empty — refusing to upload a partial config set." >&2
    exit 1
  fi
done

# Detect the bucket's own default encryption rather than assuming SSE-KMS is
# enforced (it may not be, on a hand-created bucket). A bucket with no
# default-encryption rule at all, or one this role cannot read, degrades to a
# plain upload — S3 always encrypts at rest with at least SSE-S3 regardless of
# what this script passes.
ENCRYPTION_JSON="$(aws s3api get-bucket-encryption \
  --bucket "$bucket" --region "$region" 2>/dev/null || echo '')"

SSE_ARGS=()
if [ -n "$ENCRYPTION_JSON" ]; then
  SSE_ALGO="$(echo "$ENCRYPTION_JSON" | jq -r '.ServerSideEncryptionConfiguration.Rules[0].ApplyServerSideEncryptionByDefault.SSEAlgorithm // empty')"
  if [ "$SSE_ALGO" = "aws:kms" ]; then
    SSE_ARGS=(--sse aws:kms --sse-kms-key-id "$kms_key_id")
    echo "Bucket '${bucket}' enforces SSE-KMS — uploading with --sse aws:kms."
  else
    echo "Bucket '${bucket}' default encryption is '${SSE_ALGO:-unset}' — uploading without an explicit --sse flag (bucket default applies)."
  fi
else
  echo "::notice::Could not read default encryption for '${bucket}' (none configured, or this role lacks s3:GetEncryptionConfiguration) — uploading without an explicit --sse flag. S3 still encrypts at rest with at least SSE-S3."
fi

content_type_for() {
  case "$1" in
    *.sh)          echo "text/x-shellscript" ;;
    *.yml | *.yaml) echo "text/yaml" ;;
    *)             echo "application/octet-stream" ;;
  esac
}

# `aws s3 cp` exits non-zero on any failed PUT (set -e stops here) and S3 is
# read-after-write consistent, so a separate head-object pass proved nothing more.
for src in "$@"; do
  key="$(basename "$src")"
  aws s3 cp "$src" "s3://${bucket}/config/${key}" \
    --region "$region" \
    --content-type "$(content_type_for "$key")" \
    "${SSE_ARGS[@]}"
  echo "  uploaded: config/${key}"
done
