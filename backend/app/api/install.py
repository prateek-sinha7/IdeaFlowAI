"""Installer endpoint for the /flowin-handoff slash command.

Returns a self-contained bash script that, when piped to ``bash``,
writes two files into the user's home:

* ``~/.claude/commands/flowin-handoff.md`` — the Claude Code slash
  command. Invokes the binary by name (PATH-based) rather than by
  relative path so it works from any repo.
* ``~/.local/bin/flowin-handoff`` — the script that captures the
  current Claude Code session transcript and POSTs to
  ``/api/handoff/receive``.

This module is the canonical source of truth for both files. The
``.claude/`` directory in the Flowin repo no longer holds them — they
exist here as Python string constants so the install endpoint, the
backend tests, and any future surface (web download button, npm
package, etc.) can all reference the same bytes.

The endpoint is intentionally unauthenticated: the installer text is
generic, contains no secrets, and the user still needs their Flowin
API key and PAT to actually use the result. Returning it without a
gate makes the ``curl | bash`` onboarding shape work for first-time
users who haven't logged in yet.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from app.core.config import settings

router = APIRouter(prefix="/install", tags=["install"])


# --- Canonical file contents -------------------------------------------
#
# These two strings are what the installer drops into the user's home.
# They are the SOURCE of truth — the bash installer below uses
# heredoc-style ``cat`` to write them verbatim.


SLASH_COMMAND_MD = """\
---
description: Hand off a coding or test task to VelocityAI (multi-agent pipeline that opens a PR)
argument-hint: <task description, e.g. "fix the failing user-login test">
allowed-tools: Bash(flowin-handoff:*)
---

Hand off the current task to VelocityAI. VelocityAI will run a multi-agent pipeline
(coding agent → test analysis → compliance review) against the current
repository on a fresh branch, then open a draft pull request.

**Task to hand off**: $ARGUMENTS

Run the handoff (the `flowin-handoff` binary is on your PATH after running the installer):

!flowin-handoff "$ARGUMENTS"

Once the script prints a URL, tell the user to open it in their browser. Do
not attempt to run the pipeline yourself — that work happens server-side at
the URL.
"""


HANDOFF_SCRIPT_SH = """\
#!/usr/bin/env bash
# flowin-handoff — capture the current IDE session transcript + a task
# description and POST them to Flowin's /api/handoff/receive endpoint.
#
# Installed by: curl -fsSL <FLOWIN_API_URL>/install/flowin-handoff | bash
#
# Required env (set in ~/.claude/settings.json under "env", or export
# in your shell rc):
#   FLOWIN_API_URL    — e.g. https://3-121-190-113.nip.io
#   FLOWIN_API_KEY    — long-lived key minted at /api/settings/api-keys
#
# Optional env:
#   FLOWIN_MODE       — auto | coding | test  (default: auto)
#   FLOWIN_BRANCH     — source branch override (default: current branch)
#   FLOWIN_SOURCE     — source_client tag (default: "claude-code")
#   FLOWIN_TRANSCRIPT — explicit transcript path; otherwise auto-detected

set -euo pipefail

TASK="${1-${FLOWIN_TASK-}}"
if [[ -z "${TASK// }" ]]; then
  echo "usage: flowin-handoff <task description>" >&2
  exit 2
fi

if [[ -z "${FLOWIN_API_URL-}" ]]; then
  echo "FLOWIN_API_URL is not set. Add it to ~/.claude/settings.json under 'env' and reload." >&2
  exit 2
fi
if [[ -z "${FLOWIN_API_KEY-}" ]]; then
  echo "FLOWIN_API_KEY is not set. Create one at ${FLOWIN_API_URL}/handoff/settings (VelocityAI API keys → Create key)." >&2
  exit 2
fi

if ! command -v git >/dev/null 2>&1; then
  echo "git is required but was not found on PATH." >&2
  exit 2
fi
if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required but was not found on PATH. Install via:  brew install jq  (macOS) or  apt-get install jq  (Debian/Ubuntu)." >&2
  exit 2
fi

REPO_URL="$(git remote get-url origin 2>/dev/null || true)"
if [[ -z "$REPO_URL" ]]; then
  echo "No 'origin' remote in the current directory. Run from inside the target git repo." >&2
  exit 2
fi
BRANCH="${FLOWIN_BRANCH-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '')}"
if [[ "$BRANCH" == "HEAD" ]]; then
  BRANCH=""
fi

# Locate the Claude Code session transcript.
# Claude Code stores per-session JSONL at:
#   ~/.claude/projects/<encoded-cwd>/<session-id>.jsonl
# where <encoded-cwd> is the absolute path with '/' replaced by '-'.
# We pick the most-recently-modified file under that directory.
TRANSCRIPT_PATH="${FLOWIN_TRANSCRIPT-${CLAUDE_TRANSCRIPT_PATH-}}"
if [[ -z "$TRANSCRIPT_PATH" ]]; then
  CWD_KEY="$(pwd | sed 's:/:-:g')"
  CANDIDATE_DIR="$HOME/.claude/projects/${CWD_KEY}"
  if [[ -d "$CANDIDATE_DIR" ]]; then
    TRANSCRIPT_PATH="$(ls -t "$CANDIDATE_DIR"/*.jsonl 2>/dev/null | head -n1 || true)"
  fi
fi

TRANSCRIPT_CONTENT=""
if [[ -n "$TRANSCRIPT_PATH" && -f "$TRANSCRIPT_PATH" ]]; then
  # Cap at ~512 KB to stay well under the backend's 1 MiB limit even if the
  # body inflates a bit during JSON-encoding.
  TRANSCRIPT_CONTENT="$(tail -c 524288 "$TRANSCRIPT_PATH" || true)"
fi

MODE="${FLOWIN_MODE-auto}"
SOURCE_CLIENT="${FLOWIN_SOURCE-claude-code}"

PAYLOAD="$(
  jq -n \\
    --arg task "$TASK" \\
    --arg transcript "$TRANSCRIPT_CONTENT" \\
    --arg repo_url "$REPO_URL" \\
    --arg mode "$MODE" \\
    --arg source_branch "$BRANCH" \\
    --arg source_client "$SOURCE_CLIENT" \\
    '{
      task: $task,
      transcript: $transcript,
      repo_url: $repo_url,
      mode: $mode,
      source_branch: ($source_branch | select(length>0)),
      source_client: $source_client
    }'
)"

RESPONSE="$(
  curl -sS \\
    --fail-with-body \\
    -X POST \\
    -H "Content-Type: application/json" \\
    -H "X-Flowin-API-Key: $FLOWIN_API_KEY" \\
    --data "$PAYLOAD" \\
    "$FLOWIN_API_URL/api/handoff/receive"
)" || {
  status=$?
  echo "VelocityAI handoff failed (exit $status):" >&2
  echo "$RESPONSE" >&2
  exit "$status"
}

URL="$(jq -r '.url // empty' <<<"$RESPONSE")"
TOKEN="$(jq -r '.token // empty' <<<"$RESPONSE")"

if [[ -z "$URL" ]]; then
  echo "Handoff API returned no URL. Raw response:" >&2
  echo "$RESPONSE" >&2
  exit 1
fi

cat <<EOF
✓ Handoff created.

  Open in your browser:
    $URL

  Token: $TOKEN
  Expires: $(jq -r '.expires_at' <<<"$RESPONSE")

The pipeline runs in the VelocityAI web UI — log in there, supply your
GitHub PAT at ${FLOWIN_API_URL}/handoff/settings if you have not
already, and click Start.
EOF
"""


# --- Installer assembler -----------------------------------------------


def _build_installer(api_url: str) -> str:
    """Return the bash installer text, with ``$FLOWIN_API_URL`` defaulting
    to the Flowin instance that served the request.

    The installer:

    1. Resolves a writable bin dir (``~/.local/bin``, created if missing).
    2. Writes ``flowin-handoff`` to it with ``0755`` permissions.
    3. Resolves ``~/.claude/commands`` (created if missing) and writes
       the slash-command markdown.
    4. Warns if ``~/.local/bin`` is not on ``PATH`` (without trying to
       edit the user's shell rc — that's their decision).
    5. Prints the next-step checklist (set env vars, reload Claude Code).

    The two file bodies are embedded verbatim via single-quoted ``cat
    <<'EOF_*'`` heredocs so shell expansion inside them is impossible —
    the installer cannot accidentally execute or mangle the payload.
    """
    # Use a literal placeholder so we can sed-replace the URL below without
    # having to escape every $ in the installer.
    default_url_line = f'FLOWIN_API_URL_DEFAULT="{api_url.rstrip("/")}"'

    installer = f"""\
#!/usr/bin/env bash
# Flowin handoff installer.
# Writes ~/.claude/commands/flowin-handoff.md and ~/.local/bin/flowin-handoff.
# Idempotent — safe to re-run.

set -euo pipefail

{default_url_line}

COMMAND_DIR="${{HOME}}/.claude/commands"
BIN_DIR="${{HOME}}/.local/bin"

echo "→ Installing VelocityAI handoff command..."
mkdir -p "$COMMAND_DIR" "$BIN_DIR"

# --- Slash-command markdown (project: $COMMAND_DIR/flowin-handoff.md) ---
cat > "$COMMAND_DIR/flowin-handoff.md" <<'EOF_SLASH_COMMAND'
{SLASH_COMMAND_MD}EOF_SLASH_COMMAND
chmod 0644 "$COMMAND_DIR/flowin-handoff.md"
echo "  ✓ Wrote $COMMAND_DIR/flowin-handoff.md"

# --- Binary script ($BIN_DIR/flowin-handoff) ----------------------------
cat > "$BIN_DIR/flowin-handoff" <<'EOF_BIN'
{HANDOFF_SCRIPT_SH}EOF_BIN
chmod 0755 "$BIN_DIR/flowin-handoff"
echo "  ✓ Wrote $BIN_DIR/flowin-handoff"

# --- PATH check ---------------------------------------------------------
case ":${{PATH:-}}:" in
  *":$BIN_DIR:"*) ;;
  *)
    echo ""
    echo "⚠  $BIN_DIR is not on your PATH."
    echo "   Add this line to your shell rc (~/.zshrc or ~/.bashrc):"
    echo ""
    echo "      export PATH=\\"$BIN_DIR:\\$PATH\\""
    echo ""
    ;;
esac

# --- Dependency check ---------------------------------------------------
missing=()
for dep in git jq curl; do
  command -v "$dep" >/dev/null 2>&1 || missing+=("$dep")
done
if (( ${{#missing[@]}} > 0 )); then
  echo ""
  echo "⚠  Missing required tools: ${{missing[*]}}"
  echo "   Install via:  brew install ${{missing[*]}}  (macOS)"
  echo "             or  apt-get install ${{missing[*]}}  (Debian/Ubuntu)"
fi

cat <<EOF

✓ VelocityAI handoff installed.

Next steps (one time):

  1. Log into VelocityAI and open:
       $FLOWIN_API_URL_DEFAULT/handoff/settings

  2. Under "VelocityAI API keys" → "Create key" → copy the plaintext token
     (it is shown ONLY once).

  3. On the same page, under "GitHub access token", paste a GitHub PAT
     with 'repo' scope and click Save.

  4. Add the two values to ~/.claude/settings.json:
       {{
         "env": {{
           "FLOWIN_API_URL": "$FLOWIN_API_URL_DEFAULT",
           "FLOWIN_API_KEY": "flowin_<the-token-you-copied>"
         }}
       }}

  5. Reload Claude Code. From inside any git repo, run:
       /flowin-handoff <task description>

EOF
"""
    return installer


@router.get("/flowin-handoff", response_class=PlainTextResponse)
async def get_flowin_handoff_installer(request: Request) -> PlainTextResponse:
    """Serve the ``curl | bash`` installer.

    The base URL is derived from ``settings.PUBLIC_BASE_URL`` so the
    installer hard-codes the right host. We deliberately do NOT pull it
    from ``request.url`` — that would trust the inbound ``Host`` header,
    which a proxy could spoof to point a victim's install at an
    attacker-controlled URL.
    """
    body = _build_installer(settings.PUBLIC_BASE_URL)
    return PlainTextResponse(
        content=body,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
        media_type="text/x-shellscript",
    )


@router.get("/flowin-handoff/command", response_class=PlainTextResponse)
async def get_slash_command_markdown() -> PlainTextResponse:
    """Raw slash-command markdown (without the installer wrapping).

    Useful for users who prefer to drop the file into their own
    ``~/.claude/commands/`` manually, or for documentation tools that
    want to render the file contents.
    """
    return PlainTextResponse(content=SLASH_COMMAND_MD, media_type="text/markdown")


@router.get("/flowin-handoff/script", response_class=PlainTextResponse)
async def get_handoff_script() -> PlainTextResponse:
    """Raw binary script (without the installer wrapping).

    Same rationale as ``/command`` — exposed for advanced users who
    want to wire the script into something other than Claude Code.
    """
    return PlainTextResponse(content=HANDOFF_SCRIPT_SH, media_type="text/x-shellscript")
