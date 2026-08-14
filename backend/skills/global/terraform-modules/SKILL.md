---
name: terraform-modules
display_name: Terraform Module Library
description: Build reusable Terraform modules for AWS, Azure, GCP, and OCI infrastructure following IaC best practices.
category: workflow
isBeta: false
tags:
- terraform
- infrastructure-as-code
- aws
- azure
- gcp
- modules
- cloud-provisioning
- iac
---

# Terraform Module Library

Production-ready Terraform module patterns for AWS, Azure, GCP, and OCI infrastructure.

## When to Use

- Build reusable infrastructure components
- Standardize cloud resource provisioning
- Implement infrastructure as code best practices
- Create multi-cloud compatible modules
- Establish organizational Terraform standards

## Module Structure

```
module-name/
├── main.tf          # Main resources
├── variables.tf     # Input variables
├── outputs.tf       # Output values
├── versions.tf      # Provider versions
├── README.md        # Documentation
├── examples/        # Usage examples
│   └── complete/
│       ├── main.tf
│       └── variables.tf
└── tests/           # Terratest files
    └── module_test.go
```

## Standard Variables Pattern

```hcl
variable "name" {
  description = "Name prefix for all resources"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  validation {
    condition     = contains(["dev", "test", "stage", "prod"], var.environment)
    error_message = "Environment must be one of: dev, test, stage, prod."
  }
}

variable "tags" {
  description = "Additional tags to merge with mandatory tags"
  type        = map(string)
  default     = {}
}
```

## Tagging Pattern

```hcl
locals {
  mandatory_tags = {
    environment = var.environment
    managed_by  = "terraform"
    module      = "vpc"
  }
  tags = merge(local.mandatory_tags, var.tags)
}
```

## Version Pinning

```hcl
terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
```

## Best Practices

1. **Pin versions**: Lock provider and module versions
2. **Validate inputs**: Use validation blocks on variables
3. **Output useful values**: IDs, ARNs, endpoints consumers need
4. **Document examples**: Include complete working examples
5. **Test modules**: Use Terratest or native terraform test
6. **Secure defaults**: Encryption on, public access off, logging enabled
7. **No hardcoded values**: Pass environment-specific values as variables
