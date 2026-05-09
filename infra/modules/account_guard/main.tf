data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_partition" "current" {}

# Guard: refuse to apply if the provider is authenticated to a different
# account or running in a different region. This is the single most important
# safety net in the suite — the suite shares an AWS Organizations account with
# other tenants, so a mis-targeted apply could damage unrelated workloads.
resource "terraform_data" "guard" {
  input = {
    actual_account_id   = data.aws_caller_identity.current.account_id
    expected_account_id = var.expected_account_id
    actual_region       = data.aws_region.current.name
    expected_region     = var.expected_region
  }

  lifecycle {
    precondition {
      condition     = data.aws_caller_identity.current.account_id == var.expected_account_id
      error_message = "Account mismatch: provider authenticated to ${data.aws_caller_identity.current.account_id}, expected ${var.expected_account_id}. Refusing to apply Flowin Terraform."
    }

    precondition {
      condition     = data.aws_region.current.name == var.expected_region
      error_message = "Region mismatch: provider region is ${data.aws_region.current.name}, expected ${var.expected_region}. Refusing to apply Flowin Terraform."
    }
  }
}

# Belt-and-braces: a `check` block runs on every plan and surfaces a warning
# (rather than an error) on mismatch. Useful when the precondition is bypassed
# by the planning order — `check` is evaluated last.
check "account_match" {
  assert {
    condition     = data.aws_caller_identity.current.account_id == var.expected_account_id
    error_message = "Account drift: still authenticated to ${data.aws_caller_identity.current.account_id}, expected ${var.expected_account_id}."
  }
}

check "region_match" {
  assert {
    condition     = data.aws_region.current.name == var.expected_region
    error_message = "Region drift: provider region is ${data.aws_region.current.name}, expected ${var.expected_region}."
  }
}
