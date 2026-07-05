# Module: `account_guard`

Refuses to plan or apply when the AWS provider is authenticated to the wrong
account or running in the wrong region. This is the single most important
safety net in the suite: VelocityAI shares an AWS Organizations account with
other Hexaware projects, so a mis-targeted apply could damage unrelated
workloads.

Instantiate this module **first** in every layer (`bootstrap`, `shared`,
`foundation`, `app`) and wire downstream resources to depend on its
`account_id` output so the precondition runs before anything is created.

## How it works

- A `terraform_data.guard` resource with `lifecycle.precondition` blocks aborts
  `plan`/`apply` on an account or region mismatch (hard error).
- `check "account_match"` / `check "region_match"` blocks run on every plan and
  surface a warning even when the precondition is bypassed by planning order
  (`check` blocks are evaluated last).

This module creates **no AWS resources** — only data sources and the guard.

## Usage

```hcl
module "account_guard" {
  source = "../../modules/account_guard"

  expected_account_id = var.expected_account_id # 12-digit account id
  expected_region     = var.aws_region          # e.g. eu-central-1
}

# Force downstream resources to wait for the guard.
resource "aws_kms_key" "example" {
  # ...
  depends_on = [module.account_guard]
}
```

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|----------|
| `expected_account_id` | 12-digit AWS account ID Terraform must be authenticated to. Mismatch aborts plan/apply. | `string` | — | yes |
| `expected_region` | AWS region Terraform must be running in. Mismatch aborts plan/apply. | `string` | — | yes |

## Outputs

| Name | Description |
|------|-------------|
| `account_id` | Account ID confirmed by the guard. Depend on this to order resources after the check. |
| `region` | Region confirmed by the guard. |
| `partition` | AWS partition (`aws`, `aws-us-gov`, `aws-cn`) for ARN construction. |

## Notes

- The guard cannot stop a destructive apply that does not reference its output —
  always thread `module.account_guard.account_id`/`partition` into ARNs and add
  `depends_on = [module.account_guard]` where there is no natural dependency.
