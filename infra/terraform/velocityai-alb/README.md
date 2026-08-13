# velocityai-alb

Standalone Terraform layer adding an **internal ALB** in front of the
**existing** VelocityAI EC2 instance for **one environment per apply**
(dev, stage, or prod). The instance/VPC/subnets were provisioned outside
this Terraform tree — this layer looks them up by ID and never manages them
directly. See `../modules/alb_internal/README.md` for the full security
model (scoped security groups, encrypted log bucket, alarms, TLS handling).

- **State key:** `velocityai/<environment>/alb.tfstate` — one state object
  per environment, so applying dev can never affect stage/prod resources or
  state.
- **Per-env config:** `dev.tfvars` / `stage.tfvars` / `prod.tfvars`
  (non-secret: VPC/subnet/instance IDs, trusted CIDR, environment name).
  `environment` is set in the tfvars file, same convention as
  `foundation`/`app`.
- **Naming:** prod is bare (`velocityai-*`), dev/stage get a suffix
  (`velocityai-dev-*`, `velocityai-stage-*`) — identical rule to
  `foundation/locals.tf` and `app/locals.tf`.
- **Secrets:** none created or read by this layer. `certificate_arn` must
  point at a certificate provisioned out-of-band (private/corporate CA, or
  imported via `.local/velocityai-alb/{bash,powershell}/04-import-certificate.*`).
  Never generate private key material with Terraform.

## Apply (per environment)

```bash
ENV=dev   # or stage, or prod
ACCOUNT_ID=265331052706
AWS_REGION=eu-central-1

terraform init \
  -backend-config="bucket=$TF_STATE_BUCKET" \
  -backend-config="key=velocityai/${ENV}/alb.tfstate" \
  -backend-config="region=$AWS_REGION" \
  -backend-config="dynamodb_table=$TF_STATE_LOCK_TABLE" \
  -backend-config="encrypt=true"

terraform plan \
  -var-file="${ENV}.tfvars" \
  -var="expected_account_id=$ACCOUNT_ID" \
  -var="certificate_arn=$CERT_ARN" \
  -var="alarm_email=$ALERT_EMAIL"
```

Each environment is a fully independent apply — nothing here is shared
across environments except the module source and the VPC (all three
environments' EC2 instances currently live in the same VPC,
`vpc-0535cb2c8b9dadcb4`, per live AWS inspection).

## Two-step certificate rollout (per environment)

AWS's auto-assigned ALB hostname (`internal-<name>-<id>.<region>.elb.amazonaws.com`)
is only known **after** the first apply, and ACM cannot issue a public
certificate for it. For each environment:

1. Apply once with any placeholder `certificate_arn` (or a throwaway
   self-signed cert imported via the CLI scripts) to get the ALB DNS name
   from the `alb_dns_name` output.
2. Get/import the real certificate for that exact hostname.
3. Apply again with `-var="certificate_arn=<real-arn>"`.

This applies **independently per environment** — dev, stage, and prod each
get their own generated hostname and therefore their own certificate.

## Prod

Production applies should go through the approved CI/CD pipeline with
manual approval, not a local workstation — see the workspace's Terraform
security guardrails and `../foundation/README.md`. `prod.tfvars` carries a
comment reminder of this.

## Inputs / Outputs

See `variables.tf` and `outputs.tf`. Notable variables:

- `environment` (`dev` | `stage` | `prod`) — required, drives naming/state.
- `vpc_id`, `subnet_ids`, `instance_id` — existing infra for this
  environment, looked up by ID.
- `trusted_ingress_cidrs` — approved corporate VPN/TGW CIDR(s) for this
  environment's ALB. Must never contain `0.0.0.0/0`.
- `certificate_arn` — ACM cert ARN for this environment's ALB hostname.
- `log_bucket_name` — optional; auto-derives to
  `<name_prefix>-alb-logs-<account_id>-euc1` when left empty.

Outputs: `environment`, `alb_url`, `alb_dns_name`, `alb_security_group_id`,
`target_security_group_id`, `log_bucket_name`.
