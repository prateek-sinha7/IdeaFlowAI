---
inclusion: always
---

# Terraform Security Guardrails

Mandatory rules for writing, reviewing, and deploying Terraform in this
workspace. Goal: prevent leakage of secrets and sensitive data, and block
insecure cloud configurations. When a request conflicts with a rule here, flag
the conflict and propose a secure alternative instead of silently violating it.

## 1. Secrets and sensitive data

- Never hardcode secrets in `.tf` code, comments, or examples: passwords, API
  keys, access/secret keys, tokens, client secrets, private keys, certificates,
  database connection strings, or URLs containing credentials.
- Mark every sensitive variable and output with `sensitive = true`. This redacts
  CLI/UI output but does NOT keep values out of state, so state must still be
  protected.
- For production secrets, source from a secret manager (Azure Key Vault, AWS
  Secrets Manager, HashiCorp Vault, Google Secret Manager) via data sources, not
  Terraform variables. Avoid creating long-lived secrets in Terraform; prefer
  managed identity, workload identity federation, OIDC, or short-lived
  credentials.
- Never commit secret-bearing `.tfvars`/`.tfvars.json`, state files, or key
  material. Keep them in `.gitignore`. Commit `.terraform.lock.hcl` for
  reproducible provider versions.

```hcl
# Bad
resource "aws_db_instance" "main" {
  username = "admin"
  password = "Admin@123456"
}

# Good
variable "db_password" {
  type      = string
  sensitive = true
}

resource "aws_db_instance" "main" {
  username = var.db_username
  password = var.db_password
}
```

Sensitive files to keep out of source control:

```gitignore
*.tfvars
*.tfvars.json
.env
*.pem
*.key
*.pfx
*.p12
terraform.tfstate
terraform.tfstate.*
.terraform/
crash.log
override.tf
override.tf.json
*_override.tf
*_override.tf.json
```

Reference secrets from a vault rather than declaring them in code:

```hcl
data "azurerm_key_vault_secret" "db_password" {
  name         = "db-password"
  key_vault_id = data.azurerm_key_vault.main.id
}
```

Reference: [HashiCorp — manage sensitive data](https://developer.hashicorp.com/terraform/language/manage-sensitive-data).

## 2. State management

- Never use local state for shared environments (dev, test, staging, prod). Use
  a secure remote backend: Azure Storage, AWS S3 with locking, GCS, or HCP
  Terraform. Local state is plaintext and may contain secrets.
- Enable encryption at rest and TLS in transit on remote state storage.
- Restrict state access to approved users and CI/CD identities only: no public
  access, RBAC/IAM least privilege, separate state and backend key per
  environment/workload, versioning + soft delete + logging enabled,
  network-restricted where possible.

```hcl
terraform {
  backend "azurerm" {
    resource_group_name  = "rg-tfstate-prod"
    storage_account_name = "sttfstateprod001"
    container_name       = "tfstate"
    key                  = "prod/network/terraform.tfstate"
  }
}
```

## 3. Modules

- Build common infrastructure as reusable modules. Standard layout per module:
  `main.tf`, `variables.tf`, `outputs.tf`, `versions.tf`, `README.md`, and an
  `examples/` folder.
- Do not hardcode environment-specific values in modules (subscription/tenant/
  account IDs, resource group names, region, environment name, IPs, owner, cost
  center, application name, passwords). Pass them as variables.
- Give every variable a `type` and `description`; add `validation` where it
  constrains valid input. Set a default only when it is safe.
- Enforce secure defaults: public access disabled, HTTPS-only, encryption on,
  diagnostics on, network access restricted, minimum TLS version set, soft
  delete on where supported, local auth disabled where supported, managed
  identity preferred over secrets, public IP off unless explicitly required.

```hcl
variable "environment" {
  description = "Deployment environment."
  type        = string

  validation {
    condition     = contains(["dev", "test", "stage", "prod"], var.environment)
    error_message = "Environment must be one of: dev, test, stage, prod."
  }
}
```

## 4. Providers and versions

- Pin `required_version` and provider versions in every module and environment.
- Never put provider credentials in `.tf` files. Use managed identity, workload
  identity federation, OIDC, or CI/CD secret variables.

```hcl
terraform {
  required_version = ">= 1.6.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

# Good — no inline credentials
provider "azurerm" {
  features {}
}
```

## 5. Access control and environment isolation

- Apply least privilege to the Terraform identity. Avoid `Owner`; prefer a
  custom role. Use a separate identity per environment/subscription, no shared
  credentials, and avoid long-lived secrets where OIDC/workload identity exists.
  Review access periodically.
- Keep environments fully separate: distinct configuration, state file, backend
  key, variables, service connection, approval flow, and access control.
  Production deployments must require approval.

## 6. Resource security

- Do not create public resources unless explicitly approved (public IP, public
  storage account/bucket, public DB endpoint, public Kubernetes API server,
  public load balancer, open firewall rule).
- Do not use open network rules (`source_address_prefix = "*"` or `0.0.0.0/0`)
  unless formally approved. Use restricted CIDR ranges.
- Enable logging/diagnostics on production resources (Azure Monitor diagnostics,
  CloudTrail/CloudWatch, Cloud Logging, storage/Key Vault/database/Kubernetes
  audit logs).
- Enable encryption for storage, databases, disks, backups, queues, secrets, and
  state. Use customer-managed keys where compliance requires.

## 7. Naming and tagging

- Tag every supported resource with standard tags via a merged locals map.

```hcl
locals {
  mandatory_tags = {
    environment = var.environment
    managed_by  = "terraform"
    owner       = var.owner
    cost_center = var.cost_center
    application = var.application
  }
  tags = merge(local.mandatory_tags, var.tags)
}
```

## 8. CI/CD and scanning

- Apply shared-environment Terraform through a pipeline, not manually from local
  machines. Pipeline order: `fmt` → `validate` → `init` → `plan` → security scan
  → manual approval → `apply`.
- Always run `terraform fmt -check -recursive` and `terraform validate`.
- Run IaC security scanning before merge ([Checkov](https://www.checkov.io/),
  [Trivy config / tfsec](https://github.com/aquasecurity/tfsec), TFLint;
  OPA/Conftest for policy-as-code).
- Scan every PR for secrets (GitHub secret scanning, Gitleaks, TruffleHog,
  Checkov).

```bash
terraform fmt -check -recursive
terraform validate
checkov -d .
trivy config .
tflint --recursive
gitleaks detect --source .
```

## 9. PR review checklist

- [ ] No hardcoded secrets, keys, or credentials
- [ ] No `.tfstate` or secret-bearing `.tfvars` committed
- [ ] Sensitive variables/outputs marked `sensitive = true`
- [ ] Production secrets sourced from an approved secret manager
- [ ] Remote backend configured, encrypted, access-restricted
- [ ] Provider credentials not hardcoded; versions pinned
- [ ] Reusable modules used; variables have `type` and `description`
- [ ] Secure defaults enabled; no public access or `0.0.0.0/0` unless approved
- [ ] Logging/diagnostics and encryption enabled
- [ ] Standard tags applied
- [ ] `fmt`, `validate`, and security scans passed; plan reviewed
- [ ] Production apply approved

## Policy statement

> Terraform code must not contain hardcoded secrets, sensitive values,
> credentials, or environment-specific values inside reusable modules. Secrets
> must come from approved secret managers or secure CI/CD variables. State must
> live in an encrypted remote backend with restricted access. All infrastructure
> code must use reusable modules, secure defaults, version pinning, input
> validation, mandatory tagging, and security scanning before merge or
> deployment.