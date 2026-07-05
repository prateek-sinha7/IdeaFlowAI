# Module: `resourcegroups`

Creates AWS Resource Groups so the console (and Resource Groups Tag Editor,
cost views, automation) can slice this environment's resources. It builds a
top-level "all resources for this environment" group plus one group per
component, all driven by the standard tags the providers apply
(`Project=velocityai`, `Environment`, `Component`).

## Resources created

- `aws_resourcegroups_group.all` — every resource tagged `Project=velocityai` +
  `Environment=<env>`.
- `aws_resourcegroups_group.per_component` (one per `components` entry) — adds a
  `Component=<name>` tag filter (network, compute, storage, monitoring, iam,
  secrets, ecr).

## Usage

```hcl
module "resourcegroups" {
  source = "../../modules/resourcegroups"

  name_prefix = local.name_prefix # e.g. velocityai-prod
  environment = var.environment   # e.g. prod
}
```

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|----------|
| `name_prefix` | Resource name prefix, e.g. `velocityai-prod`. | `string` | — | yes |
| `environment` | Environment short name (matches the `Environment` tag value). | `string` | — | yes |
| `components` | Map of component name → human description. Each becomes a group filtering on `Component=<name>`. | `map(string)` | network/compute/storage/monitoring/iam/secrets/ecr | no |
| `description_separator` | Glyph between the component name and its description in the group description. | `string` | `" - "` | no |

## Outputs

| Name | Description |
|------|-------------|
| `all_group_arn` / `all_group_name` | The top-level all-resources group. |
| `per_component_group_arns` | Map of component name → Resource Group ARN. |
| `per_component_group_names` | Map of component name → Resource Group name. |

## Notes

- AWS Resource Groups validates the `description` field against
  `[\sa-zA-Z0-9_.-]*` — no commas, parentheses, slashes, or em-dashes. Both
  `components` values and `description_separator` are validated against that
  regex so you get a fail-at-plan error instead of a fail-at-apply error.
- Groups are only as accurate as the `Component` tags on resources; the modules
  set `Component` per resource, and the providers set `Project`/`Environment`
  via `default_tags`.
