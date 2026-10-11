# shellcheck shell=bash
# =============================================================================
# host-common.sh — shared host-provisioning helpers.
# =============================================================================
# SOURCED, never executed. Deliberately has no shebang and no `set -euo
# pipefail`: it inherits the caller's shell options, and setting them here would
# silently change the error posture of whichever script sources it.
#
# Sourced by:
#   infra/scripts/bootstrap-ec2.sh      — from /opt/velocityai/lib/host-common.sh,
#                                         fetched from s3://<bucket>/config/
#   .github/scripts/remote-bootstrap.sh — INLINED into the SSM payload by
#                                         .github/workflows/provision.yml, because
#                                         that script runs before any file exists
#                                         on the box
#
# R-05/R-06/R-13: apt-over-HTTPS rewriting, the apt-lock wait, the AWS CLI v2
# install and the CloudWatch namespace map each existed in two places. The
# AWSCLI_VERSION pin in particular was written twice ("2.17.42" in both
# bootstrap-ec2.sh §2b and remote-bootstrap.sh §2), so a bump could land on one
# provisioning path and not the other — and which path a given box took depends on
# whether it was Terraform-created or hand-created, i.e. on history rather than on
# anything visible in the repo.
#
# Every function is idempotent: whichever caller runs first leaves nothing for the
# other to do.
#
# ⚠ THIS FILE MUST STAY POSIX-sh PARSEABLE. P10 requires the SSM payload's first
# executable line to be the `if [ -z "${BASH_VERSION:-}" ]; then exec bash ...; fi`
# re-exec guard, because SSM's AWS-RunShellScript invokes the payload with /bin/sh
# (dash on Ubuntu) and ignores the shebang. This library is catted into the payload
# BEFORE remote-bootstrap.sh, so dash parses and executes everything here before it
# ever reaches that guard. Therefore: no `[[ ]]`, no arrays, no `${var^}`, no
# `<<<`, no `mapfile`. `local` is fine — dash supports it.
# Verified by parsing the assembled payload with `sh -n`.
#
# LOG PREFIX: callers set HOST_COMMON_LOG_PREFIX (e.g. "[bootstrap]" or
# "[provision]") so output stays attributable to the script the operator is
# reading. Defaults to "[host]".

: "${HOST_COMMON_LOG_PREFIX:=[host]}"

# The ONE AWS CLI v2 pin for every host provisioning path. Bump here only.
AWSCLI_VERSION="2.17.42"

_hc_log() {
    echo "${HOST_COMMON_LOG_PREFIX} $*"
}

_hc_err() {
    echo "${HOST_COMMON_LOG_PREFIX} $*" >&2
}

# ---------------------------------------------------------------------------
# apt_force_https — rewrite Ubuntu apt sources from http:// to https://
# ---------------------------------------------------------------------------
# This host egresses on 443 ONLY (a single security-group rule, tcp/443 to
# 0.0.0.0/0) and routes via a Transit Gateway rather than a NAT/internet gateway.
# Ubuntu ships its apt sources as http:// (port 80), so every archive fetch times
# out and `apt-get install` dies with exit 100 — while SSM, S3 and KMS all keep
# working, which makes the failure look unrelated to networking.
#
# archive.ubuntu.com, security.ubuntu.com and the regional
# <region>.ec2.archive.ubuntu.com mirrors all serve TLS, so matching by hostname
# preserves the in-region mirror (lower latency, no cross-region egress) and
# leaves third-party lists alone. apt has had native HTTPS support since 1.5 and
# ca-certificates ships on the Canonical AMI, so this needs no package installed
# first — which matters, because installing one is exactly what is blocked.
#
# Covers both Noble's deb822 /etc/apt/sources.list.d/*.sources and the legacy
# .list format. Idempotent: a second pass finds no http:// Ubuntu URLs left.
apt_force_https() {
    local apt_src rewritten=0
    local host_re='http://([A-Za-z0-9.-]*\.)?(archive|security)\.ubuntu\.com'

    # Each path is tested with -f rather than globbed into grep: Noble ships no
    # *.list in sources.list.d, the shell leaves the unmatched glob literal, and
    # grep then exits 2 on a nonexistent path — which under `set -e` + `pipefail`
    # aborts the caller's whole run.
    for apt_src in /etc/apt/sources.list \
                   /etc/apt/sources.list.d/*.sources \
                   /etc/apt/sources.list.d/*.list; do
        [ -f "$apt_src" ] || continue
        grep -Eq "$host_re" "$apt_src" || continue
        [ -f "${apt_src}.pre-https.bak" ] || cp -a "$apt_src" "${apt_src}.pre-https.bak"
        sed -E -i "s#${host_re}#https://\1\2.ubuntu.com#g" "$apt_src"
        _hc_log "apt sources: rewrote http -> https in ${apt_src}"
        rewritten=1
    done

    if [ "$rewritten" -eq 0 ]; then
        _hc_log "apt sources: already https (nothing to rewrite)"
    fi
}

# ---------------------------------------------------------------------------
# apt_wait_lock — block until dpkg's frontend lock is free
# ---------------------------------------------------------------------------
# unattended-upgrades and cloud-init's own package steps hold this lock on a
# freshly booted box. Bounded, unlike the original `while fuser ...; do sleep 2;
# done`: a stuck lock now fails with a diagnosis instead of consuming the whole
# SSM execution timeout and reporting nothing.
apt_wait_lock() {
    local waited=0 limit="${1:-300}"

    while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1; do
        if [ "$waited" -ge "$limit" ]; then
            _hc_err "ERROR: dpkg frontend lock still held after ${limit}s."
            _hc_err "       investigate: fuser -v /var/lib/dpkg/lock-frontend; systemctl status unattended-upgrades"
            return 1
        fi
        if [ "$waited" -eq 0 ]; then
            _hc_log "waiting for the apt lock"
        fi
        sleep 2
        waited=$((waited + 2))
    done
}

# ---------------------------------------------------------------------------
# install_awscli_v2 [version] — install/update the AWS CLI v2
# ---------------------------------------------------------------------------
# Ubuntu Noble (24.04 LTS) removed the `awscli` apt package: it was v1
# (deprecated, EOL July 2025) and the Debian/Ubuntu package was unmaintained. AWS
# distributes v2 as a self-contained binary from awscli.amazonaws.com.
#
# Pinned rather than "latest" so provisioning is reproducible. Idempotent twice
# over: the version check short-circuits when the pin is already installed, and
# `aws/install --update` is itself a no-op at the same version.
#
# Requires curl and unzip to already be present.
install_awscli_v2() {
    local want="${1:-$AWSCLI_VERSION}" tmp have

    have="$(aws --version 2>&1 | awk -F'[/ ]' '{print $2}' || true)"
    if [ "$have" = "$want" ]; then
        _hc_log "aws cli already at ${want}"
        return 0
    fi

    _hc_log "installing aws-cli v2 (${want})"
    tmp="$(mktemp -d)"
    if ! curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64-${want}.zip" \
            -o "${tmp}/awscliv2.zip"; then
        _hc_err "ERROR: could not download the AWS CLI v2 installer for ${want}."
        rm -rf "$tmp"
        return 1
    fi
    unzip -q "${tmp}/awscliv2.zip" -d "$tmp"
    "${tmp}/aws/install" --update --bin-dir /usr/local/bin --install-dir /usr/local/aws-cli
    rm -rf "$tmp"

    _hc_log "aws cli version: $(aws --version)"
}

# ---------------------------------------------------------------------------
# cw_namespace <environment> — the CloudWatch metric namespace for an environment
# ---------------------------------------------------------------------------
# MUST match modules/monitoring's `cw_metric_namespace` ("VelocityAI/" +
# title(environment)), which is what every alarm queries.
#
# FAIL-CLOSED AND SPELLED OUT LITERALLY, not derived with `${env^}`. Those are not
# equivalent: `${env^}` happily produces "VelocityAI/Staging" from "staging" or
# "VelocityAI/Qa" from "qa" — a syntactically valid namespace that no alarm
# watches, so metrics vanish silently and every alarm sits in INSUFFICIENT_DATA
# looking like a quiet system. An unknown environment must be an error.
#
# R-13: reconcile-host-config.sh derived this with `${ENVIRONMENT^}` while
# bootstrap-ec2.sh's velocityai-cw-namespace used the literal map — two
# derivations that agree for dev/stage/prod and disagree for anything else.
cw_namespace() {
    local env="${1:-}"

    if [ -z "$env" ]; then
        echo "cw_namespace: no environment given (expected dev|stage|prod)" >&2
        return 1
    fi

    case "$env" in
        dev)   echo "VelocityAI/Dev"   ;;
        stage) echo "VelocityAI/Stage" ;;
        prod)  echo "VelocityAI/Prod"  ;;
        *)
            echo "cw_namespace: unknown environment '${env}' (expected dev|stage|prod)" >&2
            echo "cw_namespace: refusing to guess — a namespace no alarm queries is worse than a failure" >&2
            return 1
            ;;
    esac
}
