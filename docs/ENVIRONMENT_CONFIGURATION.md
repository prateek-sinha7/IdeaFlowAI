# Environment Configuration Reference

This document explains all environment variables used by Flowin, how to configure them, and where they apply.

**Table of Contents:**
- [Quick Start](#quick-start)
- [Backend Configuration](#backend-configuration)
- [Frontend Configuration](#frontend-configuration)
- [Docker Compose Setup](#docker-compose-setup)
- [Production Deployment](#production-deployment)

---

## Quick Start

### Native Local Development (Windows PowerShell)

1. **Backend:**
   ```powershell
   cd backend
   Copy-Item .env.example .env
   # Edit .env with your local values (Cognito creds, DATABASE_URL, etc.)
   uv run alembic upgrade head
   ```

2. **Frontend:**
   ```powershell
   cd frontend
   Copy-Item .env.example .env.local
   npm run dev
   ```

3. **Verify:**
   - Backend: `uv run uvicorn app.main:app --reload` (backend/)
   - Frontend: `npm run dev` (frontend/)
   - Visit http://localhost:3000

### Docker Compose Local Development

1. **Prepare app.env:**
   ```bash
   cp app.env.example app.env
   # Edit app.env with your Cognito credentials
   ```

2. **Build and start:**
   ```bash
   docker compose build
   docker compose up -d
   ```

---

## Backend Configuration

All backend configuration is loaded from the environment into `backend/app/core/config.py::Settings` via Pydantic.

### Core Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `ENV` | Yes | `development` | Environment selector (dev/staging/production). Controls SECRET_KEY strictness. |
| `SECRET_KEY` | Yes | - | ≥32 chars. Cryptographic key for JWT signing. In dev, anything goes. Generate: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `DATABASE_URL` | Yes | `sqlite:///./dev.db` | PostgreSQL connection string. Format: `postgresql+psycopg://user:pass@host:5432/db`. SQLite is not supported. |
| `CORS_ORIGINS` | Yes | `["http://localhost:3000"]` | JSON array of allowed CORS origins for cross-origin requests. |
| `PUBLIC_BASE_URL` | Yes | `http://localhost:3000` | Public base URL for the frontend (used in /api/handoff links, etc.). |
| `RUNS_ROOT` | Yes | `/app/runs` | Sandbox filesystem for per-run artifacts. Native dev: use `./runs`. Docker: `/app/runs` (mounted volume). |

### Cognito Authentication

Cognito is the sole authentication authority. No local bcrypt/HS256 fallback exists.

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `COGNITO_USER_POOL_ID` | No* | - | Cognito user pool ID (e.g., `eu-central-1_abc123`). Development only warns if missing; production fails to boot. |
| `COGNITO_CLIENT_ID` | No* | - | Cognito app client ID. |
| `COGNITO_CLIENT_SECRET` | No* | - | Cognito app client secret. **Credential** — never commit. |
| `COGNITO_REGION` | No | `AWS_REGION` | Region where Cognito pool resides (e.g., `eu-central-1`). Defaults to `AWS_REGION` if empty. |
| `COGNITO_JWKS_CACHE_TTL_SECONDS` | No | `3600` | Time-to-live for cached public signing keys. Key rotation triggers a single refetch. |
| `ADMIN_MFA_REQUIRED` | No | `True` | Require MFA for `/api/admin/*` routes. Do not enable until all admins have enrolled at /settings/security. |
| `AUTH_EMAIL_MFA_ENABLED` | No | `False` | Mirrors pool's email-OTP constraint. Set by Terraform; don't hand-edit. When True, `forgot-password` endpoints return 409 (Cognito cannot use email as both MFA and recovery). |

*In `ENV=development`, Cognito values are optional (only warn); outside development, they are required.

### LLM Provider

The backend calls Bedrock unconditionally.

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `AWS_REGION` | No | `eu-central-1` | AWS region for Bedrock API calls. |
| `BEDROCK_MODEL_ID` | No | `anthropic.claude-haiku-4-5-20251001-v1:0` | Foundation model ID. IAM policy scopes invoke to this exact ID. |
| `BEDROCK_INFERENCE_PROFILE_ID` | No | `eu.anthropic.claude-haiku-4-5-20251001-v1:0` | Cross-region inference profile (default for EU). |
| `BEDROCK_CODING_MODEL_ID` | No | `` | Optional higher-capacity model for coding agent (e.g., `eu.anthropic.claude-sonnet-4-5-20250929-v1:0`). Empty = use default model. |
| `ANTHROPIC_API_KEY` | No | `` | Direct Anthropic API key (Bedrock takes precedence). For fallback only when Bedrock is unavailable. |
| `MISTRAL_API_KEY` | No | `` | Optional Mistral API key for free-tier fallback or eval harness. |

**AWS Credentials:**
- Bedrock uses the boto3 credential chain (IAM role, `~/.aws/credentials`, or `AWS_PROFILE` env var).
- Do NOT put AWS access keys in `.env` files.
- Local development: Set `$env:AWS_PROFILE = "your-profile"` in PowerShell, then `aws sso login`.

### Advanced Configuration

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `HOST_CAPACITY_ENABLED` | No | `True` | Enable CPU/memory matrix collection from CloudWatch. |
| `HOST_CAPACITY_GATE_ENABLED` | No | `False` | Enforce admission gate on high capacity. Default OFF (enable per environment after observation). |
| `MAX_OUTPUT_TOKENS` | No | `32768` | Token ceiling for all LLM calls. Raise only after confirming model supports it. |
| `AGENT_RECURSION_LIMIT` | No | `400` | Runaway-loop backstop for agent graph recursion. |
| `RUN_DIR_TTL_HOURS` | No | `168` | Sandbox retention after run completion (7 days, covers revision-parent window). |
| `SHUTDOWN_STOP_RUNS` | No | `False` (prod), `True` (dev) | Cooperatively cancel in-flight runs on shutdown. Development-only by default. |
| `SSE_KEEPALIVE_PING_SECONDS` | No | `15` | Ping cadence to keep SSE streams alive (ingress idle-timeout must exceed this). |
| `SSE_SUBSCRIBER_QUEUE_MAXSIZE` | No | `1000` | Per-subscriber queue size for SSE fan-out (0 = unbounded). |
| `BRIEF_MAX_CHARS` | No | `450000` | Input brief character cap (≈150k tokens, safe under Haiku's 200k context). |
| `LLM_CALL_TIMEOUT_SECONDS` | No | `900` | Per-call timeout (15 min, accommodates full-length generations). |
| `LOG_LEVEL_APP` | No | `` (auto) | Logging level. Empty = DEBUG (dev) or INFO (prod). |
| `LOG_FORMAT` | No | `` (auto) | `json` or `pretty`. Empty = auto (pretty in dev, json elsewhere). |
| `LANGSMITH_TRACING` | No | `false` | Enable LangSmith tracing. Set to `true` to enable. |

---

## Frontend Configuration

Frontend configuration is minimal and loaded at **build time** into the browser bundle.

### Environment Variables

| Variable | Required | Build-Time? | Purpose |
|----------|----------|-------------|---------|
| `NEXT_PUBLIC_API_URL` | No | Yes | API base URL for REST calls (inlined at build). Empty = same-origin proxy. |

**Resolution order (if empty or unset):**
1. Explicit `NEXT_PUBLIC_API_URL` → use verbatim
2. Browser on non-localhost host → same-origin (relative `/api`) — nginx proxies it
3. Otherwise → `http://localhost:8000` (local dev default)

**Build-time behavior:**
- `NEXT_PUBLIC_*` variables are captured at image build time
- Production images are built with empty `NEXT_PUBLIC_API_URL` so one image works dev→stage→prod
- nginx rewrites `/api` requests to the backend

**Example:**
```bash
# Native dev: backend at localhost:8000
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev

# Docker Compose: same
NEXT_PUBLIC_API_URL=http://localhost:8000 docker compose up

# Production: image built with empty value, nginx proxies /api
# (NEXT_PUBLIC_API_URL unset or empty)
docker run velocityai-frontend:latest
```

---

## Docker Compose Setup

Use `app.env` for Docker Compose local development.

### Example app.env

```bash
# Backend
ENV=development
SECRET_KEY=<generated-32-char-key>
DATABASE_URL=postgresql+psycopg://postgres:postgres@host.docker.internal:5432/velocityai
CORS_ORIGINS=["http://localhost:3000"]
PUBLIC_BASE_URL=http://localhost:3000
RUNS_ROOT=/app/runs

# Cognito (point at dev pool)
COGNITO_USER_POOL_ID=eu-central-1_abc123
COGNITO_CLIENT_ID=xyz789
COGNITO_CLIENT_SECRET=secret123
COGNITO_REGION=eu-central-1
ADMIN_MFA_REQUIRED=false
AUTH_EMAIL_MFA_ENABLED=false

# LLM
AWS_REGION=eu-central-1
BEDROCK_MODEL_ID=anthropic.claude-haiku-4-5-20251001-v1:0
BEDROCK_INFERENCE_PROFILE_ID=eu.anthropic.claude-haiku-4-5-20251001-v1:0

# Images
BACKEND_IMAGE=velocityai-backend:local
FRONTEND_IMAGE=velocityai-frontend:local

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Key Differences from Native Dev

| Setting | Native Backend | Docker Backend |
|---------|----------------|----------------|
| `DATABASE_URL` | `localhost:5432` | `host.docker.internal:5432` |
| `RUNS_ROOT` | `./runs` | `/app/runs` (mounted volume) |
| AWS credentials | Shell env (`AWS_PROFILE`) | Container inherits from host `~/.aws/` |

---

## Production Deployment

**Never commit production credentials to git.** Production configuration is loaded via Terraform and an on-host secrets loader.

### Secrets Management

- **Terraform:** Provisions Cognito pools, AWS credentials, and Bedrock policies
- **GitHub Actions + SSM:** CI/CD retrieves secrets from AWS Systems Manager Parameter Store
- **On-host loader:** At container startup, the loader script (e.g., `bootstrap-ec2.sh`) writes `app.env` from SSM values
- **docker-entrypoint.sh:** `set -eu` ensures app fails fast if config is incomplete

### Required Production Secrets (via SSM)

```
/flowin/production/SECRET_KEY
/flowin/production/DATABASE_URL
/flowin/production/COGNITO_USER_POOL_ID
/flowin/production/COGNITO_CLIENT_ID
/flowin/production/COGNITO_CLIENT_SECRET
/flowin/production/AWS_REGION
/flowin/production/BEDROCK_MODEL_ID
```

See `infra/scripts/velocityai-load-secrets.sh` for the loader allowlist (which variables are accepted). The normal deploy refreshes this script on the host before it materializes SSM values.

### Deployment Gate

The deploy pipeline runs a pre-flight check before `compose up -d`:

```bash
# .github/scripts/remote-deploy.sh §10a
docker compose run --entrypoint python migrate_local_users_to_cognito.py \
  --report --fail-on-unlinked
```

This ensures all database users are linked to Cognito before the migration 0038 runs (which requires non-NULL `cognito_sub`).

---

## Troubleshooting

### Backend won't start: Missing Cognito

```
RuntimeError: Cannot apply migration 0038 (Cognito-only users):
  the following row(s) are not cleanly Cognito-linked...
```

**Fix:**
```bash
cd backend
uv run python scripts/migrate_local_users_to_cognito.py --report
# Link unlinked rows, then retry alembic upgrade head
```

### Backend won't start: SECRET_KEY too weak (production)

```
SecretKeyMisconfigured: SECRET_KEY must be >= 32 characters in ENV=production
```

**Fix:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
# Copy output to backend/.env or SSM parameter
```

### Frontend calls wrong API

Browser console shows requests to `http://localhost:8000` instead of same-origin `/api`.

**Fix:**
- Native dev: Set `NEXT_PUBLIC_API_URL=http://localhost:8000` before `npm run dev`
- Docker: Build with empty `NEXT_PUBLIC_API_URL` and rely on nginx proxy
- Verify nginx rewrite: `docker exec <frontend-container> curl -I http://localhost:3000/api/workflows`

### Database connection timeout

```
psycopg.OperationalError: could not connect to server: No such file or directory
```

**Fix:**
- Verify PostgreSQL is running: `SELECT version();` in psql
- Check `DATABASE_URL` format: `postgresql+psycopg://user:pass@host:5432/db`
- On Windows, localhost vs 127.0.0.1 may matter; try both

---

## Quick Reference Checklist

### Deploying Backend

- [ ] `ENV` matches target (development/staging/production)
- [ ] `SECRET_KEY` is ≥32 random characters
- [ ] `DATABASE_URL` points to correct PostgreSQL instance
- [ ] `COGNITO_*` values match the target pool (never mixed pools)
- [ ] `ADMIN_MFA_REQUIRED` reflects pool state
- [ ] `RUNS_ROOT` is writable and has enough disk space
- [ ] AWS credentials are available (IAM role in prod, `AWS_PROFILE` locally)
- [ ] `uv run alembic upgrade head` succeeds before starting
- [ ] No old auth vars (`AUTH_PROVIDER`, `BREAK_GLASS_ENABLED`) are set

### Deploying Frontend

- [ ] `NEXT_PUBLIC_API_URL` set correctly (empty for prod, localhost:8000 for local)
- [ ] `npm run build` succeeds without errors
- [ ] nginx is configured with `proxy_buffering off` for `/api` (production)
- [ ] CSP header allows `connect-src` to the backend URL

---

## References

- Backend settings schema: `backend/app/core/config.py::Settings`
- Cognito migration: `.kiro/specs/login/prompt.md`
- Deployment scripts: `.github/scripts/remote-deploy.sh`
- Terraform: `infra/terraform/foundation/main.tf`
