# =============================================================================
# TFLint configuration for the VelocityAI Terraform suite.
# =============================================================================
# Shared by every layer (bootstrap/shared/foundation/app) and every module.
# The CI pipeline (infra/buildspec.yml) exports TFLINT_CONFIG_FILE to this
# file's absolute path and runs `tflint --recursive`, so each directory is
# linted against this same config — recursive mode would otherwise look for a
# per-directory .tflint.hcl and silently lint with no rules where none exists.
#
# Plugin versions are pinned, matching the pin-everything policy the rest of
# the pipeline follows (buildspec.yml pins Terraform + checkov/gitleaks/trivy).
# `tflint --init` downloads the pinned plugins from GitHub before the run.
#
# Exit behaviour: tflint fails the build on findings of severity `error` (e.g.
# the AWS ruleset catching an invalid instance type or malformed ARN). The
# Terraform-ruleset "recommended" rules are mostly `warning`/`notice`, which
# are reported but do not fail by default. To make warnings a hard gate too,
# add `--minimum-failure-severity=warning` to the tflint invocation in
# buildspec.yml.
# =============================================================================

config {
  # Recursive mode lints each layer and module dir as its own root. "local"
  # (the current default, set explicitly for clarity) inspects locally
  # referenced child modules from the layer roots; the module dirs are still
  # linted directly by the recursive walk.
  call_module_type = "local"

  # Report every finding rather than stopping at the first.
  force = false
}

# Bundled Terraform ruleset: naming conventions, unused declarations,
# deprecated syntax, required_version / required_providers presence, etc.
plugin "terraform" {
  enabled = true
  preset  = "recommended"
}

# AWS ruleset: invalid instance types, malformed ARNs, deprecated arguments,
# and other provider-specific correctness checks.
plugin "aws" {
  enabled = true
  version = "0.48.0"
  source  = "github.com/terraform-linters/tflint-ruleset-aws"
}
