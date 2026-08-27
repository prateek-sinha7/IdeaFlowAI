"""Selectors for screens/16-pages-outside-routes.feature.md.

Five Next.js pages `routes.ts` does not describe. They were found by
enumerating `app/**/page.tsx`, not by reading the routing contract — which is
why nothing else in the suite reaches them.
"""

# ── /workflow, the second workflow builder ───────────────────────────────────

LEGACY_HEADING = "VelocityAI — Agent Workflows"
LEGACY_CONTROLS = ["Browse Library", "Add Agent", "Run Workflow"]
LEGACY_CATEGORIES = [
    "All", "User Stories", "Presentation", "Prototype", "App Builder",
    "Mulesoft → Spring Boot", ".NET → Azure", "Custom",
]
NO_AGENTS_FOUND = "No agents found"

# ── /preview-fullscreen ──────────────────────────────────────────────────────

QUOTA_HEADING = "Project too large for full screen"
QUOTA_BODY = (
    "The generated project exceeds the browser session storage limit (~5MB). "
    "Use the Download ZIP button in the preview panel to get all files."
)

# ── /handoff/settings ────────────────────────────────────────────────────────

HANDOFF_HEADING = "Handoff integrations"
INSTALL_LINE = "curl -fsSL"
SLASH_COMMAND = "/flowin-handoff"
IDEMPOTENT = "Idempotent — safe to re-run"

GITHUB_PAT = 'input[name="github-pat"]'
GITHUB_PAT_HELP = "Needs repo scope. Encrypted at rest, never returned by any API."
NO_TOKEN = "No GitHub token saved yet."
SAVE = 'button:text-is("Save")'
# The backend VERIFIES a PAT against GitHub before storing it, so an invalid
# value can never be saved — the response is a 400 carrying this line.
PAT_REJECTED = "GitHub rejected the PAT"

API_KEY_NAME = 'input[name="api-key-name"]'
CREATE_KEY = 'button:text-is("Create key")'
NO_KEYS = "No API keys yet."
REVOKE = 'button:text-is("Revoke")'
# The saved key is listed masked — `flowin_j··· · never used`.
KEY_MASK = "···"
PLAINTEXT_ONCE = "Plaintext shown once."

# ── /handoff/{token} ─────────────────────────────────────────────────────────

HANDOFF_NOT_FOUND = "Handoff not found"
BACK_TO_DASHBOARD = "Back to dashboard"
