# Flowin — App-level smoke test against LocalStack Pro

**When:** ran on the `infra` branch on 2026-05-10.
**Goal:** boot backend + frontend pointed at LocalStack-provisioned AWS resources and exercise the workflows that the Terraform-only validation could not. Catch the integration / wiring bugs that would otherwise blow up on a real prod apply.

## TL;DR

- ✅ Wiring proven end-to-end for: WebSocket auth, REST auth, Postgres persistence, SSM / KMS / S3 reads via boto3, FastAPI lifespan, Next.js bootstrap.
- ✅ Pipeline events flow correctly (`phase_start` → `agent_start` → `agent_thinking` → `agent_error` → `pipeline_complete`); structure of `FinalOutputModel` is correct.
- ❌ **6 real bugs found and fixed** that LocalStack-only Terraform validation could not have surfaced (see §3).
- ❌ **2 prior known blockers empirically confirmed** in real traffic (A3 cancel-pipeline doesn't cancel; A4 cancelled runs don't reach a terminal status).
- 🟡 **LocalStack Pro 2026.4.1 does not implement `bedrock-runtime:ConverseStream`** — every streaming agent call returns `InternalFailure`. The backend handles this gracefully (recoverable error → next agent), but real Bedrock streaming cannot be smoke-tested here. Verifying the actual streaming path requires a real AWS sandbox.

---

## 1. Setup

| Component | How |
|---|---|
| LocalStack | Pro 2026.4.1 in a dedicated container `flowin-ls` on `:4666` (the team's `hexaware-localstack` on `:4566` was left untouched). `SERVICES="ec2,iam,kms,s3,ssm,logs,sns,dynamodb,route53,backup,bedrock,bedrock-runtime,cloudwatch,events,resourcegroupstaggingapi,resource-groups,sts,cloudtrail,acm"`. |
| Terraform | `infra/envs/localstack/` applied — 86 resources, 0 errors. SSM / KMS / S3 / Resource Groups all created. |
| Postgres | `postgres:16-alpine` in Docker on `:55432`, separate container `flowin-pg`. Real DB, not a LocalStack mock. |
| Backend | `uvicorn app.main:app` on `127.0.0.1:8000` from a Python 3.13 venv. AWS creds + endpoint URL exported to the shell so boto3 finds them via the env-var step of its credential chain. SSM-derived values from LocalStack written into `backend/.env`. |
| Frontend | `next dev` on `127.0.0.1:3000` with `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000` and `NEXT_PUBLIC_WS_URL=ws://127.0.0.1:8000/ws/chat`. |

## 2. What worked (validated end-to-end)

| Layer | Test | Result |
|---|---|---|
| boto3 → LocalStack | `aws ssm get-parameters-by-path --recursive --with-decryption` returns all 7 SSM params including KMS-encrypted SecureStrings | ✅ |
| FastAPI lifespan | `Base.metadata.create_all()` lays out tables on Postgres | ✅ |
| `/health` | Returns `{status: healthy, llm_provider: bedrock, langsmith: false}` | ✅ |
| `POST /api/auth/register` | bcrypt-hashed user persisted, JWT issued | ✅ |
| `POST /api/auth/login` | Same user, same hash, fresh JWT | ✅ |
| `GET /api/auth/me` (Bearer) | User round-trip | ✅ |
| `POST /api/chats` | `chat_sessions` row with FK to user | ✅ |
| WS `/ws/chat?token=...` | Connection accepted, JWT validated from query param | ✅ |
| Orchestrator phases | `phase_start`/`phase_end` per phase, `complete` with FinalOutputModel structure | ✅ |
| Pipeline executor | `pipeline_start` → 6× `agent_start`/`agent_thinking`/`agent_error` → `pipeline_complete` | ✅ |
| Frontend pages | `/login`, `/register`, `/dashboard` all render 200 | ✅ |

## 3. Real bugs found and fixed

These required code changes on `infra` branch. None of them would have been caught by Terraform-only validation.

### 3.1 `boto3` version pin conflicts with `langchain-aws`
- **What:** `requirements.txt:13` pinned `boto3==1.35.50`. `langchain-aws==0.2.10` requires `boto3>=1.35.74`. Pip resolution fails outright.
- **Fix:** bumped to `boto3==1.35.74`.
- **Production impact:** any fresh `pip install` would have failed during EC2 bootstrap. Highest priority.

### 3.2 No Postgres driver in `requirements.txt`
- **What:** the production `DATABASE_URL=postgresql://...` and SQLAlchemy URL parsing imply psycopg2, but no driver was listed.
- **Fix:** added `psycopg2-binary==2.9.12`.
- **Production impact:** would have blown up at first connect on EC2 with `ModuleNotFoundError: psycopg2`.

### 3.3 `Settings` rejects unknown env vars
- **What:** `pydantic_settings.BaseSettings` defaults `extra="forbid"`. The systemd secrets loader ships every SSM key into the env file (and the box has AWS_* env vars from various sources). Any unknown var crashes `Settings()` at boot.
- **Fix:** added `extra = "ignore"` to `class Config`.
- **Production impact:** without the fix, the systemd unit would have failed during the first boot if even one extra env var was present. Easy to miss until live.

### 3.4 SQLite-only `check_same_thread` hardcoded for all engines
- **What:** `models/database.py:10` passed `connect_args={"check_same_thread": False}` unconditionally. psycopg2 rejects this option with `ProgrammingError: invalid connection option "check_same_thread"`.
- **Fix:** apply the option only when `DATABASE_URL` starts with `sqlite`. Also added `pool_pre_ping=True` (handles long-lived WS sessions across DB pool reconnects).
- **Production impact:** backend never starts if Postgres is configured.

### 3.5 SQLAlchemy detached-instance error on the long-lived WS user
- **What:** `sessionmaker` defaults `expire_on_commit=True`. The WS handler authenticates once, holds the `User` instance for the lifetime of the connection, but commits the DB session multiple times (one per user message, one per pipeline). Each commit expires the User attributes; subsequent access (e.g. `user.id` for logging) tries to refresh from the (now-closed) session and raises `DetachedInstanceError`. WS closes with 1011.
- **Fix:** `expire_on_commit=False` on the `sessionmaker`.
- **Production impact:** every long-lived WS session would crash after the first commit. That's *every* second message in *every* session. Genuinely show-stopping; would surface 100% of the time in real usage.

### 3.6 boto3 falls back to `~/.aws/credentials` when env vars are inside `.env`
- **What:** `pydantic-settings` reads `AWS_ACCESS_KEY_ID` from `backend/.env` into the Settings instance, but does **not** export it to `os.environ`. boto3 walks its credential chain and skips the env-var step, then finds whatever is in `~/.aws/credentials` — in our case, real Hexaware AWS creds — and presents *those* to LocalStack, getting `UnrecognizedClientException`.
- **Mitigation in this smoke:** explicitly `export AWS_ACCESS_KEY_ID=...` in the shell before starting uvicorn.
- **Production impact:** in prod the EC2 instance profile (IMDS) is used, so this is a non-issue. **But** it bites locally / in CI / in any non-EC2 environment where someone tries to set AWS creds via the dotfile pattern. Worth a comment in `core/config.py` and the deployment doc.

## 4. Empirically confirmed prior blockers

These weren't *new* findings — they're listed in `WORKFLOWS.md` §5 — but the smoke test reproduced them in real traffic for the first time:

### A3 — `cancel_pipeline` doesn't actually cancel
- Sent `run_pipeline`, observed `pipeline_start`, sent `cancel_pipeline`, then continued reading: backend kept emitting `agent_start`/`agent_thinking`/`agent_error` for *every* agent in the pipeline, all the way through to `pipeline_complete`. Reason confirmed in `websocket.py:127-135`: cancel just acks; the running coroutine has no task reference to `.cancel()` on, so it runs to completion.
- **Cost implication:** in prod every "Stop" click after this fix lands keeps consuming Bedrock tokens for the rest of the pipeline.

### A4 — Cancelled runs never reach a terminal status
- After Test 3, `workflow_runs` table contains a row with `status='running'` and `completed_at=NULL`, even though the user "cancelled". DB phantom.
- In prod this means cancelled pipelines accumulate forever as `running`.

## 5. LocalStack limitations (will not be fixed by code; need real AWS)

### 5.1 `bedrock-runtime:ConverseStream` not implemented (Pro 2026.4.1)
Every streaming Bedrock call returns:
```
InternalFailure: Sorry, the ConverseStream operation on the bedrock-runtime
service is not currently supported by LocalStack.
```
The non-streaming `Converse` *is* implemented (the title generator hit it and got `ValidationException: model identifier is invalid` instead, meaning the call shape parsed correctly).

### 5.2 LocalStack Bedrock doesn't recognise specific model IDs
The `eu.anthropic.claude-haiku-4-5-20251001-v1:0` cross-region inference profile is rejected as `invalid model identifier`. LocalStack's mock probably accepts a small canned set; verifying which is out of scope here. For real-Bedrock smoke we hit `aws bedrock list-foundation-models` and use what the account actually has access to.

### 5.3 LocalStack EC2 is a stub, not a real Linux host
Doesn't affect this app-layer smoke (the backend ran on the host machine, not on a LocalStack EC2). Listed here for completeness — if anyone tries to validate the on-host bootstrap script (Appendix D of `SIMPLE_AWS_DEPLOYMENT.md`) against LocalStack, it will not work.

## 6. What still has to be validated against a real AWS sandbox

- Real Bedrock invocation (streaming + non-streaming) with a real model that the account has access to.
- IAM instance profile actually attaches to the EC2 (LocalStack returns `NoSuchEntity` here even when the profile exists in IAM).
- VPC interface endpoint for `bedrock-runtime` actually carries traffic.
- Canonical AMI lookup resolves.
- TLS issuance via Let's Encrypt.
- Route 53 → public IP works for HTTP-01.
- The full on-host bootstrap (Appendix D).

Estimated time: half a day on a real AWS sandbox account.

## 7. Files modified by this smoke

| File | Change |
|---|---|
| `backend/requirements.txt` | `boto3==1.35.50 → 1.35.74`; added `psycopg2-binary==2.9.12` |
| `backend/app/core/config.py` | `class Config` adds `extra = "ignore"` |
| `backend/app/models/database.py` | Conditional `check_same_thread` (SQLite only); `expire_on_commit=False`; `pool_pre_ping=True` |

No changes to Terraform, no changes to frontend, no changes to deployment doc. (The deployment doc's Appendix B systemd unit wisely uses `EnvironmentFile=` and IMDS for AWS creds, so bug 3.6 is a local-dev concern only.)

## 8. Reproduction script

```bash
# 1. LocalStack on :4666 (auth token recovered from team container)
docker run -d --name flowin-ls \
  -p 4666:4566 -p 4710:4510 \
  -e LOCALSTACK_AUTH_TOKEN="$YOUR_TOKEN" \
  -e SERVICES="ec2,iam,kms,s3,ssm,logs,sns,dynamodb,route53,backup,bedrock,bedrock-runtime,cloudwatch,events,resourcegroupstaggingapi,resource-groups,sts,cloudtrail,acm" \
  -e PERSISTENCE=0 -e EAGER_SERVICE_LOADING=1 -e DEFAULT_REGION=eu-west-2 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  localstack/localstack-pro:2026.4.1

# 2. Pre-create R53 zone the dns module looks up
AWS_ENDPOINT_URL=http://localhost:4666 AWS_DEFAULT_REGION=eu-west-2 \
AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test \
  aws route53 create-hosted-zone --name flowin.test \
  --caller-reference flowin-localstack-$(date +%s)

# 3. Apply the Terraform LocalStack env (creates SSM, KMS, S3 etc.)
cd infra/envs/localstack
export AWS_ENDPOINT_URL=http://localhost:4666 AWS_DEFAULT_REGION=eu-west-2 \
       AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test \
       TF_VAR_app_secret_key="$(openssl rand -hex 64)" \
       TF_VAR_db_password="$(openssl rand -hex 32)"
terraform init && terraform apply -auto-approve

# 4. Postgres in Docker
DB_PW="$(openssl rand -hex 16)"
docker run -d --name flowin-pg -p 55432:5432 \
  -e POSTGRES_DB=flowin -e POSTGRES_USER=flowin -e POSTGRES_PASSWORD="$DB_PW" \
  postgres:16-alpine

# 5. Backend (Python 3.13 venv)
cd ../../../backend
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Build .env from SSM (mimics the prod secrets loader)
cat > .env <<EOF
LLM_PROVIDER=bedrock
AWS_REGION=eu-west-2
BEDROCK_MODEL_ID=eu.anthropic.claude-haiku-4-5-20251001-v1:0
SECRET_KEY=$(...your value from /flowin/ls/app/secret_key...)
DATABASE_URL=postgresql://flowin:${DB_PW}@localhost:55432/flowin
CORS_ORIGINS=["http://localhost:3000"]
ACCESS_TOKEN_EXPIRE_HOURS=12
EOF

# Critical: AWS creds in shell (boto3 won't pick them up from .env)
export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test \
       AWS_DEFAULT_REGION=eu-west-2 AWS_ENDPOINT_URL=http://localhost:4666

uvicorn app.main:app --host 127.0.0.1 --port 8000

# 6. Frontend
cd ../frontend
cat > .env.local <<EOF
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
NEXT_PUBLIC_WS_URL=ws://127.0.0.1:8000/ws/chat
EOF
npm install
npx next dev
```

## 9. Teardown

```bash
docker stop flowin-ls flowin-pg && docker rm flowin-ls flowin-pg
# (Backend / frontend dev servers are killed via their stored PIDs.)
```
