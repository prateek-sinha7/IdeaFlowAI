# AWS Setup Guide — GitHub Actions OIDC CI/CD for VelocityAI

Step-by-step instructions for the **AWS side** of the GitHub Actions CI/CD
pipeline. Follow these in order. Every real value (account ID, instance ID,
domain) is shown as a `<PLACEHOLDER>` — fill in your own.

> This is the "do these steps in AWS" guide. For the GitHub-side configuration
> and the day-to-day operator runbook, see
> [`GITHUB_CICD_SETUP.md`](./GITHUB_CICD_SETUP.md).

---

## 0. Values you need to gather first

Collect these before you start. You'll paste them into the commands below.

| Placeholder | What it is | How to find it |
|---|---|---|
| `<AWS_ACCOUNT_ID>` | 12-digit AWS account number | `aws sts get-caller-identity --query Account --output text` |
| `<REGION>` | AWS region | e.g. `eu-central-1` |
| `<GITHUB_ORG>/<REPO>` | GitHub org + repo slug | From the repo URL, e.g. `my-org/flowin` |
| `<ENV>` | Environment short name | One of `dev`, `stage`, `prod` |
| `<INSTANCE_ID>` | The EC2 instance for that env | `aws ec2 describe-instances --filters "Name=tag:Name,Values=velocityai-<ENV>-app" --query "Reservations[].Instances[].InstanceId" --output text` |
| `<KMS_KEY_ID>` | KMS key ID/ARN for SecureString params | `aws kms list-aliases` (or create one, step 5) |
| `<PUBLIC_FQDN>` | Public hostname for the env | e.g. your domain or nip.io host |
| `<ROLE_NAME>` | Name for the deploy role | e.g. `github-cicd` |

You need **AWS IAM admin permissions** to run steps 1–3 (create OIDC provider,
IAM role, policy). Steps 4–6 need ECR/EC2/KMS/SSM write access. See
[§8 — Do you need admin access?](#8-do-you-need-admin-access) for the full
breakdown of who needs what.

---

## How GitHub OIDC connects to AWS (the flow)

GitHub OIDC lets your workflows assume an AWS role using a short-lived token
instead of storing long-lived AWS access keys in GitHub secrets:

```
GitHub Actions workflow
   │  (1) requests an OIDC token (JWT) for the run
   ▼
token.actions.githubusercontent.com   ── issues JWT with claims:
   │                                        aud = sts.amazonaws.com
   │                                        sub = repo:<ORG>/<REPO>:environment:<ENV>
   ▼
AWS STS : AssumeRoleWithWebIdentity
   │  (2) validates the JWT against the OIDC provider (Step 1)
   │  (3) checks the role's trust policy conditions (Step 2) — aud + sub
   ▼
Short-lived AWS credentials (default ~1 hour)
   │  exported as AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN
   ▼
Every subsequent `aws` CLI call in the job uses these creds
```

Two AWS objects make this work: the **OIDC identity provider** (Step 1, tells
AWS to trust GitHub's token issuer) and the **IAM role trust policy** (Step 2,
says *which* repo/environment may assume the role). No AWS keys ever live in
GitHub.

---

## Step 1 — Create the GitHub OIDC identity provider (once per account)

This lets GitHub Actions authenticate to AWS with short-lived tokens instead of
stored access keys.

### Option A — Console

1. Go to **IAM → Identity providers → Add provider**.
2. **Provider type:** OpenID Connect.
3. **Provider URL:** `https://token.actions.githubusercontent.com`
4. Click **Get thumbprint**.
5. **Audience:** `sts.amazonaws.com`
6. Click **Add provider**.

### Option B — CLI

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list "sts.amazonaws.com" \
  --thumbprint-list "1c58a3a8518e8759bf075b76b750d4f2df264fcd" \
  --region <REGION>
```

> **Getting the thumbprint yourself** (optional — the value above is GitHub's
> published fingerprint and is safe to use):
> ```bash
> echo | openssl s_client -servername token.actions.githubusercontent.com \
>   -showcerts 2>/dev/null | openssl x509 -fingerprint -noout
> ```
> Modern AWS validates the OIDC cert chain against trusted CAs, so the
> thumbprint is largely a legacy field — but the API still requires it.

**Values to use:**

| Field | Value |
|---|---|
| Provider URL | `https://token.actions.githubusercontent.com` |
| Audience (client ID) | `sts.amazonaws.com` |

**Verify:**

```bash
aws iam list-open-id-connect-providers
```

You should see an ARN ending in `token.actions.githubusercontent.com`.

---

## Step 2 — Create the IAM deploy role with the OIDC trust policy

Create a role that GitHub Actions can assume. The **trust policy** controls
*who* may assume it; the **permissions policy** (Step 3) controls *what* it can do.

### 2.1 Write the trust policy

Save this as `trust-policy.json`. It restricts assumption to your repo — and,
optionally, to specific GitHub Environments.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<AWS_ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:<GITHUB_ORG>/<REPO>:*"
        }
      }
    }
  ]
}
```

**Values to fill in:**

| Placeholder | Example | Notes |
|---|---|---|
| `<AWS_ACCOUNT_ID>` | `123456789012` | Your account number |
| `<GITHUB_ORG>/<REPO>` | `my-org/flowin` | Your GitHub slug |

> **`sub` scoping options:**
> - `repo:<GITHUB_ORG>/<REPO>:*` — any branch, tag, or environment in the repo (simplest).
> - `repo:<GITHUB_ORG>/<REPO>:environment:dev` — only the `dev` GitHub Environment (tighter).
> - `repo:<GITHUB_ORG>/<REPO>:ref:refs/heads/main` — only the `main` branch.

### 2.1a Single shared role for all three environments (what we use)

Instead of one role per environment, you can use a **single role** (e.g.
`github-cicd`) whose trust policy admits all three GitHub Environments. Use a
`StringLike` list on the `sub` claim:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<AWS_ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": [
            "repo:<GITHUB_ORG>/<REPO>:environment:dev",
            "repo:<GITHUB_ORG>/<REPO>:environment:stage",
            "repo:<GITHUB_ORG>/<REPO>:environment:prod"
          ]
        }
      }
    }
  ]
}
```

> **⚠️ The `environment:` segment MUST exactly match your GitHub Environment
> names.** We use `dev` / `stage` / `prod` (see the naming note in
> `GITHUB_CICD_SETUP.md`). If your trust policy lists `staging`/`production`
> but your GitHub Environments are named `stage`/`prod`, the assume-role call
> will **fail** for those two environments (the `dev` one will still work).
> Keep the trust-policy environment names and the GitHub Environment names in
> lock-step.

### 2.2 Create the role

```bash
aws iam create-role \
  --role-name <ROLE_NAME> \
  --assume-role-policy-document file://trust-policy.json \
  --description "GitHub Actions OIDC deploy role for VelocityAI"
```

Note the returned **Role ARN** — you'll set it as the `AWS_ROLE_ARN` GitHub
variable later.

---

## Step 3 — Attach the permissions policy

This grants exactly what the pipeline needs: push images to ECR, push config to
SSM, run the redeploy command, and read command status.

### 3.1 Write the policy

Save as `deploy-policy.json`.

> **Critical — the `ssm:SendCommand` permission MUST be split into two
> statements.** `SendCommand` authorizes against *both* the target instance
> *and* the `AWS-RunShellScript` document. The document has no `Environment`
> tag, so if you put the tag condition on a single `Resource: "*"` statement,
> the document check can never pass and **every deploy fails** with
> `AccessDeniedException ... no identity-based policy allows ssm:SendCommand`.
> Keep the two statements below separate.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ECRAuth",
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    },
    {
      "Sid": "ECRPushPull",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload"
      ],
      "Resource": [
        "arn:aws:ecr:<REGION>:<AWS_ACCOUNT_ID>:repository/velocityai/backend",
        "arn:aws:ecr:<REGION>:<AWS_ACCOUNT_ID>:repository/velocityai/frontend"
      ]
    },
    {
      "Sid": "SSMPutParameters",
      "Effect": "Allow",
      "Action": "ssm:PutParameter",
      "Resource": "arn:aws:ssm:<REGION>:<AWS_ACCOUNT_ID>:parameter/velocityai/*"
    },
    {
      "Sid": "SSMSendCommandDocument",
      "Effect": "Allow",
      "Action": "ssm:SendCommand",
      "Resource": "arn:aws:ssm:<REGION>::document/AWS-RunShellScript"
    },
    {
      "Sid": "SSMSendCommandInstance",
      "Effect": "Allow",
      "Action": "ssm:SendCommand",
      "Resource": "arn:aws:ec2:<REGION>:<AWS_ACCOUNT_ID>:instance/*",
      "Condition": {
        "StringEquals": {
          "ssm:resourceTag/Environment": ["dev", "stage", "prod"]
        }
      }
    },
    {
      "Sid": "SSMCommandStatus",
      "Effect": "Allow",
      "Action": [
        "ssm:GetCommandInvocation",
        "ssm:ListCommandInvocations"
      ],
      "Resource": "*"
    },
    {
      "Sid": "KMSForSecureString",
      "Effect": "Allow",
      "Action": [
        "kms:Encrypt",
        "kms:Decrypt",
        "kms:GenerateDataKey"
      ],
      "Resource": "arn:aws:kms:<REGION>:<AWS_ACCOUNT_ID>:key/<KMS_KEY_ID>"
    },
    {
      "Sid": "STSIdentity",
      "Effect": "Allow",
      "Action": "sts:GetCallerIdentity",
      "Resource": "*"
    }
  ]
}
```

### 3.2 Attach it

```bash
aws iam put-role-policy \
  --role-name <ROLE_NAME> \
  --policy-name <ROLE_NAME>Policy \
  --policy-document file://deploy-policy.json
```

> **Tightening vs. simplicity:** the policy above scopes ECR and
> `PutParameter` to specific ARNs. For a single shared role across all three
> environments, you may instead use `"Resource": "*"` for `ECRAuth`,
> `ECRPushPull`, and `SSMPutParameters` (simpler, still safe because the role
> is only assumable by your repo). The **two `SendCommand` statements must stay
> split** either way — that split is the non-negotiable part.

### 3.3 Verify (without running a workflow)

Use the policy simulator — both must return `allowed`:

```bash
# Document
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::<AWS_ACCOUNT_ID>:role/<ROLE_NAME> \
  --action-names ssm:SendCommand \
  --resource-arns "arn:aws:ssm:<REGION>::document/AWS-RunShellScript" \
  --query "EvaluationResults[].EvalDecision" --output text

# Instance (with the Environment tag context)
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::<AWS_ACCOUNT_ID>:role/<ROLE_NAME> \
  --action-names ssm:SendCommand \
  --resource-arns "arn:aws:ec2:<REGION>:<AWS_ACCOUNT_ID>:instance/<INSTANCE_ID>" \
  --context-entries "ContextKeyName=ssm:resourceTag/Environment,ContextKeyValues=<ENV>,ContextKeyType=string" \
  --query "EvaluationResults[].EvalDecision" --output text
```

---

## Step 4 — Create the ECR repositories (once per account)

```bash
aws ecr create-repository --repository-name velocityai/backend \
  --image-tag-mutability MUTABLE \
  --image-scanning-configuration scanOnPush=true --region <REGION>

aws ecr create-repository --repository-name velocityai/frontend \
  --image-tag-mutability MUTABLE \
  --image-scanning-configuration scanOnPush=true --region <REGION>
```

Your **`ECR_REGISTRY`** value (for GitHub) is:
`<AWS_ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com`

---

## Step 5 — Per-environment AWS setup (repeat for dev, stage, prod)

### 5.1 Tag the EC2 instance — REQUIRED

The `SSMSendCommandInstance` condition only allows targeting instances tagged
with the matching `Environment`. Without this tag the deploy fails.

```bash
aws ec2 create-tags --resources <INSTANCE_ID> \
  --tags Key=Environment,Value=<ENV> --region <REGION>

# Verify
aws ec2 describe-tags --filters "Name=resource-id,Values=<INSTANCE_ID>" \
  --region <REGION> --query "Tags[?Key=='Environment'].Value" --output text
```

### 5.2 KMS key (once; reused across envs)

Create or reuse a symmetric KMS key for SecureString params. Grant the deploy
role `Encrypt`/`GenerateDataKey` and the EC2 instance role `Decrypt`. Note its
key ID for `<KMS_KEY_ID>`.

### 5.3 Seed the SSM parameters

Seed the minimum so the box can boot before the first deploy. Replace `<ENV>`.

```bash
PREFIX="/velocityai/<ENV>"

# Secret — the app JWT signing key
aws ssm put-parameter --name "$PREFIX/SECRET_KEY" \
  --type SecureString --key-id <KMS_KEY_ID> \
  --value "$(openssl rand -hex 64)" --region <REGION>

# Bedrock LLM config
aws ssm put-parameter --name "$PREFIX/llm/region" \
  --type String --value "<REGION>" --region <REGION>
aws ssm put-parameter --name "$PREFIX/llm/model_id" \
  --type String --value "anthropic.claude-haiku-4-5-20251001-v1:0" --region <REGION>
aws ssm put-parameter --name "$PREFIX/llm/inference_profile_id" \
  --type String --value "eu.anthropic.claude-haiku-4-5-20251001-v1:0" --region <REGION>
```

> `DATABASE_PASSWORD` is generated **on the box** by `bootstrap-ec2.sh` and
> written to SSM from there — do **not** set it from GitHub. `ENV` is hardcoded
> to `production` on the host and is not pushed either.

---

## Step 6 — What value goes where (GitHub side reference)

After the AWS steps, set these in GitHub (**Settings → Environments →
`<ENV>`**). All config is **per-environment** — `dev`, `stage`, `prod` each get
their own copy with env-specific values. There are **no repository-level**
secrets/variables, and `ci.yml` needs **nothing** (it has no AWS access). Full
GitHub-side instructions are in [`GITHUB_CICD_SETUP.md`](./GITHUB_CICD_SETUP.md).

**Variables (non-secret):**

| # | GitHub Variable | Required? | Value / example | Maps to |
|---|---|---|---|---|
| 1 | `AWS_ROLE_ARN` | ✅ Required | `arn:aws:iam::<AWS_ACCOUNT_ID>:role/<ROLE_NAME>` | OIDC role assumed (Step 2) |
| 2 | `AWS_REGION` | ✅ Required | `<REGION>` | — |
| 3 | `ECR_REGISTRY` | ✅ Required | `<AWS_ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com` | Where images push (Step 4) |
| 4 | `EC2_INSTANCE_ID` | ✅ Required | `<INSTANCE_ID>` | SSM deploy target (Step 5.1) |
| 5 | `CORS_ORIGINS` | ⚠️ Recommended | `["https://<PUBLIC_FQDN>"]` | SSM `CORS_ORIGINS` (falls back to box FQDN) |
| 6 | `PUBLIC_BASE_URL` | ⚠️ Recommended | `https://<PUBLIC_FQDN>` | SSM `PUBLIC_BASE_URL` (falls back to box FQDN) |
| 7 | `BEDROCK_MODEL_ID` | ⚠️ Recommended | `anthropic.claude-haiku-4-5-20251001-v1:0` | SSM `llm/model_id` |
| 8 | `BEDROCK_INFERENCE_PROFILE_ID` | ⚠️ Recommended | `eu.anthropic.claude-haiku-4-5-20251001-v1:0` | SSM `llm/inference_profile_id` |
| 9 | `ACCESS_TOKEN_EXPIRE_HOURS` | ⭕ Optional | `24` | SSM `ACCESS_TOKEN_EXPIRE_HOURS` |
| 10 | `BEDROCK_CODING_MODEL_ID` | ⭕ Optional | *(empty = default)* | SSM `llm/coding_model_id` |
| 11 | `HANDOFF_MAX_TRANSCRIPT_BYTES` | ⭕ Optional | `1048576` | SSM `HANDOFF_MAX_TRANSCRIPT_BYTES` |
| 12 | `LANGSMITH_TRACING` | ⭕ Optional | `false` | SSM `LANGSMITH_TRACING` |
| 13 | `LANGSMITH_PROJECT` | ⭕ Optional | `velocityai-<ENV>` | SSM `LANGSMITH_PROJECT` |

**Secrets (masked):**

| # | GitHub Secret | Required? | Value | Notes |
|---|---|---|---|---|
| 1 | `SECRET_KEY` | ✅ Required | `openssl rand -hex 64` | App JWT signing key → SSM SecureString. Reuse the existing SSM value to avoid logging users out; a new value rotates the key. |
| 2 | `LANGSMITH_API_KEY` | ⭕ Optional | *(from LangSmith)* | Leave unset if unused |

**Absolute minimum to get a `dev` deploy working** — just these 5:

```
Variables:
  AWS_ROLE_ARN     = arn:aws:iam::<AWS_ACCOUNT_ID>:role/<ROLE_NAME>
  AWS_REGION       = <REGION>
  ECR_REGISTRY     = <AWS_ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com
  EC2_INSTANCE_ID  = <INSTANCE_ID>
Secret:
  SECRET_KEY       = <openssl rand -hex 64>
```

Everything else has a fallback (host loader defaults, or the SSM values seeded
in Step 5.3).

**Notes:**
- These repeat **per environment** (`dev`/`stage`/`prod`), each with its own values.
- `DATABASE_PASSWORD` is **not** here — host-generated by `bootstrap-ec2.sh` (D-5).
- `ENV` is **not** here — hardcoded to `production` on the host (D-6).
- `deploy.yml` only pushes **non-empty** values to SSM, so unset optionals are safe.

---

## Step 7 — Trigger and verify

1. Push to the `dev` branch (or **Actions → Deploy → Run workflow → dev**).
2. Watch the run: `resolve` → `build` → `deploy`. The deploy step should end
   with `Deploy succeeded.`
3. Confirm the running images on the box (no SSH needed):

```bash
CMD_ID=$(aws ssm send-command \
  --document-name "AWS-RunShellScript" \
  --instance-ids <INSTANCE_ID> \
  --parameters 'commands=["docker ps --format \"{{.Names}} {{.Image}} {{.Status}}\""]' \
  --region <REGION> --query "Command.CommandId" --output text)

sleep 8
aws ssm get-command-invocation --command-id "$CMD_ID" \
  --instance-id <INSTANCE_ID> --region <REGION> \
  --query "StandardOutputContent" --output text
```

### 7.1 (Optional) Manually verify OIDC assumption

You normally never need this — the workflow does it automatically. But to prove
the OIDC trust works outside a workflow (requires a GitHub PAT with `repo` scope):

```bash
GITHUB_TOKEN=<your-github-pat-with-repo-scope>

JWT=$(curl -sH "Authorization: token $GITHUB_TOKEN" \
  "https://token.actions.githubusercontent.com?scope=https://github.com/<GITHUB_ORG>/<REPO>" \
  --header "Accept: application/vnd.github+json" | jq -r '.token')

aws sts assume-role-with-web-identity \
  --role-arn arn:aws:iam::<AWS_ACCOUNT_ID>:role/<ROLE_NAME> \
  --web-identity-token "$JWT" \
  --duration-seconds 3600 \
  --region <REGION>
```

If it returns temporary credentials, OIDC is wired correctly.

---

## 8. Do you need admin access?

You do **not** need GitHub org-owner rights to *use* OIDC. Here's the split:

### GitHub side

| Task | Access needed |
|---|---|
| Push workflow files, trigger runs, view logs | Repo **Write** |
| Create Environments, set variables/secrets, protection rules | Repo **Admin** (or a delegated maintainer role) |

If you only have Write, ask a repo admin to create the three Environments and
set the variables/secrets once — after that, anyone with Write can trigger
deploys.

### AWS side

| Task | Access needed |
|---|---|
| Create the OIDC provider + IAM role + policy (Steps 1–3) | **IAM admin** (one-time) |
| Create ECR repos, tag EC2, KMS, seed SSM (Steps 4–6) | ECR / EC2 / KMS / SSM write |
| Assume the role at deploy time | Nothing extra — the workflow's OIDC token does it |

If you don't have IAM admin, an AWS admin can create the OIDC provider and the
deploy role for you and just hand you the **role ARN** — you (or a repo admin)
then set it as the `AWS_ROLE_ARN` GitHub variable. The minimal IAM permissions
an admin needs to do the one-time setup:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "iam:CreateRole",
        "iam:PutRolePolicy",
        "iam:CreateOpenIDConnectProvider",
        "iam:GetRole"
      ],
      "Resource": [
        "arn:aws:iam::<AWS_ACCOUNT_ID>:role/<ROLE_NAME>",
        "arn:aws:iam::<AWS_ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
      ]
    }
  ]
}
```

---

## Common pitfalls (learned the hard way)

| Symptom | Cause | Fix |
|---|---|---|
| `sts:AssumeRoleWithWebIdentity` not authorized | OIDC provider missing, or trust `sub` doesn't match `repo:<ORG>/<REPO>:environment:<ENV>` | Re-check Step 1; confirm the `environment:` names in the trust policy exactly match your GitHub Environment names (`dev`/`stage`/`prod`, **not** `staging`/`production`) — see §2.1a |
| `ssm:SendCommand ... no identity-based policy allows` | `SendCommand` tag condition applied to the document too | Split into two statements (Step 3.1) |
| SSM command status `Failed` immediately with `Illegal option -o pipefail` | On-box script ran under dash, not bash | The `deploy.yml` script starts with `#!/bin/bash` (already fixed) |
| Config value not reaching the app | Wrong SSM key name (loader drops unknown keys) | Use exact names; Bedrock keys live under `llm/*` |
| Deploy targets the wrong/no box | EC2 `Environment` tag missing or wrong | Set the tag (Step 5.1) using the short env name `dev`/`stage`/`prod` |

---

## Setup order summary

```
Step 1  OIDC provider ............ once per account   (IAM admin)
Step 2  IAM role + trust ......... once (or per env)  (IAM admin)
Step 3  Permissions policy ....... once (or per env)  (IAM admin)
Step 4  ECR repos ................ once per account   (ECR write)
Step 5  Per-env: tag + KMS + SSM . per environment    (EC2/KMS/SSM write)
Step 6  GitHub variables/secrets . per environment    (repo Admin)
Step 7  Trigger + verify ......... per deploy         (repo Write)
```
