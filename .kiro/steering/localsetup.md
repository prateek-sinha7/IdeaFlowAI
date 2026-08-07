---
inclusion: always
---

# Local Development Environment

**Platform:** Windows (PowerShell) | **Python:** `uv` with `uv run` | **Node:** `npm` | **Database:** PostgreSQL

## Working Directory Rules

**For Kiro/automation:**
- Never use `cd` commands. Always set the `cwd` parameter to the target directory.
- Backend commands: use `cwd: backend/` and prefix with `uv run`
- Frontend commands: use `cwd: frontend/` and use `npm` directly

**For manual terminals:**
- Change to `backend/` or `frontend/` before running any command in that directory.

## Backend

### Dependencies

- Update dependencies in `requirements.txt`, then run: `uv pip install -r requirements.txt`
- Add a new dependency: `uv add <package>==<version>` (use exact versions, never floating ranges)

### Database (PostgreSQL only)

- Local database URL: stored in `backend/.env` (use `app.env.example` as template)
- Never commit `backend/.env`
- After schema/migration changes, always run before starting the backend: `uv run alembic upgrade head`

### Common Tasks

| Task | Command | Working Directory |
|---|---|---|
| Install/update deps | `uv pip install -r requirements.txt` | `backend/` |
| Run Python command | `uv run <command>` | `backend/` |
| Run tests (once) | `uv run pytest` | `backend/` |
| Apply migrations | `uv run alembic upgrade head` | `backend/` |

## Frontend

### Dependencies

- Use `npm` exclusively (no `yarn`, no `pnpm`)
- Install: `npm install`
- Add dependency with exact version: `npm install --save-exact <package>@<version>`
- Keep `package-lock.json` synchronized with `package.json`

### Common Tasks

| Task | Command |
|---|---|
| Install dependencies | `npm install` |
| Run lint | `npm run lint` |
| Run tests (once) | `npm run test` |
| Run E2E tests (once) | `npm run e2e` |
| Build for production | `npm run build` |

## Critical Rules

- **No long-running processes in automation:** Do not start dev servers, watch mode (`--watch`), or `uvicorn --reload` through Kiro. Tell the user to run these manually with the exact command.
- **Tests must be single-pass:** Always use single-execution mode (e.g., `--run` flag); never enable watch mode.
- **No watch mode:** All automated commands must complete and exit.
- **Validation location:** Run backend validation from `backend/` with `uv run`; run frontend validation from `frontend/` with `npm`.

## File Locations

- Backend env: `backend/.env` (local only, not committed)
- Env template: `app.env.example` (at project root)
- Migrations: run commands from `backend/`
- Frontend output: check build configuration first (may be `.next`, `dist`, or custom path)
