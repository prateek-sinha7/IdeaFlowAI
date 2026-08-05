# =============================================================================
# tflint configuration for the VelocityAI Terraform tree (infra/terraform/**).
# =============================================================================
# Referenced by BOTH consumers, which must stay in lock-step:
#   - .pre-commit-config.yaml  — local hook, exports TFLINT_CONFIG_FILE to this
#     file and runs `tflint --chdir=infra/terraform --recursive
#     --minimum-failure-severity=error`
#   - .github/workflows/ci.yml — the `security-scan` job runs the identical
#     command, so a commit that passes pre-commit cannot fail CI on lint alone
#
# Both consumers referenced this path before it existed; this file closes that
# gap. Scope is deliberately narrow: the bundled `terraform` ruleset on its
# `recommended` preset plus the AWS ruleset, aligned to the provider version
# pinned in every infra/terraform/*/versions.tf layer (hashicorp/aws ~> 5.70).
# No per-rule overrides — the rulesets' default severities are used, and CI
# gates on `error` only so a style warning never blocks a deploy.
#
# One-time setup per clone (plugins are fetched from GitHub, not vendored):
#   tflint --chdir=infra/terraform --init
#
# NOTE on `call_module_type`: this replaced the old `module = true` boolean in
# tflint v0.54.0, and the boolean is REJECTED as an unsupported argument by the
# v0.64.0 binary that CI installs. `local` (the default, stated explicitly) is
# what we want: every layer AND every module under modules/ is linted directly
# by the recursive walk, so pulling remote modules in would add nothing.
# =============================================================================

tflint {
  # Floor, not a pin: `call_module_type` does not exist before v0.54.0, so an
  # older local binary would fail confusingly on this file rather than clearly.
  required_version = ">= 0.54.0"
}

config {
  call_module_type    = "local"
  disabled_by_default = false
}

# `format` and `force` are intentionally absent: tflint ignores both in
# recursive mode (they must come from CLI flags there), so setting them here
# would be misleading dead config.

plugin "aws" {
  enabled = true
  version = "0.48.0"
  source  = "github.com/terraform-linters/tflint-ruleset-aws"
}

plugin "terraform" {
  # Bundled with the tflint binary — no version/source needed.
  enabled = true
  preset  = "recommended"
}
