# /flowin-handoff — IDE → Flowin pipeline

A slash command (and reusable CLI binary) for handing off a coding or
test task to Flowin. Flowin runs a multi-agent pipeline (coding → test
analysis → compliance review) against your repository, commits the
result on a fresh branch, and opens a draft pull request for human
review.

## One-time setup

### 1. Install the slash command

Run this on each developer machine (one line, idempotent, ~1 second):

```bash
curl -fsSL https://3-121-190-113.nip.io/install/flowin-handoff | bash
```

The installer writes:

- `~/.claude/commands/flowin-handoff.md` — the Claude Code slash command
- `~/.local/bin/flowin-handoff` — the CLI binary the command shells out to

It will warn if `~/.local/bin` is not on your `PATH` or if `git`, `jq`,
or `curl` are missing (install those via `brew` / `apt-get`).

### 2. Mint a Flowin API key

Log into Flowin and open **`https://3-121-190-113.nip.io/handoff/settings`**
→ under **Flowin API keys** click **Create key**. The plaintext token is
shown exactly once — copy it.

### 3. Connect your GitHub account

On the same page (`/handoff/settings`) → under **GitHub access token** →
paste a GitHub Personal Access Token with the `repo` scope and click
Save. The token is Fernet-encrypted at rest and never returned by any
API.

### 4. Tell Claude Code about the API key

Edit `~/.claude/settings.json`:

```json
{
  "env": {
    "FLOWIN_API_URL": "https://3-121-190-113.nip.io",
    "FLOWIN_API_KEY": "flowin_<the-key-you-copied>"
  }
}
```

Reload Claude Code.

## Usage

### Claude Code

From inside any git repository, type:

```
/flowin-handoff <task description>
```

Examples:

```
/flowin-handoff fix the failing test in tests/auth/test_login.py
/flowin-handoff add unit tests for the new RateLimiter class
/flowin-handoff refactor the upload handler to stream from disk
```

The slash command captures the current Claude Code session's
transcript, bundles it with the task description, and POSTs to Flowin.
You get a browser URL — open it to start the pipeline.

### Cursor / VS Code / Windsurf (via MCP)

Flowin exposes a remote MCP server. Add to your IDE's MCP config:

```json
{
  "mcpServers": {
    "flowin": {
      "url": "https://3-121-190-113.nip.io/mcp/handoff",
      "transport": "http",
      "headers": {
        "Authorization": "Bearer flowin_<your-key>"
      }
    }
  }
}
```

The server exposes one tool: `flowin_handoff(task, repo_url, mode?,
transcript_excerpt?, source_branch?)`. Because MCP servers cannot
directly read chat history (the IDE host owns it), the model decides
what to put in `transcript_excerpt` based on the prompt's hint.

### Bare shell (Kiro, GH Copilot, plain terminal)

After running the installer, `flowin-handoff` is on your `PATH`:

```bash
FLOWIN_API_URL=https://3-121-190-113.nip.io \
FLOWIN_API_KEY=flowin_xxx \
flowin-handoff "fix the failing test"
```

## What runs on the server

| Step | Agent | Model |
|---|---|---|
| 1. Classify task | tiny classifier | Haiku |
| 2. Clone repo (depth 50) | `git` subprocess | — |
| 3. Coding edits (skipped in `test` mode) | CodingAgent | Sonnet (Haiku fallback) |
| 4. Apply edits | path-traversal-checked file writes | — |
| 5. Test coverage analysis | TestAgent | Haiku |
| 6. Compliance review (OWASP, best practices) | ComplianceAgent | Haiku |
| 7. Commit + push | `git` subprocess | — |
| 8. Open draft PR | GitHub REST API | — |

The execution sandbox uses POSIX rlimits (CPU, virtual memory, FD
count, max-process count) and a wall-clock timeout. The workspace
lives under `/tmp/handoff-<id>/` and is deleted on completion or
failure. No user-supplied code is executed at any point — the test
agent reads files and produces analysis, it does not run tests.

## Safety

- The handoff URL token alone is **not** enough to view or start the
  pipeline — opening it requires a logged-in Flowin session that
  matches the issuer. A leaked URL leaks nothing.
- The PAT is decrypted only in the running pipeline process, never
  logged, never returned over any API.
- The branch name is `flowin-handoff/<short-id>-<slug>` and the PR is
  always opened as **draft** so CI can run before a human merges.

## Reinstalling / updating

The installer is idempotent — re-running `curl ... | bash` overwrites
both files with the latest server-side versions. Use this whenever the
Flowin team ships a new slash-command shape.

## Uninstalling

```bash
rm -f ~/.claude/commands/flowin-handoff.md ~/.local/bin/flowin-handoff
```
