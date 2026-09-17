# Flowin

Flowin is a manifest-driven workflow runtime with a FastAPI backend and a Next.js frontend. Cognito is the only authentication authority; pipeline run events use REST commands and per-run Server-Sent Events (SSE).

## Native local setup (Windows)

Prerequisites: Python 3.13+ with `uv`, Node.js 24, npm, a locally running PostgreSQL instance, AWS access for the development Cognito pool, and either AWS Bedrock access or an Anthropic API key. Docker is not required or supported for the native local path.

1. Create your ignored local configuration files:

   ```powershell
   Copy-Item backend/.env.example backend/.env
   Copy-Item frontend/.env.example frontend/.env.local
   ```

2. Edit `backend/.env` with a valid PostgreSQL `DATABASE_URL` and the Cognito pool values supplied by the environment owner. Create the writable sandbox location:

   ```powershell
   New-Item -ItemType Directory -Force backend/runs
   ```

3. Authenticate to AWS when using Cognito or Bedrock. `AWS_PROFILE` belongs in the current PowerShell session, not in `backend/.env`:

   ```powershell
   $env:AWS_PROFILE = "your-profile"
   aws sso login
   ```

4. Install dependencies and inspect existing local users before migrations. Migration `0038` deliberately refuses to drop local credentials for an unlinked user:

   ```powershell
   # Run from backend/
   uv sync
   uv run python scripts/migrate_local_users_to_cognito.py --report
   ```

   If the report lists users, follow `docs/runbooks/cognito-cutover.md` to link an existing Cognito account or invite a user before continuing. Do not invent a Cognito `sub` or delete an account with application data.

5. Apply migrations and install frontend packages:

   ```powershell
   # Run from backend/
   uv run alembic upgrade head
   ```

   ```powershell
   # Run from frontend/
   npm install
   ```

6. Run each server manually in its own terminal:

   ```powershell
   # backend/ terminal
   uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

   ```powershell
   # frontend/ terminal
   npm run dev
   ```

Open `http://localhost:3000`. The frontend only uses `NEXT_PUBLIC_API_URL`; no public WebSocket URL exists. An app can start in development without Cognito settings for non-auth work, but sign-in and protected APIs require a configured Cognito development pool.

## Configuration reference

- `backend/.env.example` is the authoritative native backend template.
- `frontend/.env.example` is the authoritative native frontend template.
- `app.env.example` is for the separate Docker Compose path only.
- `env-templates/.env.production.example` describes the production backend contract. Production secrets must come from the secrets loader or approved secret manager.

All `NEXT_PUBLIC_*` variables are exposed to browsers and are fixed when the frontend is built. Never place a secret in a frontend environment file.

## Verification

```powershell
# backend/
uv run alembic heads
uv run python scripts/verify_cognito_cutover.py --check-pool

# frontend/
npm run lint
npm run build
```
