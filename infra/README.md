# Flowin — Terraform infrastructure

Terraform suite for the Flowin single-EC2 deployment described in
[`docs/SIMPLE_AWS_DEPLOYMENT.md`](../docs/SIMPLE_AWS_DEPLOYMENT.md). Branch
`infra`. The architecture is one EC2 instance running nginx + Postgres
natively, with backend (FastAPI/uvicorn) and frontend (Next.js standalone)
as Docker Compose containers pulled from ECR. The backend talks to AWS
Bedrock (Claude Haiku 4.5) for LLM calls.

> **Important — shared account.** This Terraform runs in an AWS Organizations
> account that other Hexaware projects also use. The single most important
> rule of this codebase is *touch only this project's resources, never
> account-wide settings*. The list of forbidden resource types is enforced by
> review (and by `grep` — see below); the account-ID and region guard catches
> the other half of the problem (running against the wrong account).

---

## Repository layout

```
infra/
├── README.md                  # this file
├── .gitignore                 # state, plans, secrets ignored; lock file committed
├── bootstrap/                 # one-time: state bucket + DynamoDB lock (local state)
├── envs/
│   ├── prod/                  # the production environment composition
│   └── localstack/            # hermetic LocalStack-Pro fixture (sibling of prod)
├── modules/
│   ├── account_guard/         # account-id + region precondition
│   ├── network/               # VPC, subnet, IGW, SGs, VPC endpoints, flow logs
│   ├── compute/               # EC2, EBS data volume, EIP
│   ├── iam/                   # instance role + policies (Bedrock, SSM, KMS, Logs, S3, ECR)
│   ├── kms/                   # customer-managed CMK + alias + key policy
│   ├── secrets/               # SSM Parameter Store entries
│   ├── dns/                   # data-lookup of existing Route 53 zone + A record (or nip.io)
│   ├── ecr/                   # private container registries (backend + frontend)
│   ├── backups/               # S3 bucket + AWS Backup vault + plan + selection
│   ├── monitoring/            # CloudWatch log groups + alarms + SNS topic
│   └── resourcegroups/        # AWS Resource Groups (top-level + per-component)
└── policies/                  # IAM policy JSON templates
```

---

## What it deploys

Per `docs/SIMPLE_AWS_DEPLOYMENT.md`:

- **Network**: a single VPC (`10.20.0.0/16`), one public subnet
  (`10.20.1.0/24`) in the configured AZ, an Internet Gateway, a default
  route, an explicit-egress security group on the EC2, a separate security
  group on the VPC endpoints, and **VPC interface endpoints** for `bedrock`,
  `bedrock-runtime`, `ssm`, `ssmmessages`, `ec2messages`, `logs`, plus a
  **gateway endpoint for S3**.
- **Compute**: one `m6i.2xlarge` Ubuntu 24.04 LTS instance, an encrypted
  100 GB gp3 root volume, an encrypted 50 GB gp3 data volume tagged
  `Backup=true`, and an Elastic IP. Docker engine + Compose plugin install
  on first boot via the Appendix-D bootstrap script.
- **IAM**: an instance profile whose role can:
  - Invoke the Claude Haiku 4.5 model and the EU cross-region inference
    profile (no other Bedrock model);
  - Read SSM parameters under `/flowin/${env}/*`;
  - Use the project KMS key for `Decrypt`/`GenerateDataKey`;
  - Write to log groups under `/flowin/${env}/*`;
  - Read/write under one S3 backup bucket;
  - Pull images from the two project ECR repos (`GetAuthorizationToken`
    is account-wide; pull verbs are scoped to the project repo ARNs).
- **ECR**: two private repositories, `flowin-${env}-backend` and
  `flowin-${env}-frontend`. KMS-encrypted, scan-on-push, `IMMUTABLE`
  tags (rollback is by re-deploying a previous tag, not by re-tagging
  `latest`). Lifecycle policy keeps the last 10 tagged images and expires
  untagged images after 14 days. Repository policies grant pull only to
  the EC2 instance role — pushes come from CI using its own credentials.
- **KMS**: one customer-managed symmetric CMK with rotation enabled,
  alias `alias/flowin-${env}`, used by EBS, the S3 backup bucket, the
  AWS Backup vault, the SNS topic, and SSM SecureStrings.
- **Secrets**: SSM Parameter Store entries under `/flowin/${env}/...`
  (LLM provider/region/model id, app secret key, db password, optional
  Anthropic fallback key, CORS origins, JWT expiry).
- **DNS**: two paths controlled by `var.use_nip_io` (see Variables below).
  Default `true` in `terraform.tfvars.example`: the FQDN is computed from
  the EIP via [nip.io](https://nip.io) (e.g. `1-2-3-4.nip.io` for EIP
  `1.2.3.4`) and **no AWS DNS resources are created**. Flip to `false` to
  use a customer-owned Route 53 hosted zone (which must already exist) and
  create an A record at `${app_subdomain}.${route53_zone_name}` → EIP.
- **Backups**: S3 bucket for `pg_dump` archives (versioned, KMS-encrypted,
  TLS-only, lifecycle rules) + AWS Backup vault + daily plan (35-day
  retention) + tag-based selection (`Backup=true`).
- **Monitoring**: seven log groups under `/flowin/${env}/`, an SNS topic
  with an email subscription, and 17 alarms (host CPU/memory/disk; backend
  /frontend container health proxy via journald-error rate; nginx 5xx;
  DB connection failures; Bedrock throttles + server errors + per-region
  invocation count; AWS Backup job failures; agent error rate; stuck
  workflows probe; billing in `us-east-1`). VPC flow logs ship to a
  dedicated CW log group with per-flow KMS encryption.
- **Resource Groups**: a top-level `flowin-${env}-all` group plus seven
  per-component groups (`network`, `compute`, `storage`, `monitoring`,
  `iam`, `secrets`, `ecr`), each filtering on its `Component` tag.

---

## What it does NOT deploy (forbidden in the shared account)

The following resource types are deliberately not used and will be caught
in review:

| Type | Why forbidden |
|---|---|
| `aws_organizations_*` | Account/org-wide; affects sibling tenants |
| `aws_iam_account_password_policy` | Account-wide |
| `aws_iam_account_alias` | Account-wide |
| `aws_s3_account_public_access_block` | Account-wide; we use bucket-scoped BPA |
| `aws_inspector*` (account-level) | Account-wide |
| `aws_guardduty_detector` | Org-managed; we consume only |
| `aws_config_*` | Account-wide |
| `aws_securityhub_*` | Account-wide |
| `aws_macie2_account` | Account-wide |
| `aws_*default*` (default VPC / SG / RT) | Account-wide; we always create our own |
| Bedrock `PutModelInvocationLoggingConfiguration` | Account-wide; the security team owns it |

You can audit:

```bash
grep -rE "aws_organizations_|aws_iam_account_|aws_s3_account_public_access_block|aws_config_|aws_securityhub_|aws_macie2_account|aws_guardduty_detector" infra/
```

That command should return zero matches.

---

## Account / region guard

The first thing every plan/apply does is evaluate the
`modules/account_guard` module, which uses
`data.aws_caller_identity` + `data.aws_region` and a `terraform_data` block
with **two `lifecycle.precondition`s** plus two `check` blocks:

- The provider's authenticated account ID **must** equal
  `var.expected_account_id`.
- The provider's region **must** equal `var.aws_region`.

A mismatch aborts plan/apply with a clear error before any resource is read
or created. The guard's outputs (account_id, region, partition) are wired
through as inputs to every downstream module, so a misconfigured root
config cannot accidentally bypass it — there's nothing to plumb if the
guard fails.

---

## Tagging convention

Every resource is tagged via the provider's `default_tags`:

| Tag | Source | Example |
|---|---|---|
| `Project` | hard-coded | `flowin` |
| `Environment` | `var.environment` | `prod` |
| `ManagedBy` | hard-coded | `terraform` |
| `Repo` | hard-coded | `gitlab.com/hexaware-uki/flowin` |
| `Owner` | `var.owner` | `flowin-platform-team@hexaware.com` |
| `CostCenter` | `var.cost_center` | `UKI-FLOWIN-PROD` |

Plus, **every resource** also gets a per-resource `Component` tag
(`network`, `compute`, `storage`, `monitoring`, `iam`, `secrets`, or `ecr`)
so the Resource Groups can split by component. Many resources also get a
`Name` tag for the AWS console.

The data EBS volume additionally carries `Backup = true`, which is the
selector AWS Backup uses to discover what to snapshot.

---

## Resource Groups — how to navigate the AWS console

The `resourcegroups` module creates these tag-query groups. Open AWS
Console → Resource Groups → Saved Groups:

- **`flowin-${env}-all`** — every resource in the environment, regardless
  of component.
- **`flowin-${env}-network`** — VPC, subnet, IGW, route table, security
  groups, VPC endpoints.
- **`flowin-${env}-compute`** — EC2 instance, root EBS, EIP.
- **`flowin-${env}-storage`** — data EBS volume, S3 backup bucket,
  AWS Backup vault.
- **`flowin-${env}-monitoring`** — CloudWatch log groups, alarms, SNS.
- **`flowin-${env}-iam`** — IAM role, KMS key.
- **`flowin-${env}-secrets`** — SSM Parameter Store entries.
- **`flowin-${env}-ecr`** — backend + frontend container repositories.

A "what does Flowin own?" question is answered by the `*-all` group; a
"what changed in compute today?" question is answered by `*-compute`.

---

## Running it for the first time

### 0. Pre-requisites

- AWS credentials in `~/.aws/credentials` or via `AWS_PROFILE`/STS.
- An IAM principal with permission to create the resources listed above
  in **only this account**.
- A DNS strategy: either accept the default `use_nip_io = true` (which
  needs no upstream DNS provisioning at all — the FQDN is derived from
  the EIP via [nip.io](https://nip.io)) or set `use_nip_io = false` and
  bring an existing Route 53 hosted zone you own (the DNS module never
  creates one — `data "aws_route53_zone"` looks it up).
- Terraform `>= 1.7.0`. AWS provider `~> 5.70`. Both are pinned in
  `versions.tf`.

### 1. Bootstrap (one-time)

The bootstrap creates the S3 bucket and DynamoDB table the prod backend
will use for state and locking. It uses **local state** itself.

```bash
cd infra/bootstrap

cat > terraform.tfvars <<'EOF'
expected_account_id = "123456789012"
aws_region          = "eu-central-1"
owner               = "flowin-platform-team@hexaware.com"
cost_center         = "UKI-FLOWIN-PROD"
state_bucket_name   = "flowin-tfstate-123456789012-eu-central-1"
lock_table_name     = "flowin-tfstate-locks"
EOF

terraform init
terraform plan
terraform apply
```

Note the `state_bucket_name` output — you'll pass it to
`terraform init -backend-config="bucket=..."` below. The other backend
keys (`key`, `region`, `encrypt`, `dynamodb_table`) are committed in
`envs/prod/backend.tf` so every operator inits against the same state
location.

### 2. Variables for the prod environment

```bash
cd ../envs/prod

cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars and fill in everything.
# Secrets are easier to inject via env vars:
export TF_VAR_app_secret_key="$(openssl rand -hex 64)"
export TF_VAR_db_password="$(openssl rand -hex 32)"
```

Variables the operator MUST set in `terraform.tfvars`:

| Variable | Notes |
|---|---|
| `expected_account_id` | Forces the guard to the right account |
| `aws_region` | Default `eu-central-1`; override only if needed |
| `availability_zone` | The single AZ you chose |
| `environment` | Default `prod` |
| `owner` | Tag value |
| `cost_center` | Tag value |
| `use_nip_io` | DNS strategy. `true` (default in tfvars.example) derives FQDN from the EIP via nip.io — no Route 53 needed. `false` uses Route 53 + the two vars below |
| `route53_zone_name` | Existing hosted zone name. Required when `use_nip_io = false`; ignored when `true` |
| `app_subdomain` | Subdomain — usually `flowin`. Ignored when `use_nip_io = true` |
| `cors_origins` | JSON list of allowed origins |
| `alert_email` | SNS subscription email |
| `ssh_allowed_cidrs` | List of CIDRs (or empty for SSM-only) |
| `app_secret_key` | Either via tfvars or `TF_VAR_app_secret_key` |
| `db_password` | Either via tfvars or `TF_VAR_db_password` |
| `backup_bucket_name` | Globally-unique S3 bucket name |

Optional but commonly tuned:

| Variable | Default | Purpose |
|---|---|---|
| `instance_type` | `m6i.2xlarge` | Vertical scaling |
| `root_volume_size_gb` | `100` | Headroom for logs/code/releases |
| `data_volume_size_gb` | `50` | Postgres data |
| `bedrock_model_id` | `anthropic.claude-haiku-4-5-20251001-v1:0` | If model id changes |
| `bedrock_inference_profile_id` | `eu.anthropic.claude-haiku-4-5-20251001-v1:0` | EU profile |
| `use_inference_profile_for_app` | `true` | App invokes profile, IAM allows both |
| `daily_backup_retention_days` | `35` | AWS Backup retention |
| `log_retention_days` | `30` | CloudWatch logs retention |
| `billing_alarm_threshold_usd` | `500` | Account-wide billing alarm |
| `anthropic_api_key` | `""` | Optional emergency fallback |

### 3. Initialise the prod backend

`envs/prod/backend.tf` commits the non-secret backend keys (`key`,
`region`, `encrypt`, `dynamodb_table`) so every operator inits against
the same state location. The only operator-supplied value is the bucket
name (which embeds the account ID and so isn't worth committing in a
shared-account repo):

```bash
terraform init \
  -backend-config="bucket=flowin-tfstate-123456789012-eu-central-1"
```

The state location is therefore unambiguous: regardless of which
operator runs `init`, the state lives at
`s3://<bucket>/envs/prod/terraform.tfstate`, locked via
`flowin-tfstate-locks`. Two engineers cannot silently fork state by
typing different `key=...` values.

If the bucket name is sensitive in your org, commit a `backend.hcl` to
a private channel and use `terraform init -backend-config=backend.hcl`
instead — but never the other way round (don't push the operator-only
flags back into a flat list of CLI args; the point of committing the
non-secret keys is to remove them from the operator's working memory).

### 4. Plan and apply

```bash
terraform plan -out plan.out
terraform apply plan.out
```

The plan output is the source of truth — read it. Pay particular
attention to:

- The `account_guard` module evaluates first; if your provider is wired
  to the wrong account, the plan aborts here.
- Any `aws_*` resource type **not** in the allowed list above is a
  review-failing change — investigate before approving.

### 5. Day 2: post-apply manual steps

These are deliberately out of Terraform scope (driven by the architecture
doc, Appendix D):

- Run the on-host bootstrap (Postgres init, nginx config, certbot, systemd
  units, app deploy) via SSM RunCommand against the new instance.
- Confirm the email subscription on the SNS alerts topic (AWS sends a
  confirmation email to `var.alert_email`).
- Submit a Bedrock service-quota increase request for Claude Haiku 4.5
  before any load testing.

---

## Updating

Day-to-day changes go through `terraform plan` + `terraform apply` from
`envs/prod`. Some resources are protected with `prevent_destroy = true`:

- The KMS CMK
- The S3 backup bucket
- The AWS Backup vault
- The data EBS volume

If you actually need to destroy one of these, you must first remove the
`prevent_destroy` and apply, then destroy. Do that **only** during a
declared maintenance window, with a confirmed off-site copy of any data
held by the resource.

---

## Operator quick reference

| Want to... | Where |
|---|---|
| See every Flowin resource | Console → Resource Groups → `flowin-${env}-all` |
| Read the IAM role's policies | Console → IAM → Roles → `flowin-${env}-instance` |
| Tail the uvicorn log | Console → CloudWatch → Log groups → `/flowin/${env}/uvicorn` |
| Trigger a manual snapshot | Console → AWS Backup → Vaults → `flowin-${env}-vault` |
| Rotate the SECRET_KEY | `aws ssm put-parameter --name /flowin/${env}/app/secret_key --type SecureString --value "$(openssl rand -hex 64)" --overwrite` then restart the backend service |
| SSH onto the box | `aws ssm start-session --target $INSTANCE_ID` (no SSH keypair required) |

---

## Troubleshooting

- **"AccessDenied" creating an SSM SecureString**: confirm the IAM identity
  running Terraform has `kms:Encrypt` on the project key. The KMS key
  policy grants the root account; if the account uses an SCP that strips
  `kms:*`, that breaks here.
- **"InvalidParameterValue: KmsKeyId"**: AWS Backup sometimes refuses an
  alias here; the module passes the key ARN, not the alias, to avoid this.
- **VPC endpoint creation hangs**: the endpoint security group must allow
  443 inbound from the app SG. Check `modules/network/main.tf` —
  `aws_vpc_security_group_ingress_rule.endpoints_from_app`.
- **CloudWatch alarm in `INSUFFICIENT_DATA`**: the agent on the instance
  hasn't started shipping metrics. Confirm
  `amazon-cloudwatch-agent.service` is active on the box (the on-host
  bootstrap step covers this — see Appendix D).
- **`Error: aws_caller_identity` mismatch**: the account guard caught a
  misconfigured `AWS_PROFILE`. Switch profiles or fix
  `var.expected_account_id`.

---

## Future environments (e.g. staging)

Each new environment lives in `infra/envs/<name>/` as a sibling of `prod/`,
with its own `backend.tf` (different state key), its own
`terraform.tfvars`, and the same `main.tf` composing the modules. Modules
are shared. The `name_prefix` (`flowin-${var.environment}`) keeps every
resource name distinct.

This Terraform deliberately does **not** use Terraform workspaces — each
environment has its own state file in its own folder. That keeps blast
radius small if someone fat-fingers a workspace switch.
