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
| Instance type | `m6i.2xlarge` (8 vCPU / 32 GB RAM / 100 GB gp3 EBS) on Ubuntu 24.04 LTS | Doubles the heavy-pipeline headroom of `m6i.xlarge` for B7/B8 memory profile (~100 MB / pipeline); 6-7 concurrent heavy pipelines well within budget | §5 |
| OS | Ubuntu 24.04 LTS (Canonical official AMI) | LTS kernel, free `unattended-upgrades`, well-known Postgres/nginx packages | §5, §8.1 |
| Reverse proxy + TLS | nginx 1.24+ on the box, Let's Encrypt certs via certbot (HTTP-01) | Customer rejects ALB; ACM doesn't issue free certs to EC2; certbot+nginx is boring and proven | §7, §8.2 |
| DNS strategy | **Default: nip.io** — the FQDN is computed from the EIP at apply time (e.g. `1-2-3-4.nip.io` for EIP `1.2.3.4`). No Route 53 zone, no A record, no DNS provisioning. nip.io is on the Public Suffix List so Let's Encrypt issues real certs. Alternative: Route 53 + a customer-owned domain (set `use_nip_io = false`, supply `route53_zone_name` and `app_subdomain`; the zone must already exist). | Customer doesn't have / doesn't want a custom domain yet. nip.io's wildcard DNS gives a real HTTPS hostname with zero DNS wiring; we keep the Route 53 path so it's a single tfvars flip when the customer brings a domain. | §7 |
| WebSocket timeout | nginx `proxy_read_timeout 5400s; proxy_send_timeout 5400s` (90 min) | Long PPT/prototype runs in B7 stream tokens for tens of minutes; idle close on 90 min cap | §8.2, W21/W33/B5 |
| Database | PostgreSQL 16 on the same instance, on a *separate* encrypted gp3 EBS volume (50 GB) mounted at `/var/lib/postgresql` | Customer accepts; isolating the data volume gives clean snapshot/restore | §8.4, §11 |
| Secrets store | AWS Systems Manager Parameter Store (SecureString, KMS-encrypted) | Free tier; meets "encrypted at rest, not in git, IAM-gated"; cheaper than Secrets Manager and adequate for this footprint | §9 |
| LLM provider | **AWS Bedrock — Claude Haiku 4.5 via cross-region inference profile (`eu.anthropic.claude-haiku-4-5-20251001-v1:0`).** Auth via instance-profile IAM role; no API key. | IAM-only auth removes the highest-risk long-lived secret; LLM traffic stays inside AWS via VPC interface endpoints; spend and audit consolidate onto the AWS bill. | §0.1, §5.3, §6.4, §9 |
| Outbound ACL | NAT-less: instance has a public IP in a public subnet. Security-group egress rule keeps TCP/443 to `0.0.0.0/0` open for apt, GitHub releases, and the Bedrock public endpoint as a fallback path; the **preferred** Bedrock path is the VPC interface endpoint provisioned in §6.4, which keeps LLM traffic private. | NAT Gateway is $35/mo per AZ for no real benefit on a single box; the Bedrock interface endpoint covers the data-residency story instead. | §6, §6.4 |
| TLS termination | nginx terminates; backend listens on `127.0.0.1:8000`; frontend listens on `127.0.0.1:3000` | All inter-service traffic stays on loopback; only 80/443/22 reach the network | §8.2 |
| Logging | CloudWatch Agent ships nginx, journald (systemd units), and Postgres logs | The customer named CloudWatch as the AWS-mandated service; alarms fire from there | §10 |
| Backups | (a) EBS snapshot of the data volume nightly via AWS Backup; (b) `pg_dump` → S3 (SSE-S3) hourly via systemd timer. RPO 1 hour, RTO 30 min. | Belt-and-braces. Snapshot is fast, dump is portable. | §11 |
| Disaster recovery | Bootstrap script (Appendix D) + latest snapshot + Parameter Store puts a fresh instance back in service in <30 min | §11 |
| Concurrency ceiling | ~300 concurrent live pipeline sessions on `m6i.2xlarge`, ~100 concurrent if all running PPT/prototype (the 32K-token agents) | B7 / B8: each running pipeline holds ~100 MB Python heap | §15 |
| Migration path | Vertical scale → split frontend onto static-host EC2 → move to ECS/ALB/RDS per `PRODUCTION_DEPLOYMENT_GUIDE.md` | §16 |
| Monthly cost band | Infra-only: low ~$377, typical ~$416, high ~$517 (includes the new ~$15/mo Bedrock VPC interface endpoint pair). LLM token spend is **separate and traffic-dependent**: ~$50–$200/mo typical, $1k+ at high volume. | §14 |

### 0.1 The Bedrock vs Anthropic question, settled

We use AWS Bedrock for all Claude calls. The original analysis (preserved in commit history) recommended deferring this; the customer overrode that decision. Note that `WORKFLOWS.md` B7 still says "no Bedrock integration" — that section is now stale and points to the migration commit (`[infra]` — backend code migration).

The three concrete benefits we now realise:

1. **No long-lived API key.** Auth is the EC2 instance-profile IAM role; rotation is handled by STS. This removes the highest-risk secret from the system — there is no `ANTHROPIC_API_KEY` to leak from Parameter Store, from a `.env` file on disk, from a journald log line, or from a developer's shell history.
2. **Traffic stays inside AWS.** Combined with a Bedrock VPC interface endpoint (see §6.4), the entire LLM data path is private — request and response never traverse the public internet. Important for the shared org account / data-residency story Hexaware UKI tells regulated customers.
3. **Single audit pane.** All LLM invocations are visible in CloudTrail (`bedrock:InvokeModel*` events). Spend lands on the same AWS bill as everything else; one PO, one invoice line, one finance owner.

Honest trade-offs:

| Trade-off | Mitigation |
|---|---|
| **(a) Region availability.** Haiku 4.5 may not be directly available in `eu-central-1`. Confirm with `aws bedrock list-foundation-models --region eu-central-1 --query 'modelSummaries[?contains(modelId, \`claude-haiku-4-5\`)].modelId' --output table`. If the model is not available directly, use the EU cross-region inference profile `eu.anthropic.claude-haiku-4-5-20251001-v1:0` which routes invocations between EU regions transparently. | The deployment defaults to the inference profile; data-residency is preserved across the EU geography. |
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
                            |  DNS — pick one (§7):           |
                            |  (a) nip.io (default):          |
                            |    1-2-3-4.nip.io  → EIP        |
                            |        (no AWS resources;       |
                            |         wildcard handled by     |
                            |         nip.io upstream)        |
                            |  (b) Route 53 hosted zone:      |
                            |    flowin.example.com  A → EIP  |
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
   |   |  | EC2 m6i.2xlarge       |  |    Egress: 443/tcp 0.0.0.0/0 (apt,    |
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
   |   |  |   flowin-app  (docker |  |                                        |
   |   |  |     compose: backend  |  |                                        |
   |   |  |     + frontend)       |  |                                        |
   |   |  |   docker              |  |                                        |
   |   |  |   nginx               |  |                                        |
   |   |  |   postgresql          |  |                                        |
   |   |  |   amazon-cloudwatch-  |  |                                        |
   |   |  |     agent             |  |                                        |
   |   |  |   flowin-ecr-login    |  |                                        |
   |   |  |     .timer            |  |                                        |
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
          (com.amazonaws.eu-central-1.bedrock-runtime). Auth via instance-profile
          IAM role; traffic stays inside the VPC. See §6.4.
```

That's it. Seven AWS services in total: EC2, EBS, CloudWatch, Systems Manager Parameter Store, S3, Bedrock (via VPC interface endpoints), Route 53 (only on the custom-domain path; the default nip.io path uses zero AWS DNS resources), plus AWS Backup which is just a scheduler over EBS snapshots. Nothing else.

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
- **Vertical scaling has a ceiling.** ~100 concurrent prototype/PPT pipelines on `m6i.2xlarge` (B7 says each holds ~100 MB heap on a 32K-token output agent). Past that, vertical scaling on `m6i` tops out at `m6i.4xlarge` (16 vCPU / 64 GB), which is not three years of headroom.
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

**Non-code pre-launch item:** **submit a Bedrock service quota increase request** for `Tokens per minute` and `Requests per minute` for Claude Haiku 4.5 in `eu-central-1` (and any cross-region inference targets — see §0.1). Default Bedrock quotas are conservative (~100 RPM for Haiku 4.5 in some regions); load testing without an increase will hit `InvocationThrottles`. Open the request via Service Quotas console at least 5 business days before the planned load test — increases for Bedrock can require human review.

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
7. **Choose a region.** For Hexaware UKI customers, **`eu-central-1` (Frankfurt)** is the default. EU data residency. If a customer requires Ireland (`eu-west-1`) or London (`eu-central-1`), the guide below works unchanged — just substitute `eu-central-1` everywhere.
8. **Pick an Availability Zone within that region** — e.g. `eu-central-1a`. Single-AZ design (§2). Document the choice; the snapshot-restore drill in §11 needs to know it.
9. **Reserve an Elastic IP** in the region (`aws ec2 allocate-address`). Cost: free while attached to a running instance. Keep the EIP across instance replacements so the FQDN never has to update — true for both DNS paths (a Route 53 A record outliving an instance replacement, or the nip.io hostname being a deterministic function of the EIP).
10. **DNS — pick a path.** Two options, see §7:
    - **nip.io (default for sandbox / no-domain customers).** No Route 53 zone, no setup. The FQDN is computed from the EIP at apply time (e.g. `1-2-3-4.nip.io`). Skip step 10 entirely — Terraform's `var.use_nip_io = true` does the rest.
    - **Custom domain (Route 53).** Buy a Route 53 hosted zone for the apex domain (e.g. `flowin.example.com`). Set `var.use_nip_io = false`, `var.route53_zone_name` and `var.app_subdomain` in tfvars. Terraform looks up the zone (it must already exist) and creates the A record.

---

## 5. EC2 instance — sizing, AMI, IAM role

### 5.1 Sizing rationale

The dominant memory consumer is per-pipeline Python heap. From `WORKFLOWS.md` B7/B8:

- Each running pipeline holds ~100 MB resident memory (LangChain stream buffers + per-agent output buffers up to 32K tokens for the `backlog-compiler`, `ppt-code-generator`, `ppt-assembler`, `prototype-finalizer`, `app-builder`, `reverse-engineer` agents).
- Postgres for ~1500 active users at steady state is ~1 GB on disk and ~512 MB shared_buffers (we'll tune to 4 GB shared_buffers; see §8.4).
- Next.js production server idles around 200 MB; uvicorn + FastAPI idles around 150 MB; nginx well under 50 MB.

A reasonable steady-state budget on `m6i.2xlarge` (32 GB RAM):

| Component | Reserved RAM |
|---|---|
| Linux kernel + system services | 1.0 GB |
| nginx | 0.1 GB |
| Postgres (`shared_buffers=8GB`, plus work_mem etc.) | 9.0 GB |
| Next.js (`next start`) | 0.4 GB |
| FastAPI baseline | 0.2 GB |
| Per-pipeline working memory | 21.3 GB (≈ 200 concurrent pipelines if each holds 100 MB) |

That gives a **comfortable headroom of ~200 concurrent active pipelines** before swap pressure starts (double the `m6i.xlarge` ceiling per WORKFLOWS.md §B7's ~100 MB/pipeline memory profile). With chat sessions (cheaper, short-lived agent calls) the practical concurrency is higher: ~300–400 *connected* WebSocket sessions, ~100 of which can be running heavy pipelines simultaneously — well above the 6–7 concurrent heavy pipelines we sized for. If you need more, vertical scale to `m6i.4xlarge` (16 vCPU / 64 GB) before you split the topology.

### 5.2 AMI choice

Use the **official Canonical Ubuntu 24.04 LTS** AMI (Noble Numbat). At time of writing the AMI ID in `eu-central-1` is published at `https://ubuntu.com/server/docs/cloud-images/amazon-ec2`; resolve it dynamically:

```bash
aws ec2 describe-images \
  --region eu-central-1 \
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
      "Resource": "arn:aws:ssm:eu-central-1:<ACCOUNT_ID>:parameter/flowin/prod/*"
    },
    {
      "Sid": "ParameterStoreKMS",
      "Effect": "Allow",
      "Action": ["kms:Decrypt"],
      "Resource": "arn:aws:kms:eu-central-1:<ACCOUNT_ID>:key/<PARAMETER_STORE_KMS_KEY_ID>",
      "Condition": {
        "StringEquals": {"kms:EncryptionContext:PARAMETER_ARN": "arn:aws:ssm:eu-central-1:<ACCOUNT_ID>:parameter/flowin/prod/*"}
      }
    },
    {
      "Sid": "BackupBucketWrite",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:PutObjectAcl",
        "s3:AbortMultipartUpload",
        "s3:ListMultipartUploadParts"
      ],
      "Resource": [
        "arn:aws:s3:::flowin-prod-backups/postgres/*",
        "arn:aws:s3:::flowin-prod-backups/skills/*"
      ]
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
        "arn:aws:bedrock:eu-central-1::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
        "arn:aws:bedrock:*::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
        "arn:aws:bedrock:eu-central-1:*:inference-profile/eu.anthropic.claude-haiku-4-5-20251001-v1:0"
      ],
      "Condition": {
        "StringEquals": {
          "aws:RequestedRegion": ["eu-central-1", "eu-west-1", "eu-west-2"]
        }
      }
    }
  ]
}
```

The second resource ARN with `*` for region is required because the cross-region inference profile fans invocations out to multiple regions (e.g. `eu-central-1`, `eu-west-1`, `eu-west-2`); the IAM check evaluates against the eventual target region's foundation-model ARN, so the wildcard is mandatory for the profile to work. Keep it scoped to the *exact* `claude-haiku-4-5` model — never broaden to `anthropic.*` or `*`.

The `aws:RequestedRegion` condition pins invocation to the EU regions the cross-region inference profile fans to — without it a leaked instance credential could invoke Bedrock in any region the account has Bedrock enabled, which is a real cost vector. The list must match the EU profile's fan-out set; if AWS adds another EU region to the profile, update both this doc and `infra/policies/bedrock-invoke.json`. Reference: <https://docs.aws.amazon.com/bedrock/latest/userguide/cross-region-inference.html>.

Notes:

- The `Resource: "*"` on the CloudWatch Agent block is unavoidable (CloudWatch and EC2-describe APIs do not support resource-level scoping for these actions). The blast radius is limited to log/metric write and instance metadata read — both safe.
- The S3 statement is *write-only* under two prefixes (`postgres/` for `pg_dump` uploads and `skills/` for the skills tarball). The instance cannot enumerate the bucket, cannot read either prefix back, cannot get bucket location, cannot delete. Multipart upload completion (`AbortMultipartUpload`, `ListMultipartUploadParts`) is permitted under the same two prefixes only. Backup retention/expiry is enforced by S3 lifecycle policy (§11). DR restore (which needs `s3:GetObject`) is a different identity — see §11.3.
- KMS decrypt is split into four narrowly-scoped statements: SSM SecureStrings (gated on `kms:EncryptionContext:PARAMETER_ARN`), EBS volumes (gated on `kms:ViaService = ec2.<region>.amazonaws.com`), S3 backup PUTs (gated on `kms:ViaService = s3.<region>.amazonaws.com`), and CloudWatch Logs streams (gated on `kms:ViaService = logs.<region>.amazonaws.com` plus the `aws:logs:arn` encryption context). The role no longer holds an unconditional `kms:DescribeKey` on the project CMK. A leaked AWS credential cannot lift a Parameter Store value that was put with a different context, cannot decrypt EBS or S3 objects directly (only via the integrated services), and cannot read foreign log streams.
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
  --region eu-central-1
aws kms create-alias \
  --alias-name alias/flowin-prod-data \
  --target-key-id <KEY_ID> \
  --region eu-central-1
```

### 5.5 Launching the instance

```bash
aws ec2 run-instances \
  --region eu-central-1 \
  --image-id <AMI_ID_FROM_5.2> \
  --instance-type m6i.2xlarge \
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
  --query 'Reservations[0].Instances[0].InstanceId' --output text --region eu-central-1)

aws ec2 associate-address \
  --instance-id $INSTANCE_ID \
  --allocation-id <EIP_ALLOCATION_ID_FROM_§4_step_9> \
  --region eu-central-1
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
  --region eu-central-1

aws ec2 create-subnet \
  --vpc-id <VPC_ID> \
  --cidr-block 10.20.1.0/24 \
  --availability-zone eu-central-1a \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=flowin-prod-public-2a}]' \
  --region eu-central-1

aws ec2 create-internet-gateway \
  --tag-specifications 'ResourceType=internet-gateway,Tags=[{Key=Name,Value=flowin-prod-igw}]' \
  --region eu-central-1

aws ec2 attach-internet-gateway --vpc-id <VPC_ID> --internet-gateway-id <IGW_ID> --region eu-central-1

aws ec2 create-route-table --vpc-id <VPC_ID> \
  --tag-specifications 'ResourceType=route-table,Tags=[{Key=Name,Value=flowin-prod-public-rt}]' \
  --region eu-central-1
aws ec2 create-route --route-table-id <RT_ID> --destination-cidr-block 0.0.0.0/0 --gateway-id <IGW_ID> --region eu-central-1
aws ec2 associate-route-table --route-table-id <RT_ID> --subnet-id <SUBNET_ID> --region eu-central-1

aws ec2 modify-subnet-attribute --subnet-id <SUBNET_ID> --map-public-ip-on-launch --region eu-central-1
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
  --region eu-central-1 \
  --query 'GroupId' --output text)

# Inbound 80/tcp from world (HTTP -> HTTPS redirect + ACME challenge)
aws ec2 authorize-security-group-ingress --group-id $SG_ID \
  --protocol tcp --port 80 --cidr 0.0.0.0/0 --region eu-central-1

# Inbound 443/tcp from world (HTTPS, WSS)
aws ec2 authorize-security-group-ingress --group-id $SG_ID \
  --protocol tcp --port 443 --cidr 0.0.0.0/0 --region eu-central-1

# Inbound 22/tcp ONLY from the bastion / corporate egress CIDR
# Replace <BASTION_CIDR> with the team's egress IP/32 or corporate VPN CIDR.
# This is a hardline rule. SSH from anywhere = automatic credential-stuffing.
aws ec2 authorize-security-group-ingress --group-id $SG_ID \
  --protocol tcp --port 22 --cidr <BASTION_CIDR>/32 --region eu-central-1

# Outbound: 443/tcp to anywhere (apt, GitHub, S3, Bedrock fallback path).
# Bedrock traffic normally goes via the VPC interface endpoint (§6.4) and stays
# inside the VPC; the 0.0.0.0/0:443 egress rule is required for apt + GitHub
# + Bedrock-fallback only.
# 80/tcp to anywhere (apt, Let's Encrypt OCSP)
# Default sg has 0.0.0.0/0 all-egress; replace it with explicit rules:
aws ec2 revoke-security-group-egress --group-id $SG_ID \
  --protocol -1 --port -1 --cidr 0.0.0.0/0 --region eu-central-1
aws ec2 authorize-security-group-egress --group-id $SG_ID \
  --protocol tcp --port 443 --cidr 0.0.0.0/0 --region eu-central-1
aws ec2 authorize-security-group-egress --group-id $SG_ID \
  --protocol tcp --port 80 --cidr 0.0.0.0/0 --region eu-central-1
# DNS — VPC resolver lives at the VPC's +2 address but UDP/53 outbound is also needed
aws ec2 authorize-security-group-egress --group-id $SG_ID \
  --protocol udp --port 53 --cidr 0.0.0.0/0 --region eu-central-1
aws ec2 authorize-security-group-egress --group-id $SG_ID \
  --protocol tcp --port 53 --cidr 0.0.0.0/0 --region eu-central-1
```

**SSH ingress is the most-abused vector on the public internet.** Locking it to `<BASTION_CIDR>/32` is the single most valuable rule on the list. If you do not have a bastion or a corporate VPN egress IP, drop the SSH ingress rule entirely and use **Systems Manager Session Manager** for shell access (§8.1) — it requires zero open ports.

### 6.3 Egress posture for non-AWS traffic

The non-AWS egress requirements after migration to Bedrock are:

- **apt repos** (Ubuntu archive + Canonical security) — TCP/443 (and a small amount of TCP/80 for repo metadata).
- **GitHub releases** — TCP/443 (`github.com`, `objects.githubusercontent.com`, `codeload.github.com`).
- **Let's Encrypt** — TCP/80 (HTTP-01 challenge inbound) + TCP/443 (OCSP outbound).
- **Bedrock public endpoint as fallback** — TCP/443 to `bedrock-runtime.eu-central-1.amazonaws.com` *only if* the VPC interface endpoint (§6.4) is unavailable.

These all share Cloudflare-/CDN-style fronts whose IPs rotate, so pinning egress to specific IPs *will* break in production. Egress filtering instead happens at the application layer: only the backend, the apt updater, certbot, and the AWS SDK make outbound calls — no other process on the box can reach the internet because it is firewalled by ufw (§8.1).

**Free S3 gateway endpoint.** Add this regardless — it stops the backup path from depending on internet egress and costs nothing:

```bash
aws ec2 create-vpc-endpoint \
  --vpc-id <VPC_ID> \
  --service-name com.amazonaws.eu-central-1.s3 \
  --route-table-ids <RT_ID> \
  --region eu-central-1
```

For Bedrock (the LLM data path) we go further and provision interface endpoints — see §6.4.

### 6.4 Bedrock VPC interface endpoints

Provision two interface endpoints in the VPC so that Bedrock traffic never leaves AWS:

- `com.amazonaws.eu-central-1.bedrock-runtime` — used by `InvokeModel`, `InvokeModelWithResponseStream`, `Converse`, `ConverseStream`. **This is the one the application uses at runtime.**
- `com.amazonaws.eu-central-1.bedrock` — management plane, rarely needed at runtime; useful for `aws bedrock list-foundation-models`, model discovery, and operator diagnostics. Provision it for completeness; if budget is tight you can drop this one and only keep `bedrock-runtime`.

```bash
# Runtime endpoint — required.
aws ec2 create-vpc-endpoint \
  --vpc-id <VPC_ID> \
  --service-name com.amazonaws.eu-central-1.bedrock-runtime \
  --vpc-endpoint-type Interface \
  --subnet-ids <SUBNET_ID> \
  --security-group-ids $SG_ID \
  --private-dns-enabled \
  --region eu-central-1

# Management endpoint — recommended, drop if cost-pressured.
aws ec2 create-vpc-endpoint \
  --vpc-id <VPC_ID> \
  --service-name com.amazonaws.eu-central-1.bedrock \
  --vpc-endpoint-type Interface \
  --subnet-ids <SUBNET_ID> \
  --security-group-ids $SG_ID \
  --private-dns-enabled \
  --region eu-central-1
```

**Why the public subnet?** The endpoints attach to the same public subnet as the EC2 instance — acceptable for our single-AZ minimum-footprint design. The `--private-dns-enabled` flag overrides the public DNS name for `bedrock-runtime.eu-central-1.amazonaws.com` so the `boto3` SDK uses the endpoint transparently with no application config changes.

**Cost.** ~$7.30/mo per AZ per endpoint (≈ $0.01/hr per AZ) plus $0.01/GB data processed. With one AZ and two endpoints that's ~$15/mo all-in; data charges are negligible at our throughput (a few GB/mo of LLM token traffic).

**Net effect on the security group.** Outbound 443 to `bedrock-runtime.eu-central-1.amazonaws.com` no longer leaves the VPC — that's the point. Combined with this, the `0.0.0.0/0:443` SG egress rule is still needed for apt, GitHub releases, and the Bedrock public-endpoint fallback path, but **the LLM data path itself is now private**. Document this explicitly when responding to compliance questionnaires: "no LLM request or response leaves the AWS network boundary in normal operation."

**Cross-region inference profile note.** When you invoke via `eu.anthropic.claude-haiku-4-5-20251001-v1:0`, Bedrock fans the actual model invocation out to one of the EU regions (`eu-west-1`, `eu-west-2`, `eu-central-1`, etc.). The fan-out happens *inside* AWS — your traffic from the EC2 still terminates at the `eu-central-1` interface endpoint; Bedrock handles the cross-region hop on its own backbone. You do not need additional interface endpoints in other regions.

Optional hardening for paranoid environments: put a Squid or `nginx` egress proxy on the box and configure the application to use `HTTPS_PROXY=http://127.0.0.1:3128`, with the proxy's domain allowlist set to apt + GitHub + the Bedrock public hostname. This is out of scope for the simple-deployment promise but trivially added later.

---

## 7. DNS & TLS — nip.io / Route 53, certbot/Let's Encrypt

### 7.1 The two DNS paths

This stack supports two DNS strategies, picked at apply time via `var.use_nip_io` (in `infra/envs/prod/`):

#### Path A — nip.io (default; no real DNS)

`use_nip_io = true` (the current default in `terraform.tfvars.example`).

The FQDN is **computed from the Elastic IP** by the `dns` Terraform module:

> **EIP `1.2.3.4`** → **`1-2-3-4.nip.io`** (dots in the IP become hyphens in the host label).

Why this works:

- **nip.io** is a magic-DNS service whose authoritative servers run a wildcard rule: any subdomain of the form `<dashed-ip>.nip.io` resolves to that exact IP. No zone provisioning, no A record, no propagation delay.
- nip.io is on the **Public Suffix List** (`https://publicsuffix.org/list/`), which Let's Encrypt's CA accepts as a valid eTLD parent. HTTP-01 challenges against `1-2-3-4.nip.io` issue real, browser-trusted TLS certs.
- The Terraform `dns` module creates **zero AWS resources** in this path: no Route 53 zone, no record. The single output is `module.dns.fqdn` = `1-2-3-4.nip.io`. The bootstrap script (Appendix D) reads this from `/etc/flowin/bootstrap.env` and uses it for nginx `server_name`, certbot, and the Next.js build's public URL.

When to pick this path:

- Sandbox / proof-of-concept deployments where the customer doesn't have a custom domain yet.
- Internal demos where running an HTTPS hostname matters but registrar provisioning is friction.
- Any deployment where DNS configuration is out-of-band or hasn't been completed yet.

Limitations (read these before recommending nip.io to a customer):

- The hostname is **not memorable** — it embeds the EIP. If the EIP is ever released and re-allocated, the FQDN changes (the EIP has `prevent_destroy = true` so this is hard, but operators should know the failure mode).
- Email DKIM/SPF, SaaS allowlists, and corporate egress filters that work on hostname rather than IP may not whitelist `*.nip.io`. The browser-facing path works; sending mail _from_ this FQDN is not supported anyway (we don't run an MTA).
- The third-party operator (nipio LLC) controls the resolver. If `nip.io` itself ever fails, name resolution fails. Public IP path still works directly. We accept this for the no-DNS use case.

#### Path B — Route 53 (custom domain)

`use_nip_io = false`. Set `route53_zone_name` and `app_subdomain` in tfvars. The zone must **already exist** in this account; this Terraform never creates a zone (the resource type is forbidden in the shared account — see `infra/README.md`). The module looks up the zone via `data "aws_route53_zone"` and writes a single A record.

```bash
# (Done by Terraform — no manual aws-cli call needed when use_nip_io = false.
# The aws-cli equivalent below is for operator-side verification.)
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

- **Let's Encrypt + certbot** (recommended): free, 90-day rotation, automated. The HTTP-01 challenge requires port 80 reachable from the public internet — which we already need for the HTTPS redirect. Renewal runs as a systemd timer (Appendix B). Works equally for nip.io and custom-domain paths because both expose a hostname that resolves to the EIP.
- **AWS Private CA + ACM** (~$400/month for a CA + cert issuance): only justified if you must have certificates issued by your own CA chain. Massively over-budget for this deployment.
- **Bring-your-own-cert from DigiCert / Sectigo**: fine, but adds a manual rotation chore. Pick this only if the customer has a corporate cert procurement they are committed to. (Not applicable to the nip.io path — the upstream CAs only issue to domains the customer owns.)

**Decision: Let's Encrypt + certbot.**

Install (in the bootstrap; see Appendix D). `$FLOWIN_FQDN` comes from `/etc/flowin/bootstrap.env`, which Terraform writes via the `user_data_extra_env` mechanism (compute module). It's the same value whether the deployment uses nip.io or a custom domain.

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx \
  -d "$FLOWIN_FQDN" \
  --non-interactive --agree-tos \
  --email security@example.com \
  --redirect --hsts --staple-ocsp
```

`certbot --nginx` will rewrite the nginx config to add the `ssl_certificate` and `ssl_certificate_key` directives and the HTTP→HTTPS redirect block. Verify the resulting nginx config matches Appendix A; if certbot's auto-edit clashes with our config, supply a pre-prepared nginx config first and use `certbot certonly --webroot -w /var/www/letsencrypt -d "$FLOWIN_FQDN"` instead.

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

After deployment, validate against SSL Labs (`https://www.ssllabs.com/ssltest/analyze.html?d=$FLOWIN_FQDN`). Target **A+**. Substitute the actual FQDN — the same URL works for nip.io and custom-domain hostnames.

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
aws ssm start-session --target $INSTANCE_ID --region eu-central-1
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

> Nginx upstreams `127.0.0.1:8000` (backend) and `127.0.0.1:3000` (frontend) are now Docker port mappings — the containers bind to those ports on the loopback interface (`docker-compose.yml` uses `127.0.0.1:8000:8000` / `127.0.0.1:3000:3000`). The nginx config is unchanged from the pre-Docker version: the same upstream URLs work, since Docker Compose's port mapping is transparent to the proxy.

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

### 8.3 systemd unit for the app stack (Docker Compose)

The backend and frontend run as containers managed by a single systemd unit, `flowin-app.service`, which delegates to `docker compose`. Postgres has its own native unit (`postgresql@16-main.service`, §8.4) and nginx has `nginx.service` (§8.2 and Appendix A) — those are unchanged from the pre-Docker design.

**Why one unit, not two.** Docker Compose already orchestrates start ordering (the frontend's `depends_on: backend` with `condition: service_healthy`) and per-container restart policies (`restart: unless-stopped`). Splitting into two systemd units would duplicate that orchestration in two places and create races between systemd's `After=`/`Requires=` graph and Compose's healthcheck-driven start order. One unit, one source of truth.

**Why `Type=oneshot` + `RemainAfterExit=yes`.** `docker compose up -d` exits immediately once the containers are detached; we need systemd to mark the unit "active" at that point and then leave Docker to manage the actual container lifecycles via its own restart policies. A long-running `Type=simple`/`Type=exec` would block on a process that has already detached.

Key properties of the unit:

- `Type=oneshot` + `RemainAfterExit=yes` — systemd marks the unit "active" once `docker compose up -d` returns; the Docker daemon then keeps the containers running.
- `EnvironmentFile=/etc/flowin/app.env` — populated on every start by `ExecStartPre=/usr/local/bin/flowin-load-secrets` (same SSM-pull mechanism as the native version, just renamed from `flowin.env` to `app.env`). The file is also picked up by Compose's `env_file:` so backend container env stays in sync.
- `ExecStartPre=/usr/bin/docker compose pull` — refreshes images from ECR before bringing them up. (No-op locally if `BACKEND_IMAGE` / `FRONTEND_IMAGE` aren't set; `docker compose up` falls back to the local `flowin-backend:local` / `flowin-frontend:local` tags built from the source tree.)
- `ExecStart=/usr/bin/docker compose up -d --remove-orphans` — `--remove-orphans` cleans up any stale containers from a previous compose definition (e.g. an old `redis` service we removed).
- `ExecStop=/usr/bin/docker compose down` — graceful stop; honours each service's `stop_grace_period:` (30 s on backend so uvicorn drains in-flight WS frames).
- `ExecReload=/usr/bin/docker compose restart` — wired so `systemctl reload flowin-app` is the operator-facing knob.
- `WorkingDirectory=/opt/flowin` — the compose file lives there; bootstrap copies it from the repo on first deploy.

Hardening at the systemd level is intentionally light here because the security boundary is the container, not the unit. The Dockerfiles (`backend/Dockerfile`, `frontend/Dockerfile`) already enforce `USER 10001:10001`, drop unnecessary packages, and the daemon applies the default seccomp profile and capability set. Re-asserting `NoNewPrivileges=` etc. on a unit that just calls `docker compose` would constrain Docker itself, not the workload.

Keep `Restart=on-failure` (with `RestartSec=30s`) so a `docker compose` failure (e.g. ECR auth token expired between the `pull` and `up`, or a transient daemon hiccup) bounces the unit instead of leaving the host in a half-up state.

**Crucial detail about `NEXT_PUBLIC_*`:** these vars are **inlined at build time** in Next.js. You cannot change them via the runtime container env. They are passed to the frontend image as `--build-arg NEXT_PUBLIC_API_URL=...` and `--build-arg NEXT_PUBLIC_WS_URL=...` in CI (see §12.1) so the image is bound to the FQDN of the environment it will run in. Once the image is built, the EC2 just pulls and runs it — the systemd unit never touches those variables.

Enable:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now flowin-app.service
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

The `flowin` user no longer owns a Python venv or a frontend build — those live inside the container images, built in CI (§12). The host-side responsibilities of the user are:

1. Owning the bind-mount target `/opt/flowin/data/skills` so files written by the in-container UID 10001 survive container restarts and stay readable for the skills-backup timer.
2. Owning the compose file at `/opt/flowin/docker-compose.yml`.
3. Running the host-side timers (`flowin-pg-dump`, `flowin-skills-backup`, `flowin-stuck-workflows-check`).

The `flowin-app.service` itself runs as **root** (it needs to talk to the Docker socket); the workload inside each container drops to UID 10001 via the Dockerfiles' `USER` directive. Don't add the `flowin` user to the `docker` group — Docker socket access is root-equivalent and we keep that to the systemd-managed flow only.

For Next.js standalone output, the frontend repo already has `output: "standalone"` in `frontend/next.config.ts`. The frontend Dockerfile depends on this — no host-side action.

Permissions:

```
/opt/flowin                       drwxr-xr-x flowin:flowin
/opt/flowin/data/skills           drwxr-xr-x flowin:flowin   # bind-mounted RW into backend container (UID 10001)
/opt/flowin/docker-compose.yml    -rw-r--r-- flowin:flowin
/etc/flowin                       drwxr-x--- root:flowin
/etc/flowin/app.env               -rw-r----- root:flowin (mode 0640)
/etc/flowin/bootstrap.env         -rw-r----- root:flowin (mode 0640)
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
  --region eu-central-1 \
  --name /flowin/prod/SECRET_KEY \
  --type SecureString \
  --value "$(openssl rand -hex 64)" \
  --key-id alias/flowin-prod-data \
  --overwrite

# DATABASE_PASSWORD only — the on-host loader composes DATABASE_URL from this
# value (postgresql://flowin:<pw>@127.0.0.1:5432/flowin). Terraform doesn't
# write DATABASE_URL because it doesn't know about the on-host Postgres.
aws ssm put-parameter \
  --region eu-central-1 \
  --name /flowin/prod/DATABASE_PASSWORD \
  --type SecureString \
  --value "<openssl rand -hex 32 output>" \
  --key-id alias/flowin-prod-data \
  --overwrite

aws ssm put-parameter \
  --region eu-central-1 \
  --name /flowin/prod/CORS_ORIGINS \
  --type String \
  --value '["https://flowin.example.com"]' \
  --overwrite

aws ssm put-parameter \
  --region eu-central-1 \
  --name /flowin/prod/ACCESS_TOKEN_EXPIRE_HOURS \
  --type String \
  --value "12" \
  --overwrite

# LLM provider config — selects Bedrock and pins the model. Stored as plain
# String (not secret), but kept in Parameter Store so all runtime config lives
# in one place and a model swap doesn't require a redeploy.
aws ssm put-parameter \
  --region eu-central-1 \
  --name /flowin/prod/llm/provider \
  --type String \
  --value "bedrock" \
  --overwrite

aws ssm put-parameter \
  --region eu-central-1 \
  --name /flowin/prod/llm/region \
  --type String \
  --value "eu-central-1" \
  --overwrite

aws ssm put-parameter \
  --region eu-central-1 \
  --name /flowin/prod/llm/model_id \
  --type String \
  --value "eu.anthropic.claude-haiku-4-5-20251001-v1:0" \
  --overwrite
```

**Note:** there is no required `/flowin/prod/ANTHROPIC_API_KEY` in normal operation — auth to Bedrock is via the EC2 instance-profile role (§5.3). For the optional emergency fallback, see the entry at the end of this section.

(Optional, only if LangSmith is enabled:)

```bash
aws ssm put-parameter --region eu-central-1 --name /flowin/prod/LANGSMITH_API_KEY \
  --type SecureString --value "lsv2_pt_..." --key-id alias/flowin-prod-data --overwrite
```

**Optional emergency-fallback entry** — only populated during a Bedrock outage:

```bash
# Empty placeholder. Populate ONLY during a Bedrock regional outage; flip
# /flowin/prod/llm/provider to "anthropic" and restart the backend. The
# application code reads LLM_PROVIDER and switches between bedrock and
# direct-Anthropic backends.
aws ssm put-parameter \
  --region eu-central-1 \
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
# preserved from the previous app.env (it's written once by the bootstrap
# script — see Appendix D §8c — and persists across loader runs via the
# `BACKEND_IMAGE|FRONTEND_IMAGE|ENV` preserve clause below).
set -euo pipefail

OUT=/etc/flowin/app.env
TMP=$(mktemp /etc/flowin/app.env.XXXXXX)
chmod 0640 "$TMP"
chown root:flowin "$TMP"

REGION=eu-central-1
PREFIX=/flowin/prod

# Preserve operator-managed image-tag pins from the previous app.env. Lines
# starting with BACKEND_IMAGE= or FRONTEND_IMAGE= are CI-managed (the deploy
# step seds them in place) — we don't want a load-secrets run to clobber a
# freshly deployed tag.
if [[ -f "$OUT" ]]; then
    grep -E '^(BACKEND_IMAGE|FRONTEND_IMAGE|ENV)=' "$OUT" >> "$TMP" || true
fi

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
            # host.docker.internal resolves inside the backend container to
            # the host gateway (mapped via extra_hosts in docker-compose.yml).
            # Host-side scripts (flowin-stuck-workflows-check) substitute
            # this back to 127.0.0.1 before invoking psql.
            emit DATABASE_URL "postgresql://flowin:${value}@host.docker.internal:5432/flowin" ;;
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

The `flowin` user has read access to the env file (group-read), but not write. Compose reads `/etc/flowin/app.env` via the `env_file:` block in `docker-compose.yml`, the secret values land in the backend container's environment, and the application reads `os.environ` at boot.

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
      "disk":   {"measurement": ["used_percent","inodes_free_percent"], "resources": ["/", "/var/lib/postgresql"], "metrics_collection_interval": 60},
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
          {"file_path": "/var/log/unattended-upgrades/unattended-upgrades.log", "log_group_name": "/flowin/prod/system", "log_stream_name": "{instance_id}", "timezone": "UTC"},
          {"file_path": "/var/log/letsencrypt/letsencrypt.log", "log_group_name": "/flowin/prod/letsencrypt", "log_stream_name": "{instance_id}", "timezone": "UTC"}
        ]
      }
    }
  }
}
```

Application logs are now written to stdout by uvicorn / `next` *inside* their containers; the Docker daemon's `json-file` log driver captures them in `/var/lib/docker/containers/<id>/<id>-json.log`. The CloudWatch agent tails those files (rather than journald) and tags each stream with the container name, so backend and frontend land in distinct streams in `/flowin/prod/app`:

```json
"files": {
  "collect_list": [
    /* ... existing nginx/postgres/auth entries ... */
    {
      "file_path":      "/var/lib/docker/containers/*/*-json.log",
      "log_group_name": "/flowin/prod/app",
      "log_stream_name": "{instance_id}/docker",
      "timezone": "UTC"
    }
  ]
}
```

(Add this under `logs.logs_collected.files` in the same config — the existing `journald` block can stay for systemd-managed services like sshd; the application-log path no longer goes through journald.)

**File-permission requirement.** Docker daemon writes JSON logs as `root:root 0640` by default — the `cwagent` user cannot read them out of the box. Adding `cwagent` to the `docker` group is the obvious fix but it grants *full* Docker socket access (root-equivalent), which is too broad. The right fix is a POSIX ACL granting `cwagent` read+traverse on the directory and a default ACL so newly-created log files inherit the same:

```bash
sudo apt-get install -y acl
sudo setfacl -R -m u:cwagent:rX /var/lib/docker/containers
sudo setfacl -R -d -m u:cwagent:rX /var/lib/docker/containers
```

The bootstrap script (Appendix D) does this automatically right after the Docker install. If you skip it, the CloudWatch agent runs without errors but quietly captures zero application log lines — silent failure, so test once with `aws logs tail /flowin/prod/app --since 5m` after a deploy.

Alternatively, run a sidecar like `vector` or use the AWS CloudWatch Logs Docker logging driver (`awslogs`) per service in `docker-compose.yml`. The file-tail approach above keeps the local `docker compose logs` tool working for ad-hoc debugging, which is why we recommend it.

Apply:

```bash
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config -m ec2 -s -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
sudo systemctl enable --now amazon-cloudwatch-agent
```

### 10.2 Log retention

Set a sane retention on every log group. The default is "Never expire", which is bad for cost and for GDPR posture:

```bash
# Terraform's monitoring module sets retention on seven groups
# (nginx-access, nginx-error, app, postgres, system, auth, letsencrypt).
# Per-group overrides via `var.log_retention_overrides` (Audit D P2-5):
#   - /flowin/prod/nginx-access: 7d  (high churn, low forensic value)
#   - /flowin/prod/auth:         90d (forensics — sshd / sudo events)
#   - others:                    var.log_retention_days (default 30d)
# The loop below is the equivalent CLI form for ad-hoc verification.
for lg in /flowin/prod/nginx-access /flowin/prod/nginx-error \
          /flowin/prod/app /flowin/prod/postgres \
          /flowin/prod/system /flowin/prod/auth \
          /flowin/prod/letsencrypt; do
  aws logs put-retention-policy --region eu-central-1 \
    --log-group-name "$lg" --retention-in-days 90
done
```

The split balances forensic value against cost. nginx-access is the largest by volume (~$3/month at 100 req/sec) and the lowest in forensic value (the same data shows up in CloudFront access logs / app traces); auth gets the long retention because sshd / sudo events are what an investigator wants on day-30 of an incident.

The `letsencrypt` log group (new in Phase 3) backs the cert-renew failure and renewal-heartbeat alarms — see §10.3 alarms 12a/12b.

### 10.3 Alarms

Eighteen alarms in total — eight infra alarms below (1–8), three Bedrock-specific alarms in §10.4 (9–11), the WS-disconnect spike + Bedrock-tokens-daily + pg-dump heartbeat from Phase 2 (which Terraform owns), and six Phase 3 hardening alarms (12a/b–15a/b — covered by Terraform; see `infra/modules/monitoring/main.tf` for canonical definitions). Each fires to an SNS topic (`flowin-prod-alerts`) which fans out to PagerDuty / Slack / email per the on-call setup.

Phase 3 additions (Audit D P2-2, P2-3, P3-4, P3-12 + Phase 3 item 21):

| # | Alarm | What it catches |
|---|---|---|
| 12a | `cert-renew-failure` | certbot logged "Failed to renew" or "All renewals failed" — cert about to expire |
| 12b | `cert-renew-heartbeat-stale` | No certbot activity in /var/log/letsencrypt/* for 30 days — timer is stuck |
| 13 | `agent-error-high` | `>20 agent_error events / 5-min` for 2 windows — Bedrock throttling, prompt regression, cancel-storm |
| 14 | `stuck-running-workflows` | WorkflowRun rows in `running` for >60 min — orchestrator crash / DB drop / A4 regression |
| 15a/b | `inode-low-` (root + data) | `disk_inodes_free_percent < 20%` per disk — many small files, runaway logs, ENOSPC about to bite |

Alarm 14 is fed by a small SQL probe (a new systemd timer; see Appendix B.6 below) that publishes the count to CloudWatch every 15 min. The IAM instance role already grants `cloudwatch:PutMetricData` on `Resource:*` (documented exception — that API doesn't support resource-level scoping).

Alarm 16 (Bedrock throttle threshold tuning, Audit D P3-12): the original `bedrock_throttles` alarm fired at threshold=0 (any single throttle in 5 min). Phase 3 makes it tunable via `var.bedrock_throttles_threshold` (default 5) and `var.bedrock_throttles_evaluation_periods` (default 2) — bursty quota pressure auto-recovers after backoff; only sustained pressure pages.

```bash
# 1. CPU pegged (sustained throttle)
aws cloudwatch put-metric-alarm --region eu-central-1 \
  --alarm-name flowin-prod-cpu-high \
  --metric-name cpu_usage_idle --namespace Flowin/Prod \
  --statistic Average --period 300 --evaluation-periods 3 \
  --threshold 20 --comparison-operator LessThanThreshold \
  --alarm-actions <SNS_TOPIC_ARN> \
  --dimensions Name=InstanceId,Value=$INSTANCE_ID

# 2. Memory pressure
aws cloudwatch put-metric-alarm --region eu-central-1 \
  --alarm-name flowin-prod-mem-high \
  --metric-name mem_used_percent --namespace Flowin/Prod \
  --statistic Average --period 300 --evaluation-periods 2 \
  --threshold 85 --comparison-operator GreaterThanThreshold \
  --alarm-actions <SNS_TOPIC_ARN> \
  --dimensions Name=InstanceId,Value=$INSTANCE_ID

# 3. Root disk near full
aws cloudwatch put-metric-alarm --region eu-central-1 \
  --alarm-name flowin-prod-disk-root-high \
  --metric-name used_percent --namespace Flowin/Prod \
  --statistic Maximum --period 300 --evaluation-periods 2 \
  --threshold 80 --comparison-operator GreaterThanThreshold \
  --alarm-actions <SNS_TOPIC_ARN> \
  --dimensions Name=InstanceId,Value=$INSTANCE_ID Name=path,Value=/

# 4. Postgres data disk near full (this is the dangerous one)
aws cloudwatch put-metric-alarm --region eu-central-1 \
  --alarm-name flowin-prod-disk-pgdata-high \
  --metric-name used_percent --namespace Flowin/Prod \
  --statistic Maximum --period 300 --evaluation-periods 2 \
  --threshold 75 --comparison-operator GreaterThanThreshold \
  --alarm-actions <SNS_TOPIC_ARN> \
  --dimensions Name=InstanceId,Value=$INSTANCE_ID Name=path,Value=/var/lib/postgresql

# 5. nginx 5xx surge — derived metric from a log filter
aws logs put-metric-filter --region eu-central-1 \
  --log-group-name /flowin/prod/nginx-access \
  --filter-name "5xx-responses" \
  --filter-pattern '[ip, id, user, ts, request, status_code=5*, ...]' \
  --metric-transformations 'metricName=Nginx5xx,metricNamespace=Flowin/Prod,metricValue=1'
aws cloudwatch put-metric-alarm --region eu-central-1 \
  --alarm-name flowin-prod-nginx-5xx-spike \
  --metric-name Nginx5xx --namespace Flowin/Prod \
  --statistic Sum --period 60 --evaluation-periods 5 \
  --threshold 10 --comparison-operator GreaterThanThreshold \
  --alarm-actions <SNS_TOPIC_ARN>
# 10 5xx in any 1-minute window for 5 minutes is an outage signal.

# 6. WebSocket disconnect spike — derived from journald app logs
aws logs put-metric-filter --region eu-central-1 \
  --log-group-name /flowin/prod/app \
  --filter-name "ws-disconnects" \
  --filter-pattern 'WebSocketDisconnect' \
  --metric-transformations 'metricName=WSDisconnects,metricNamespace=Flowin/Prod,metricValue=1'
aws cloudwatch put-metric-alarm --region eu-central-1 \
  --alarm-name flowin-prod-ws-disconnect-spike \
  --metric-name WSDisconnects --namespace Flowin/Prod \
  --statistic Sum --period 60 --evaluation-periods 3 \
  --threshold 30 --comparison-operator GreaterThanThreshold \
  --alarm-actions <SNS_TOPIC_ARN>

# 7. Postgres down / connection failures
aws logs put-metric-filter --region eu-central-1 \
  --log-group-name /flowin/prod/app \
  --filter-name "db-connection-error" \
  --filter-pattern 'OperationalError ?could not connect' \
  --metric-transformations 'metricName=DBConnError,metricNamespace=Flowin/Prod,metricValue=1'
aws cloudwatch put-metric-alarm --region eu-central-1 \
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
aws cloudwatch put-metric-alarm --region eu-central-1 \
  --alarm-name flowin-prod-bedrock-throttles \
  --metric-name InvocationThrottles --namespace AWS/Bedrock \
  --statistic Sum --period 300 --evaluation-periods 1 \
  --threshold 0 --comparison-operator GreaterThanThreshold \
  --dimensions Name=ModelId,Value=eu.anthropic.claude-haiku-4-5-20251001-v1:0 \
  --alarm-actions <SNS_TOPIC_ARN>
# Any throttle in any 5-minute window is a quota signal — request an increase.

# 10. Bedrock server errors — Bedrock-side outage indicator
aws cloudwatch put-metric-alarm --region eu-central-1 \
  --alarm-name flowin-prod-bedrock-5xx \
  --metric-name InvocationServerErrors --namespace AWS/Bedrock \
  --statistic Sum --period 300 --evaluation-periods 1 \
  --threshold 5 --comparison-operator GreaterThanThreshold \
  --dimensions Name=ModelId,Value=eu.anthropic.claude-haiku-4-5-20251001-v1:0 \
  --alarm-actions <SNS_TOPIC_ARN>
# >5 5xx in 5 minutes — likely a Bedrock regional fault. Consider flipping to
# the optional Anthropic-direct fallback (see §0.1, §9).

# 11. Bedrock input-token daily total — cost runaway detector
aws cloudwatch put-metric-alarm --region eu-central-1 \
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
- The skills directory (`/opt/flowin/data/skills`) — small, but custom user content. Bind-mounted into the backend container; lives on the EBS data volume.
- The TLS cert + key (`/etc/letsencrypt`) — annoying to lose but recreatable in 5 min.

The OS root volume contains nothing irreplaceable; the bootstrap script can recreate it.

### 11.2 Two backup paths (belt and braces)

#### Path A — EBS snapshot of the data volume (AWS Backup)

```bash
aws backup create-backup-vault \
  --backup-vault-name flowin-prod-vault \
  --encryption-key-arn alias/flowin-prod-data \
  --region eu-central-1

aws backup create-backup-plan \
  --region eu-central-1 \
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
# injects these via user_data_extra_env in module.compute). app.env carries
# the application secrets; pg_dump doesn't need them but loading both is fine.
EnvironmentFile=/etc/flowin/bootstrap.env
EnvironmentFile=/etc/flowin/app.env
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
    --region eu-central-1 \
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
   - Installs nginx, postgres, Docker engine + Compose plugin, certbot, cloudwatch agent.
   - Mounts the data volume.
   - Authenticates to ECR and pulls the backend + frontend images.
   - Pulls secrets from Parameter Store into `/etc/flowin/app.env`.
   - Renews the Let's Encrypt cert if it's already in `/etc/letsencrypt/live/` (skip if old cert is fine).
   - Brings up `flowin-app.service` (which runs `docker compose up -d`), `nginx`, `postgresql@16-main`.
6. **Smoke test:** `curl https://flowin.example.com/health`. Click through `/login`, run a small pipeline.

**Wallclock target: 30 minutes.** Practiced quarterly during a maintenance window. Document the most recent drill date in the runbook.

If the data volume is also lost (region-wide outage, AZ failure), the recovery path is the same as above but step 1 becomes "create a new volume from the latest AWS Backup snapshot" (`aws backup start-restore-job ...`). RTO grows to ~45 min; RPO degrades to last-completed hourly `pg_dump` if the snapshot is older.

**Restore identity — must not be the production EC2 role.** The `pg_dump` recovery path needs `s3:GetObject` on the backup bucket and `kms:Decrypt` on the project CMK; the production EC2 instance role grants neither (the S3 backup policy is write-only under `postgres/` and `skills/`, and the KMS policy decrypts S3 only via the `s3.<region>.amazonaws.com` ViaService channel which doesn't help for direct GETs from a non-EC2 caller). A DR drill or real restore therefore runs from a different identity: either an operator's workstation using IAM-Identity-Center / SSO credentials with a "DR-restore" permission set, or a separate short-lived DR-drill EC2 with its own role. That role's permissions list `s3:GetObject` + `s3:ListBucket` on the backup bucket and `kms:Decrypt` on the project CMK conditioned on `kms:ViaService = s3.<region>.amazonaws.com`. Do not extend the production EC2 role to read its own backups — a compromised production instance could then exfiltrate every historical dump in one call.

### 11.4 What we explicitly do not back up

- Application logs in CloudWatch — they're already durable.
- LLM (Bedrock) responses — re-derivable on demand.
- Skills (small, low-churn) — *do* back up. The systemd unit in Appendix B.5 is the supported path (it sources `/etc/flowin/bootstrap.env` for `FLOWIN_BACKUP_BUCKET` and `FLOWIN_KMS_KEY_ID` and uploads with `--sse aws:kms`). The skills directory now lives at `/opt/flowin/data/skills` (the backend container's bind-mount target) instead of `/opt/flowin/src/backend/skills`. If you prefer cron for any reason, the equivalent line is:
  ```bash
  echo '0 4 * * * flowin . /etc/flowin/bootstrap.env && tar -czf - /opt/flowin/data/skills | aws s3 cp - s3://${FLOWIN_BACKUP_BUCKET}/skills/$(date -u +\%Y\%m\%d).tar.gz --region eu-central-1 --sse aws:kms --sse-kms-key-id $FLOWIN_KMS_KEY_ID' | sudo tee -a /etc/cron.d/flowin-skills-backup
  ```

---

## 12. Deployment / release procedure

### 12.1 Release pipeline (GitLab CI)

The project repo is `gitlab.com/hexaware-uki/flowin`. The release job lives in `.gitlab-ci.yml`. The pipeline now builds and pushes Docker images to ECR, then SSH's into the EC2 to point `/etc/flowin/app.env` at the new tags and restart the unit.

The minimal deploy job (test stages omitted for brevity — they run unchanged):

```yaml
# .gitlab-ci.yml (snippet)
build_and_deploy:
  stage: deploy
  image: docker:27
  services:
    - docker:27-dind
  variables:
    AWS_REGION:    eu-central-1
    ECR_REGISTRY:  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
    BACKEND_REPO:  $ECR_REGISTRY/flowin-prod-backend
    FRONTEND_REPO: $ECR_REGISTRY/flowin-prod-frontend
    TAG: v$(date +%Y%m%d)-$CI_COMMIT_SHORT_SHA
  before_script:
    - apk add --no-cache aws-cli openssh-client
    - aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"
  script:
    # FQDN comes from a CI variable populated by `terraform output -raw fqdn`
    # (the Terraform CI job runs first; the value is published as $DEPLOY_FQDN).
    - docker build -t $BACKEND_REPO:$TAG  backend/
    - docker build -t $FRONTEND_REPO:$TAG --build-arg NEXT_PUBLIC_API_URL=https://$DEPLOY_FQDN --build-arg NEXT_PUBLIC_WS_URL=wss://$DEPLOY_FQDN/ws/chat frontend/
    - docker push $BACKEND_REPO:$TAG
    - docker push $FRONTEND_REPO:$TAG
    # SSH to the EC2 and update /etc/flowin/app.env to point at the new tags,
    # then restart. The SSH key + user come from CI secrets; the EC2 host is
    # in $DEPLOY_HOST (also from CI vars).
    - |
      ssh -o StrictHostKeyChecking=no flowin-deploy@$DEPLOY_HOST <<EOF
      set -e
      sudo /usr/local/bin/flowin-update-image-tag backend  "$BACKEND_REPO:$TAG"
      sudo /usr/local/bin/flowin-update-image-tag frontend "$FRONTEND_REPO:$TAG"
      sudo systemctl restart flowin-app.service
      EOF
  only:
    - main
```

**Notes:**

- `NEXT_PUBLIC_API_URL` / `NEXT_PUBLIC_WS_URL` are baked into the frontend image at build time. That is why the build job needs the FQDN — it cannot be supplied at run time. A consequence: every environment (prod, staging, etc.) gets its own frontend image; you cannot reuse the staging image in prod.
- The EC2 has a `flowin-deploy` system user (created by Appendix D §13) with **restricted sudo** on three exact commands. CI never runs `sudo sed` directly — it calls `/usr/local/bin/flowin-update-image-tag`, a wrapper that whitelists `(backend|frontend)` and a regex-bounded image URI before editing `/etc/flowin/app.env`. The full sudoers stanza Appendix D installs:
  ```
  flowin-deploy ALL=(root) NOPASSWD: /usr/local/bin/flowin-update-image-tag backend *
  flowin-deploy ALL=(root) NOPASSWD: /usr/local/bin/flowin-update-image-tag frontend *
  flowin-deploy ALL=(root) NOPASSWD: /usr/bin/systemctl restart flowin-app.service
  ```
  This is the minimum-privilege deploy account: it cannot read secrets, cannot install packages, cannot escalate, and cannot edit any file outside `/etc/flowin/app.env`.
- Image tags are immutable (Terraform's ECR module enforces `IMAGE_TAG_MUTABILITY = "IMMUTABLE"`). A double-deploy of the same SHA fails on push — that's intentional; bump a commit, retry.
- ECR retains the last 10 tagged images per repo (lifecycle policy in `infra/modules/ecr/main.tf`). Older tags expire automatically. Rollback is to pick a still-resident tag.
- `only: [main]` plus `when: manual` (add it back if you want — omitted here for brevity) gives the operator-clicks-Deploy gate. **Never auto-deploy main to prod on a single-EC2 topology** — there's no canary, no blue-green, no rollback besides re-deploying the previous tag.

### 12.2 What `flowin-app.service restart` actually does

When the CI deploy step runs `systemctl restart flowin-app.service`:

1. systemd runs `ExecStop=docker compose down`, which sends SIGTERM to each container then SIGKILL after `stop_grace_period` (30 s for backend so uvicorn drains in-flight WS frames).
2. systemd runs `ExecStartPre=/usr/local/bin/flowin-load-secrets` — this re-reads SSM Parameter Store and rewrites `/etc/flowin/app.env`, but it preserves the `BACKEND_IMAGE=` / `FRONTEND_IMAGE=` lines that the CI deploy step just `sed`'d in (the loader's "preserve image-tag pins" merge — see §9.3).
3. systemd runs `ExecStartPre=docker compose pull`, which pulls the new image tags from ECR. ECR auth is fresh (the `flowin-ecr-login.timer` refreshes it every 6 h).
4. systemd runs `ExecStart=docker compose up -d --remove-orphans`. Backend starts; its `docker-entrypoint.sh` runs `alembic upgrade head` against the host Postgres, then `exec`s uvicorn. Frontend waits for backend's healthcheck to go green (`depends_on: { backend: { condition: service_healthy } }`), then starts.

Total downtime: ~5–15 seconds depending on image pull cache.

### 12.3 Rollback

Rollback is now two `flowin-update-image-tag` invocations pointing `BACKEND_IMAGE` / `FRONTEND_IMAGE` in `/etc/flowin/app.env` at the previous tag, plus `sudo systemctl restart flowin-app.service`. ECR retains the last 10 tagged images per the lifecycle policy (Terraform `infra/modules/ecr`), so the previous-known-good image is always available.

```bash
# On the EC2 (via SSH as flowin-deploy or SSM as the operator):
PREV_BACKEND=v20260509-abc1234   # whatever was running before the bad deploy
PREV_FRONTEND=v20260509-abc1234
sudo /usr/local/bin/flowin-update-image-tag backend  "${ECR_REGISTRY}/flowin-prod-backend:$PREV_BACKEND"
sudo /usr/local/bin/flowin-update-image-tag frontend "${ECR_REGISTRY}/flowin-prod-frontend:$PREV_FRONTEND"
sudo systemctl restart flowin-app.service
```

~30 seconds end-to-end. Acceptable because deployments happen in a maintenance window (§13).

### 12.4 First-time deploy

On a fresh box, the bootstrap script (Appendix D) installs Docker, authenticates to ECR, copies `docker-compose.yml` from the repo, and writes an initial `/etc/flowin/app.env` with `:latest`-tagged image URIs. The first `systemctl enable --now flowin-app.service` then pulls and runs whatever `:latest` resolves to. Steady-state deploys (§12.1) replace `:latest` with pinned, immutable tags as soon as the first CI run completes. For a recovery boot from snapshot, the `app.env` is preserved across instance replacement (it lives on the host's encrypted root volume, not on the data EBS), so the recovered instance comes up on the same tags it was running before.

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
| `/health` returns 5xx for >5 min | `sudo systemctl status flowin-app.service` and `sudo docker compose -f /opt/flowin/docker-compose.yml logs --tail=200 backend` | If OOM, consider scaling up; if DB, check Postgres on the host (`systemctl status postgresql@16-main`) |
| HTTPS down (no TLS handshake) | `sudo systemctl status nginx`, `sudo nginx -t`, `sudo certbot certificates` | Cert expired? `sudo certbot renew --force-renewal` |
| Disk full on `/` | `journalctl --vacuum-size=500M`, `apt clean`, check `/var/log` | Permanent fix: log rotation, or expand the root volume |
| Disk full on `/var/lib/postgresql` | **DO NOT** run `VACUUM FULL` blindly. Check for runaway agent_outputs JSON. Truncate old `workflow_runs` per Blocker 6. | Long term: expand the volume (`aws ec2 modify-volume`, then `xfs_growfs`) |
| Bedrock 5xx surge (`flowin-prod-bedrock-5xx`) | Reactive: nothing. The retries in `pipeline.py:95-122` (B5) handle transient errors. | If sustained, check the AWS Service Health Dashboard for `eu-central-1` Bedrock; if confirmed regional outage, flip `/flowin/prod/llm/provider` to `anthropic`, populate the fallback API key, restart backend (§9). Alert customers via status page. |
| Bedrock throttles (`flowin-prod-bedrock-throttles`) | Open a Service Quotas increase request for Haiku 4.5 TPM/RPM in `eu-central-1`. | Until granted, expect `Invocation` failures during peaks; the `pipeline.py:95-122` retries cushion this but only up to a point. |
| WS storm (clients reconnecting frantically) | Check `flowin-prod-ws-disconnect-spike` alarm; check uvicorn worker count | A bug in W05 reconnect logic? Check `useWebSocket.ts:113-121` — exponential backoff should keep this bounded |
| User reports stale data | Confirm last successful `pg_dump` from S3; check `pg_stat_activity` for stuck connections | If DB row stuck `running` (Blocker 6), nudge via SQL UPDATE |
| Suspected breach | (1) Take EBS snapshot for forensics, (2) rotate all Parameter Store secrets, (3) terminate the instance from a fresh one | CloudTrail + GuardDuty + auditd logs in CloudWatch are your evidence |

---

## 14. Cost estimate (monthly, low/typical/high)

All in USD, `eu-central-1`, list price (no Reserved Instance / Savings Plan — when traffic is steady, buying a 1-year RI on the EC2 saves ~30%).

| Item | Low | Typical | High |
|---|---|---|---|
| EC2 `m6i.2xlarge` (730h) | $327 | $327 | $327 |
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
| **Subtotal AWS infra (no LLM tokens)** | **~$377** | **~$416** | **~$517** |
| Bedrock model invocations (Haiku 4.5, list pricing) | ~$10 | ~$50–$200 | ~$1000+ |
| **Total** | **~$387** | **~$466–616** | **~$1517+** |

Notes:

- **Bedrock token spend** is *separate and traffic-dependent*. At time of writing, list pricing is **$0.80 per million input tokens** and **$4.00 per million output tokens** for Claude Haiku 4.5 — verify on the Bedrock pricing page. Bedrock charges parity with the Anthropic direct list price; expect ~$50–$200/mo on top of infra at typical pilot traffic, $1k+ at high volume. With Blocker 3 (cancel) unfixed, a single user "Stop"-clicking a runaway PPT pipeline can burn $5+ of tokens — fix it before going wide.
- **Reserved Instance / Savings Plan:** committing to a 1-year, no-upfront RI on `m6i.2xlarge` drops the EC2 line to ~$220/month. Worth doing once steady-state usage is confirmed (~3 months in).
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

On `m6i.2xlarge` (8 vCPU / 32 GB):

| Workload mix | Comfortable concurrent | Warning at | Hard ceiling |
|---|---|---|---|
| All chat sessions | 400 | 500 | 700 |
| All user_stories pipelines | 120 | 150 | 180 |
| All PPT / prototype pipelines | 80 | 100 | 120 |
| Realistic mix (60% chat, 30% user_stories, 10% PPT) | 300 | 360 | 440 |

The ceiling is **memory** before it is **CPU**. Vertical-scale signals:

- `mem_used_percent` consistently >80% (alarm fires).
- Postgres OOM-killed event in dmesg.
- Uvicorn worker restart spikes in journald.

### 15.2 The vertical scale path

| From | To | When |
|---|---|---|
| `m6i.2xlarge` (8 vCPU / 32 GB) | `m6i.4xlarge` (16 vCPU / 64 GB) | Sustained >240 concurrent pipelines |
| `m6i.4xlarge` | `m6i.8xlarge` (32 vCPU / 128 GB) | Sustained >500 concurrent pipelines |
| `m6i.8xlarge` | **migrate to multi-service** | At this point the single-box outage cost outweighs the operational simplicity |

Vertical scale procedure:
1. Stop traffic during a maintenance window (set Route 53 to a maintenance page, or just accept downtime — single-box reality).
2. `aws ec2 stop-instances --instance-ids <ID>`.
3. `aws ec2 modify-instance-attribute --instance-id <ID> --instance-type m6i.4xlarge`.
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

Past ~500 concurrent active pipelines on `m6i.8xlarge`, the *real* answer is: ECS Fargate, multiple tasks, ALB sticky sessions for WS, RDS Multi-AZ, ElastiCache for chat-session-id-to-task pinning, S3 for artifacts. That is `PRODUCTION_DEPLOYMENT_GUIDE.md`. We have no business pretending otherwise.

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

> **Note:** the upstreams `127.0.0.1:8000` / `127.0.0.1:3000` are now Docker port mappings (the backend and frontend containers each bind their listening port on the host's loopback interface). The nginx config itself is unchanged from the pre-Docker version — Compose's port mapping is transparent to the proxy.

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

### B.1 `/etc/systemd/system/flowin-app.service`

A single unit replaces the previous `flowin-backend.service` + `flowin-frontend.service` pair. The rationale (one source of truth for ordering, no duplicate orchestration between systemd and Compose, security boundary is the container) is in §8.3. The unit delegates all process management to `docker compose`; container-level hardening (non-root UID 10001, default seccomp, capability drop) lives in the Dockerfiles, not here.

```ini
# /etc/systemd/system/flowin-app.service
[Unit]
Description=Flowin app stack (backend + frontend) via Docker Compose
After=docker.service network-online.target postgresql.service
Requires=docker.service
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/flowin
EnvironmentFile=/etc/flowin/app.env
ExecStartPre=/usr/local/bin/flowin-load-secrets
ExecStartPre=/usr/bin/docker compose pull
ExecStart=/usr/bin/docker compose up -d --remove-orphans
ExecStop=/usr/bin/docker compose down
ExecReload=/usr/bin/docker compose restart
TimeoutStartSec=600
Restart=on-failure
RestartSec=30s

[Install]
WantedBy=multi-user.target
```

Notes on the design:

- `Type=oneshot` + `RemainAfterExit=yes` is the correct shape for a unit whose `ExecStart` returns immediately (Compose detaches the containers). A `Type=simple` unit would think the work is done and exit; `Type=forking` would expect a PID file we don't produce.
- `Requires=docker.service` is hard, not soft — without the daemon there is nothing for compose to talk to.
- `After=postgresql.service` keeps the start ordering "host services first, app last", same as the old design. Compose's healthcheck on the backend will retry until Postgres is reachable, so this is belt-and-braces.
- `ExecStartPre=/usr/local/bin/flowin-load-secrets` repopulates `/etc/flowin/app.env` from Parameter Store before each start. The file is then read both by systemd (`EnvironmentFile=`) and by Compose (`env_file:` in `docker-compose.yml`).
- `ExecStartPre=/usr/bin/docker compose pull` keeps the box honest — every restart pulls the tag pinned in `app.env`. ECR auth is refreshed by the `flowin-ecr-login.timer` (every 6 h) so this rarely fails on auth.
- `Restart=on-failure` with `RestartSec=30s` retries on transient ECR / daemon errors without busy-looping.
- `TimeoutStartSec=600` covers the worst case of a slow ECR pull + container start on a cold cache.

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
# Source path moved from /opt/flowin/src/backend/skills (native install) to
# /opt/flowin/data/skills (Docker bind-mount target — see docker-compose.yml
# `volumes:` for the backend service). Files are written from inside the
# container by UID 10001 and are readable by the host's flowin user via the
# permissions set in the bootstrap script.
tar -czf - -C /opt/flowin/data skills \
  | aws s3 cp - "s3://${FLOWIN_BACKUP_BUCKET}/skills/${TS}.tar.gz" \
      --region eu-central-1 \
      --sse aws:kms \
      --sse-kms-key-id "$FLOWIN_KMS_KEY_ID"
```

### B.6 `/etc/systemd/system/flowin-stuck-workflows-check.service` and `.timer`

Audit D P2-3: a stuck `running` WorkflowRun row (orchestrator crash, DB drop between status updates) wouldn't be caught by the cancel-pipeline path. This timer runs every 15 min, queries Postgres for rows in `running` for >60 min, and pushes the count to CloudWatch as `Flowin/App::StuckRunningWorkflows`. The corresponding alarm (`flowin-prod-stuck-running-workflows` in the monitoring module) pages when the count > 0.

`flowin-stuck-workflows-check.service`:

```ini
[Unit]
Description=Flowin stuck-running WorkflowRun probe
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=flowin
Group=flowin
EnvironmentFile=/etc/flowin/bootstrap.env
EnvironmentFile=/etc/flowin/app.env
ExecStart=/usr/local/bin/flowin-stuck-workflows-check
TimeoutStartSec=60
```

`flowin-stuck-workflows-check.timer`:

```ini
[Unit]
Description=Run stuck-workflows probe every 15 minutes

[Timer]
OnCalendar=*:0/15
Persistent=true
RandomizedDelaySec=60
Unit=flowin-stuck-workflows-check.service

[Install]
WantedBy=timers.target
```

`/usr/local/bin/flowin-stuck-workflows-check`:

```bash
#!/usr/bin/env bash
# Audit D P2-3 — push StuckRunningWorkflows custom metric.
# DATABASE_URL is exported by /etc/flowin/app.env via the secrets loader
# (Appendix D). The loader writes the URL with `host.docker.internal` as
# the hostname (so the in-container backend can reach native Postgres);
# this script runs ON THE HOST, so we rewrite that to 127.0.0.1 below.
# psql in tuples-only mode keeps the output to just the integer count.
set -euo pipefail
: "${DATABASE_URL:?DATABASE_URL is required}"
AWS_REGION="${AWS_REGION:-eu-central-1}"

# Container-side hostname → host-loopback. The substring is unique enough
# in a DATABASE_URL to swap unambiguously.
HOST_DB_URL="${DATABASE_URL//host.docker.internal/127.0.0.1}"

COUNT=$(psql "$HOST_DB_URL" -tAc \
  "SELECT count(*) FROM workflow_runs \
   WHERE status='running' AND created_at < NOW() - INTERVAL '60 minutes'")

# Empty result -> 0. Defensive but should never happen.
COUNT=${COUNT:-0}

aws cloudwatch put-metric-data \
  --namespace Flowin/Prod \
  --metric-name StuckRunningWorkflows \
  --value "$COUNT" \
  --region "$AWS_REGION"
```

The IAM instance role already grants `cloudwatch:PutMetricData` on `Resource:*` (documented exception — the API doesn't support resource-level scoping; see `infra/modules/iam/main.tf::cw_agent_describes`).

---

## Appendix C — Parameter Store key list

Canonical reference. **All keys live under `/flowin/prod/`** and are written by an operator (never by the application). Type `SecureString` unless noted.

The columns:
- **SSM key** — the parameter name in Parameter Store (Terraform writes these via `infra/modules/secrets/`).
- **Env var** — the variable name the on-host loader (`/usr/local/bin/flowin-load-secrets`) emits into `/etc/flowin/app.env`, which Compose then injects into the backend container's environment. Settings (`backend/app/core/config.py`) reads these.

> **Note on `ENV`.** `ENV` is **declared in `/etc/flowin/app.env` directly** (the bootstrap script writes `ENV=production` once on first boot; the load-secrets script preserves it on every refresh — see the `BACKEND_IMAGE|FRONTEND_IMAGE|ENV` preserve clause in §9.3). It is intentionally kept out of SSM so an out-of-band parameter rotation cannot accidentally disarm the A1 SECRET_KEY hard-fail in `backend/app/core/config.py`. Anchoring it on disk in the host's protected `/etc/flowin/app.env` makes the production-strict mode unconditional.
>
> **Note on `DATABASE_URL`.** The composed URL embeds `127.0.0.1` (the on-host Postgres), which Terraform doesn't know. The loader composes it from `DATABASE_PASSWORD` at boot.

| SSM key | Env var | Type | Source / generation | Rotation | Notes |
|---|---|---|---|---|---|
| `/flowin/prod/SECRET_KEY` | `SECRET_KEY` | SecureString | `openssl rand -hex 64` | Yearly + on compromise | Used by python-jose for HS256. **Required non-default at boot** (Blocker 1). |
| `/flowin/prod/DATABASE_PASSWORD` | `DATABASE_URL` (composed by loader) | SecureString | `openssl rand -hex 32` | Yearly + on compromise | Drives `ALTER USER flowin WITH PASSWORD ...`. The loader composes `DATABASE_URL=postgresql://flowin:${pw}@127.0.0.1:5432/flowin` from this value. |
| `/flowin/prod/CORS_ORIGINS` | `CORS_ORIGINS` | String | – | When domains change | JSON array. Currently `["https://flowin.example.com"]`. |
| `/flowin/prod/ACCESS_TOKEN_EXPIRE_HOURS` | `ACCESS_TOKEN_EXPIRE_HOURS` | String | `12` | Re-evaluate yearly | Production override per env-template (env-templates/.env.production). |
| `/flowin/prod/llm/provider` | `LLM_PROVIDER` | String | `bedrock` | Only on emergency Anthropic-direct fallback (§0.1) | Selects the LLM backend. Values: `bedrock` (default) or `anthropic` (fallback). |
| `/flowin/prod/llm/region` | `AWS_REGION` | String | `eu-central-1` | When deployment region changes | AWS region the Bedrock SDK targets. The cross-region inference profile fans out to other EU regions transparently — the SDK target stays `eu-central-1`. |
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
  --region eu-central-1 \
  --query 'Parameters[].Name' --output table
```

To audit who-has-read access:

```bash
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::<ACCOUNT_ID>:role/flowin-prod-instance \
  --action-names ssm:GetParameter \
  --resource-arns arn:aws:ssm:eu-central-1:<ACCOUNT_ID>:parameter/flowin/prod/SECRET_KEY \
  --region eu-central-1
```

(Run this as a quarterly audit.)

---

## Appendix D — bootstrap script for a fresh EC2

`bootstrap.sh`. Pass via `aws ec2 run-instances --user-data file://bootstrap.sh`. Runs as root, idempotent, takes ~6 minutes wall-clock.

The script supports two modes auto-detected at run:

- **Fresh provision:** no data on `/dev/nvme1n1`. Script formats it, initializes Postgres, generates a new DB password, puts it into Parameter Store, installs Docker, authenticates to ECR, pulls the backend + frontend images, and starts `flowin-app.service`. (No host-side `git clone` / `npm run build` / `pip install` — application code lives only inside the container images.)
- **Recovery from snapshot:** `/dev/nvme1n1` has an xfs filesystem with an existing Postgres data dir. Script mounts it, skips `initdb`, reuses the existing password from Parameter Store. Same Docker / ECR / image-pull path as fresh provision (the OS root volume is recreated; the data volume's contents are preserved).

```bash
#!/usr/bin/env bash
# Flowin production EC2 bootstrap.
# Idempotent. Detects whether it is provisioning a new box or
# recovering one from snapshot and behaves accordingly.
set -euo pipefail
exec > >(tee -a /var/log/flowin-bootstrap.log) 2>&1
echo "[bootstrap] start $(date -u --iso-8601=seconds)"

# Pull operator-controlled values from /etc/flowin/bootstrap.env, written by
# the EC2 user-data template (see infra/modules/compute/user_data.sh.tpl).
# That file carries:
#   FLOWIN_REGION         — AWS region for SSM, ECR, S3 calls
#   FLOWIN_PARAM_PREFIX   — Parameter Store prefix, e.g. /flowin/prod
#   FLOWIN_KMS_KEY_ID     — project CMK ARN/alias for backup encryption
#   FLOWIN_BACKUP_BUCKET  — S3 bucket for pg_dump + skills tarballs
#   FLOWIN_FQDN           — public hostname (nip.io or Route 53)
#   FLOWIN_ENVIRONMENT    — short env tag, e.g. prod / staging
#   FLOWIN_ECR_REGISTRY   — <ACCOUNT>.dkr.ecr.<region>.amazonaws.com
#                           (no path/repo suffix — bootstrap composes per-image URIs)
#   FLOWIN_GIT_REF        — branch or tag the bootstrap fetches docker-compose.yml from
# Terraform's module.compute writes all of these via the `user_data_extra_env`
# mechanism. The bootstrap below uses them all.
# shellcheck source=/dev/null
. /etc/flowin/bootstrap.env

REGION="${FLOWIN_REGION:-eu-central-1}"
DOMAIN="${FLOWIN_FQDN:?FLOWIN_FQDN missing in /etc/flowin/bootstrap.env — apply Terraform first}"
ACME_EMAIL=security@example.com
PARAM_PREFIX="${FLOWIN_PARAM_PREFIX:-/flowin/prod}"
DATA_DEV=/dev/nvme1n1
DATA_MOUNT=/var/lib/postgresql
APP_USER=flowin
REPO_URL=https://gitlab.com/hexaware-uki/flowin.git

# ── 0. Wait for cloud-init to settle ───────────────────────────────────
while ! cloud-init status --wait > /dev/null 2>&1; do sleep 2; done

# ── 1. Patch & baseline tools ──────────────────────────────────────────
# Note: python venv + node toolchains are intentionally NOT installed on the
# host any more — backend and frontend ship as containers. Postgres and nginx
# stay on the host (see docs §8 and the docker-compose.yml header comment).
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get -y full-upgrade
apt-get install -y \
    nginx postgresql-16 postgresql-contrib-16 \
    git curl jq xfsprogs \
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
# Kept as a real Unix user for backwards compat (skills-backup unit still
# runs as it; ownership of /opt/flowin/data/skills and /var/log/flowin
# matters for the bind-mount into the backend container — files written by
# the in-container UID 10001 must be readable by the host's flowin user
# for the skills-backup timer to tar them up).
id -u $APP_USER >/dev/null 2>&1 || useradd -r -m -d /opt/flowin -s /usr/sbin/nologin $APP_USER
mkdir -p /opt/flowin /opt/flowin/data/skills /var/log/flowin /etc/flowin
chown -R $APP_USER:$APP_USER /opt/flowin /var/log/flowin
chown root:$APP_USER /etc/flowin
chmod 0750 /etc/flowin

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

# ── 7. Docker engine + Compose plugin ──────────────────────────────────
echo "[bootstrap] installing Docker engine + Compose plugin"

# Use Docker's official APT repo, NOT Ubuntu's docker.io package — that one
# lags badly and ships Compose v1 (deprecated). The official repo gives us
# Compose v2 as a plugin (`docker compose`, no hyphen).
apt-get install -y ca-certificates gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

systemctl enable --now docker

# We do NOT add the ubuntu/admin user to the docker group — Docker socket
# access is root-equivalent and we keep that to the systemd-managed flow
# only (the `flowin-app.service` unit and `flowin-load-secrets` both run as
# root). Operators reach the app via SSM Session Manager (§8.1) and use
# `sudo docker compose ...` when they need ad-hoc inspection.

# Grant cwagent read access to /var/lib/docker/containers via POSIX ACLs so
# the CloudWatch agent can tail JSON log files (see §10.1). Adding cwagent to
# the docker group would also work but grants full docker.sock access — too
# broad. ACLs grant exactly the right bit (read+traverse).
apt-get install -y acl
setfacl -R -m u:cwagent:rX /var/lib/docker/containers || true
setfacl -R -d -m u:cwagent:rX /var/lib/docker/containers || true
# `|| true` because cwagent is installed later in §13; we re-run setfacl from
# §13's post-install hook to capture the user once it exists. The two
# invocations together guarantee the ACL is in place regardless of install
# order. New containers' log files inherit the default ACL automatically.

echo "[bootstrap] Docker installed: $(docker --version), $(docker compose version)"

# ── 8. ECR login (one-shot — pull happens via flowin-app's ExecStartPre) ─
echo "[bootstrap] authenticating to ECR"

# FLOWIN_ECR_REGISTRY is written into /etc/flowin/bootstrap.env by Terraform
# (compute module's user_data_extra_env). It is the registry hostname
# without a path suffix, e.g.
#   <ACCOUNT>.dkr.ecr.eu-central-1.amazonaws.com
# The per-image URIs (with tags) live in /etc/flowin/app.env — populated
# below as part of the compose-env bootstrap.
ECR_REGISTRY="${FLOWIN_ECR_REGISTRY:-}"
if [ -z "$ECR_REGISTRY" ]; then
    echo "[bootstrap] ERROR: FLOWIN_ECR_REGISTRY not set in /etc/flowin/bootstrap.env"
    exit 1
fi

aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$ECR_REGISTRY"

# ECR auth tokens expire after 12 hours. A systemd timer refreshes the
# docker login twice the rate (every 6 hours, with a 5-minute randomized
# delay). Keeping this on a timer rather than cron matches the rest of the
# project (certbot, pg-dump, skills-backup, stuck-workflows are all timers).
cat > /etc/systemd/system/flowin-ecr-login.service <<'UNIT'
[Unit]
Description=Refresh Docker login to ECR
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
EnvironmentFile=/etc/flowin/bootstrap.env
ExecStart=/bin/bash -c '/usr/local/bin/aws ecr get-login-password --region $FLOWIN_REGION | /usr/bin/docker login --username AWS --password-stdin $FLOWIN_ECR_REGISTRY'
UNIT

cat > /etc/systemd/system/flowin-ecr-login.timer <<'TIMER'
[Unit]
Description=Refresh Docker login to ECR every 6 hours

[Timer]
OnCalendar=*-*-* 00,06,12,18:00:00
RandomizedDelaySec=5min
Persistent=true

[Install]
WantedBy=timers.target
TIMER

systemctl daemon-reload
systemctl enable --now flowin-ecr-login.timer

# ── 8b. docker-compose.yml on the host ─────────────────────────────────
# The compose file is committed at the repo root (so devs can `docker
# compose up` locally); for the bootstrap we fetch it from the deployed
# branch. Steady-state deploys (§12) overwrite this file via SSH-and-sed
# OR keep this initial copy and only mutate /etc/flowin/app.env (image
# tags), depending on whether the compose file itself is changing.
curl -fsSL "https://raw.githubusercontent.com/<ORG>/<REPO>/${FLOWIN_GIT_REF:-main}/docker-compose.yml" \
  | tee /opt/flowin/docker-compose.yml > /dev/null
chown $APP_USER:$APP_USER /opt/flowin/docker-compose.yml
chmod 0644 /opt/flowin/docker-compose.yml

# ── 8c. /etc/flowin/app.env  — single source of runtime config for both containers
# /usr/local/bin/flowin-load-secrets (created in §9 below) overwrites this
# file on every flowin-app.service start. The bootstrap creates an initial
# version with the image URIs (set to ":latest" — the first deploy via the
# CI pipeline replaces these with a pinned tag). The systemd unit's
# EnvironmentFile= would fail-stop if the file didn't exist on first boot.
if [[ ! -f /etc/flowin/app.env ]]; then
    cat > /etc/flowin/app.env <<EOF
# Populated by /usr/local/bin/flowin-load-secrets on every start. The loader
# preserves the BACKEND_IMAGE / FRONTEND_IMAGE / ENV lines below; everything
# else is overwritten from /flowin/prod/* in SSM.

# ENV is environment-defining — kept on the host (NOT in SSM) so an
# out-of-band SSM rotation cannot accidentally disarm the A1 SECRET_KEY
# hard-fail in backend/app/core/config.py. See Appendix C note on ENV.
ENV=production

# Container image URIs (with tags) — the CI pipeline (§12) updates these
# in-place via sed on every deploy.
BACKEND_IMAGE=${ECR_REGISTRY}/flowin-${FLOWIN_ENVIRONMENT:-prod}-backend:latest
FRONTEND_IMAGE=${ECR_REGISTRY}/flowin-${FLOWIN_ENVIRONMENT:-prod}-frontend:latest
EOF
    chown root:$APP_USER /etc/flowin/app.env
    chmod 0640 /etc/flowin/app.env
fi

# Note: DB schema migrations are now run inside the backend container by
# backend/docker-entrypoint.sh on every container start (alembic upgrade
# head, then exec uvicorn). The bootstrap doesn't run alembic itself.

# ── 9. Secrets loader ──────────────────────────────────────────────────
# Pulls all parameters under /flowin/prod/* and emits them as KEY=value lines
# into a 0640 root:flowin env file consumed both by the systemd
# EnvironmentFile= on flowin-app.service AND by Compose's `env_file:` block
# inside docker-compose.yml. The mapping is per-key and explicit (see §9.3
# for the table):
#
#   SECRET_KEY,CORS_ORIGINS,ACCESS_TOKEN_EXPIRE_HOURS,LANGSMITH_*  → passthrough
#   DATABASE_PASSWORD                                              → DATABASE_URL=postgresql://flowin:${value}@host.docker.internal:5432/flowin
#   llm/provider                                                   → LLM_PROVIDER
#   llm/region                                                     → AWS_REGION
#   llm/model_id                                                   → BEDROCK_MODEL_ID
#   anthropic/api_key                                              → ANTHROPIC_API_KEY
#   anything else                                                  → warn, ignore
#
# Why host.docker.internal: the backend now runs in a container; Postgres is
# still native on the host. From inside the container, the host's loopback
# is reachable via the host-gateway alias (extra_hosts in docker-compose.yml
# wires this up). Compose v2.24+ also lets us drop the alias and use the
# magic name directly, but we keep the alias for older Compose installs.
#
# The loader does NOT touch BACKEND_IMAGE / FRONTEND_IMAGE — those are
# managed by the CI deploy step (§12) and the bootstrap's first-run
# initializer above. The loader uses a "merge" strategy: it preserves any
# pre-existing BACKEND_IMAGE / FRONTEND_IMAGE lines and only rewrites the
# parameter-store-sourced keys.
#
# Note: ENV is written ONCE by the bootstrap (§8c above) and preserved by
# this loader on each refresh via the BACKEND_IMAGE|FRONTEND_IMAGE|ENV
# regex below. It is intentionally OUT of SSM — see Appendix C "Note on ENV".
cat > /usr/local/bin/flowin-load-secrets <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

OUT=/etc/flowin/app.env
TMP=$(mktemp /etc/flowin/app.env.XXXXXX)
chmod 0640 "$TMP"; chown root:flowin "$TMP"

REGION=eu-central-1
PREFIX=/flowin/prod

# Preserve operator-managed image-tag pins from the previous app.env. Lines
# starting with BACKEND_IMAGE= or FRONTEND_IMAGE= are CI-managed (the deploy
# step seds them in place) — we don't want a load-secrets run to clobber a
# freshly deployed tag with the bootstrap's :latest default.
if [[ -f "$OUT" ]]; then
    grep -E '^(BACKEND_IMAGE|FRONTEND_IMAGE|ENV)=' "$OUT" >> "$TMP" || true
fi

emit() {
    printf '%s=%q\n' "$1" "$2" >> "$TMP"
}

while IFS=$'\t' read -r name value; do
    rel="${name#${PREFIX}/}"
    case "$rel" in
        SECRET_KEY|CORS_ORIGINS|ACCESS_TOKEN_EXPIRE_HOURS|LANGSMITH_TRACING|LANGSMITH_API_KEY|LANGSMITH_PROJECT)
            emit "$rel" "$value" ;;
        DATABASE_PASSWORD)
            emit DATABASE_URL "postgresql://flowin:${value}@host.docker.internal:5432/flowin" ;;
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
# The new layout is:
#   /etc/systemd/system/flowin-app.service                (B.1 — wraps compose)
#   /etc/systemd/system/flowin-pg-dump.{service,timer}    (B.3 — host pg_dump)
#   /etc/systemd/system/flowin-skills-backup.{service,timer}  (B.5)
#   /etc/systemd/system/flowin-stuck-workflows-check.{service,timer}  (B.6)
# (flowin-ecr-login.{service,timer} are inlined in §8 above.)

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

# Re-run the ACL grant now that the cwagent user definitely exists. §7 ran
# this with `|| true` because the user is created by the cw-agent .deb
# postinst, which only ran above.
setfacl -R -m u:cwagent:rX /var/lib/docker/containers
setfacl -R -d -m u:cwagent:rX /var/lib/docker/containers

# Drop in /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json (see §10.1)
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
    -a fetch-config -m ec2 -s -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
systemctl enable --now amazon-cloudwatch-agent

# ── 13. flowin-deploy user (CI deploy account, restricted sudo) ──────────
# CI runs `ssh flowin-deploy@$DEPLOY_HOST` to update /etc/flowin/app.env and
# restart the app service (see §12). The user has NO interactive shell role
# and a tightly-scoped sudoers stanza — only the two sed patterns and the
# single systemctl restart needed for deploys.
if ! id flowin-deploy >/dev/null 2>&1; then
    useradd --system --create-home --shell /bin/bash flowin-deploy
    install -d -o flowin-deploy -g flowin-deploy -m 0700 /home/flowin-deploy/.ssh
    # The CI public key is uploaded out-of-band by the operator (or fetched
    # from SSM Parameter Store at /flowin/$ENVIRONMENT/deploy/ssh_authorized_key
    # if you want to manage it via Terraform). The bootstrap creates the file
    # empty here; CI deploys will fail until the key is provisioned. We
    # deliberately do NOT copy any default key — explicit pairing only.
    install -o flowin-deploy -g flowin-deploy -m 0600 /dev/null \
        /home/flowin-deploy/.ssh/authorized_keys
fi

# Wrapper script that CI calls instead of `sudo sed`. Validates inputs (only
# `backend` or `frontend`, only docker-URI-shaped image strings) before
# editing /etc/flowin/app.env. Allowing `sudo sed` directly would leak: sed's
# `-i` could write any file with the right glob; sed's expression syntax
# allows escaping that's hard to whitelist in sudoers. A 30-line wrapper is
# the right boundary.
cat > /usr/local/bin/flowin-update-image-tag <<'WRAPPER'
#!/bin/bash
# /usr/local/bin/flowin-update-image-tag — called by `sudo` from CI.
# Usage: flowin-update-image-tag (backend|frontend) <image_uri>
# Edits the matching IMAGE= line in /etc/flowin/app.env and exits 0 on
# success. Any malformed input rejects with non-zero.
set -euo pipefail
if [ "$#" -ne 2 ]; then
    echo "ERROR: usage: $0 (backend|frontend) <image_uri>" >&2
    exit 64
fi
component="$1"
image="$2"
case "$component" in
    backend|frontend) ;;
    *) echo "ERROR: component must be backend or frontend, got: $component" >&2; exit 65 ;;
esac
# Permissive but bounded character class for a docker image URI: lowercase
# alphanumerics, hyphens, dots, slashes (registry/repo separator), colons
# (tag separator), underscores. Rejects shell metachars, spaces, newlines.
if [ "${#image}" -gt 255 ] || ! [[ "$image" =~ ^[a-z0-9._/:-]+$ ]]; then
    echo "ERROR: image URI rejected — must match ^[a-z0-9._/:-]+$ (max 255 chars)" >&2
    exit 66
fi
upper="${component^^}"
sed -i.bak "s|^${upper}_IMAGE=.*|${upper}_IMAGE=${image}|" /etc/flowin/app.env
rm -f /etc/flowin/app.env.bak
WRAPPER
chmod 0755 /usr/local/bin/flowin-update-image-tag
chown root:root /usr/local/bin/flowin-update-image-tag

# Restricted sudoers — three exact commands. The wrapper script validates its
# own arguments, so sudoers' wildcard match is bounded by the wrapper's
# regex check. Use visudo -cf to refuse a malformed file rather than locking
# the operator out.
SUDOERS_TMP=$(mktemp)
cat > "$SUDOERS_TMP" <<'SUDO'
# /etc/sudoers.d/flowin-deploy — deploy account, NOPASSWD restricted commands.
# Generated by Flowin bootstrap (Appendix D §13). Do not edit by hand.
flowin-deploy ALL=(root) NOPASSWD: /usr/local/bin/flowin-update-image-tag backend *
flowin-deploy ALL=(root) NOPASSWD: /usr/local/bin/flowin-update-image-tag frontend *
flowin-deploy ALL=(root) NOPASSWD: /usr/bin/systemctl restart flowin-app.service
SUDO
chmod 0440 "$SUDOERS_TMP"
if visudo -cf "$SUDOERS_TMP"; then
    install -o root -g root -m 0440 "$SUDOERS_TMP" /etc/sudoers.d/flowin-deploy
else
    echo "[bootstrap] ERROR: flowin-deploy sudoers stanza failed visudo check" >&2
    rm -f "$SUDOERS_TMP"
    exit 1
fi
rm -f "$SUDOERS_TMP"

# ── 13. Backups (see §11.2) ────────────────────────────────────────────
# Drop in /usr/local/bin/flowin-pg-dump and the timer/service files.
chmod +x /usr/local/bin/flowin-pg-dump /usr/local/bin/flowin-skills-backup \
         /usr/local/bin/flowin-stuck-workflows-check
systemctl daemon-reload
systemctl enable --now flowin-pg-dump.timer flowin-skills-backup.timer \
                       flowin-stuck-workflows-check.timer

# ── 14. Application units ──────────────────────────────────────────────
/usr/local/bin/flowin-load-secrets
systemctl daemon-reload
# Single unit replaces flowin-backend.service + flowin-frontend.service.
# It wraps `docker compose up -d`. Start ordering for backend → frontend
# is handled by Compose's depends_on/healthcheck, not systemd. See §8.3.
systemctl enable --now flowin-app.service

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
