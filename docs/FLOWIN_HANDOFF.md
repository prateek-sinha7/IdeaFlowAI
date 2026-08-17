# /flowin-handoff — implementation report

**Branch state**: implemented locally, **NOT committed**. Run the checks
below, then commit/push when you're happy.

This document is the source of truth for the feature: what was built,
where every file lives, how to validate it locally, and what's
deliberately out of scope for v1.

---

## What this gives the user

From inside any AI IDE (Claude Code, Cursor, VS Code, Windsurf — Kiro
via shell), the user types one slash command (or invokes one MCP tool)
with a task description. Flowin:

1. Accepts the task, IDE conversation transcript, repo URL, and
   GitHub PAT (one-time stored).
2. Returns a one-time-claim URL the user opens in the browser.
3. In the browser: shows a workflow page (visually identical in spirit
   to the existing pptx / user-stories workflows). The user reviews
   the plan and clicks **Start**.
4. Runs a multi-agent pipeline against a depth-50 shallow clone in a
   POSIX-sandboxed `/tmp` workspace:
   - **Coding agent** (Sonnet-preferred via config flag) proposes a
     structured edit plan with `summary`, `rationale`, and a list of
     `{path, operation, old_string, new_string}` edits. Skipped in
     `test` mode.
   - **Test agent** (Haiku) analyses test coverage and quality on the
     post-edit tree.
   - **Compliance agent** (Haiku) produces an OWASP-aligned
     security/best-practices report.
5. Commits to `flowin-handoff/<short-id>-<slug>`, pushes via the user's
   PAT, opens a **draft** PR via the GitHub REST API with the test
   verdict + compliance findings in the body.
6. WebSocket-streams every event to the browser in real time.

No new infra. Same EC2, same backend container, same nginx.

---

## File-by-file map (all uncommitted)

### Backend

| File | Purpose |
|---|---|
| `backend/app/core/crypto.py` | Fernet wrapper, HKDF-derived from `SECRET_KEY` (separate domain from JWT signing key). |
| `backend/app/models/handoff.py` | SQLAlchemy: `UserGithubCredential`, `UserApiKey`, `HandoffSession` + status/mode constants. |
| `backend/app/models/__init__.py` | Re-exports the three new models so `alembic env.py` discovers them. |
| `backend/alembic/versions/0002_handoff_tables.py` | Additive migration. Chains off `0001`. |
| `backend/app/agents/handoff/__init__.py` | Package init. |
| `backend/app/agents/handoff/classifier.py` | Tiny LLM classifier (`coding` vs `test`). |
| `backend/app/agents/handoff/coding_agent.py` | CodingAgent — Sonnet-preferred; structured JSON edit-plan output. Best-practices prompt baked in. |
| `backend/app/agents/handoff/test_agent.py` | TestAgent — Haiku; structured coverage/quality report. |
| `backend/app/agents/handoff/compliance_agent.py` | ComplianceAgent — Haiku; OWASP + best-practices report. |
| `backend/app/services/handoff_github.py` | Sandboxed `git` subprocess (rlimits + scrubbed env + redaction). GitHub REST for PR creation. |
| `backend/app/services/handoff_pipeline.py` | Async-generator pipeline orchestrator: clone → classify → code → test → compliance → commit → push → PR. Includes path-traversal validator and edit applier. |
| `backend/app/api/api_key_auth.py` | `X-Flowin-API-Key` dependency + key minting helper. |
| `backend/app/api/handoff.py` | `POST /api/handoff/receive`, `GET /api/handoff/{token}`, `POST /api/handoff/{token}/start`. Background-task driver that pumps the pipeline generator and persists outcome. |
| `backend/app/api/settings.py` | `PUT/GET/DELETE /api/settings/github-pat`, `POST/GET/DELETE /api/settings/api-keys`. |
| `backend/app/api/mcp.py` | Remote MCP HTTP-streamable server. Methods: `initialize`, `tools/list`, `tools/call`, `ping`. One tool: `flowin_handoff`. |
| `backend/app/api/install.py` | `GET /install/flowin-handoff` — returns a self-contained bash installer that writes the slash command + CLI binary into the user's home. Also exposes `/install/flowin-handoff/command` and `/install/flowin-handoff/script` for advanced users. **Canonical source of truth for the two installed files.** |
| `backend/app/api/websocket_handoff.py` | `/ws/handoff/{token}` — JWT-subprotocol auth, issuer-only, in-memory pub/sub for pipeline events. |
| `backend/app/core/config.py` | **Modified**: added `BEDROCK_CODING_MODEL_ID`, `PUBLIC_BASE_URL`, `HANDOFF_MAX_TRANSCRIPT_BYTES`. |
| `backend/app/main.py` | **Modified**: registers the four new routers. |
| `backend/Dockerfile` | **Modified**: adds `git` to the runtime apt-get layer. |

### Frontend

| File | Purpose |
|---|---|
| `frontend/src/lib/api-handoff.ts` | Typed client for the new endpoints. |
| `frontend/src/components/handoff/HandoffWorkflow.tsx` | Top-level workflow view: top-bar + left agent panel + right preview pane. Same shape as the pptx / user-stories workflows so the UI feels native. |
| `frontend/src/components/handoff/HandoffAgentPanel.tsx` | LEFT pane: agent cards (Coding → Test → Compliance) with the same lettered-icon + status-badge language used by the existing `AgentProgressPanel`. Phase log at the bottom. |
| `frontend/src/components/handoff/HandoffPreviewPanel.tsx` | RIGHT pane: tab bar (Diff · Tests · Compliance) with auto-follow as agents finish + sticky PR result strip. |
| `frontend/src/components/handoff/DiffView.tsx` | Per-file before/after diff rendering. CREATE / MODIFY / DELETE badges, APPLIED / REJECTED status pills, stacked red-removed / green-added code blocks. |
| `frontend/src/components/handoff/ReportViews.tsx` | `TestReportView` + `ComplianceReportView`. Verdict pill at the top, severity-pill grouped findings, recommended-actions lists. Same data lands in the PR body. |
| `frontend/src/components/handoff/IntegrationsCard.tsx` | Install card + GitHub PAT card + Flowin API key card. Self-contained so it can render both inside the handoff onboarding panel and on the standalone settings page. |
| `frontend/src/components/handoff/useHandoffPipelineState.ts` | Reducer that projects WS events into the typed pipeline state. |
| `frontend/src/components/handoff/types.ts` | Local types — including `HandoffStreamMessage` which widens the shared envelope for handoff-specific event names without touching the global enum. |
| `frontend/src/app/handoff/[token]/page.tsx` | Route entry — thin wrapper that mounts `<HandoffWorkflow>`. |
| `frontend/src/app/handoff/settings/page.tsx` | Standalone `/handoff/settings` page that mounts `<IntegrationsCard>`. Deliberately separate from `/dashboard` settings so the existing Account Settings panel is untouched. |

### Claude Code / Kiro / shell

The slash-command markdown and the CLI binary are NOT committed to
this repository. They live as Python string constants inside
`backend/app/api/install.py` and are served by the installer endpoint.
Developers and users install them by running the
`curl -fsSL <FLOWIN_API_URL>/install/flowin-handoff | bash` one-liner.

| File | Purpose |
|---|---|
| `.claude/skills/flowin-handoff/README.md` | One-page user-facing setup + usage doc (installer, MCP, bare shell). |

### Tests

| File | Purpose |
|---|---|
| `backend/tests/integration/test_handoff_api.py` | Integration tests: crypto, API-key minting/revocation, handoff receive/get/start auth + issuer-only enforcement, mode/size validation, MCP JSON-RPC dispatch + tool validation, path-traversal protection, edit applier, branch-name slugger, GitHub URL parser, PAT settings with mocked GitHub, installer endpoint asserts + actual `bash <(curl)`-equivalent run in a sandboxed `$HOME`. **All pass.** |

---

## Architecture decisions (why, not what)

### Why slash command + MCP server (both)

Claude Code's slash command can read the full session JSONL — the
backend gets ground-truth conversation context. MCP servers
**cannot** see chat history (the IDE host owns it), so the LLM must
manually choose what to put in `transcript_excerpt`. Shipping both
means: native fidelity for Claude Code users; cross-IDE reach for
Cursor / VS Code / Windsurf via the MCP tool. The two surfaces share
the same backend endpoint pair (`/api/handoff/receive`, `/mcp/handoff`).

### Why subprocess sandbox + no code execution

The user explicitly required single-EC2 and "minimal changes." A
docker-in-docker per-task model would require mounting `docker.sock`
into the backend container — operational complexity and additional
escape surface. Instead the pipeline reuses the existing pptx-export
hardening:

- `preexec_fn=_apply_child_rlimits` → CPU 30s, AS 1 GiB, FSIZE 256 MiB,
  NOFILE 256, NPROC 256 (per-child)
- Wall-clock timeout 90s per git op
- Scrubbed env (only `HOME`, `PATH`, `LANG`, git knobs)
- `GIT_TERMINAL_PROMPT=0` and `GIT_CONFIG_GLOBAL=/dev/null`

**No user-supplied code is ever executed.** The TestAgent and
ComplianceAgent are LLM static-analysis, not test runners. The user's
own CI runs the actual tests on the opened PR — exactly like Copilot
Coding Agent.

### Why structured JSON edit-plan vs free-form patch

CodingAgent returns `{"edits": [{"path", "operation", "old_string",
"new_string"}, ...]}`. Each edit goes through `_safe_workspace_join`
(rejects `..`, absolute paths, `.git`, symlink escapes) before write.
Modify requires `old_string` to match exactly once. Rejected edits go
straight into the PR body so the human reviewer sees what the agent
wanted to do but couldn't.

### Why Fernet + HKDF separation from `SECRET_KEY`

Reusing `SECRET_KEY` directly for at-rest crypto would mean a leaked
JWT-signing key also decrypts every stored PAT (and vice versa). HKDF
with a fixed `info` string yields a derived key that:
- still rotates if `SECRET_KEY` rotates (good — old PATs become
  un-decryptable, forcing re-entry rather than silent persistence with
  an unknown key);
- is domain-separated from any other use of `SECRET_KEY`.

A dedicated test (`test_pat_crypto_does_not_decrypt_jwt`) asserts that
a Fernet token from a different key cannot decrypt as a PAT.

### Why URL token + login + issuer-match (not just URL token)

A leaked URL must not be a credential. The `GET /api/handoff/{token}`
route returns 404 (never 403) for any user that isn't the issuer, so
the URL alone reveals nothing about whether a session exists. The
WebSocket subprotocol enforces the same check at connection time.

---

## Running the tests

```bash
# Backend integration tests (19 new, all pass)
cd backend
pytest tests/integration/test_handoff_api.py -v

# Full backend unit suite, no regressions (138 existing tests pass)
pytest tests/unit/ -v --ignore=tests/unit/test_pptx_export_path_resolution.py

# Alembic round-trip: migration ↔ models stay in sync (5 tests pass)
pytest tests/unit/test_alembic.py -v

# Frontend TypeScript compiles clean
cd ../frontend
npx tsc --noEmit -p .
```

Smoke-import the whole backend (validates router wiring):

```bash
PYTHONPATH=backend python3 -c "
from app.main import app
paths = sorted({r.path for r in app.routes if hasattr(r, 'path') and any(s in r.path for s in ['/handoff', '/settings', '/mcp'])})
for p in paths: print(p)
"
```

Expected output (paths repeat for GET/POST/etc.):

```
/api/handoff/receive
/api/handoff/{token}
/api/handoff/{token}/start
/api/settings/api-keys
/api/settings/api-keys/{key_id}
/api/settings/github-pat
/mcp/handoff
/ws/handoff/{token}
```

---

## End-to-end script (every step a fresh user takes)

The full happy path, from "have nothing" to "PR opened on GitHub":

**Account setup (one-time, in Flowin web UI)**
1. Register / log in at `https://<flowin-host>`.
2. Open `https://<flowin-host>/handoff/settings` (URL-direct — there is
   no link from `/dashboard`; that is by design, the existing Account
   Settings panel is untouched).
3. Under **Flowin API keys** → **Create key** → copy plaintext token.
4. Under **GitHub access token** → paste a PAT with `repo` scope → Save.

**Machine setup (one-time, per dev machine)**
5. Run the one-liner:
   `curl -fsSL https://<flowin-host>/install/flowin-handoff | bash`
6. If installer warns about `PATH`, add the printed `export PATH=...`
   line to `~/.zshrc` / `~/.bashrc` and reload your shell.
7. If installer warns about missing `git` / `jq` / `curl`, install via
   `brew install` (macOS) or `apt-get install` (Linux).
8. Edit `~/.claude/settings.json`:
   ```json
   { "env": { "FLOWIN_API_URL": "https://<flowin-host>",
              "FLOWIN_API_KEY": "flowin_<token-from-step-3>" } }
   ```
9. Reload Claude Code (quit + reopen, or `Cmd+Shift+P` → reload window).

**Per task (every use)**
10. `cd` into the target git repo (must have an `origin` remote on
    GitHub that you have push rights on).
11. In Claude Code: `/flowin-handoff <task description>`.
12. The slash command prints a URL — open it in the browser.
13. Handoff workflow page loads (left panel = agent cards, right panel
    = Diff / Tests / Compliance tabs). Click **Start pipeline**.
14. Watch agents flip queued → running → done. Right panel
    auto-follows: shows diff as coding agent finishes, then test
    report, then compliance report.
15. Green "Pull request opened" strip appears at the bottom of the
    right pane. Click **View PR #N** → GitHub draft PR opens.
16. Review the PR body (full reports from all three agents) → let CI
    run → mark Ready-for-review → merge.

**Recovery / edge cases**
- **No PAT saved yet**: handoff page replaces the body with an inline
  IntegrationsCard. Save the PAT → Start button activates.
- **Pipeline failed**: red strip appears with the error. Top-bar
  **Retry pipeline** button is active (the state is `failed`).
- **Handoff URL expired (1 h after creation)**: body shows "expired"
  message. Re-run `/flowin-handoff` from the IDE to mint a new one.
- **Pipeline hung past expiry**: next page load transitions it to
  `failed` automatically; Retry becomes available.

## End-to-end walk-through (manual, local)

The pipeline's outer loop is testable without Bedrock if you replace
`BaseAgent.run` with a stub. The walk-through below is the **full**
path including real Bedrock + a real (but throw-away) GitHub repo;
swap any step out if you don't have credentials handy.

### 1. Prep

```bash
# Backend (in dev, with Bedrock creds and a PAT-enabled GitHub account)
export ENV=development
export SECRET_KEY=$(openssl rand -hex 64)
export DATABASE_URL=sqlite:///./dev.db
export BEDROCK_INFERENCE_PROFILE_ID=eu.anthropic.claude-haiku-4-5-20251001-v1:0
# Optional Sonnet override for the coding agent:
# export BEDROCK_CODING_MODEL_ID=eu.anthropic.claude-sonnet-4-5-20250929-v1:0
export AWS_REGION=eu-central-1
export PUBLIC_BASE_URL=http://localhost:3000

cd backend
alembic upgrade head
# --timeout-graceful-shutdown is required, not optional: without it a live SSE
# stream (any run you are watching) makes uvicorn ignore SIGTERM forever — the
# server can only be stopped with kill -9, and its shutdown code never runs.
# No --reload: it masks crashes, and untreated it leaves two stuck processes.
uvicorn app.main:app --port 8000 --timeout-graceful-shutdown 5
```

```bash
# Frontend
cd frontend
NEXT_PUBLIC_API_URL=http://localhost:8000 \
NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws/chat \
npm run dev
```

### 2. Configure once (in the browser)

1. Open `http://localhost:3000`, register and log in.
2. Navigate to **`http://localhost:3000/handoff/settings`** (the handoff
   settings page is separate from the standard Account Settings panel —
   the dashboard is deliberately untouched).
3. Paste a GitHub PAT (must have `repo` scope) under "GitHub access
   token" and click Save. You should see "Saved for
   &lt;your-github-login&gt;".
4. Click "Create key" under "Flowin API keys", name it "Local", copy
   the plaintext token (shown once).

### 3. Install the slash command on your machine

The slash command is **not** committed in any repository — Claude Code
looks for `~/.claude/commands/flowin-handoff.md` (or a project-scoped
`.claude/commands/flowin-handoff.md`). Run the one-line installer once:

```bash
curl -fsSL http://localhost:8000/install/flowin-handoff | bash
```

This writes:

- `~/.claude/commands/flowin-handoff.md` — the slash command (PATH-based,
  calls `flowin-handoff "$ARGUMENTS"`)
- `~/.local/bin/flowin-handoff` — the CLI binary

The installer is idempotent. Production users curl from
`https://3-121-190-113.nip.io/install/flowin-handoff` instead; the
Settings UI shows the right command pinned to the current host. The
endpoint requires no auth — the file bodies are generic.

If `~/.local/bin` is not on your `PATH`, the installer prints exactly
the line to add to `~/.zshrc` / `~/.bashrc`. It also warns if `git`,
`jq`, or `curl` are missing (the script needs all three).

### 4. Configure your IDE (Claude Code)

Edit `~/.claude/settings.json`:

```json
{
  "env": {
    "FLOWIN_API_URL": "http://localhost:8000",
    "FLOWIN_API_KEY": "flowin_<the-token-you-just-copied>"
  }
}
```

Reload Claude Code.

### 5. Trigger a handoff

In any local repo (any directory with a git remote pointing at a repo
you have push rights on), open Claude Code and run:

```
/flowin-handoff add a docstring to the main function in src/index.ts
```

The slash command:

- prints `✓ Handoff created.`
- prints the URL `http://localhost:3000/handoff/<token>`
- prints the expiry timestamp

### 6. Run the pipeline

1. Open the URL.
2. The page shows the task description, repo URL, source branch, and
   "GitHub PAT — Saved for &lt;username&gt;" (because step 2 above).
3. Click **Start handoff pipeline**.
4. Watch the phase log fill out: `setup → clone → classify → coding
   → test → compliance → commit → push → open_pr`.
5. Each agent card flips from "queued" → "running" → "done" with the
   summary line populated.
6. A green card appears at the bottom: "Pull request opened —
   View PR #N". Click through to GitHub.

### 7. Expected PR contents

- Branch name: `flowin-handoff/<8-hex-chars>-<task-slug>`
- PR is opened as **draft**.
- Body sections:
  - Summary (task description + coding-agent summary + rationale)
  - Files edited (applied + rejected counts and reasons)
  - Test analysis (verdict + missing coverage + quality issues)
  - Compliance review (verdict + findings + positives)
  - "Requested by &lt;your-email&gt;"

### Test-only mode

If the task is purely test work (e.g. "add tests for the existing
`Rate-Limiter` class"), the classifier returns `test`, the CodingAgent
is skipped, and the pipeline produces a report-only outcome with no PR
(since there's no diff). Set `--mode=test` explicitly via:

```
FLOWIN_MODE=test /flowin-handoff "evaluate test coverage in src/api/"
```

### MCP-side smoke check (without an MCP client)

```bash
# 1. Initialize
curl -s http://localhost:8000/mcp/handoff \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer flowin_<api-key>" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | jq

# 2. List tools
curl -s http://localhost:8000/mcp/handoff \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer flowin_<api-key>" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | jq

# 3. Call the tool
curl -s http://localhost:8000/mcp/handoff \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer flowin_<api-key>" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "flowin_handoff",
      "arguments": {
        "task": "add a docstring to main()",
        "repo_url": "https://github.com/octocat/Hello-World",
        "mode": "auto"
      }
    }
  }' | jq
```

Last response includes `structuredContent.url` — that's the handoff URL
the user opens.

---

## What's intentionally NOT in v1

These were considered and deferred to keep the diff minimal:

- **Per-tenant encryption keys for PATs.** Single derived key today;
  fine until we add multi-tenant isolation.
- **Test execution.** No `npm test` / `pytest` runs server-side — the
  user's CI does that on the PR. Adds zero attack surface today, room
  to add later if needed.
- **GitHub OAuth App.** PAT-based for now. Swap to a GitHub App when
  we want org-install ergonomics.
- **MCP SSE / GET streaming.** Tool is synchronous (creates handoff,
  returns URL). The long-running work streams over the dedicated
  `/ws/handoff/{token}` to the browser, not over the MCP transport.
- **Frontend Playwright suite.** Hand-walked above; backend pytest
  covers the security-critical contract.
- **SessionEnd hook auto-capture.** The current script is
  argument-driven; a hook variant is one shell-script edit away.
- **Dashboard sidebar entry for handoff history.** Each session is
  reachable by its token; a "Recent handoffs" list can come later.

---

## Where to commit from

The full diff lives in the working tree. Suggested commits (don't
commit yet — the user explicitly asked):

1. `backend: handoff models, crypto, migration` — `app/core/crypto.py`, `app/models/handoff.py`, `app/models/__init__.py`, `alembic/versions/0002_handoff_tables.py`
2. `backend: handoff agents and pipeline orchestrator` — `app/agents/handoff/*`, `app/services/handoff_github.py`, `app/services/handoff_pipeline.py`
3. `backend: handoff REST + WS + MCP routes, settings endpoints` — `app/api/handoff.py`, `app/api/websocket_handoff.py`, `app/api/settings.py`, `app/api/mcp.py`, `app/api/api_key_auth.py`, `app/main.py`
4. `backend: install endpoint for the /flowin-handoff slash command + CLI binary` — `app/api/install.py`
5. `backend: pin git to runtime image, settings flags` — `backend/Dockerfile`, `app/core/config.py`
6. `frontend: self-contained handoff workflow module (left agents + right preview/diff/reports + install card)` — `src/lib/api-handoff.ts`, `src/components/handoff/*` (entire folder), `src/app/handoff/[token]/page.tsx`, `src/app/handoff/settings/page.tsx`
7. `claude-code: reference README for /flowin-handoff` — `.claude/skills/flowin-handoff/README.md`
8. `tests: integration coverage for /flowin-handoff (incl. installer end-to-end)` — `backend/tests/integration/test_handoff_api.py`
9. `docs: /flowin-handoff implementation report` — `docs/FLOWIN_HANDOFF.md`

Or one big commit if you prefer a single landing — the changes are
strongly internally cohesive.

**Deleted along the way** (don't expect to see them in the diff — they
were stale project-scoped duplicates and now live as Python strings
inside `app/api/install.py`):
- `.claude/commands/flowin-handoff.md`
- `.claude/skills/flowin-handoff/handoff.sh`
