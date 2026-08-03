variable "expected_account_id" {
  description = "AWS account ID this bootstrap must run against. Leave blank to auto-adopt the account the AWS CLI / Terraform provider is currently authenticated to (the live `aws sts get-caller-identity` account). Set to a concrete 12-digit id to make the guard abort plan/apply on any mismatch — recommended for shared / multi-account org setups."
  type        = string
  default     = ""

  validation {
    condition     = var.expected_account_id == "" || can(regex("^[0-9]{12}$", var.expected_account_id))
    error_message = "expected_account_id must be empty (auto-detect) or a 12-digit AWS account ID."
  }
}

variable "aws_region" {
  description = "AWS region for the state bucket and lock table."
  type        = string
  default     = "eu-central-1"

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9]$", var.aws_region))
    error_message = "aws_region must look like e.g. eu-central-1."
  }
}

variable "owner" {
  description = "Tag value for Owner. Drives AWS Cost Explorer / Billing reports filtered by tag — finance can answer 'how much is team X costing us?' when this is set. Default 'velocityai' is fine for single-team / single-project accounts; override for multi-team / multi-project accounts where per-team cost allocation matters."
  type        = string
  default     = "velocityai"
}

variable "cost_center" {
  description = "Tag value for CostCenter (finance code). Same Cost-Explorer reasoning as `owner`; default 'velocityai' is the catch-all. Set to your org's real finance code (e.g. 'UKI-AI-001') when you want this stack's spend to roll up into a specific budget."
  type        = string
  default     = "velocityai"
}

variable "state_bucket_name" {
  description = "Globally-unique S3 bucket name for the Terraform state. Suggested: velocityai-tfstate-<region> (e.g. velocityai-tfstate-eu-central-1). NOTE: S3 bucket names are globally unique across ALL AWS accounts, so pick a name unlikely to collide; the region suffix helps but is not a guarantee."
  type        = string

  validation {
    condition     = length(var.state_bucket_name) >= 3 && length(var.state_bucket_name) <= 63
    error_message = "S3 bucket names must be 3-63 chars."
  }
}

variable "lock_table_name" {
  description = "DynamoDB table name for Terraform state locking."
  type        = string
  default     = "velocityai-tfstate-locks"
}

# --- CI/CD identity ----------------------------------------------------------
# The retired GitLab connection + per-env CodeBuild runner variables
# (create_gitlab_runner, gitlab_repo_url, runners) lived here. CI/CD is now
# GitHub Actions only (see github_oidc.tf); deploy_permissions_boundary_arn is
# kept because github_oidc.tf's shared deploy role still uses it.

variable "deploy_permissions_boundary_arn" {
  description = "Optional IAM permissions-boundary ARN attached to EVERY GitHub Actions role github_oidc.tf creates (the build role and each per-environment deploy role). RECOMMENDED in a shared account: scope it to velocityai-* so these roles cannot touch non-project resources. Empty = no boundary, which github_oidc.tf surfaces as a plan/apply warning via its `check` block."
  type        = string
  default     = ""

  validation {
    condition     = var.deploy_permissions_boundary_arn == "" || can(regex("^arn:aws[a-zA-Z-]*:iam::[0-9]{12}:policy/", var.deploy_permissions_boundary_arn))
    error_message = "deploy_permissions_boundary_arn must be empty or an IAM policy ARN (arn:aws:iam::<account>:policy/<name>)."
  }
}

# --- GitHub Actions OIDC (github_oidc.tf) ------------------------------------
# PRE-EXISTING GAP found while decommissioning CodeBuild: these 8 variables are
# referenced throughout github_oidc.tf (added alongside it, presumably in the
# same change that never got a matching variables.tf update) but were never
# declared anywhere in this module — `terraform validate` was already broken
# before this cleanup touched anything. bootstrap.tfvars sets
# create_github_oidc + github_org_repo, which only worked because Terraform
# silently treats an undeclared `-var-file` entry as a warning, not an error;
# `validate`/`plan` is where the missing declarations actually surface. Adding
# them here (matching every var.* usage in github_oidc.tf) is a correctness fix
# needed to get `terraform validate` green again, not a scope change to what
# CI/CD does.

variable "create_github_oidc" {
  description = "Create the GitHub Actions OIDC identity provider + the shared deploy role (github_oidc.tf). Default false keeps a state-backend-only bootstrap; set true once you're ready to wire GitHub Actions (docs/GITHUB_CICD_SETUP.md)."
  type        = bool
  default     = false
}

variable "github_oidc_create_provider" {
  description = "Create the token.actions.githubusercontent.com OIDC provider (true), or adopt an existing one already present in this account (false). There can be only one provider per account for a given URL, so set false if a sibling project already created it. Ignored when create_github_oidc = false."
  type        = bool
  default     = true
}

variable "github_oidc_thumbprints" {
  description = "TLS certificate thumbprint(s) for GitHub's OIDC token endpoint. Only used when github_oidc_create_provider = true. Verify at https://github.blog/changelog/ before relying on this default long-term — AWS validates the OIDC cert chain against trusted CAs itself, so this is largely a legacy required field."
  type        = list(string)
  default     = ["1c58a3a8518e8759bf075b76b750d4f2df264fcd"]
}

variable "github_org_repo" {
  description = "EXACT GitHub \"<owner>/<repository>\" whose workflows may assume the CI/CD roles, e.g. \"Hexaware-HnI/velocityai\". Combined with each entry in github_environments to form the OIDC subject \"repo:<github_org_repo>:environment:<env>\", matched with StringEquals. WILDCARDS ARE REJECTED: a glob like \"my-org*/my-repo*\" also admits any other GitHub owner/repository sharing that prefix — a repo-impersonation path into this account. Rename of the org/repo is a deliberate infrastructure change, not something the trust policy should absorb. Required when create_github_oidc = true."
  type        = string
  default     = ""

  validation {
    condition     = var.github_org_repo != "" || !var.create_github_oidc
    error_message = "github_org_repo must be set when create_github_oidc = true."
  }

  validation {
    condition     = var.github_org_repo == "" || can(regex("^[A-Za-z0-9][A-Za-z0-9-_.]*/[A-Za-z0-9][A-Za-z0-9-_.]*$", var.github_org_repo))
    error_message = "github_org_repo must be an exact \"<owner>/<repository>\" pair with no wildcards (e.g. \"Hexaware-HnI/velocityai\")."
  }
}

variable "github_environments" {
  description = "GitHub Environment names (must match the deploy-environment names, NOT branch names — see docs/GITHUB_CICD_SETUP.md's naming callout). One deploy role is created PER entry, each trusting only its own OIDC subject and scoped to only its own SSM prefix and EC2 `Environment` tag value."
  type        = list(string)
  default     = ["dev", "stage", "prod"]

  validation {
    condition     = alltrue([for e in var.github_environments : contains(["dev", "stage", "prod"], e)])
    error_message = "github_environments entries must be one of: dev, stage, prod."
  }

  validation {
    condition     = length(var.github_environments) == length(toset(var.github_environments))
    error_message = "github_environments must not contain duplicates (each entry names one IAM role)."
  }
}

variable "github_cicd_role_name" {
  description = "Base name for the IAM roles GitHub Actions assumes via OIDC. Creates \"<name>-build\" (ECR only, shared) plus one \"<name>-<env>\" deploy role per entry in github_environments (e.g. velocityai-gha-deploy-dev)."
  type        = string
  default     = "velocityai-gha-deploy"
}

variable "github_ecr_repository_names" {
  description = "ECR repository names (not ARNs) the BUILD role may push/pull, scoped exactly — no wildcard beyond what's listed here. The per-environment deploy roles get no ECR access at all: images are pulled on the box by the EC2 instance role."
  type        = list(string)
  default     = ["velocityai/backend", "velocityai/frontend"]
}

variable "github_cicd_kms_key_arns" {
  description = "KMS key ARNs the per-environment deploy roles may kms:Encrypt against when writing SSM SecureString parameters. Empty (default) scopes to every key in this account+region instead of a bare \"*\", because the per-env project CMKs (modules/kms) don't exist yet at bootstrap time. That breadth is closed by two conditions on the statement — kms:ViaService (SSM only) and kms:RequestAlias (this environment's own CMK alias only) — so a dev role still cannot encrypt under the prod key. Pass concrete ARNs once they exist to tighten the Resource as well."
  type        = list(string)
  default     = []
}
