# Flowin — Simple Secure AWS Deployment

> **Audience:** the Hexaware UKI / Flowin platform engineering team.
> **Branch:** `agent-pipeline-execution`. **Remote:** `gitlab.com/hexaware-uki/flowin`.
> **Companion documents:** `docs/WORKFLOWS.md` (frontend + backend behaviour, must read), `docs/PRODUCTION_DEPLOYMENT_GUIDE.md` (the multi-service alternative; deliberately not what we recommend here).
> **Scope of this guide:** the smallest secure AWS footprint that runs the full Flowin stack on a single EC2 instance, hardened to enterprise standards.

---

## 0. TL;DR & decision log

The customer asked for "as little AWS as possible, but no security shortcuts". The recommendation below is the smallest footprint that still passes a sensible enterprise threat model.

| Decision | Choice | Why (one line) | Cross-ref |
|---|---|---|---|
| Topology | Single EC2 instance running everything | Smallest moving parts, smallest blast radius, smallest bill | §2 |
| Instance type | `m6i.xlarge` (4 vCPU / 16 GB RAM / 100 GB gp3 EBS) on Ubuntu 24.04 LTS | Headroom for ~200 concurrent sessions given B7/B8 memory profile (~100 MB / pipeline) | §5 |
| OS | Ubuntu 24.04 LTS (Canonical official AMI) | LTS kernel, free `unattended-upgrades`, well-known Postgres/nginx packages | §5, §8.1 |
| Reverse proxy + TLS | nginx 1.24+ on the box, Let's Encrypt certs via certbot (HTTP-01) | Customer rejects ALB; ACM doesn't issue free certs to EC2; certbot+nginx is boring and proven | §7, §8.2 |
| WebSocket timeout | nginx `proxy_read_timeout 5400s; proxy_send_timeout 5400s` (90 min) | Long PPT/prototype runs in B7 stream tokens for tens of minutes; idle close on 90 min cap | §8.2, W21/W33/B5 |
| Database | PostgreSQL 16 on the same instance, on a *separate* encrypted gp3 EBS volume (50 GB) mounted at `/var/lib/postgresql` | Customer accepts; isolating the data volume gives clean snapshot/restore | §8.4, §11 |
| Secrets store | AWS Systems Manager Parameter Store (SecureString, KMS-encrypted) | Free tier; meets "encrypted at rest, not in git, IAM-gated"; cheaper than Secrets Manager and adequate for this footprint | §9 |
| LLM provider | **AWS Bedrock — Claude Haiku 4.5 via cross-region inference profile (`eu.anthropic.claude-haiku-4-5-20251001-v1:0`).** Auth via instance-profile IAM role; no API key. | IAM-only auth removes the highest-risk long-lived secret; LLM traffic stays inside AWS via VPC interface endpoints; spend and audit consolidate onto the AWS bill. | §0.1, §5.3, §6.4, §9 |
| Outbound ACL | NAT-less: instance has a public IP in a public subnet. Security-group egress rule keeps TCP/443 to `0.0.0.0/0` open for apt, GitHub releases, and the Bedrock public endpoint as a fallback path; the **preferred** Bedrock path is the VPC interface endpoint provisioned in §6.4, which keeps LLM traffic private. | NAT Gateway is $35/mo per AZ for no real benefit on a single box; the Bedrock interface endpoint covers the data-residency story instead. | §6, §6.4 |
| TLS termination | nginx terminates; backend listens on `127.0.0.1:8000`; frontend listens on `127.0.0.1:3000` | All inter-service traffic stays on loopback; only 80/443/22 reach the network | §8.2 |
| Logging | CloudWatch Agent ships nginx, journald (systemd units), and Postgres logs | The customer named CloudWatch as the AWS-mandated service; alarms fire from there | §10 |
| Backups | (a) EBS snapshot of the data volume nightly via AWS Backup; (b) `pg_dump` → S3 (SSE-S3) hourly via systemd timer. RPO 1 hour, RTO 30 min. | Belt-and-braces. Snapshot is fast, dump is portable. | §11 |
| Disaster recovery | Bootstrap script (Appendix D) + latest snapshot + Parameter Store puts a fresh instance back in service in <30 min | §11 |
| Concurrency ceiling | ~150 concurrent live pipeline sessions on `m6i.xlarge`, ~50 concurrent if all running PPT/prototype (the 32K-token agents) | B7 / B8: each running pipeline holds ~100 MB Python heap | §15 |
| Migration path | Vertical scale → split frontend onto static-host EC2 → move to ECS/ALB/RDS per `PRODUCTION_DEPLOYMENT_GUIDE.md` | §16 |
| Monthly cost band | Infra-only: low ~$200, typical ~$240–285, high ~$415 (includes the new ~$15/mo Bedrock VPC interface endpoint pair). LLM token spend is **separate and traffic-dependent**: ~$50–$200/mo typical, $1k+ at high volume. | §14 |

### 0.1 The Bedrock vs Anthropic question, settled

We use AWS Bedrock for all Claude calls. The original analysis (preserved in commit history) recommended deferring this; the customer overrode that decision. Note that `WORKFLOWS.md` B7 still says "no Bedrock integration" — that section is now stale and points to the migration commit (`[infra]` — backend code migration).

The three concrete benefits we now realise:

1. **No long-lived API key.** Auth is the EC2 instance-profile IAM role; rotation is handled by STS. This removes the highest-risk secret from the system — there is no `ANTHROPIC_API_KEY` to leak from Parameter Store, from a `.env` file on disk, from a journald log line, or from a developer's shell history.
2. **Traffic stays inside AWS.** Combined with a Bedrock VPC interface endpoint (see §6.4), the entire LLM data path is private — request and response never traverse the public internet. Important for the shared org account / data-residency story Hexaware UKI tells regulated customers.
3. **Single audit pane.** All LLM invocations are visible in CloudTrail (`bedrock:InvokeModel*` events). Spend lands on the same AWS bill as everything else; one PO, one invoice line, one finance owner.

Honest trade-offs:

| Trade-off | Mitigation |
|---|---|
| **(a) Region availability.** Haiku 4.5 may not be directly available in `eu-west-2`. Confirm with `aws bedrock list-foundation-models --region eu-west-2 --query 'modelSummaries[?contains(modelId, \`claude-haiku-4-5\`)].modelId' --output table`. If the model is not available directly, use the EU cross-region inference profile `eu.anthropic.claude-haiku-4-5-20251001-v1:0` which routes invocations between EU regions transparently. | The deployment defaults to the inference profile; data-residency is preserved across the EU geography. |
| **(b) Model-version lag.** Anthropic ships new Claude variants on direct API a few weeks before Bedrock. Acceptable for production. | We don't auto-track the bleeding edge anyway; model upgrades are a release-gated change (§9). |
| **(c) Throughput tier.** Bedrock has its own per-account / per-model TPM and RPM quotas. The default tier is conservative (e.g. ~100 RPM for Haiku 4.5 in some regions). | Open a quota-increase request **before** load testing — see §10.4 and the new pre-launch item in §3. |

**Emergency continuity.** If Bedrock has a regional outage and direct Anthropic is needed for emergency continuity, the migration is one config change (`LLM_PROVIDER=anthropic`, set `ANTHROPIC_API_KEY` in Parameter Store) — the codebase keeps both backends behind a feature flag (see commit `[infra]` — backend code migration). The optional fallback Parameter Store entry exists precisely for this case (§9).

---

## 1. What this guide deploys (architecture diagram)

```
                                           Internet
                                              |
                                              | TCP/443 (HTTPS, WSS)
                                              | TCP/80 (redirect + ACME http-01)
                                              v
                            +---------------------------------+
                            |       Route 53 hosted zone      |
                            |  flowin.example.com  A → EIP    |
                            +---------------------------------+
                                              |
                                              v
   +-------------------------------------------------------------------------+
   |                            VPC (10.20.0.0/16)                            |
   |                                                                          |
   |   +-----------------------------+    +------------------------------+    |
   |   |  Public subnet (1 AZ)       |    |  IGW                          |    |
   |   |  10.20.1.0/24               |<-->|                               |    |
   |   |                             |    +------------------------------+    |
   |   |  +-----------------------+  |                                        |
   |   |  | EC2 m6i.xlarge        |  |    Egress: 443/tcp 0.0.0.0/0 (apt,    |
   |   |  | Ubuntu 24.04 LTS      |  |    github, Bedrock fallback only),    |
   |   |  | EIP attached          |  |    80/tcp 0.0.0.0/0 (ACME).           |
   |   |  |                       |  |    LLM via Bedrock VPC endpoint (§6.4).|
   |   |  |                       |  |    Ingress: 22/tcp restricted         |
   |   |  |                       |  |    /32 bastion CIDR; 80/tcp world;     |
   |   |  | nginx :80, :443       |  |    443/tcp world.                     |
   |   |  |   |                   |  |                                        |
   |   |  |   +-> uvicorn 127.0.0.1:8000 (FastAPI + WebSocket)               |
   |   |  |   +-> next start 127.0.0.1:3000 (Next.js prod build)             |
   |   |  |                       |  |                                        |
   |   |  | postgres 16           |  |                                        |
   |   |  |   listen 127.0.0.1    |  |                                        |
   |   |  |   data on /var/lib/   |  |                                        |
   |   |  |     postgresql (gp3,  |  |                                        |
   |   |  |     50 GB, encrypted) |  |                                        |
   |   |  |                       |  |                                        |
   |   |  | systemd units:        |  |                                        |
   |   |  |   flowin-backend      |  |                                        |
   |   |  |   flowin-frontend     |  |                                        |
   |   |  |   nginx               |  |                                        |
   |   |  |   postgresql          |  |                                        |
   |   |  |   amazon-cloudwatch-  |  |                                        |
   |   |  |     agent             |  |                                        |
   |   |  |   pg-dump-to-s3.timer |  |                                        |
   |   |  |   certbot.timer       |  |                                        |
   |   |  +-----------------------+  |                                        |
   |   +-----------------------------+                                        |
   |                                                                          |
   +-------------------------------------------------------------------------+
                |                |                  |                |
                v                v                  v                v
        +-------------+   +-------------+   +-----------------+  +----------+
        | CloudWatch  |   | Systems     |   | S3 bucket        |  | AWS      |
        | Logs +      |   | Manager     |   | flowin-prod-     |  | Backup   |
        | Metrics +   |   | Parameter   |   | backups          |  | Vault    |
        | Alarms      |   | Store       |   | (versioned, SSE) |  | (EBS     |
        |             |   | (KMS)       |   |                  |  | snaps)   |
        +-------------+   +-------------+   +-----------------+  +----------+

LLM:      AWS Bedrock (Claude Haiku 4.5) via VPC interface endpoint
          (com.amazonaws.eu-west-2.bedrock-runtime). Auth via instance-profile
          IAM role; traffic stays inside the VPC. See §6.4.
```

That's it. Seven AWS services in total: EC2, EBS, Route 53, CloudWatch, Systems Manager Parameter Store, S3, Bedrock (via VPC interface endpoints), plus AWS Backup which is just a scheduler over EBS snapshots. Nothing else.

---

## 2. Why a single EC2 (and where this design breaks)

### Why this design

- **One unit to reason about.** Reverse proxy, application, database, and cache (we don't actually need a cache today — see B2/B5; the chat server is in-process) all live in one OS, share one log timeline, share one filesystem. Debugging a production incident requires `ssh` and `journalctl`, not seven AWS consoles.
- **No network plane between services.** All inter-process traffic crosses loopback (`127.0.0.1`). There is no VPC routing, no security-group fan-out, no ALB target health, no service mesh. Less to misconfigure, smaller attack surface.
- **Deterministic cost.** Fixed monthly EC2 + EBS charges. The unpredictable line item is Bedrock token spend, which is the same regardless of topology and now lands on the same AWS invoice.
- **Boring, well-trodden tooling.** nginx + systemd + postgres + apt + ufw + certbot is a stack any senior Linux admin can operate.

### Where this design breaks

- **Single AZ.** Hardware fault, EBS volume issue, or Availability-Zone outage takes the whole product down. The recovery story is "snapshot + bootstrap to a new instance, possibly in a different AZ" (§11). RTO is 30 min in practice; if you need a single-digit-minute RTO, you need the multi-service architecture.
- **Single OS upgrade.** A bad kernel update or a Postgres major-version upgrade brings everything down at once. Mitigated by a strict maintenance-window policy (§13) and the bootstrap-from-snapshot drill.
- **Vertical scaling has a ceiling.** ~50 concurrent prototype/PPT pipelines (B7 says each holds ~100 MB heap on a 32K-token output agent). Past that, vertical scaling on `m6i` tops out at `m6i.4xlarge` (16 vCPU / 64 GB), which is not three years of headroom.
- **Co-resident database.** Application memory pressure can OOM-kill Postgres. We pin Postgres to a cgroup-managed memory floor (§8.4) but at any non-trivial load, RDS is the right answer.
- **You cannot do a zero-downtime release on one box.** A backend rollout is "stop, deploy, start" — typically 5–10 seconds of WS reconnect noise. Frontend rollout is the same. For a true blue-green you need at least two boxes.

These are honest trade-offs. They are acceptable for **enterprise pilot** and **internal-only** workloads of the kind Hexaware UKI typically runs. They are *not* acceptable for an SLA'd customer-facing product — at which point you migrate (§16).

---

## 3. Pre-launch blockers (must-fix in code before deploying)

These are extracted directly from `WORKFLOWS.md` §5. **No production deployment proceeds until items 1–6 below are merged.** Items 7–10 are strongly recommended but can launch with documented compensating controls.

### Blocker 1 — Default `SECRET_KEY` literal (B1, gap-row 1; §5 item 9)

`backend/app/core/config.py:16` ships with `SECRET_KEY: str = "dev-secret-key-change-in-production"`. Any deployment that fails to override it produces predictable, forgeable JWTs.

**Required fix (in code):**

1. Remove the default. Make `SECRET_KEY` required:
   ```python
   SECRET_KEY: str  # no default
   ```
2. Add a startup assertion in `app/main.py` `lifespan()`:
   ```python
   if settings.SECRET_KEY in ("", "dev-secret-key-change-in-production"):
       raise RuntimeError("SECRET_KEY must be set to a non-default value in production")
   if len(settings.SECRET_KEY) < 32:
       raise RuntimeError("SECRET_KEY must be >= 32 characters")
   ```
3. Generate the production value once with `openssl rand -hex 64`; store in Parameter Store (§9).

### Blocker 2 — Skills authorisation gap (B6; §5 item 1)

`api/agents.py:138-155` lets *any* authenticated user POST or DELETE *any* agent's skill, and `pipeline.py:72-74` then prepends that skill to the agent's system prompt for whoever runs the next pipeline. This is a cross-tenant prompt-injection vector.

**Required fix (in code):**

Either (a) namespace skills to the user — `backend/skills/{user_id}/{agent_id}/SKILL.md` — and filter all four skill endpoints by `current_user.id`; or (b) gate skill mutation behind `User.is_admin = True` and treat skills as global config maintained by the admin team.

Option (a) is more flexible; option (b) is faster to ship. **Pick (a) for production.** Either fix is mandatory before this deployment is exposed to more than one human user.

### Blocker 3 — Cancel-pipeline does not actually cancel (B2/B5; §5 item 2)

`websocket.py:127-135` acknowledges `cancel_pipeline` to the client, but the orchestrator task is not stored, not awaited, and not cancellable. The pipeline keeps streaming until natural completion, burning Bedrock tokens after the user clicked Stop (W38). At enterprise scale this directly inflates the AWS invoice — and unlike the previous Anthropic-direct setup, the cost now hits the same bill as the rest of the infra, so the Bedrock token-budget alarm in §10.4 is the only protective guardrail.

**Required fix (in code):**

Wrap each `_handle_pipeline_execution` call in `asyncio.create_task(...)`, store the task on the per-connection state, and call `task.cancel()` in the `cancel_pipeline` branch. Inside the executor, catch `asyncio.CancelledError` between agents (between `agent_complete` events) and emit a real `pipeline_cancelled`, then UPDATE the `workflow_runs` row to `status="cancelled"` (which also fixes Blocker 6).

### Blocker 4 — No JWT revocation / no logout endpoint (B1; §5 item 3)

W06 logout is purely client-side; tokens remain valid on the server until the 24-hour `exp`. Combined with W07 (password change does not invalidate sessions), a stolen token survives a password rotation.

**Required fix (in code):**

Either (a) add a `password_version: int` column to `users`, embed it in the JWT, bump on password change, validate on every request; or (b) introduce a Redis-backed denylist. Since this guide explicitly does not deploy Redis, **use option (a)**. It fits a single-EC2 footprint, is one column, and addresses both the logout and the password-change cases.

### Blocker 5 — WS token in query string leaks to logs (B1; §5 item 10)

`useWebSocket.ts` connects to `${WS_URL}?token=…` (B1). Tokens land in nginx access logs, in browser history, in any HTTP-aware proxy. We can mitigate two ways: (a) configure nginx to strip the `token` query parameter from the access log (mitigation, not fix); (b) move the token to the `Sec-WebSocket-Protocol` subprotocol header — this is the real fix.

**Required fix (in code + nginx):**

Code: change the WS handler in `backend/app/api/websocket.py` and the frontend `useWebSocket.ts` to use the subprotocol header pattern (`websocket.headers.get("sec-websocket-protocol")`).

Nginx: until the code change ships, mask the query string in the access log — see Appendix A. This is mandatory either way as defence-in-depth.

### Blocker 6 — Cancelled runs never reach a terminal state (B4; §5 item 4)

A consequence of Blocker 3. `workflow_runs` accumulates rows stuck in `status="running"` forever. A nightly cleanup job is *not* the right answer (it masks the bug). The correct fix is the same patch as Blocker 3 — when cancellation works, run the UPDATE to `cancelled` in the `except CancelledError:` arm.

### Strongly recommended (non-blocking but ship before going wide)

7. **Rate limit `/api/auth/login`, `/api/auth/register`, `/api/auth/change-password`.** Add `slowapi` keyed on remote-IP. nginx already adds `X-Real-IP` (Appendix A), so `key_func=get_remote_address` works.
8. **Per-user Bedrock token-budget cap.** Sum input/output tokens over a rolling 24h window and reject `run_pipeline` over the cap. This is the only line of defence against a compromised account running expensive prototype pipelines on loop. (Same intent as the prior "Anthropic spend cap" item; the metric source is now Bedrock `InputTokenCount` / `OutputTokenCount`.)
9. **Email verification on `/api/auth/register`** (out of scope for this deployment guide, but trivially abused otherwise).
10. **Move `localStorage` JWT to an HttpOnly+SameSite=Strict cookie** (large frontend change; deferred).

**Non-code pre-launch item:** **submit a Bedrock service quota increase request** for `Tokens per minute` and `Requests per minute` for Claude Haiku 4.5 in `eu-west-2` (and any cross-region inference targets — see §0.1). Default Bedrock quotas are conservative (~100 RPM for Haiku 4.5 in some regions); load testing without an increase will hit `InvocationThrottles`. Open the request via Service Quotas console at least 5 business days before the planned load test — increases for Bedrock can require human review.

These are tracked in the project backlog. They are *not* deployment blockers; they are launch-readiness items. The first deployment goes to a small invite-only pilot — keep the user list short until 7 and 8 are done.

---

## 4. AWS account prerequisites (account-level setup)

Run these once per AWS account, ideally well before the deployment. None of them are Flowin-specific; they are baseline hygiene.

1. **Enable AWS CloudTrail** in the home region; deliver to a dedicated S3 bucket with object-lock and a 365-day retention. Without CloudTrail there is no audit trail for "who created/modified the EC2 instance" — non-negotiable for enterprise.
2. **Enable AWS Config** with the AWS-managed conformance pack `Operational-Best-Practices-for-EC2`. This catches "EBS volume not encrypted" etc. before they bite.
3. **Enable IAM Access Analyzer** at the account level.
4. **Enable GuardDuty** in the deployment region (~$3/month at this scale, well worth it). This is the one extra paid service the security argument forces us to add — it detects EC2 instance compromise from VPC flow logs and CloudTrail without needing any agent on the box.
5. **Set the root account on hardware MFA**, no static keys.
6. **Create a dedicated IAM user `flowin-deployer`** with programmatic access; attach the least-privilege policy in §5.3. Use this for the bootstrap; do not use a personal SSO identity for instance lifecycle.
7. **Choose a region.** For Hexaware UKI customers, **`eu-west-2` (London)** is the default. UK data residency. If a customer requires Ireland (`eu-west-1`) or Frankfurt (`eu-central-1`), the guide below works unchanged — just substitute `eu-west-2` everywhere.
8. **Pick an Availability Zone within that region** — e.g. `eu-west-2a`. Single-AZ design (§2). Document the choice; the snapshot-restore drill in §11 needs to know it.
9. **Reserve an Elastic IP** in the region (`aws ec2 allocate-address`). Cost: free while attached to a running instance. Keep the EIP across instance replacements so the Route 53 A-record never has to update.
10. **Buy a Route 53 hosted zone** for the apex domain (e.g. `flowin.example.com`).

---

## 5. EC2 instance — sizing, AMI, IAM role

### 5.1 Sizing rationale

The dominant memory consumer is per-pipeline Python heap. From `WORKFLOWS.md` B7/B8:

- Each running pipeline holds ~100 MB resident memory (LangChain stream buffers + per-agent output buffers up to 32K tokens for the `backlog-compiler`, `ppt-code-generator`, `ppt-assembler`, `prototype-finalizer`, `app-builder`, `reverse-engineer` agents).
- Postgres for ~1500 active users at steady state is ~1 GB on disk and ~512 MB shared_buffers (we'll tune to 4 GB shared_buffers; see §8.4).
- Next.js production server idles around 200 MB; uvicorn + FastAPI idles around 150 MB; nginx well under 50 MB.

A reasonable steady-state budget on `m6i.xlarge` (16 GB RAM):

| Component | Reserved RAM |
|---|---|
| Linux kernel + system services | 1.0 GB |
| nginx | 0.1 GB |
| Postgres (`shared_buffers=4GB`, plus work_mem etc.) | 5.0 GB |
| Next.js (`next start`) | 0.4 GB |
| FastAPI baseline | 0.2 GB |
| Per-pipeline working memory | 9.3 GB (≈ 90 concurrent pipelines if each holds 100 MB) |

That gives a **comfortable headroom of ~90 concurrent active pipelines** before swap pressure starts. With chat sessions (cheaper, short-lived agent calls) the practical concurrency is higher: ~150–200 *connected* WebSocket sessions, ~50 of which can be running heavy pipelines simultaneously. If you need more, vertical scale to `m6i.2xlarge` (8 vCPU / 32 GB, doubles the heavy-pipeline ceiling) before you split the topology.

### 5.2 AMI choice

Use the **official Canonical Ubuntu 24.04 LTS** AMI (Noble Numbat). At time of writing the AMI ID in `eu-west-2` is published at `https://ubuntu.com/server/docs/cloud-images/amazon-ec2`; resolve it dynamically:

```bash
aws ec2 describe-images \
  --region eu-west-2 \
  --owners 099720109477 \
  --filters \
    "Name=name,Values=ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*" \
    "Name=state,Values=available" \
  --query 'sort_by(Images, &CreationDate)[-1].ImageId' \
  --output text
```

Do not use Amazon Linux 2023. The Ubuntu Postgres/nginx packages are well-trodden, and the systemd unit files in this guide are written against Ubuntu 24.04 paths.

### 5.3 IAM role for the instance

The instance role grants exactly five permission groups. Nothing else.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ParameterStoreRead",
      "Effect": "Allow",
      "Action": ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"],
      "Resource": "arn:aws:ssm:eu-west-2:<ACCOUNT_ID>:parameter/flowin/prod/*"
    },
    {
      "Sid": "ParameterStoreKMS",
      "Effect": "Allow",
      "Action": ["kms:Decrypt"],
      "Resource": "arn:aws:kms:eu-west-2:<ACCOUNT_ID>:key/<PARAMETER_STORE_KMS_KEY_ID>",
      "Condition": {
        "StringEquals": {"kms:EncryptionContext:PARAMETER_ARN": "arn:aws:ssm:eu-west-2:<ACCOUNT_ID>:parameter/flowin/prod/*"}
      }
    },
    {
      "Sid": "BackupBucketWrite",
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:PutObjectAcl"],
      "Resource": "arn:aws:s3:::flowin-prod-backups/postgres/*"
    },
    {
      "Sid": "CloudWatchAgent",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DescribeLogStreams",
        "cloudwatch:PutMetricData",
        "ec2:DescribeTags",
        "ec2:DescribeVolumes"
      ],
      "Resource": "*"
    }
  ]
}
```

**Bedrock invocation policy.** Attach this as a separate inline statement (or a separate managed policy) on the same instance role. Scoped to exactly the model and inference profile we use, *not* `bedrock:*` and *not* `Resource: "*"`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowBedrockClaudeHaiku45",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
        "bedrock:Converse",
        "bedrock:ConverseStream"
      ],
      "Resource": [
        "arn:aws:bedrock:eu-west-2::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
        "arn:aws:bedrock:*::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
        "arn:aws:bedrock:eu-west-2:*:inference-profile/eu.anthropic.claude-haiku-4-5-20251001-v1:0"
      ]
    }
  ]
}
```

The second resource ARN with `*` for region is required because the cross-region inference profile fans invocations out to multiple regions (e.g. `eu-west-2`, `eu-west-1`, `eu-central-1`); the IAM check evaluates against the eventual target region's foundation-model ARN, so the wildcard is mandatory for the profile to work. Keep it scoped to the *exact* `claude-haiku-4-5` model — never broaden to `anthropic.*` or `*`.

Notes:

- The `Resource: "*"` on the CloudWatch Agent block is unavoidable (CloudWatch and EC2-describe APIs do not support resource-level scoping for these actions). The blast radius is limited to log/metric write and instance metadata read — both safe.
- The S3 statement is *write-only* under one prefix. The instance cannot enumerate the bucket, cannot read other prefixes, cannot delete. Backup retention/expiry is enforced by S3 lifecycle policy (§11).
- Parameter Store decrypts are gated on a KMS encryption-context match, so a leaked AWS credential cannot lift a parameter that was put with a different context.
- The Bedrock policy contains no API-key material. Auth is the EC2 instance-profile role + STS; rotation is handled by AWS. There is no `ANTHROPIC_API_KEY` Parameter Store entry in the normal path — see §9 for the optional emergency-fallback entry.

Attach this role to the instance via an IAM **instance profile** (`flowin-prod-instance`). You will reference it in the `aws ec2 run-instances --iam-instance-profile Name=flowin-prod-instance`.

### 5.4 EBS volumes

Two volumes:

| Mount | Type | Size | Encryption | Notes |
|---|---|---|---|---|
| `/` (root) | gp3 (3000 IOPS, 125 MB/s) | 30 GB | KMS (AWS-managed key) | OS, application code, logs |
| `/var/lib/postgresql` | gp3 (3000 IOPS, 125 MB/s) | 50 GB | KMS (customer-managed key `alias/flowin-prod-data`) | Postgres data dir; mounted xfs; isolating it makes snapshot/restore atomic |

Use a **customer-managed KMS key** (CMK) for the data volume. AWS-managed keys do not produce KMS audit events for cryptographic operations the way CMKs do; for a database disk that holds user content you want CloudTrail to log every decrypt.

```bash
# Create the CMK once
aws kms create-key \
  --description "Flowin prod data volume encryption" \
  --key-usage ENCRYPT_DECRYPT \
  --key-spec SYMMETRIC_DEFAULT \
  --region eu-west-2
aws kms create-alias \
  --alias-name alias/flowin-prod-data \
  --target-key-id <KEY_ID> \
  --region eu-west-2
```

### 5.5 Launching the instance

```bash
aws ec2 run-instances \
  --region eu-west-2 \
  --image-id <AMI_ID_FROM_5.2> \
  --instance-type m6i.xlarge \
  --key-name flowin-prod-bastion \
  --subnet-id <PUBLIC_SUBNET_ID> \
  --security-group-ids <SG_ID_FROM_§6> \
  --iam-instance-profile Name=flowin-prod-instance \
  --metadata-options "HttpTokens=required,HttpEndpoint=enabled,HttpPutResponseHopLimit=1" \
  --block-device-mappings '[
    {"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":30,"VolumeType":"gp3","Encrypted":true,"DeleteOnTermination":true}},
    {"DeviceName":"/dev/sdf","Ebs":{"VolumeSize":50,"VolumeType":"gp3","Encrypted":true,"KmsKeyId":"alias/flowin-prod-data","DeleteOnTermination":false}}
  ]' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=flowin-prod},{Key=Environment,Value=prod},{Key=Owner,Value=flowin-team}]' \
  --user-data file://bootstrap.sh
```

Key flags:

- `HttpTokens=required` enforces IMDSv2. IMDSv1 is an SSRF target and must be disabled.
- `HttpPutResponseHopLimit=1` blocks containers and exec runtimes from reaching IMDS (defence-in-depth).
- `DeleteOnTermination=false` on the data volume — losing user data because the instance was terminated is not acceptable.
- `--key-name`: an SSH key for emergency access. Day-to-day SSH should be via Systems Manager Session Manager (free, audited via CloudTrail) — see §8.1.

After launch:

```bash
INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=flowin-prod" "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].InstanceId' --output text --region eu-west-2)

aws ec2 associate-address \
  --instance-id $INSTANCE_ID \
  --allocation-id <EIP_ALLOCATION_ID_FROM_§4_step_9> \
  --region eu-west-2
```

`bootstrap.sh` (Appendix D) takes the instance from cold to "ready for app deploy" in ~6 minutes.

---

## 6. Network & firewall — VPC, subnets, security groups

### 6.1 VPC layout

This is intentionally minimal. **One VPC, one public subnet, one Internet Gateway, no NAT Gateway.** Putting the instance in a public subnet with a public IP is fine *because* the security group is the perimeter, and it is locked down.

```bash
aws ec2 create-vpc \
  --cidr-block 10.20.0.0/16 \
  --tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=flowin-prod-vpc}]' \
  --region eu-west-2

aws ec2 create-subnet \
  --vpc-id <VPC_ID> \
  --cidr-block 10.20.1.0/24 \
  --availability-zone eu-west-2a \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=flowin-prod-public-2a}]' \
  --region eu-west-2

aws ec2 create-internet-gateway \
  --tag-specifications 'ResourceType=internet-gateway,Tags=[{Key=Name,Value=flowin-prod-igw}]' \
  --region eu-west-2

aws ec2 attach-internet-gateway --vpc-id <VPC_ID> --internet-gateway-id <IGW_ID> --region eu-west-2

aws ec2 create-route-table --vpc-id <VPC_ID> \
  --tag-specifications 'ResourceType=route-table,Tags=[{Key=Name,Value=flowin-prod-public-rt}]' \
  --region eu-west-2
aws ec2 create-route --route-table-id <RT_ID> --destination-cidr-block 0.0.0.0/0 --gateway-id <IGW_ID> --region eu-west-2
aws ec2 associate-route-table --route-table-id <RT_ID> --subnet-id <SUBNET_ID> --region eu-west-2

aws ec2 modify-subnet-attribute --subnet-id <SUBNET_ID> --map-public-ip-on-launch --region eu-west-2
```

**Why no NAT Gateway?** NAT is $0.045/hour ($32/month) per AZ, plus per-GB processing. A single instance in a public subnet with a strict outbound security group is functionally equivalent for our use case (egress to apt + Bedrock fallback + Let's Encrypt + S3 backup endpoint; the bulk of LLM traffic goes via the VPC interface endpoint in §6.4 and never leaves AWS). The instance has no inbound ports open beyond 80/443/22, so the public IP is not a meaningful attack surface — the security group is.

**Why one AZ?** Because a single EC2 cannot span AZs. Multi-AZ requires multiple instances behind something — at which point §16 applies.

### 6.2 Security group

One security group, four rules. Order matters: deny-by-default unless explicitly allowed.

```bash
SG_ID=$(aws ec2 create-security-group \
  --group-name flowin-prod-sg \
  --description "Flowin production single-EC2" \
  --vpc-id <VPC_ID> \
  --region eu-west-2 \
  --query 'GroupId' --output text)

# Inbound 80/tcp from world (HTTP -> HTTPS redirect + ACME challenge)
aws ec2 authorize-security-group-ingress --group-id $SG_ID \
  --protocol tcp --port 80 --cidr 0.0.0.0/0 --region eu-west-2

# Inbound 443/tcp from world (HTTPS, WSS)
aws ec2 authorize-security-group-ingress --group-id $SG_ID \
  --protocol tcp --port 443 --cidr 0.0.0.0/0 --region eu-west-2

# Inbound 22/tcp ONLY from the bastion / corporate egress CIDR
# Replace <BASTION_CIDR> with the team's egress IP/32 or corporate VPN CIDR.
# This is a hardline rule. SSH from anywhere = automatic credential-stuffing.
aws ec2 authorize-security-group-ingress --group-id $SG_ID \
  --protocol tcp --port 22 --cidr <BASTION_CIDR>/32 --region eu-west-2

# Outbound: 443/tcp to anywhere (apt, GitHub, S3, Bedrock fallback path).
# Bedrock traffic normally goes via the VPC interface endpoint (§6.4) and stays
# inside the VPC; the 0.0.0.0/0:443 egress rule is required for apt + GitHub
# + Bedrock-fallback only.
# 80/tcp to anywhere (apt, Let's Encrypt OCSP)
# Default sg has 0.0.0.0/0 all-egress; replace it with explicit rules:
aws ec2 revoke-security-group-egress --group-id $SG_ID \
  --protocol -1 --port -1 --cidr 0.0.0.0/0 --region eu-west-2
aws ec2 authorize-security-group-egress --group-id $SG_ID \
  --protocol tcp --port 443 --cidr 0.0.0.0/0 --region eu-west-2
aws ec2 authorize-security-group-egress --group-id $SG_ID \
  --protocol tcp --port 80 --cidr 0.0.0.0/0 --region eu-west-2
# DNS — VPC resolver lives at the VPC's +2 address but UDP/53 outbound is also needed
aws ec2 authorize-security-group-egress --group-id $SG_ID \
  --protocol udp --port 53 --cidr 0.0.0.0/0 --region eu-west-2
aws ec2 authorize-security-group-egress --group-id $SG_ID \
  --protocol tcp --port 53 --cidr 0.0.0.0/0 --region eu-west-2
```

**SSH ingress is the most-abused vector on the public internet.** Locking it to `<BASTION_CIDR>/32` is the single most valuable rule on the list. If you do not have a bastion or a corporate VPN egress IP, drop the SSH ingress rule entirely and use **Systems Manager Session Manager** for shell access (§8.1) — it requires zero open ports.

### 6.3 Egress posture for non-AWS traffic

The non-AWS egress requirements after migration to Bedrock are:

- **apt repos** (Ubuntu archive + Canonical security) — TCP/443 (and a small amount of TCP/80 for repo metadata).
- **GitHub releases** — TCP/443 (`github.com`, `objects.githubusercontent.com`, `codeload.github.com`).
- **Let's Encrypt** — TCP/80 (HTTP-01 challenge inbound) + TCP/443 (OCSP outbound).
- **Bedrock public endpoint as fallback** — TCP/443 to `bedrock-runtime.eu-west-2.amazonaws.com` *only if* the VPC interface endpoint (§6.4) is unavailable.

These all share Cloudflare-/CDN-style fronts whose IPs rotate, so pinning egress to specific IPs *will* break in production. Egress filtering instead happens at the application layer: only the backend, the apt updater, certbot, and the AWS SDK make outbound calls — no other process on the box can reach the internet because it is firewalled by ufw (§8.1).

**Free S3 gateway endpoint.** Add this regardless — it stops the backup path from depending on internet egress and costs nothing:

```bash
aws ec2 create-vpc-endpoint \
  --vpc-id <VPC_ID> \
  --service-name com.amazonaws.eu-west-2.s3 \
  --route-table-ids <RT_ID> \
  --region eu-west-2
```

For Bedrock (the LLM data path) we go further and provision interface endpoints — see §6.4.

### 6.4 Bedrock VPC interface endpoints

Provision two interface endpoints in the VPC so that Bedrock traffic never leaves AWS:

- `com.amazonaws.eu-west-2.bedrock-runtime` — used by `InvokeModel`, `InvokeModelWithResponseStream`, `Converse`, `ConverseStream`. **This is the one the application uses at runtime.**
- `com.amazonaws.eu-west-2.bedrock` — management plane, rarely needed at runtime; useful for `aws bedrock list-foundation-models`, model discovery, and operator diagnostics. Provision it for completeness; if budget is tight you can drop this one and only keep `bedrock-runtime`.

```bash
# Runtime endpoint — required.
aws ec2 create-vpc-endpoint \
  --vpc-id <VPC_ID> \
  --service-name com.amazonaws.eu-west-2.bedrock-runtime \
  --vpc-endpoint-type Interface \
  --subnet-ids <SUBNET_ID> \
  --security-group-ids $SG_ID \
  --private-dns-enabled \
  --region eu-west-2

# Management endpoint — recommended, drop if cost-pressured.
aws ec2 create-vpc-endpoint \
  --vpc-id <VPC_ID> \
  --service-name com.amazonaws.eu-west-2.bedrock \
  --vpc-endpoint-type Interface \
  --subnet-ids <SUBNET_ID> \
  --security-group-ids $SG_ID \
  --private-dns-enabled \
  --region eu-west-2
```

**Why the public subnet?** The endpoints attach to the same public subnet as the EC2 instance — acceptable for our single-AZ minimum-footprint design. The `--private-dns-enabled` flag overrides the public DNS name for `bedrock-runtime.eu-west-2.amazonaws.com` so the `boto3` SDK uses the endpoint transparently with no application config changes.

**Cost.** ~$7.30/mo per AZ per endpoint (≈ $0.01/hr per AZ) plus $0.01/GB data processed. With one AZ and two endpoints that's ~$15/mo all-in; data charges are negligible at our throughput (a few GB/mo of LLM token traffic).

**Net effect on the security group.** Outbound 443 to `bedrock-runtime.eu-west-2.amazonaws.com` no longer leaves the VPC — that's the point. Combined with this, the `0.0.0.0/0:443` SG egress rule is still needed for apt, GitHub releases, and the Bedrock public-endpoint fallback path, but **the LLM data path itself is now private**. Document this explicitly when responding to compliance questionnaires: "no LLM request or response leaves the AWS network boundary in normal operation."

**Cross-region inference profile note.** When you invoke via `eu.anthropic.claude-haiku-4-5-20251001-v1:0`, Bedrock fans the actual model invocation out to one of the EU regions (`eu-west-1`, `eu-west-2`, `eu-central-1`, etc.). The fan-out happens *inside* AWS — your traffic from the EC2 still terminates at the `eu-west-2` interface endpoint; Bedrock handles the cross-region hop on its own backbone. You do not need additional interface endpoints in other regions.

Optional hardening for paranoid environments: put a Squid or `nginx` egress proxy on the box and configure the application to use `HTTPS_PROXY=http://127.0.0.1:3128`, with the proxy's domain allowlist set to apt + GitHub + the Bedrock public hostname. This is out of scope for the simple-deployment promise but trivially added later.

---

## 7. DNS & TLS — Route 53, certbot/Let's Encrypt

### 7.1 Domain & A-record

In the existing Route 53 hosted zone for `flowin.example.com`:

```bash
aws route53 change-resource-record-sets \
  --hosted-zone-id <ZONE_ID> \
  --change-batch '{
    "Changes": [{
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "flowin.example.com",
        "Type": "A",
        "TTL": 60,
        "ResourceRecords": [{"Value": "<EIP_ADDRESS>"}]
      }
    }]
  }'
```

A 60-second TTL during go-live; raise to 300 once stable. Adding a `www.` CNAME to the apex is fine; nginx will canonicalise to the apex.

### 7.2 Certificates: Let's Encrypt + certbot

**Why not ACM?** ACM does not issue free public TLS certs to EC2 instances directly — only to ALB / CloudFront / API Gateway. The customer rejects ALB. The honest options are:

- **Let's Encrypt + certbot** (recommended): free, 90-day rotation, automated. The HTTP-01 challenge requires port 80 reachable from the public internet — which we already need for the HTTPS redirect. Renewal runs as a systemd timer (Appendix B).
- **AWS Private CA + ACM** (~$400/month for a CA + cert issuance): only justified if you must have certificates issued by your own CA chain. Massively over-budget for this deployment.
- **Bring-your-own-cert from DigiCert / Sectigo**: fine, but adds a manual rotation chore. Pick this only if the customer has a corporate cert procurement they are committed to.

**Decision: Let's Encrypt + certbot.**

Install (in the bootstrap; see Appendix D):

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx \
  -d flowin.example.com \
  --non-interactive --agree-tos \
  --email security@example.com \
  --redirect --hsts --staple-ocsp
```

`certbot --nginx` will rewrite the nginx config to add the `ssl_certificate` and `ssl_certificate_key` directives and the HTTP→HTTPS redirect block. Verify the resulting nginx config matches Appendix A; if certbot's auto-edit clashes with our config, supply a pre-prepared nginx config first and use `certbot certonly --webroot -w /var/www/letsencrypt -d flowin.example.com` instead.

Certbot also installs `/etc/systemd/system/timers.target.wants/certbot.timer`, which runs twice-daily and renews when <30 days remain. Monitor renewals via CloudWatch alarm on the cert-expiry metric (§10).

### 7.3 TLS hardening posture

In nginx (Appendix A), force these settings:

- `ssl_protocols TLSv1.2 TLSv1.3;` (TLS 1.0/1.1 explicitly disabled)
- `ssl_ciphers HIGH:!aNULL:!MD5:!3DES;` plus a curated `ssl_ciphers` suite for forward secrecy.
- `ssl_prefer_server_ciphers on;`
- `ssl_session_cache shared:SSL:10m;`
- `ssl_session_tickets off;` (forward secrecy with session tickets requires careful key rotation; off is the simpler safe default)
- `add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;`
- `add_header X-Content-Type-Options nosniff always;`
- `add_header X-Frame-Options DENY always;` (Note: PPT and prototype previews use *sandboxed* iframes — see W56/W57 — so `DENY` is correct because the *parent page* shouldn't be framable; the inner iframes still work because they sandbox into themselves, not into a cross-origin parent.)
- `add_header Referrer-Policy strict-origin-when-cross-origin always;`

After deployment, validate against SSL Labs (`https://www.ssllabs.com/ssltest/analyze.html?d=flowin.example.com`). Target **A+**.

---

## 8. The on-host stack

This is the meat of the deployment. Everything below assumes Ubuntu 24.04 LTS and runs as part of the bootstrap (Appendix D), or as the operator's manual `apt install` + `systemctl enable --now`.

### 8.1 Operating system hardening

**Run these before installing anything else.**

#### Patch and update

```bash
sudo apt-get update && sudo apt-get -y full-upgrade
sudo apt-get install -y unattended-upgrades update-notifier-common
sudo dpkg-reconfigure --priority=low unattended-upgrades
```

`unattended-upgrades` is configured (in the bootstrap) to install **security updates automatically every night**, with an explicit reboot window (see §13). This is non-negotiable for a publicly reachable box.

#### Firewall (ufw)

`ufw` is a second layer of defence behind the security group. They are not redundant — the SG protects the network interface; ufw protects against a misconfigured app process binding to a wider interface than intended.

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
```

#### SSH hardening

Edit `/etc/ssh/sshd_config.d/10-flowin.conf`:

```
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
KbdInteractiveAuthentication no
X11Forwarding no
ClientAliveInterval 300
ClientAliveCountMax 2
MaxAuthTries 3
AllowTcpForwarding no
AllowAgentForwarding no
PermitTunnel no
LoginGraceTime 30
AllowGroups flowin-admin
```

Restart sshd. Add the operator's public key to `/home/<operator>/.ssh/authorized_keys`. Operators sit in the `flowin-admin` group; the application user (`flowin`, §8.5) is *not* in the group and *cannot* SSH in.

#### Even better: SSM Session Manager

Install the SSM Agent (already preinstalled on the official Ubuntu AMI). Confirm:

```bash
sudo systemctl status snap.amazon-ssm-agent.amazon-ssm-agent.service
```

To attach a session from a developer's laptop, the developer needs an IAM principal with `ssm:StartSession` on the instance, plus the AWS CLI `session-manager-plugin`:

```bash
aws ssm start-session --target $INSTANCE_ID --region eu-west-2
```

SSM sessions are logged to CloudWatch Logs / S3 and audited via CloudTrail. **Prefer SSM over SSH for day-to-day operations.** Reserve direct SSH for the genuine emergency where SSM is broken.

To enforce: add the IAM policy `AmazonSSMManagedInstanceCore` to the instance role *only after* you have validated SSM works (it's not in §5.3 because the customer wanted minimum permissions and SSM is optional). If you adopt it, append the AWS-managed policy to the instance profile.

#### Auditd

```bash
sudo apt-get install -y auditd audispd-plugins
```

Default ruleset is fine for a small box; the meaningful events (sudo, sshd, file changes in /etc) are captured out of the box. The CloudWatch agent will ship `/var/log/audit/audit.log` (§10).

#### Fail2ban

```bash
sudo apt-get install -y fail2ban
```

Default config protects sshd and nginx. The default `bantime = 10m` is fine; enforce `findtime = 10m` and `maxretry = 5` (these are defaults). Confirm the jail status with `sudo fail2ban-client status`.

#### Time

```bash
sudo timedatectl set-timezone UTC
sudo systemctl enable --now systemd-timesyncd
```

UTC, NTP via the AWS time pool. Timestamp drift breaks JWT validation; this matters.

### 8.2 nginx (reverse proxy + TLS + WebSocket upgrade)

#### Install

```bash
sudo apt-get install -y nginx
sudo systemctl enable nginx
```

#### Site config

The full `/etc/nginx/sites-available/flowin` lives in **Appendix A**. Highlights:

- **Backend HTTP routes (`/api/*`, `/health`, `/openapi.json`, `/docs`):** proxied to `127.0.0.1:8000`. `proxy_buffering off;` is critical because the backend streams JSON tokens back from LLM calls — buffering would hold them up and break the chat-typing illusion (W44, B5).
- **WebSocket route (`/ws/chat`):** proxied to `127.0.0.1:8000` with the WS upgrade headers. `proxy_read_timeout 5400s;` and `proxy_send_timeout 5400s;` give a 90-minute idle window — see W21/W33/B5: prototype/PPT pipelines can stream tokens for tens of minutes; we want to be safely above the worst observed long-tail. *Don't* set this to "infinity"; idle WS connections must be reaped.
- **Frontend (`/`):** proxied to `127.0.0.1:3000` (Next.js prod server). `proxy_pass http://127.0.0.1:3000;` with the standard `Host`/`X-Forwarded-*` headers.
- **Access log:** custom log_format `flowin` that **omits the `args` (query string)** to mitigate Blocker 5 token leakage. See Appendix A — the `log_format flowin` block uses `$uri` instead of `$request`.
- **Rate limits:** `limit_req_zone` for `/api/auth/login` (10/min per IP), `/api/auth/register` (5/min), `/api/auth/change-password` (10/min). nginx-level rate limiting is a defence-in-depth on top of the application-level rate limit (Blocker-Recommended item 7).
- **Security headers:** see §7.3.
- **Body size:** `client_max_body_size 1m;` — Flowin doesn't accept file uploads (W22 "open issue"); 1 MB is plenty for JSON request bodies and prevents a trivial memory-exhaustion attack.
- **Hide nginx version:** `server_tokens off;`.

Enable:

```bash
sudo ln -s /etc/nginx/sites-available/flowin /etc/nginx/sites-enabled/flowin
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

### 8.3 systemd units for backend (uvicorn) and frontend (next start)

Two units, both running as the unprivileged `flowin` user. Full files in **Appendix B**. Key properties:

- `User=flowin`, `Group=flowin`. No root.
- `WorkingDirectory=/opt/flowin/backend` (or `/frontend`).
- `EnvironmentFile=/etc/flowin/environment.d/flowin.env` — populated from Parameter Store on every start by `ExecStartPre=/usr/local/bin/flowin-load-secrets`. Secrets never sit on disk in plaintext outside this 0640 file owned by root:flowin (see §9 for why this is acceptable, plus an even stricter alternative).
- `Restart=always`, `RestartSec=5s`. Crash → restart.
- `LimitNOFILE=65535` for the backend. WebSocket fan-out can otherwise hit the default 1024 ulimit.
- `PrivateTmp=yes`, `ProtectSystem=strict`, `ProtectHome=yes`, `NoNewPrivileges=yes`, `RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX`, `CapabilityBoundingSet=` (empty). Standard systemd hardening.
- `ReadWritePaths=/opt/flowin/backend/skills /var/log/flowin` — explicit allowlist of writable paths.

**Backend** (`flowin-backend.service`): runs `uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 4 --proxy-headers --forwarded-allow-ips=127.0.0.1`. Four workers gives ~4× the WS throughput on `m6i.xlarge` (4 vCPU). `--proxy-headers` makes uvicorn trust nginx's `X-Forwarded-*`. `--forwarded-allow-ips=127.0.0.1` means nginx is the *only* trusted source of those headers — you don't get IP spoofing from a misconfigured ingress.

**Frontend** (`flowin-frontend.service`): runs `node /opt/flowin/frontend/.next/standalone/server.js`. Built ahead of time with `next build` and `NEXT_PUBLIC_API_URL=https://flowin.example.com` and `NEXT_PUBLIC_WS_URL=wss://flowin.example.com/ws/chat` baked in.

**Crucial detail about `NEXT_PUBLIC_*`:** these vars are **inlined at build time** in Next.js. You cannot change them via the systemd unit's environment. Set them at the GitLab CI build step (§12) or at the bootstrap-time `npm run build` step, not afterwards.

Enable:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now flowin-backend.service flowin-frontend.service
```

### 8.4 PostgreSQL on the same instance

#### Install

```bash
sudo apt-get install -y postgresql-16 postgresql-contrib-16
```

Ubuntu 24.04 ships Postgres 16 in the default repo.

#### Move the data dir to the encrypted volume

```bash
# Mount the second EBS volume at /var/lib/postgresql
sudo mkfs.xfs /dev/nvme1n1
sudo mkdir -p /var/lib/postgresql
sudo mount /dev/nvme1n1 /var/lib/postgresql

# Persist across reboots (use blkid for UUID)
echo "UUID=$(sudo blkid -s UUID -o value /dev/nvme1n1) /var/lib/postgresql xfs defaults,nofail 0 2" | sudo tee -a /etc/fstab

# Initialize a fresh cluster on the encrypted volume
sudo systemctl stop postgresql@16-main
sudo rm -rf /var/lib/postgresql/16
sudo -u postgres /usr/lib/postgresql/16/bin/initdb -D /var/lib/postgresql/16/main --auth=scram-sha-256 --pwprompt=false
```

(If using the bootstrap script — see Appendix D — this is automated.)

#### Configuration

`/etc/postgresql/16/main/postgresql.conf` overrides:

```
listen_addresses = '127.0.0.1'      # NEVER 0.0.0.0 or *. Bound to loopback only.
port = 5432
max_connections = 100               # 4 uvicorn workers × ~10 conns + headroom
shared_buffers = 4GB                # ~25% of 16GB RAM
effective_cache_size = 10GB         # what the OS will cache for us
work_mem = 32MB                     # per sort/join
maintenance_work_mem = 512MB        # for VACUUM
wal_level = replica                 # adequate for pg_basebackup-style restore
checkpoint_completion_target = 0.9
random_page_cost = 1.1              # gp3 is SSD
effective_io_concurrency = 200
log_min_duration_statement = 1000   # slow query log >= 1s
log_line_prefix = '%t [%p] %u@%d '
log_destination = 'stderr'
log_checkpoints = on
log_lock_waits = on
log_connections = off               # too noisy
log_disconnections = off
ssl = off                           # we are on loopback only
```

`/etc/postgresql/16/main/pg_hba.conf`:

```
local   all   postgres                peer
local   all   all                     scram-sha-256
host    all   all      127.0.0.1/32   scram-sha-256
host    all   all      ::1/128        scram-sha-256
# everything else: implicit reject
```

#### Application user and database

```bash
sudo -u postgres psql <<'SQL'
CREATE USER flowin WITH ENCRYPTED PASSWORD :'pw';
CREATE DATABASE flowin OWNER flowin;
\c flowin
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT ALL ON SCHEMA public TO flowin;
SQL
```

The `:'pw'` is parameter-substituted from a one-off generated password (`openssl rand -hex 32`). Stored in Parameter Store at `/flowin/prod/DATABASE_PASSWORD` (§9).

`DATABASE_URL` in the application env becomes:

```
postgresql+psycopg2://flowin:<password>@127.0.0.1:5432/flowin
```

#### Memory protection

Postgres co-resident with the application means an OOM-kill of postmaster takes the whole product down. Add a swap file (do not skip this):

```bash
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
sudo sysctl -w vm.swappiness=10
echo 'vm.swappiness = 10' | sudo tee /etc/sysctl.d/99-flowin.conf
```

And give Postgres priority over the OOM killer:

```bash
sudo systemctl edit postgresql@16-main.service
```

Add:

```
[Service]
OOMScoreAdjust=-900
```

This makes the kernel pick a uvicorn worker before postmaster when memory runs out.

#### Schema bootstrap

The application uses SQLAlchemy `Base.metadata.create_all` at startup (`main.py:70`). This is fine for the first deploy (idempotent CREATE IF NOT EXISTS). For long-term schema management, **add Alembic** — but that's a code change, not a deployment-guide change.

### 8.5 Application user & file permissions

Create the user **before** anything else:

```bash
sudo useradd -r -m -d /opt/flowin -s /usr/sbin/nologin flowin
```

Repository checkout:

```bash
sudo -u flowin git clone https://gitlab.com/hexaware-uki/flowin.git /opt/flowin/src
sudo -u flowin ln -s /opt/flowin/src/backend /opt/flowin/backend
sudo -u flowin ln -s /opt/flowin/src/frontend /opt/flowin/frontend
```

Python venv for the backend:

```bash
sudo apt-get install -y python3.12-venv
sudo -u flowin python3.12 -m venv /opt/flowin/venv
sudo -u flowin /opt/flowin/venv/bin/pip install -U pip
sudo -u flowin /opt/flowin/venv/bin/pip install -r /opt/flowin/backend/requirements.txt
sudo -u flowin /opt/flowin/venv/bin/pip install psycopg2-binary
```

(`psycopg2-binary` isn't pinned in `requirements.txt` today — `requirements.txt` lines 1–14 — but it is required for Postgres. Document that.)

Frontend build:

```bash
# Install Node 20 (LTS) via NodeSource. The official Ubuntu apt repos are too old.
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Build with the production env vars baked in
sudo -u flowin bash -c '
  cd /opt/flowin/frontend &&
  NEXT_PUBLIC_API_URL=https://flowin.example.com \
  NEXT_PUBLIC_WS_URL=wss://flowin.example.com/ws/chat \
  npm ci &&
  npm run build
'
```

For Next.js standalone output, add `output: "standalone"` to `frontend/next.config.ts`:

```ts
const nextConfig: NextConfig = {
  devIndicators: false,
  output: "standalone",
};
```

This is a one-line code change; ship it as part of pre-launch.

Permissions:

```
/opt/flowin                       drwxr-xr-x flowin:flowin
/opt/flowin/src                   drwxr-xr-x flowin:flowin
/opt/flowin/venv                  drwxr-xr-x flowin:flowin
/etc/flowin/environment.d         drwxr-x--- root:flowin
/etc/flowin/environment.d/*.env   -rw-r----- root:flowin (mode 0640)
/var/log/flowin                   drwxrwxr-x flowin:flowin
```

The 0640 on the env file is critical: world-readable env files are the #1 reason production secrets leak from EC2 instances.

---

## 9. Secrets management (Parameter Store)

### 9.1 Why Parameter Store, not Secrets Manager

| Capability | Parameter Store SecureString | Secrets Manager |
|---|---|---|
| Encryption at rest | Yes, KMS | Yes, KMS |
| IAM-gated | Yes | Yes |
| Versioning | Yes | Yes |
| Automatic rotation | No (Lambda-driven if you write it) | Yes (built-in for RDS, others) |
| Cost | Free for standard tier (under 4 KB), $0.05/secret/mo for advanced | $0.40/secret/mo + $0.05 per 10K API calls |
| Best for | Static-ish app secrets | Frequently-rotated DB credentials, cross-account secret sharing |

We have ~10 secrets, none of them rotated automatically (the customer is fine doing manual rotations during a maintenance window). Parameter Store is the right tool. Saving ~$4/month is not the point; **fewer paid services = simpler IAM = easier audit**.

### 9.2 The secret list (Appendix C is the canonical reference)

Stored under the prefix `/flowin/prod/`, all as `SecureString` with the customer-managed KMS key created in §5.4:

```bash
aws ssm put-parameter \
  --region eu-west-2 \
  --name /flowin/prod/SECRET_KEY \
  --type SecureString \
  --value "$(openssl rand -hex 64)" \
  --key-id alias/flowin-prod-data \
  --overwrite

# DATABASE_PASSWORD only — the on-host loader composes DATABASE_URL from this
# value (postgresql://flowin:<pw>@127.0.0.1:5432/flowin). Terraform doesn't
# write DATABASE_URL because it doesn't know about the on-host Postgres.
aws ssm put-parameter \
  --region eu-west-2 \
  --name /flowin/prod/DATABASE_PASSWORD \
  --type SecureString \
  --value "<openssl rand -hex 32 output>" \
  --key-id alias/flowin-prod-data \
  --overwrite

aws ssm put-parameter \
  --region eu-west-2 \
  --name /flowin/prod/CORS_ORIGINS \
  --type String \
  --value '["https://flowin.example.com"]' \
  --overwrite

aws ssm put-parameter \
  --region eu-west-2 \
  --name /flowin/prod/ACCESS_TOKEN_EXPIRE_HOURS \
  --type String \
  --value "12" \
  --overwrite

# LLM provider config — selects Bedrock and pins the model. Stored as plain
# String (not secret), but kept in Parameter Store so all runtime config lives
# in one place and a model swap doesn't require a redeploy.
aws ssm put-parameter \
  --region eu-west-2 \
  --name /flowin/prod/llm/provider \
  --type String \
  --value "bedrock" \
  --overwrite

aws ssm put-parameter \
  --region eu-west-2 \
  --name /flowin/prod/llm/region \
  --type String \
  --value "eu-west-2" \
  --overwrite

aws ssm put-parameter \
  --region eu-west-2 \
  --name /flowin/prod/llm/model_id \
  --type String \
  --value "eu.anthropic.claude-haiku-4-5-20251001-v1:0" \
  --overwrite
```

**Note:** there is no required `/flowin/prod/ANTHROPIC_API_KEY` in normal operation — auth to Bedrock is via the EC2 instance-profile role (§5.3). For the optional emergency fallback, see the entry at the end of this section.

(Optional, only if LangSmith is enabled:)

```bash
aws ssm put-parameter --region eu-west-2 --name /flowin/prod/LANGSMITH_API_KEY \
  --type SecureString --value "lsv2_pt_..." --key-id alias/flowin-prod-data --overwrite
```

**Optional emergency-fallback entry** — only populated during a Bedrock outage:

```bash
# Empty placeholder. Populate ONLY during a Bedrock regional outage; flip
# /flowin/prod/llm/provider to "anthropic" and restart the backend. The
# application code reads LLM_PROVIDER and switches between bedrock and
# direct-Anthropic backends.
aws ssm put-parameter \
  --region eu-west-2 \
  --name /flowin/prod/anthropic/api_key \
  --type SecureString \
  --value "" \
  --key-id alias/flowin-prod-data \
  --overwrite
```

### 9.3 The loader script

`/usr/local/bin/flowin-load-secrets`:

```bash
#!/usr/bin/env bash
# Load Flowin secrets from Parameter Store into a 0640 env file consumed by
# systemd EnvironmentFile=. Runs as root before each unit start.
#
# The mapping rule (per-SSM-key, no implicit translation) is:
#
#   /flowin/prod/SECRET_KEY                  → SECRET_KEY=<value>
#   /flowin/prod/CORS_ORIGINS                → CORS_ORIGINS=<value>
#   /flowin/prod/ACCESS_TOKEN_EXPIRE_HOURS   → ACCESS_TOKEN_EXPIRE_HOURS=<value>
#   /flowin/prod/DATABASE_PASSWORD           → DATABASE_URL=postgresql://flowin:${value}@127.0.0.1:5432/flowin
#                                              (composed; loader never emits DATABASE_PASSWORD itself)
#   /flowin/prod/llm/provider                → LLM_PROVIDER=<value>
#   /flowin/prod/llm/region                  → AWS_REGION=<value>
#   /flowin/prod/llm/model_id                → BEDROCK_MODEL_ID=<value>
#   /flowin/prod/anthropic/api_key           → ANTHROPIC_API_KEY=<value>
#   /flowin/prod/LANGSMITH_*                 → LANGSMITH_*=<value>  (passthrough)
#   anything else                            → logged as a warning, ignored
#
# No fallback defaults: if /flowin/prod/llm/* is missing the loader writes
# nothing for those keys and Settings boots with its codebase default. ENV is
# set by the systemd unit (Environment=ENV=production), not by this loader.
set -euo pipefail

OUT=/etc/flowin/environment.d/flowin.env
TMP=$(mktemp /etc/flowin/environment.d/flowin.env.XXXXXX)
chmod 0640 "$TMP"
chown root:flowin "$TMP"

REGION=eu-west-2
PREFIX=/flowin/prod

emit() {
    # Escape any quotes/dollars in the value via printf %q.
    printf '%s=%q\n' "$1" "$2" >> "$TMP"
}

while IFS=$'\t' read -r name value; do
    rel="${name#${PREFIX}/}"
    case "$rel" in
        SECRET_KEY|CORS_ORIGINS|ACCESS_TOKEN_EXPIRE_HOURS|LANGSMITH_TRACING|LANGSMITH_API_KEY|LANGSMITH_PROJECT)
            emit "$rel" "$value" ;;
        DATABASE_PASSWORD)
            emit DATABASE_URL "postgresql://flowin:${value}@127.0.0.1:5432/flowin" ;;
        llm/provider)      emit LLM_PROVIDER     "$value" ;;
        llm/region)        emit AWS_REGION       "$value" ;;
        llm/model_id)      emit BEDROCK_MODEL_ID "$value" ;;
        anthropic/api_key) emit ANTHROPIC_API_KEY "$value" ;;
        *)
            echo "[flowin-load-secrets] WARN: ignoring unknown parameter ${name}" >&2 ;;
    esac
done < <(aws ssm get-parameters-by-path \
            --path "$PREFIX" \
            --recursive \
            --with-decryption \
            --region "$REGION" \
            --query 'Parameters[].[Name,Value]' \
            --output text)

mv "$TMP" "$OUT"
chmod 0640 "$OUT"
chown root:flowin "$OUT"
```

The `flowin` user has read access to the env file (group-read), but not write. The application reads `os.environ` at boot.

### 9.4 An even-stricter alternative (optional)

The pattern above writes secrets to disk in a 0640 root:flowin file. A stricter alternative is to *not* write them to disk and instead inject them via systemd's `LoadCredential=`, which puts them in a tmpfs only the unit can read. This is fiddlier (you need a oneshot service to fetch and a `LoadCredential=` per secret) and gains you protection only against an attacker with non-root file read on the box. For the simple-deployment promise, the 0640 env file is the right balance. If the threat model is "an attacker has temporarily achieved a non-flowin, non-root read primitive", revisit.

### 9.5 Rotation

Secrets rotate on a calendar:

| Secret | Rotation cadence | Procedure |
|---|---|---|
| `SECRET_KEY` | Yearly + on suspected compromise | `ssm put-parameter --overwrite`, restart backend. **All users will be logged out.** Schedule in maintenance window. |
| Bedrock IAM credentials | N/A — handled by AWS | The instance-profile role uses STS-rotated short-lived credentials. There is no static API key to rotate. If the *role* is compromised, re-issue the role; the running instance picks up new credentials at the next IMDS refresh. |
| `DATABASE_PASSWORD` | Yearly + on suspected compromise | `ALTER USER flowin WITH PASSWORD '<new>'`, `ssm put-parameter --overwrite` for both `DATABASE_PASSWORD` and `DATABASE_URL`, restart backend. |
| `/flowin/prod/anthropic/api_key` (fallback only) | Only when populated for an outage; rotate immediately after the incident | Issue new key in Anthropic console, `ssm put-parameter --overwrite`, restart backend, then **clear the parameter** when Bedrock is restored to keep the empty-by-default invariant. |
| TLS cert | 60-day automated by certbot | No action. |

Document each rotation in the runbook (§13) with a CloudTrail-verifiable timestamp.

---

## 10. Logging & monitoring (CloudWatch agent + alarms)

### 10.1 Install the CloudWatch Agent

```bash
wget https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
sudo dpkg -i amazon-cloudwatch-agent.deb
```

Drop the config at `/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json`:

```json
{
  "agent": {
    "metrics_collection_interval": 60,
    "logfile": "/var/log/amazon-cloudwatch-agent.log",
    "run_as_user": "cwagent"
  },
  "metrics": {
    "namespace": "Flowin/Prod",
    "metrics_collected": {
      "cpu":    {"measurement": ["cpu_usage_idle","cpu_usage_iowait","cpu_usage_user","cpu_usage_system"], "totalcpu": true, "metrics_collection_interval": 60},
      "mem":    {"measurement": ["mem_used_percent","mem_available"], "metrics_collection_interval": 60},
      "disk":   {"measurement": ["used_percent"], "resources": ["/", "/var/lib/postgresql"], "metrics_collection_interval": 60},
      "diskio": {"measurement": ["io_time","write_bytes","read_bytes"], "resources": ["*"], "metrics_collection_interval": 60},
      "swap":   {"measurement": ["swap_used_percent"], "metrics_collection_interval": 60},
      "net":    {"measurement": ["bytes_sent","bytes_recv","drop_in","drop_out"], "resources": ["*"], "metrics_collection_interval": 60}
    },
    "append_dimensions": {
      "InstanceId":     "${aws:InstanceId}",
      "InstanceType":   "${aws:InstanceType}",
      "AutoScalingGroupName": "${aws:AutoScalingGroupName}"
    }
  },
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {"file_path": "/var/log/nginx/access.log",    "log_group_name": "/flowin/prod/nginx-access",    "log_stream_name": "{instance_id}", "timezone": "UTC"},
          {"file_path": "/var/log/nginx/error.log",     "log_group_name": "/flowin/prod/nginx-error",     "log_stream_name": "{instance_id}", "timezone": "UTC"},
          {"file_path": "/var/log/postgresql/postgresql-16-main.log", "log_group_name": "/flowin/prod/postgres", "log_stream_name": "{instance_id}", "timezone": "UTC"},
          {"file_path": "/var/log/audit/audit.log",     "log_group_name": "/flowin/prod/system",          "log_stream_name": "{instance_id}", "timezone": "UTC"},
          {"file_path": "/var/log/auth.log",            "log_group_name": "/flowin/prod/auth",            "log_stream_name": "{instance_id}", "timezone": "UTC"},
          {"file_path": "/var/log/unattended-upgrades/unattended-upgrades.log", "log_group_name": "/flowin/prod/system", "log_stream_name": "{instance_id}", "timezone": "UTC"}
        ]
      }
    }
  }
}
```

Application logs go via journald (uvicorn and `next` write to stdout, which systemd captures). The CloudWatch agent does not natively tail journald, so we use the `journald` driver via:

```json
"journald": {
  "log_group_name": "/flowin/prod/app",
  "log_stream_name": "{instance_id}",
  "filters": [
    {"type": "include", "expression": "_SYSTEMD_UNIT=flowin-backend.service"},
    {"type": "include", "expression": "_SYSTEMD_UNIT=flowin-frontend.service"}
  ]
}
```

(Add this under `logs.logs_collected.journald` in the same config.)

Apply:

```bash
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config -m ec2 -s -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
sudo systemctl enable --now amazon-cloudwatch-agent
```

### 10.2 Log retention

Set a sane retention on every log group. The default is "Never expire", which is bad for cost and for GDPR posture:

```bash
# Terraform's monitoring module already sets retention on the six groups it
# creates (nginx-access, nginx-error, app, postgres, system, auth). The loop
# below is the equivalent CLI form for ad-hoc verification.
for lg in /flowin/prod/nginx-access /flowin/prod/nginx-error \
          /flowin/prod/app /flowin/prod/postgres \
          /flowin/prod/system /flowin/prod/auth; do
  aws logs put-retention-policy --region eu-west-2 \
    --log-group-name "$lg" --retention-in-days 90
done
```

90 days strikes a balance between forensic value and cost. nginx-access is the largest by volume (~$3/month at 100 req/sec); the others are cheap.

### 10.3 Alarms

Eleven alarms in total — eight infra alarms below (1–8) and three Bedrock-specific alarms in §10.4 (9–11). Each fires to an SNS topic (`flowin-prod-alerts`) which fans out to PagerDuty / Slack / email per the on-call setup.

```bash
# 1. CPU pegged (sustained throttle)
aws cloudwatch put-metric-alarm --region eu-west-2 \
  --alarm-name flowin-prod-cpu-high \
  --metric-name cpu_usage_idle --namespace Flowin/Prod \
  --statistic Average --period 300 --evaluation-periods 3 \
  --threshold 20 --comparison-operator LessThanThreshold \
  --alarm-actions <SNS_TOPIC_ARN> \
  --dimensions Name=InstanceId,Value=$INSTANCE_ID

# 2. Memory pressure
aws cloudwatch put-metric-alarm --region eu-west-2 \
  --alarm-name flowin-prod-mem-high \
  --metric-name mem_used_percent --namespace Flowin/Prod \
  --statistic Average --period 300 --evaluation-periods 2 \
  --threshold 85 --comparison-operator GreaterThanThreshold \
  --alarm-actions <SNS_TOPIC_ARN> \
  --dimensions Name=InstanceId,Value=$INSTANCE_ID

# 3. Root disk near full
aws cloudwatch put-metric-alarm --region eu-west-2 \
  --alarm-name flowin-prod-disk-root-high \
  --metric-name used_percent --namespace Flowin/Prod \
  --statistic Maximum --period 300 --evaluation-periods 2 \
  --threshold 80 --comparison-operator GreaterThanThreshold \
  --alarm-actions <SNS_TOPIC_ARN> \
  --dimensions Name=InstanceId,Value=$INSTANCE_ID Name=path,Value=/

# 4. Postgres data disk near full (this is the dangerous one)
aws cloudwatch put-metric-alarm --region eu-west-2 \
  --alarm-name flowin-prod-disk-pgdata-high \
  --metric-name used_percent --namespace Flowin/Prod \
  --statistic Maximum --period 300 --evaluation-periods 2 \
  --threshold 75 --comparison-operator GreaterThanThreshold \
  --alarm-actions <SNS_TOPIC_ARN> \
  --dimensions Name=InstanceId,Value=$INSTANCE_ID Name=path,Value=/var/lib/postgresql

# 5. nginx 5xx surge — derived metric from a log filter
aws logs put-metric-filter --region eu-west-2 \
  --log-group-name /flowin/prod/nginx-access \
  --filter-name "5xx-responses" \
  --filter-pattern '[ip, id, user, ts, request, status_code=5*, ...]' \
  --metric-transformations 'metricName=Nginx5xx,metricNamespace=Flowin/Prod,metricValue=1'
aws cloudwatch put-metric-alarm --region eu-west-2 \
  --alarm-name flowin-prod-nginx-5xx-spike \
  --metric-name Nginx5xx --namespace Flowin/Prod \
  --statistic Sum --period 60 --evaluation-periods 5 \
  --threshold 10 --comparison-operator GreaterThanThreshold \
  --alarm-actions <SNS_TOPIC_ARN>
# 10 5xx in any 1-minute window for 5 minutes is an outage signal.

# 6. WebSocket disconnect spike — derived from journald app logs
aws logs put-metric-filter --region eu-west-2 \
  --log-group-name /flowin/prod/app \
  --filter-name "ws-disconnects" \
  --filter-pattern 'WebSocketDisconnect' \
  --metric-transformations 'metricName=WSDisconnects,metricNamespace=Flowin/Prod,metricValue=1'
aws cloudwatch put-metric-alarm --region eu-west-2 \
  --alarm-name flowin-prod-ws-disconnect-spike \
  --metric-name WSDisconnects --namespace Flowin/Prod \
  --statistic Sum --period 60 --evaluation-periods 3 \
  --threshold 30 --comparison-operator GreaterThanThreshold \
  --alarm-actions <SNS_TOPIC_ARN>

# 7. Postgres down / connection failures
aws logs put-metric-filter --region eu-west-2 \
  --log-group-name /flowin/prod/app \
  --filter-name "db-connection-error" \
  --filter-pattern 'OperationalError ?could not connect' \
  --metric-transformations 'metricName=DBConnError,metricNamespace=Flowin/Prod,metricValue=1'
aws cloudwatch put-metric-alarm --region eu-west-2 \
  --alarm-name flowin-prod-db-conn-error \
  --metric-name DBConnError --namespace Flowin/Prod \
  --statistic Sum --period 60 --evaluation-periods 1 \
  --threshold 1 --comparison-operator GreaterThanOrEqualToThreshold \
  --alarm-actions <SNS_TOPIC_ARN>

# 8. AWS Billing alarm — Bedrock token spend can run away if Blocker 3 (cancel) bites
# Set in us-east-1 because billing metrics are emitted only there.
aws cloudwatch put-metric-alarm --region us-east-1 \
  --alarm-name flowin-prod-billing-monthly \
  --metric-name EstimatedCharges --namespace AWS/Billing \
  --statistic Maximum --period 21600 --evaluation-periods 1 \
  --threshold 500 --comparison-operator GreaterThanThreshold \
  --dimensions Name=Currency,Value=USD \
  --alarm-actions <SNS_TOPIC_ARN>
# $500/month threshold; tune to your committed budget.
# Note: this alarm now covers Bedrock spend implicitly because Bedrock is on
# the AWS bill. The application-level token-budget cap (Pre-launch recommended
# item 8) and the Bedrock-specific alarms in §10.4 are the per-event guardrails;
# this billing alarm is the daily/monthly aggregate guardrail.
```

### 10.4 Bedrock metrics & alarms

Bedrock emits CloudWatch metrics in the `AWS/Bedrock` namespace, dimensioned by `ModelId`. The metrics we care about per model:

| Metric | What it tells you |
|---|---|
| `Invocations` | Request volume — sanity check that traffic is reaching Bedrock at all. |
| `InvocationLatency` | End-to-end latency. Useful for tracking slow degradation, not for paging. |
| `InvocationClientErrors` | 4xx-class errors — auth failures, malformed requests, validation errors. Indicates a code or config bug, not a Bedrock outage. |
| `InvocationServerErrors` | 5xx-class errors — Bedrock-side faults. Page on these. |
| `InvocationThrottles` | Quota exhaustion. Page on these (default tier is conservative; see §0.1 trade-off (c)). |
| `InputTokenCount` / `OutputTokenCount` | Volumes for cost monitoring — covers the same risk the old "Anthropic billing alarm" was meant to catch. |

Three alarms wired to the same SNS topic:

```bash
# 9. Bedrock throttles — quota exhaustion, page on-call
aws cloudwatch put-metric-alarm --region eu-west-2 \
  --alarm-name flowin-prod-bedrock-throttles \
  --metric-name InvocationThrottles --namespace AWS/Bedrock \
  --statistic Sum --period 300 --evaluation-periods 1 \
  --threshold 0 --comparison-operator GreaterThanThreshold \
  --dimensions Name=ModelId,Value=eu.anthropic.claude-haiku-4-5-20251001-v1:0 \
  --alarm-actions <SNS_TOPIC_ARN>
# Any throttle in any 5-minute window is a quota signal — request an increase.

# 10. Bedrock server errors — Bedrock-side outage indicator
aws cloudwatch put-metric-alarm --region eu-west-2 \
  --alarm-name flowin-prod-bedrock-5xx \
  --metric-name InvocationServerErrors --namespace AWS/Bedrock \
  --statistic Sum --period 300 --evaluation-periods 1 \
  --threshold 5 --comparison-operator GreaterThanThreshold \
  --dimensions Name=ModelId,Value=eu.anthropic.claude-haiku-4-5-20251001-v1:0 \
  --alarm-actions <SNS_TOPIC_ARN>
# >5 5xx in 5 minutes — likely a Bedrock regional fault. Consider flipping to
# the optional Anthropic-direct fallback (see §0.1, §9).

# 11. Bedrock input-token daily total — cost runaway detector
aws cloudwatch put-metric-alarm --region eu-west-2 \
  --alarm-name flowin-prod-bedrock-tokens-daily \
  --metric-name InputTokenCount --namespace AWS/Bedrock \
  --statistic Sum --period 86400 --evaluation-periods 1 \
  --threshold 50000000 --comparison-operator GreaterThanThreshold \
  --dimensions Name=ModelId,Value=eu.anthropic.claude-haiku-4-5-20251001-v1:0 \
  --alarm-actions <SNS_TOPIC_ARN>
# Set the threshold conservatively — start at one or two times your expected
# typical-day input-token volume and tighten after a week of baseline data.
# This covers the same intent as the old "Anthropic billing alarm".
```

The CloudWatch billing alarm in §10.3 item 8 still applies and now covers Bedrock spend implicitly because Bedrock is on the AWS bill.

### 10.5 Health endpoint and external uptime check

The app already exposes `/health` (`main.py:102-109`). Hit it from outside AWS so a CloudWatch outage doesn't blind your monitoring:

- Set up a free **AWS Route 53 Health Check** against `https://flowin.example.com/health`. ($0.50/check/month). Wire it into the same SNS topic.
- Or use a third-party (BetterStack, Pingdom, UptimeRobot). The brief said "no shortcuts on safety" — having an out-of-band heartbeat is part of safety.

---

## 11. Backups & disaster recovery

### 11.1 What we are protecting

- The Postgres data dir (`/var/lib/postgresql`) — user accounts, chats, workflow runs, agent_outputs JSON.
- The skills directory (`/opt/flowin/src/backend/skills`) — small, but custom user content.
- The TLS cert + key (`/etc/letsencrypt`) — annoying to lose but recreatable in 5 min.

The OS root volume contains nothing irreplaceable; the bootstrap script can recreate it.

### 11.2 Two backup paths (belt and braces)

#### Path A — EBS snapshot of the data volume (AWS Backup)

```bash
aws backup create-backup-vault \
  --backup-vault-name flowin-prod-vault \
  --encryption-key-arn alias/flowin-prod-data \
  --region eu-west-2

aws backup create-backup-plan \
  --region eu-west-2 \
  --backup-plan '{
    "BackupPlanName": "flowin-prod-daily",
    "Rules": [{
      "RuleName": "DailyAt03UTC",
      "TargetBackupVaultName": "flowin-prod-vault",
      "ScheduleExpression": "cron(0 3 ? * * *)",
      "StartWindowMinutes": 60,
      "CompletionWindowMinutes": 180,
      "Lifecycle": {
        "MoveToColdStorageAfterDays": 30,
        "DeleteAfterDays": 365
      }
    }]
  }'
```

Apply via a resource selection that targets EBS volumes tagged `Backup=true` (tag the data volume).

- **RPO with snapshots alone:** ~24 hours.
- **RTO from snapshot:** ~10 min to create a volume from the snapshot; ~5 min to attach it to a fresh instance and start Postgres.

EBS snapshots are *crash-consistent*, not *application-consistent*. For Postgres this is acceptable because Postgres recovers from a crash-consistent state via WAL replay — it boots, replays WAL, comes up clean. We are not adding pre-/post-snapshot scripts because the complexity isn't worth it.

#### Path B — `pg_dump` to S3 hourly (logical backup)

For point-in-time-ish recovery and for portability (you can restore a `pg_dump` to a totally different Postgres host), run a logical backup hourly.

`/etc/systemd/system/flowin-pg-dump.service`:

```
[Unit]
Description=Flowin PG dump to S3
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=postgres
Group=postgres
# bootstrap.env carries FLOWIN_BACKUP_BUCKET and FLOWIN_KMS_KEY_ID (Terraform
# injects these via user_data_extra_env in module.compute). flowin.env carries
# the application secrets; pg_dump doesn't need them but loading both is fine.
EnvironmentFile=/etc/flowin/bootstrap.env
EnvironmentFile=/etc/flowin/environment.d/flowin.env
ExecStart=/usr/local/bin/flowin-pg-dump
```

`/etc/systemd/system/flowin-pg-dump.timer`:

```
[Unit]
Description=Hourly Flowin PG dump

[Timer]
OnCalendar=hourly
Persistent=true
RandomizedDelaySec=120

[Install]
WantedBy=timers.target
```

`/usr/local/bin/flowin-pg-dump`:

```bash
#!/usr/bin/env bash
set -euo pipefail

# FLOWIN_BACKUP_BUCKET and FLOWIN_KMS_KEY_ID come from /etc/flowin/bootstrap.env
# (Terraform writes them via module.compute's user_data_extra_env). The bucket
# policy in modules/backups (DenyUnencryptedPuts + DenyWrongKmsKey) requires
# `--sse aws:kms --sse-kms-key-id <project CMK>`; AES256 is rejected.
: "${FLOWIN_BACKUP_BUCKET:?FLOWIN_BACKUP_BUCKET is required}"
: "${FLOWIN_KMS_KEY_ID:?FLOWIN_KMS_KEY_ID is required}"

TS=$(date -u +%Y%m%dT%H%M%SZ)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
DUMP="$TMP/flowin-${TS}.sql.gz"
pg_dump --format=plain --no-owner --no-acl flowin | gzip -9 > "$DUMP"
aws s3 cp "$DUMP" "s3://${FLOWIN_BACKUP_BUCKET}/postgres/${TS}/flowin.sql.gz" \
    --region eu-west-2 \
    --sse aws:kms \
    --sse-kms-key-id "$FLOWIN_KMS_KEY_ID"
echo "pg_dump complete: $(stat -c%s "$DUMP") bytes uploaded to S3"
```

Enable:

```bash
sudo systemctl enable --now flowin-pg-dump.timer
sudo systemctl list-timers flowin-pg-dump.timer
```

The S3 bucket lifecycle handles retention (Terraform configures this in `infra/modules/backups/main.tf`; the snippet below is the equivalent CLI form for ad-hoc verification):

```bash
aws s3api put-bucket-lifecycle-configuration \
  --bucket "${FLOWIN_BACKUP_BUCKET}" \
  --lifecycle-configuration '{
    "Rules": [{
      "ID": "expire-pg-dumps",
      "Status": "Enabled",
      "Prefix": "postgres/",
      "Transitions": [{"Days": 30, "StorageClass": "STANDARD_IA"}, {"Days": 90, "StorageClass": "GLACIER"}],
      "Expiration": {"Days": 365}
    }]
  }'
```

Bucket also needs (all enforced by `infra/modules/backups/`):

- **Versioning enabled** (`aws s3api put-bucket-versioning --versioning-configuration Status=Enabled`).
- **Default SSE-KMS with the project CMK.** The bucket policy denies any PUT whose `x-amz-server-side-encryption` is not `aws:kms` and whose KMS key id is not the project CMK. AES256 will return 403; this is intentional.
- **Block-all-public-access enabled** (`aws s3api put-public-access-block`).
- **Object lock in compliance mode** for the most-recent N hourly dumps if you want true ransomware resistance. Out of scope for this guide; revisit if customer compliance demands it.

- **RPO with hourly dumps:** 1 hour.
- **RTO from `pg_dump`:** 5 min to create a new database, 10–60 min to restore depending on size. At 1500 active users, restoring is sub-10-min.

### 11.3 The disaster recovery drill — fresh box in <30 min

The runbook for "instance died, EIP detached, EBS data volume preserved":

1. **Verify the data volume.** `aws ec2 describe-volumes --filters "Name=tag:Name,Values=flowin-prod-data"` — note the `VolumeId` and the AZ. The volume must be `available`, not `in-use`. If it's `in-use` with a dead instance, force-detach.
2. **Launch a replacement instance** with `aws ec2 run-instances` — same params as §5.5 but **without** the `/dev/sdf` mapping (we'll attach the existing volume next). Use the bootstrap script, `--user-data file://bootstrap.sh`. The bootstrap detects the lack of an existing data volume and *will not* run `mkfs.xfs`; it will just mount whatever's at `/dev/nvme1n1`.
3. **Attach the existing data volume:** `aws ec2 attach-volume --instance-id <NEW> --volume-id <VOL> --device /dev/sdf`.
4. **Re-attach the EIP:** `aws ec2 associate-address --instance-id <NEW> --allocation-id <EIP_ALLOC>`.
5. **Wait for cloud-init.** The bootstrap script:
   - Installs nginx, postgres, node, certbot, cloudwatch agent.
   - Mounts the data volume.
   - Re-clones the repo.
   - Pulls secrets from Parameter Store.
   - Renews the Let's Encrypt cert if it's already in `/etc/letsencrypt/live/` (skip if old cert is fine).
   - Brings up `flowin-backend`, `flowin-frontend`, `nginx`, `postgresql`.
6. **Smoke test:** `curl https://flowin.example.com/health`. Click through `/login`, run a small pipeline.

**Wallclock target: 30 minutes.** Practiced quarterly during a maintenance window. Document the most recent drill date in the runbook.

If the data volume is also lost (region-wide outage, AZ failure), the recovery path is the same as above but step 1 becomes "create a new volume from the latest AWS Backup snapshot" (`aws backup start-restore-job ...`). RTO grows to ~45 min; RPO degrades to last-completed hourly `pg_dump` if the snapshot is older.

### 11.4 What we explicitly do not back up

- Application logs in CloudWatch — they're already durable.
- LLM (Bedrock) responses — re-derivable on demand.
- Skills (small, low-churn) — *do* back up. The systemd unit in Appendix B.5 is the supported path (it sources `/etc/flowin/bootstrap.env` for `FLOWIN_BACKUP_BUCKET` and `FLOWIN_KMS_KEY_ID` and uploads with `--sse aws:kms`). If you prefer cron for any reason, the equivalent line is:
  ```bash
  echo '0 4 * * * flowin . /etc/flowin/bootstrap.env && tar -czf - /opt/flowin/src/backend/skills | aws s3 cp - s3://${FLOWIN_BACKUP_BUCKET}/skills/$(date -u +\%Y\%m\%d).tar.gz --region eu-west-2 --sse aws:kms --sse-kms-key-id $FLOWIN_KMS_KEY_ID' | sudo tee -a /etc/cron.d/flowin-skills-backup
  ```

---

## 12. Deployment / release procedure

### 12.1 Release pipeline (GitLab CI)

The project repo is `gitlab.com/hexaware-uki/flowin` on branch `agent-pipeline-execution`. The release job lives in `.gitlab-ci.yml` (not currently present; ship it as part of this work).

A simple, secure pipeline:

```yaml
stages: [test, build, deploy]

variables:
  AWS_REGION: eu-west-2
  S3_BUCKET: flowin-prod-artifacts
  INSTANCE_TAG: flowin-prod

test-backend:
  stage: test
  image: python:3.12-slim
  script:
    - pip install -r backend/requirements.txt
    - pytest backend/tests/ -v

test-frontend:
  stage: test
  image: node:20
  script:
    - cd frontend && npm ci
    - npm test
    - npm run build

build-artifact:
  stage: build
  image: amazon/aws-cli:latest
  needs: [test-backend, test-frontend]
  only: [main]
  script:
    - apk add --no-cache git tar gzip
    - SHA=$(git rev-parse --short HEAD)
    - tar -czf flowin-${SHA}.tar.gz backend/ frontend/.next/standalone/ frontend/.next/static/ frontend/public/
    - aws s3 cp flowin-${SHA}.tar.gz s3://${S3_BUCKET}/releases/flowin-${SHA}.tar.gz --sse AES256
    - echo "${SHA}" > current-sha.txt
    - aws s3 cp current-sha.txt s3://${S3_BUCKET}/releases/current.txt --sse AES256

deploy:
  stage: deploy
  image: amazon/aws-cli:latest
  needs: [build-artifact]
  only: [main]
  when: manual                      # human approves prod deploy
  script:
    - INSTANCE_ID=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=${INSTANCE_TAG}" "Name=instance-state-name,Values=running" --query 'Reservations[0].Instances[0].InstanceId' --output text)
    - aws ssm send-command \
        --instance-ids ${INSTANCE_ID} \
        --document-name AWS-RunShellScript \
        --parameters 'commands=["sudo /usr/local/bin/flowin-deploy"]' \
        --comment "Deploy ${SHA}"
```

`when: manual` on the deploy stage means a human clicks "Deploy" in the GitLab UI. **Never auto-deploy main to prod on a single-EC2 topology** — there's no canary, no blue-green, no rollback besides re-deploying the previous SHA.

### 12.2 The on-host deploy script

`/usr/local/bin/flowin-deploy`:

```bash
#!/usr/bin/env bash
set -euo pipefail

AWS_REGION=eu-west-2
S3_BUCKET=flowin-prod-artifacts
DEPLOY_DIR=/opt/flowin
RELEASES_DIR=${DEPLOY_DIR}/releases

# Get the SHA the CI just published
SHA=$(aws s3 cp s3://${S3_BUCKET}/releases/current.txt - --region ${AWS_REGION})
RELEASE_DIR=${RELEASES_DIR}/${SHA}

echo "Deploying ${SHA} to ${RELEASE_DIR}"
sudo -u flowin mkdir -p ${RELEASE_DIR}
aws s3 cp s3://${S3_BUCKET}/releases/flowin-${SHA}.tar.gz /tmp/flowin-${SHA}.tar.gz --region ${AWS_REGION}
sudo -u flowin tar -xzf /tmp/flowin-${SHA}.tar.gz -C ${RELEASE_DIR}
rm /tmp/flowin-${SHA}.tar.gz

# Backend deps (incremental: only reinstall if requirements.txt changed)
sudo -u flowin /opt/flowin/venv/bin/pip install -r ${RELEASE_DIR}/backend/requirements.txt
sudo -u flowin /opt/flowin/venv/bin/pip install psycopg2-binary

# Atomic switch
sudo -u flowin ln -sfn ${RELEASE_DIR}/backend ${DEPLOY_DIR}/backend.new
sudo -u flowin ln -sfn ${RELEASE_DIR}/frontend ${DEPLOY_DIR}/frontend.new
sudo -u flowin mv -T ${DEPLOY_DIR}/backend.new ${DEPLOY_DIR}/backend
sudo -u flowin mv -T ${DEPLOY_DIR}/frontend.new ${DEPLOY_DIR}/frontend

# Reload secrets so the env file reflects the latest Parameter Store state
# BEFORE we run alembic — the migration command needs DATABASE_URL.
sudo /usr/local/bin/flowin-load-secrets

# Apply pending schema migrations BEFORE restarting uvicorn. Idempotent: if
# there are no pending migrations alembic logs "no upgrade operations" and
# exits 0. Running it pre-restart (rather than as ExecStartPre alone) means
# the deploy script fails loudly here if a migration breaks, instead of the
# systemd unit looping on Restart=always.
sudo -u flowin bash -c "cd ${DEPLOY_DIR}/backend && \
    set -a && source /etc/flowin/environment.d/flowin.env && set +a && \
    /opt/flowin/venv/bin/alembic upgrade head"

sudo systemctl restart flowin-backend.service
sleep 5
sudo systemctl restart flowin-frontend.service

# Smoke test
sleep 5
curl -fsS http://127.0.0.1:8000/health > /dev/null
echo "Deploy OK"

# Keep last 5 releases for rollback
sudo -u flowin bash -c "ls -1dt ${RELEASES_DIR}/* | tail -n +6 | xargs -r rm -rf"
```

### 12.3 Rollback

`sudo systemctl restart flowin-backend flowin-frontend` after `ln -sfn /opt/flowin/releases/<previous-sha>/backend /opt/flowin/backend && ln -sfn /opt/flowin/releases/<previous-sha>/frontend /opt/flowin/frontend`. ~30 seconds. Acceptable because deployments happen in a maintenance window (§13).

### 12.4 First-time deploy

On a fresh box, the bootstrap script (Appendix D) does a `git clone` + `npm run build` + `pip install` directly, bypassing the S3 artifact path. This means the first deploy of a *new* box uses the latest `main` rather than a pinned SHA — acceptable for a recovery scenario; not acceptable for steady-state. Steady-state always uses the artifact pipeline above.

---

## 13. Patching, maintenance windows, on-call runbook

### 13.1 OS patching

`unattended-upgrades` config (`/etc/apt/apt.conf.d/50unattended-upgrades`):

- **Apply security updates daily at 06:00 UTC** (off-peak for UK/EU users).
- **Reboot if required** at 04:00 UTC on Sunday (`Unattended-Upgrade::Automatic-Reboot-Time "04:00";`, `Unattended-Upgrade::Automatic-Reboot "true";`).
- **Notify** via `Unattended-Upgrade::Mail "ops@example.com";`.

The Sunday-04:00 reboot is the official maintenance window. **All planned changes happen in this window.** Customers see this in the SLA. Skipping patches because "the box can't reboot" is how prod boxes end up with unpatched RCEs.

### 13.2 Application patching

Application releases follow §12. Patch releases (security-only) jump the manual-approval gate by tagging the commit `security/*`; the pipeline auto-promotes those.

### 13.3 Postgres major-version upgrade

Postgres major versions (16 → 17 etc.) are *not* automatic. Plan in advance:

1. Spin up a second instance from the latest snapshot.
2. `pg_upgrade` on the second instance.
3. Validate by running the test suite against the upgraded DB.
4. In a maintenance window, drain the production instance (stop systemd units), `pg_dump` final state, restore on the upgraded instance, swap the EIP.

**Never** run `pg_upgrade` on the live production DB. Always have a rollback path that's just "re-attach the original EBS volume to a fresh instance".

### 13.4 The on-call runbook (one-pager)

| Symptom | First action | Investigation |
|---|---|---|
| `/health` returns 5xx for >5 min | Check `flowin-backend.service` status and last 200 lines of journald | If OOM, consider scaling up; if DB, check Postgres |
| HTTPS down (no TLS handshake) | `sudo systemctl status nginx`, `sudo nginx -t`, `sudo certbot certificates` | Cert expired? `sudo certbot renew --force-renewal` |
| Disk full on `/` | `journalctl --vacuum-size=500M`, `apt clean`, check `/var/log` | Permanent fix: log rotation, or expand the root volume |
| Disk full on `/var/lib/postgresql` | **DO NOT** run `VACUUM FULL` blindly. Check for runaway agent_outputs JSON. Truncate old `workflow_runs` per Blocker 6. | Long term: expand the volume (`aws ec2 modify-volume`, then `xfs_growfs`) |
| Bedrock 5xx surge (`flowin-prod-bedrock-5xx`) | Reactive: nothing. The retries in `pipeline.py:95-122` (B5) handle transient errors. | If sustained, check the AWS Service Health Dashboard for `eu-west-2` Bedrock; if confirmed regional outage, flip `/flowin/prod/llm/provider` to `anthropic`, populate the fallback API key, restart backend (§9). Alert customers via status page. |
| Bedrock throttles (`flowin-prod-bedrock-throttles`) | Open a Service Quotas increase request for Haiku 4.5 TPM/RPM in `eu-west-2`. | Until granted, expect `Invocation` failures during peaks; the `pipeline.py:95-122` retries cushion this but only up to a point. |
| WS storm (clients reconnecting frantically) | Check `flowin-prod-ws-disconnect-spike` alarm; check uvicorn worker count | A bug in W05 reconnect logic? Check `useWebSocket.ts:113-121` — exponential backoff should keep this bounded |
| User reports stale data | Confirm last successful `pg_dump` from S3; check `pg_stat_activity` for stuck connections | If DB row stuck `running` (Blocker 6), nudge via SQL UPDATE |
| Suspected breach | (1) Take EBS snapshot for forensics, (2) rotate all Parameter Store secrets, (3) terminate the instance from a fresh one | CloudTrail + GuardDuty + auditd logs in CloudWatch are your evidence |

---

## 14. Cost estimate (monthly, low/typical/high)

All in USD, `eu-west-2`, list price (no Reserved Instance / Savings Plan — when traffic is steady, buying a 1-year RI on the EC2 saves ~30%).

| Item | Low | Typical | High |
|---|---|---|---|
| EC2 `m6i.xlarge` (730h) | $140 | $140 | $140 |
| EBS gp3 root, 30 GB | $2.40 | $2.40 | $2.40 |
| EBS gp3 data, 50 GB | $4.00 | $4.00 | $4.00 |
| EBS gp3 data, 100 GB (if you grow) | – | – | $8.00 |
| EBS snapshots (50 GB × 7 daily incrementals avg) | $2 | $3 | $5 |
| AWS Backup (vault overhead) | $1 | $1 | $1 |
| EIP (attached) | $0 | $0 | $0 |
| Route 53 hosted zone | $0.50 | $0.50 | $0.50 |
| Route 53 health check (1) | $0.50 | $0.50 | $0.50 |
| Bedrock VPC interface endpoints (×2, single AZ) | $15 | $15 | $15 |
| Bedrock interface-endpoint data processing | $0.10 | $0.50 | $2 |
| Data transfer out | $5 | $20 | $50 |
| CloudWatch Logs ingestion | $5 | $15 | $40 |
| CloudWatch Logs storage (90 days) | $3 | $8 | $20 |
| CloudWatch Metrics (custom) | $3 | $5 | $10 |
| CloudWatch Alarms (11) | $1.10 | $1.10 | $1.10 |
| Parameter Store (standard tier) | $0 | $0 | $0 |
| KMS CMK | $1 | $1 | $1 |
| GuardDuty (incl. CloudTrail/VPC flow ingestion) | $5 | $10 | $25 |
| AWS CloudTrail (mgmt events to S3) | $0 | $0 | $0 |
| S3 (backups, ~5 GB versioned) | $0.20 | $0.50 | $2 |
| S3 requests (backups + artifacts) | $0.50 | $1 | $2 |
| **Subtotal AWS infra (no LLM tokens)** | **~$190** | **~$229** | **~$330** |
| Bedrock model invocations (Haiku 4.5, list pricing) | ~$10 | ~$50–$200 | ~$1000+ |
| **Total** | **~$200** | **~$280–430** | **~$1330+** |

Notes:

- **Bedrock token spend** is *separate and traffic-dependent*. At time of writing, list pricing is **$0.80 per million input tokens** and **$4.00 per million output tokens** for Claude Haiku 4.5 — verify on the Bedrock pricing page. Bedrock charges parity with the Anthropic direct list price; expect ~$50–$200/mo on top of infra at typical pilot traffic, $1k+ at high volume. With Blocker 3 (cancel) unfixed, a single user "Stop"-clicking a runaway PPT pipeline can burn $5+ of tokens — fix it before going wide.
- **Reserved Instance / Savings Plan:** committing to a 1-year, no-upfront RI on `m6i.xlarge` drops the EC2 line to ~$95/month. Worth doing once steady-state usage is confirmed (~3 months in).
- **Bedrock VPC endpoints** are the new ~$15/mo line item versus the old "direct Anthropic" design. The cost is the price we pay for keeping LLM traffic inside AWS — see §0.1 and §6.4.
- The multi-service guide (`PRODUCTION_DEPLOYMENT_GUIDE.md`) costs ~$105/$205 base — apparently cheaper at low traffic. The catch: that estimate excludes ALB, RDS Multi-AZ surcharge, ElastiCache reserved capacity, and CloudFront data transfer-out. In practice once you wire it all up the multi-service variant lands in the **$300–500/mo** band at typical traffic; the *real* difference between the two designs is **operational**, not cost.

---

## 15. Capacity & scaling ceiling

### 15.1 The numbers

From B7 / B8:

- Each running pipeline holds ~100 MB Python heap.
- The 32K-token agents (`backlog-compiler`, `ppt-code-generator`, `ppt-assembler`, `prototype-finalizer`, `app-builder`, all `reverse_engineer` agents) can stream for ~5–25 minutes wall-clock per agent.
- A typical user_stories pipeline = 6 agents × ~2 min = ~12 min wall-clock, but only one agent is active at a time (B5 — pipeline is sequential).
- Chat sessions (W42–W49) are cheaper (4–16K-token agents, 5–60 sec wall-clock).

On `m6i.xlarge` (4 vCPU / 16 GB):

| Workload mix | Comfortable concurrent | Warning at | Hard ceiling |
|---|---|---|---|
| All chat sessions | 200 | 250 | 350 |
| All user_stories pipelines | 60 | 75 | 90 |
| All PPT / prototype pipelines | 40 | 50 | 60 |
| Realistic mix (60% chat, 30% user_stories, 10% PPT) | 150 | 180 | 220 |

The ceiling is **memory** before it is **CPU**. Vertical-scale signals:

- `mem_used_percent` consistently >80% (alarm fires).
- Postgres OOM-killed event in dmesg.
- Uvicorn worker restart spikes in journald.

### 15.2 The vertical scale path

| From | To | When |
|---|---|---|
| `m6i.xlarge` (4 vCPU / 16 GB) | `m6i.2xlarge` (8 vCPU / 32 GB) | Sustained >120 concurrent pipelines |
| `m6i.2xlarge` | `m6i.4xlarge` (16 vCPU / 64 GB) | Sustained >250 concurrent pipelines |
| `m6i.4xlarge` | **migrate to multi-service** | At this point the single-box outage cost outweighs the operational simplicity |

Vertical scale procedure:
1. Stop traffic during a maintenance window (set Route 53 to a maintenance page, or just accept downtime — single-box reality).
2. `aws ec2 stop-instances --instance-ids <ID>`.
3. `aws ec2 modify-instance-attribute --instance-id <ID> --instance-type m6i.2xlarge`.
4. `aws ec2 start-instances --instance-ids <ID>`.
5. The EIP, security group, and EBS volumes all stay attached; nothing else changes.

Allow ~10 minutes downtime including DNS TTL.

### 15.3 The horizontal scale stepping-stone

Before going full multi-service, one sensible intermediate step is **split the frontend onto a second small EC2** (`t3.small`, $15/month). nginx on the front box reverse-proxies `/api/*` and `/ws/*` to the back box; the front box just serves the Next.js static + SSR. This:

- Buys ~25% more headroom on the back box (no Next.js memory or CPU).
- Adds zero new AWS services.
- Costs ~$20/month more.
- Adds one more node to monitor.

Not strictly necessary; a stepping-stone if you're on the edge of needing the multi-service refactor.

### 15.4 The hard ceiling

Past ~250 concurrent active pipelines on `m6i.4xlarge`, the *real* answer is: ECS Fargate, multiple tasks, ALB sticky sessions for WS, RDS Multi-AZ, ElastiCache for chat-session-id-to-task pinning, S3 for artifacts. That is `PRODUCTION_DEPLOYMENT_GUIDE.md`. We have no business pretending otherwise.

---

## 16. Migration path to the multi-service architecture

When the single-EC2 design no longer fits, migrate in this order:

1. **Extract the database first.** Snapshot Postgres → restore to RDS PostgreSQL Multi-AZ. Repoint `DATABASE_URL` in Parameter Store. Validate, restart backend. **This step alone removes the co-resident DB risk and is worth doing even if you stay on a single EC2 otherwise.** Cost: +$60/mo for db.t3.medium Multi-AZ.

2. **Containerize the backend.** Build the Dockerfile from `PRODUCTION_DEPLOYMENT_GUIDE.md` Phase 3. Push to ECR. *Do not* deploy ECS yet — run the container on the same EC2 first. This proves the image works without changing the topology.

3. **Add an Application Load Balancer.** Move TLS termination from nginx to ALB. Migrate the Let's Encrypt cert to ACM (free, auto-rotating). Configure WS pass-through with `IdleTimeout=4000s` (about 66 minutes — ALB caps at 4000s vs our nginx 5400s, so the backend timeout becomes the new ceiling on long pipelines; revisit then). Cost: +$20/mo.

4. **Move backend to ECS Fargate.** Two tasks behind the ALB. Sticky sessions via ALB target groups (cookie-based). Critical: WebSocket connections are stateful — a chat session must stick to the same task. Fix Blocker 3 *before* this step or you'll have dangling pipelines on task replacement.

5. **Move frontend to S3 + CloudFront** (or keep it on the EC2 if you prefer; either works).

6. **Add ElastiCache only when you actually need it.** The current code has no cache layer; introducing Redis is a code change. Defer until WS session affinity (step 4 stickiness) starts misbehaving — ElastiCache + a proper session store solves that, and also enables the JWT denylist from Blocker 4.

7. **(Already done.)** AWS Bedrock is the LLM provider from day one — see §0.1 and §6.4. No further action in this migration phase.

The single-EC2 instance can be decommissioned after step 5. Expect the migration to take 4–6 weeks calendar time with one engineer; the bulk of it is steps 4 and 6, not the AWS plumbing.

---

## Appendix A — exact `nginx.conf`

`/etc/nginx/sites-available/flowin`. Replace `flowin.example.com` with your domain. The file is what certbot's `--nginx` flag will modify on first run; if you prefer to control it yourself, use `certbot certonly --webroot` and copy the cert paths in manually.

```nginx
# Rate-limit zones — must be in nginx.conf http{} or a snippet, not server{}
# Drop into /etc/nginx/conf.d/flowin-limits.conf:
#
#   limit_req_zone $binary_remote_addr zone=flowin_login:10m rate=10r/m;
#   limit_req_zone $binary_remote_addr zone=flowin_register:10m rate=5r/m;
#   limit_req_zone $binary_remote_addr zone=flowin_change_pw:10m rate=10r/m;
#   limit_req_zone $binary_remote_addr zone=flowin_api:10m rate=120r/m;
#
#   log_format flowin '$remote_addr - $remote_user [$time_local] '
#                     '"$request_method $uri $server_protocol" '
#                     '$status $body_bytes_sent "$http_referer" '
#                     '"$http_user_agent" rt=$request_time';
#   # NOTE: $uri intentionally instead of $request — strips the query string.
#   # WebSocket auth uses Sec-WebSocket-Protocol: bearer.<jwt> per A5, so the
#   # primary fix for Blocker 5 lives in the application. The $uri-instead-of-
#   # $request choice still applies as defense in depth during the transitional
#   # window where some clients may still send ?token=.

# Upstreams
upstream flowin_backend {
    server 127.0.0.1:8000;
    keepalive 64;
}
upstream flowin_frontend {
    server 127.0.0.1:3000;
    keepalive 32;
}

# Map for WebSocket upgrade
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

# HTTP — redirect to HTTPS, except ACME challenge
server {
    listen 80;
    listen [::]:80;
    server_name flowin.example.com;

    location /.well-known/acme-challenge/ {
        root /var/www/letsencrypt;
        try_files $uri =404;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

# HTTPS
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name flowin.example.com;

    server_tokens off;
    client_max_body_size 1m;
    client_body_timeout 30s;
    client_header_timeout 30s;

    # TLS — see §7.3
    ssl_certificate     /etc/letsencrypt/live/flowin.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/flowin.example.com/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/flowin.example.com/chain.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;
    ssl_stapling on;
    ssl_stapling_verify on;
    resolver 169.254.169.253 valid=60s;
    resolver_timeout 5s;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; img-src 'self' data: blob:; font-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; connect-src 'self' https://flowin.example.com wss://flowin.example.com; frame-src 'self' blob:" always;
    # NOTE: 'unsafe-inline'/'unsafe-eval' on script-src is required because
    # the PPT and prototype previews (W56/W57) embed JS in iframes; the iframes
    # are sandbox=allow-scripts already. Tighten this CSP further when those
    # previews are refactored to use an iframe srcdoc with a generated nonce.

    access_log /var/log/nginx/access.log flowin;
    error_log  /var/log/nginx/error.log warn;

    # ── Backend HTTP API ────────────────────────────────────────────────
    location /api/auth/login {
        limit_req zone=flowin_login burst=5 nodelay;
        limit_req_status 429;
        proxy_pass         http://flowin_backend;
        include            /etc/nginx/snippets/flowin-proxy-headers.conf;
    }
    location /api/auth/register {
        limit_req zone=flowin_register burst=3 nodelay;
        limit_req_status 429;
        proxy_pass         http://flowin_backend;
        include            /etc/nginx/snippets/flowin-proxy-headers.conf;
    }
    location /api/auth/change-password {
        limit_req zone=flowin_change_pw burst=5 nodelay;
        limit_req_status 429;
        proxy_pass         http://flowin_backend;
        include            /etc/nginx/snippets/flowin-proxy-headers.conf;
    }
    location /api/ {
        limit_req zone=flowin_api burst=20 nodelay;
        limit_req_status 429;
        proxy_pass         http://flowin_backend;
        include            /etc/nginx/snippets/flowin-proxy-headers.conf;
        # Backend streams JSON; do not buffer
        proxy_buffering    off;
        proxy_request_buffering off;
        proxy_read_timeout 300s;
    }
    location = /health {
        proxy_pass         http://flowin_backend;
        include            /etc/nginx/snippets/flowin-proxy-headers.conf;
        access_log         off;
    }
    location = /openapi.json {
        proxy_pass         http://flowin_backend;
        include            /etc/nginx/snippets/flowin-proxy-headers.conf;
        # Hide /docs in production; keep openapi for tooling.
    }
    location = /docs {
        return 404;  # FastAPI Swagger UI hidden in prod
    }
    location = /redoc {
        return 404;
    }

    # ── WebSocket ───────────────────────────────────────────────────────
    location /ws/chat {
        proxy_pass              http://flowin_backend;
        proxy_http_version      1.1;
        proxy_set_header        Upgrade $http_upgrade;
        proxy_set_header        Connection $connection_upgrade;
        proxy_set_header        Host $host;
        proxy_set_header        X-Real-IP $remote_addr;
        proxy_set_header        X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header        X-Forwarded-Proto $scheme;
        # Long-lived streams: B5 says agents stream tokens for tens of minutes.
        # 5400s = 90 minutes idle window. See §0 decision log.
        proxy_read_timeout      5400s;
        proxy_send_timeout      5400s;
        proxy_buffering         off;
        proxy_request_buffering off;
    }

    # ── Frontend (Next.js) ──────────────────────────────────────────────
    location / {
        proxy_pass         http://flowin_frontend;
        include            /etc/nginx/snippets/flowin-proxy-headers.conf;
        proxy_buffering    on;     # fine to buffer SSR responses
        proxy_read_timeout 60s;
    }

    # Static assets (Next emits these under /_next/static/*) — long cache
    location /_next/static/ {
        proxy_pass         http://flowin_frontend;
        include            /etc/nginx/snippets/flowin-proxy-headers.conf;
        proxy_cache_valid  200 1y;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }
}
```

`/etc/nginx/snippets/flowin-proxy-headers.conf`:

```nginx
proxy_http_version 1.1;
proxy_set_header   Host              $host;
proxy_set_header   X-Real-IP         $remote_addr;
proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
proxy_set_header   X-Forwarded-Proto $scheme;
proxy_set_header   Connection        "";
proxy_redirect     off;
```

Validate after every edit:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

---

## Appendix B — exact systemd unit files

### B.1 `/etc/systemd/system/flowin-backend.service`

```ini
[Unit]
Description=Flowin backend (FastAPI + uvicorn)
After=network-online.target postgresql.service
Wants=network-online.target
Requires=postgresql.service

[Service]
Type=exec
User=flowin
Group=flowin
WorkingDirectory=/opt/flowin/backend

# Pull secrets and runtime config fresh on every start. The loader populates
# Bedrock provider/region/model_id from /flowin/prod/llm/*; ANTHROPIC_API_KEY
# is no longer required for boot (only for the optional outage fallback — §9).
ExecStartPre=/usr/local/bin/flowin-load-secrets
EnvironmentFile=/etc/flowin/environment.d/flowin.env

# ENV is environment-defining: it gates the A1 SECRET_KEY hard-fail in
# backend/app/core/config.py. Putting it in the unit (not in SSM) means an
# accidental SSM rotation or a missing parameter cannot disarm strict mode.
Environment=ENV=production

# Apply pending Alembic migrations before uvicorn starts. EnvironmentFile is
# loaded for ExecStartPre too, so DATABASE_URL is set when alembic runs. The
# command is idempotent — it's a no-op when the DB is already at HEAD — so
# safe to run on every restart. If a migration fails, systemd refuses to
# start uvicorn (Restart=always then loops with backoff) — this is the
# guard that prevents prod from booting against a stale schema.
ExecStartPre=/opt/flowin/venv/bin/alembic upgrade head

ExecStart=/opt/flowin/venv/bin/uvicorn app.main:app \
    --host 127.0.0.1 \
    --port 8000 \
    --workers 4 \
    --proxy-headers \
    --forwarded-allow-ips=127.0.0.1 \
    --no-access-log \
    --log-level info

Restart=always
RestartSec=5
TimeoutStopSec=30
KillMode=mixed

# File descriptor limit — uvicorn + websockets need this
LimitNOFILE=65535

# systemd hardening
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
RestrictNamespaces=yes
RestrictRealtime=yes
RestrictSUIDSGID=yes
LockPersonality=yes
MemoryDenyWriteExecute=no   # JIT-using libs (none today) would need this off; left off as defensive default
SystemCallArchitectures=native
ReadWritePaths=/opt/flowin/src/backend/skills /var/log/flowin

# Resource caps
MemoryMax=12G
TasksMax=4096

[Install]
WantedBy=multi-user.target
```

### B.2 `/etc/systemd/system/flowin-frontend.service`

```ini
[Unit]
Description=Flowin frontend (Next.js standalone)
After=network-online.target
Wants=network-online.target

[Service]
Type=exec
User=flowin
Group=flowin
WorkingDirectory=/opt/flowin/frontend/.next/standalone

Environment=NODE_ENV=production
Environment=PORT=3000
Environment=HOSTNAME=127.0.0.1

ExecStart=/usr/bin/node /opt/flowin/frontend/.next/standalone/server.js

Restart=always
RestartSec=5
TimeoutStopSec=15

LimitNOFILE=32768

NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
RestrictNamespaces=yes
LockPersonality=yes
SystemCallArchitectures=native
ReadWritePaths=/var/log/flowin

MemoryMax=2G
TasksMax=512

[Install]
WantedBy=multi-user.target
```

### B.3 `/etc/systemd/system/flowin-pg-dump.service` and `.timer`

See §11.2 — files reproduced here for completeness.

`flowin-pg-dump.service`:

```ini
[Unit]
Description=Flowin Postgres logical dump to S3
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=postgres
Group=postgres
ExecStart=/usr/local/bin/flowin-pg-dump
TimeoutStartSec=600
```

`flowin-pg-dump.timer`:

```ini
[Unit]
Description=Hourly Flowin PG dump

[Timer]
OnCalendar=hourly
Persistent=true
RandomizedDelaySec=120
Unit=flowin-pg-dump.service

[Install]
WantedBy=timers.target
```

### B.4 certbot timer (installed by the `certbot` apt package)

```ini
[Unit]
Description=Run certbot twice daily

[Timer]
OnCalendar=*-*-* 00,12:00:00
RandomizedDelaySec=43200
Persistent=true
Unit=certbot.service

[Install]
WantedBy=timers.target
```

(File is supplied by Debian; we just `systemctl enable --now certbot.timer`.)

### B.5 `/etc/systemd/system/flowin-skills-backup.service` and `.timer`

For nightly skills tarball:

`flowin-skills-backup.service`:

```ini
[Unit]
Description=Flowin skills backup to S3
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=flowin
Group=flowin
# bootstrap.env carries FLOWIN_BACKUP_BUCKET and FLOWIN_KMS_KEY_ID
# (Terraform injects these via module.compute's user_data_extra_env).
EnvironmentFile=/etc/flowin/bootstrap.env
ExecStart=/usr/local/bin/flowin-skills-backup
```

`flowin-skills-backup.timer`:

```ini
[Unit]
Description=Daily Flowin skills backup

[Timer]
OnCalendar=daily
Persistent=true
RandomizedDelaySec=600
Unit=flowin-skills-backup.service

[Install]
WantedBy=timers.target
```

`/usr/local/bin/flowin-skills-backup`:

```bash
#!/usr/bin/env bash
set -euo pipefail
: "${FLOWIN_BACKUP_BUCKET:?FLOWIN_BACKUP_BUCKET is required}"
: "${FLOWIN_KMS_KEY_ID:?FLOWIN_KMS_KEY_ID is required}"
TS=$(date -u +%Y%m%d)
tar -czf - -C /opt/flowin/src/backend skills \
  | aws s3 cp - "s3://${FLOWIN_BACKUP_BUCKET}/skills/${TS}.tar.gz" \
      --region eu-west-2 \
      --sse aws:kms \
      --sse-kms-key-id "$FLOWIN_KMS_KEY_ID"
```

---

## Appendix C — Parameter Store key list

Canonical reference. **All keys live under `/flowin/prod/`** and are written by an operator (never by the application). Type `SecureString` unless noted.

The columns:
- **SSM key** — the parameter name in Parameter Store (Terraform writes these via `infra/modules/secrets/`).
- **Env var** — the variable name the on-host loader (`/usr/local/bin/flowin-load-secrets`) emits into `/etc/flowin/environment.d/flowin.env`. Settings (`backend/app/core/config.py`) reads these.

> **Note on `ENV`.** `ENV` is **set in the systemd unit** (`Environment=ENV=production` in `flowin-backend.service`), not in SSM. It is environment-defining — putting it in SSM would let an out-of-band parameter rotation accidentally disarm the A1 SECRET_KEY hard-fail. Keeping it inline in the unit makes the production-strict mode unconditional.
>
> **Note on `DATABASE_URL`.** The composed URL embeds `127.0.0.1` (the on-host Postgres), which Terraform doesn't know. The loader composes it from `DATABASE_PASSWORD` at boot.

| SSM key | Env var | Type | Source / generation | Rotation | Notes |
|---|---|---|---|---|---|
| `/flowin/prod/SECRET_KEY` | `SECRET_KEY` | SecureString | `openssl rand -hex 64` | Yearly + on compromise | Used by python-jose for HS256. **Required non-default at boot** (Blocker 1). |
| `/flowin/prod/DATABASE_PASSWORD` | `DATABASE_URL` (composed by loader) | SecureString | `openssl rand -hex 32` | Yearly + on compromise | Drives `ALTER USER flowin WITH PASSWORD ...`. The loader composes `DATABASE_URL=postgresql://flowin:${pw}@127.0.0.1:5432/flowin` from this value. |
| `/flowin/prod/CORS_ORIGINS` | `CORS_ORIGINS` | String | – | When domains change | JSON array. Currently `["https://flowin.example.com"]`. |
| `/flowin/prod/ACCESS_TOKEN_EXPIRE_HOURS` | `ACCESS_TOKEN_EXPIRE_HOURS` | String | `12` | Re-evaluate yearly | Production override per env-template (env-templates/.env.production). |
| `/flowin/prod/llm/provider` | `LLM_PROVIDER` | String | `bedrock` | Only on emergency Anthropic-direct fallback (§0.1) | Selects the LLM backend. Values: `bedrock` (default) or `anthropic` (fallback). |
| `/flowin/prod/llm/region` | `AWS_REGION` | String | `eu-west-2` | When deployment region changes | AWS region the Bedrock SDK targets. The cross-region inference profile fans out to other EU regions transparently — the SDK target stays `eu-west-2`. |
| `/flowin/prod/llm/model_id` | `BEDROCK_MODEL_ID` | String | `eu.anthropic.claude-haiku-4-5-20251001-v1:0` | When upgrading model | The Bedrock model ID or inference-profile ID the application invokes. Not a secret, but kept in Parameter Store so model swaps don't require a redeploy. |
| `/flowin/prod/anthropic/api_key` | `ANTHROPIC_API_KEY` | SecureString | Anthropic Console → API keys (only when populated for an outage fallback) | Only when the parameter is populated; clear on incident close | **Empty by default and not required for boot.** Populated only during a Bedrock outage; pair with `/flowin/prod/llm/provider=anthropic` and restart the backend. See §0.1, §9. |
| `/flowin/prod/LANGSMITH_TRACING` | `LANGSMITH_TRACING` | String | `false` (default) or `true` | Per change | If `true`, also requires the next two keys. |
| `/flowin/prod/LANGSMITH_API_KEY` | `LANGSMITH_API_KEY` | SecureString | LangSmith Console | When LangSmith rotates | Optional — only if tracing is on. |
| `/flowin/prod/LANGSMITH_PROJECT` | `LANGSMITH_PROJECT` | String | e.g. `flowin-prod` | Per change | Optional. |

To list everything that exists today:

```bash
aws ssm get-parameters-by-path \
  --path /flowin/prod \
  --recursive \
  --region eu-west-2 \
  --query 'Parameters[].Name' --output table
```

To audit who-has-read access:

```bash
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::<ACCOUNT_ID>:role/flowin-prod-instance \
  --action-names ssm:GetParameter \
  --resource-arns arn:aws:ssm:eu-west-2:<ACCOUNT_ID>:parameter/flowin/prod/SECRET_KEY \
  --region eu-west-2
```

(Run this as a quarterly audit.)

---

## Appendix D — bootstrap script for a fresh EC2

`bootstrap.sh`. Pass via `aws ec2 run-instances --user-data file://bootstrap.sh`. Runs as root, idempotent, takes ~6 minutes wall-clock.

The script supports two modes auto-detected at run:

- **Fresh provision:** no data on `/dev/nvme1n1`. Script formats it, initializes Postgres, runs `git clone`, `npm run build`, `pip install`, generates a new password, puts it into Parameter Store.
- **Recovery from snapshot:** `/dev/nvme1n1` has an xfs filesystem with an existing Postgres data dir. Script mounts it, skips `initdb`, reuses the existing password from Parameter Store.

```bash
#!/usr/bin/env bash
# Flowin production EC2 bootstrap.
# Idempotent. Detects whether it is provisioning a new box or
# recovering one from snapshot and behaves accordingly.
set -euo pipefail
exec > >(tee -a /var/log/flowin-bootstrap.log) 2>&1
echo "[bootstrap] start $(date -u --iso-8601=seconds)"

REGION=eu-west-2
DOMAIN=flowin.example.com
ACME_EMAIL=security@example.com
PARAM_PREFIX=/flowin/prod
DATA_DEV=/dev/nvme1n1
DATA_MOUNT=/var/lib/postgresql
APP_USER=flowin
REPO_URL=https://gitlab.com/hexaware-uki/flowin.git

# ── 0. Wait for cloud-init to settle ───────────────────────────────────
while ! cloud-init status --wait > /dev/null 2>&1; do sleep 2; done

# ── 1. Patch & baseline tools ──────────────────────────────────────────
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get -y full-upgrade
apt-get install -y \
    nginx postgresql-16 postgresql-contrib-16 \
    python3.12-venv python3-pip git curl jq xfsprogs \
    certbot python3-certbot-nginx \
    ufw fail2ban auditd \
    unattended-upgrades update-notifier-common \
    awscli

# ── 2. Firewall, SSH hardening (see §8.1) ──────────────────────────────
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

cat >/etc/ssh/sshd_config.d/10-flowin.conf <<'EOF'
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
KbdInteractiveAuthentication no
X11Forwarding no
AllowTcpForwarding no
AllowAgentForwarding no
PermitTunnel no
ClientAliveInterval 300
ClientAliveCountMax 2
MaxAuthTries 3
LoginGraceTime 30
EOF
systemctl reload ssh

cat >/etc/apt/apt.conf.d/52flowin <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";
EOF
systemctl enable --now unattended-upgrades

timedatectl set-timezone UTC

# ── 3. Application user ────────────────────────────────────────────────
id -u $APP_USER >/dev/null 2>&1 || useradd -r -m -d /opt/flowin -s /usr/sbin/nologin $APP_USER
mkdir -p /opt/flowin /var/log/flowin /etc/flowin/environment.d
chown -R $APP_USER:$APP_USER /opt/flowin /var/log/flowin
chown root:$APP_USER /etc/flowin/environment.d
chmod 0750 /etc/flowin/environment.d

# ── 4. Data volume — detect fresh vs existing ──────────────────────────
systemctl stop postgresql || true
if blkid $DATA_DEV >/dev/null 2>&1; then
    echo "[bootstrap] data volume already formatted — recovery mode"
    RECOVERY=1
else
    echo "[bootstrap] data volume blank — fresh provision"
    mkfs.xfs -L flowin-data $DATA_DEV
    RECOVERY=0
fi

mkdir -p $DATA_MOUNT
if ! mountpoint -q $DATA_MOUNT; then
    UUID=$(blkid -s UUID -o value $DATA_DEV)
    grep -q "$UUID" /etc/fstab || echo "UUID=$UUID $DATA_MOUNT xfs defaults,nofail 0 2" >> /etc/fstab
    mount $DATA_MOUNT
fi
chown postgres:postgres $DATA_MOUNT

# ── 5. Postgres ────────────────────────────────────────────────────────
PG_DATA=$DATA_MOUNT/16/main
if [[ $RECOVERY -eq 0 ]]; then
    sudo -u postgres /usr/lib/postgresql/16/bin/initdb -D $PG_DATA \
        --auth=scram-sha-256 --pwprompt=false --pwfile=<(echo)
    DB_PW=$(openssl rand -hex 32)
    aws ssm put-parameter --region $REGION \
        --name $PARAM_PREFIX/DATABASE_PASSWORD \
        --type SecureString --value "$DB_PW" --overwrite
    aws ssm put-parameter --region $REGION \
        --name $PARAM_PREFIX/DATABASE_URL \
        --type SecureString \
        --value "postgresql+psycopg2://flowin:${DB_PW}@127.0.0.1:5432/flowin" \
        --overwrite
fi

# Wire pg_hba and postgresql.conf
PG_CONF=/etc/postgresql/16/main/postgresql.conf
PG_HBA=/etc/postgresql/16/main/pg_hba.conf
sed -i \
    -e "s|^#*data_directory.*|data_directory = '$PG_DATA'|" \
    -e "s|^#*listen_addresses.*|listen_addresses = '127.0.0.1'|" \
    -e "s|^#*shared_buffers.*|shared_buffers = 4GB|" \
    -e "s|^#*effective_cache_size.*|effective_cache_size = 10GB|" \
    -e "s|^#*work_mem.*|work_mem = 32MB|" \
    -e "s|^#*maintenance_work_mem.*|maintenance_work_mem = 512MB|" \
    -e "s|^#*log_min_duration_statement.*|log_min_duration_statement = 1000|" \
    $PG_CONF
cat > $PG_HBA <<'EOF'
local   all   postgres                peer
local   all   all                     scram-sha-256
host    all   all      127.0.0.1/32   scram-sha-256
host    all   all      ::1/128        scram-sha-256
EOF

mkdir -p /etc/systemd/system/postgresql@16-main.service.d
cat > /etc/systemd/system/postgresql@16-main.service.d/oom.conf <<'EOF'
[Service]
OOMScoreAdjust=-900
EOF
systemctl daemon-reload
systemctl enable --now postgresql@16-main

if [[ $RECOVERY -eq 0 ]]; then
    DB_PW=$(aws ssm get-parameter --region $REGION --name $PARAM_PREFIX/DATABASE_PASSWORD --with-decryption --query 'Parameter.Value' --output text)
    sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
CREATE USER flowin WITH ENCRYPTED PASSWORD '$DB_PW';
CREATE DATABASE flowin OWNER flowin;
\c flowin
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT ALL ON SCHEMA public TO flowin;
SQL
fi

# ── 6. Swap ────────────────────────────────────────────────────────────
if ! swapon --show | grep -q swapfile; then
    fallocate -l 4G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
sysctl -w vm.swappiness=10
echo 'vm.swappiness = 10' > /etc/sysctl.d/99-flowin.conf

# ── 7. Node.js 20 LTS ──────────────────────────────────────────────────
if ! command -v node >/dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
fi

# ── 8. App checkout & build ────────────────────────────────────────────
sudo -u $APP_USER bash <<EOF
set -euo pipefail
if [[ ! -d /opt/flowin/src ]]; then
    git clone $REPO_URL /opt/flowin/src
fi
cd /opt/flowin/src
git fetch --all
git checkout main
git pull --ff-only

# Symlinks
ln -sfn /opt/flowin/src/backend  /opt/flowin/backend
ln -sfn /opt/flowin/src/frontend /opt/flowin/frontend

# Python venv
if [[ ! -x /opt/flowin/venv/bin/python ]]; then
    python3.12 -m venv /opt/flowin/venv
fi
/opt/flowin/venv/bin/pip install -U pip
/opt/flowin/venv/bin/pip install -r backend/requirements.txt
/opt/flowin/venv/bin/pip install psycopg2-binary

# Frontend build
cd frontend
NEXT_PUBLIC_API_URL=https://$DOMAIN \
NEXT_PUBLIC_WS_URL=wss://$DOMAIN/ws/chat \
npm ci
NEXT_PUBLIC_API_URL=https://$DOMAIN \
NEXT_PUBLIC_WS_URL=wss://$DOMAIN/ws/chat \
npm run build
EOF

# ── 8b. Apply DB migrations ────────────────────────────────────────────
# The application now uses Alembic — the schema is no longer auto-created
# at uvicorn startup. We need DATABASE_URL in scope; pull it from
# Parameter Store rather than waiting for /etc/flowin/environment.d/flowin.env
# (which §9 populates further down). Idempotent: re-running on a recovery
# boot is a no-op when the DB is already at HEAD.
DB_URL=$(aws ssm get-parameter --region $REGION --name $PARAM_PREFIX/DATABASE_URL --with-decryption --query 'Parameter.Value' --output text)
sudo -u $APP_USER bash -c "cd /opt/flowin/backend && \
    DATABASE_URL='$DB_URL' \
    SECRET_KEY=\$(aws ssm get-parameter --region $REGION --name $PARAM_PREFIX/SECRET_KEY --with-decryption --query 'Parameter.Value' --output text) \
    /opt/flowin/venv/bin/alembic upgrade head"

# ── 9. Secrets loader ──────────────────────────────────────────────────
# Pulls all parameters under /flowin/prod/* and emits them as KEY=value lines
# into a 0640 root:flowin env file consumed by the systemd EnvironmentFile= in
# Appendix B. The mapping is per-key and explicit (see §9.3 for the table):
#
#   SECRET_KEY,CORS_ORIGINS,ACCESS_TOKEN_EXPIRE_HOURS,LANGSMITH_*  → passthrough
#   DATABASE_PASSWORD                                              → DATABASE_URL=postgresql://flowin:${value}@127.0.0.1:5432/flowin
#   llm/provider                                                   → LLM_PROVIDER
#   llm/region                                                     → AWS_REGION
#   llm/model_id                                                   → BEDROCK_MODEL_ID
#   anthropic/api_key                                              → ANTHROPIC_API_KEY
#   anything else                                                  → warn, ignore
#
# Note: ENV is set by the systemd unit (Environment=ENV=production), not here.
cat > /usr/local/bin/flowin-load-secrets <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

OUT=/etc/flowin/environment.d/flowin.env
TMP=$(mktemp /etc/flowin/environment.d/flowin.env.XXXXXX)
chmod 0640 "$TMP"; chown root:flowin "$TMP"

REGION=eu-west-2
PREFIX=/flowin/prod

emit() {
    printf '%s=%q\n' "$1" "$2" >> "$TMP"
}

while IFS=$'\t' read -r name value; do
    rel="${name#${PREFIX}/}"
    case "$rel" in
        SECRET_KEY|CORS_ORIGINS|ACCESS_TOKEN_EXPIRE_HOURS|LANGSMITH_TRACING|LANGSMITH_API_KEY|LANGSMITH_PROJECT)
            emit "$rel" "$value" ;;
        DATABASE_PASSWORD)
            emit DATABASE_URL "postgresql://flowin:${value}@127.0.0.1:5432/flowin" ;;
        llm/provider)      emit LLM_PROVIDER     "$value" ;;
        llm/region)        emit AWS_REGION       "$value" ;;
        llm/model_id)      emit BEDROCK_MODEL_ID "$value" ;;
        anthropic/api_key) emit ANTHROPIC_API_KEY "$value" ;;
        *)
            echo "[flowin-load-secrets] WARN: ignoring unknown parameter ${name}" >&2 ;;
    esac
done < <(aws ssm get-parameters-by-path \
            --path "$PREFIX" \
            --recursive \
            --with-decryption \
            --region "$REGION" \
            --query 'Parameters[].[Name,Value]' \
            --output text)

mv "$TMP" "$OUT"
chmod 0640 "$OUT"; chown root:flowin "$OUT"
EOF
chmod +x /usr/local/bin/flowin-load-secrets

# ── 10. systemd units (see Appendix B) ─────────────────────────────────
# (omitted here — copy Appendix B verbatim into /etc/systemd/system/)
# In real deployment, the bootstrap script writes them with cat-heredocs.

# ── 11. nginx ──────────────────────────────────────────────────────────
mkdir -p /var/www/letsencrypt /etc/nginx/snippets
# Drop in Appendix A files: /etc/nginx/sites-available/flowin
#                            /etc/nginx/snippets/flowin-proxy-headers.conf
#                            /etc/nginx/conf.d/flowin-limits.conf
ln -sfn /etc/nginx/sites-available/flowin /etc/nginx/sites-enabled/flowin
rm -f /etc/nginx/sites-enabled/default

# Initial cert (HTTP-01) — only if no cert exists yet
if [[ ! -d /etc/letsencrypt/live/$DOMAIN ]]; then
    # Temp HTTP server for ACME, then certbot
    cat > /etc/nginx/sites-available/bootstrap-http <<EOF2
server {
    listen 80 default_server;
    location /.well-known/acme-challenge/ { root /var/www/letsencrypt; }
    location / { return 200 'bootstrap'; add_header Content-Type text/plain; }
}
EOF2
    ln -sfn /etc/nginx/sites-available/bootstrap-http /etc/nginx/sites-enabled/bootstrap-http
    rm -f /etc/nginx/sites-enabled/flowin
    systemctl reload nginx
    certbot certonly --webroot -w /var/www/letsencrypt \
        --non-interactive --agree-tos --email $ACME_EMAIL -d $DOMAIN
    rm /etc/nginx/sites-enabled/bootstrap-http
    ln -sfn /etc/nginx/sites-available/flowin /etc/nginx/sites-enabled/flowin
fi

nginx -t
systemctl reload nginx
systemctl enable --now certbot.timer

# ── 12. CloudWatch agent (see §10.1) ───────────────────────────────────
if ! dpkg -s amazon-cloudwatch-agent >/dev/null 2>&1; then
    wget -q https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb \
        -O /tmp/cw-agent.deb
    dpkg -i /tmp/cw-agent.deb
    rm /tmp/cw-agent.deb
fi
# Drop in /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json (see §10.1)
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
    -a fetch-config -m ec2 -s -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
systemctl enable --now amazon-cloudwatch-agent

# ── 13. Backups (see §11.2) ────────────────────────────────────────────
# Drop in /usr/local/bin/flowin-pg-dump and the timer/service files.
chmod +x /usr/local/bin/flowin-pg-dump /usr/local/bin/flowin-skills-backup
systemctl daemon-reload
systemctl enable --now flowin-pg-dump.timer flowin-skills-backup.timer

# ── 14. Application units ──────────────────────────────────────────────
/usr/local/bin/flowin-load-secrets
systemctl daemon-reload
systemctl enable --now flowin-backend.service flowin-frontend.service

# ── 15. Smoke test ─────────────────────────────────────────────────────
sleep 15
curl -fsS http://127.0.0.1:8000/health
echo "[bootstrap] complete $(date -u --iso-8601=seconds)"
```

Notes on the script:

- The "Drop in Appendix X files" comments are placeholders. In the real bootstrap, replace each with a `cat > /path <<'EOF' ... EOF` block. The script becomes ~700 lines; the structure here is the executable skeleton.
- The script exits non-zero on any error (`set -euo pipefail`). cloud-init will retry once; persistent failures show up as "instance failed boot" in EC2 console + a CloudWatch event you should alarm on.
- Recovery mode is detected purely by "is the data volume already formatted?". This is the only branch — everything else is the same path.
- The script does *not* configure user accounts or SSH keys for operators; that's a one-time post-bootstrap step (or pulled from an LDAP/OIDC source if Hexaware UKI uses one).

---

## End

This is the simplest secure AWS deployment of Flowin we believe is honest. Six AWS services. One EC2. One Postgres. Boring, well-trodden tooling. Single-AZ trade-off documented openly in §2 and §15. Pre-launch security blockers spelled out in §3 — they are the gating items, not the AWS plumbing.

If anything in this guide conflicts with the multi-service guide at `docs/PRODUCTION_DEPLOYMENT_GUIDE.md`, this guide wins for any deployment under ~200 concurrent users; that guide wins above. Migration path is §16.
