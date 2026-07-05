# Module: `ecr`

Creates the container image repositories for VelocityAI (backend + frontend).
These repositories are **shared across environments**: an image is built once
and promoted dev → stage → prod by tag, so repo names are NOT
environment-suffixed and this module is instantiated **once, in the `shared`
layer** (`velocityai/shared.tfstate`).

## Resources created

- `aws_ecr_repository.this` (one per `repository_names` entry) — image scanning
  on push, `force_delete = false` (a `destroy` against a non-empty repo fails
  loudly rather than silently deleting pushed artifacts).
- `aws_ecr_lifecycle_policy.this` — per-environment "keep last N" rules for
  branch builds plus an untagged-image expiry rule.

There is intentionally **no `aws_ecr_repository_policy`**: pull/push access is
granted entirely IAM-side (the per-env EC2 instance roles and the CodeBuild
deploy roles), which avoids a cross-layer dependency cycle.

## Usage

```hcl
module "ecr" {
  source = "../../modules/ecr"

  repository_names = ["velocityai/backend", "velocityai/frontend"]
  # kms_key_arn omitted -> AES256 (the shared layer runs before per-env CMKs exist)
}
```

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|----------|
| `repository_names` | ECR repository names to create (namespaced, e.g. `velocityai/backend`). | `list(string)` | — | yes |
| `image_tag_mutability` | `MUTABLE` (default — allows build-retry re-push of the same tag) or `IMMUTABLE`. | `string` | `"MUTABLE"` | no |
| `kms_key_arn` | Optional KMS CMK for at-rest encryption. Empty = AES256 (correct for the shared layer, which runs before per-env CMKs exist). | `string` | `""` | no |
| `keep_last_images` | Most-recent branch-build images retained per repo per env tag prefix. | `number` | `10` | no |
| `env_tag_prefixes` | Per-env branch-build tag prefixes, each with its own keep-last-N rule. | `list(string)` | `["dev-","stage-","prod-"]` | no |
| `untagged_expire_days` | Days after push to expire untagged (orphaned) images. | `number` | `14` | no |
| `scan_on_push` | Enable image vulnerability scanning on push. | `bool` | `true` | no |

## Outputs

| Name | Description |
|------|-------------|
| `repository_urls` | Map of repo name → pull/push URL. |
| `repository_arns` | Map of repo name → repository ARN. |
| `registry_url` | Registry hostname (`<acct>.dkr.ecr.<region>.amazonaws.com`), shared by every repo in this account+region. |

## Notes

- Release-tagged images (no env prefix) are never expired by the lifecycle
  policy, so a previous release is always available to roll back to. Do not
  reuse `env_tag_prefixes` values as release-tag prefixes.
- Two `checkov:skip` annotations on the repository document the accepted
  `MUTABLE` + `AES256` defaults; flip `image_tag_mutability`/`kms_key_arn` to
  override.
