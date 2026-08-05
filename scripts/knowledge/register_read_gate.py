#!/usr/bin/env python3
"""PreToolUse gate: agents get the surface file, never the whole register.

Skill instructions are advisory — an agent under pressure still opens
`FIX-REGISTER.md`, and by then the tokens are spent. This is the layer that
actually enforces the card store.

Two behaviours, deliberately different:

  Read  → **redirected**, not denied. `updatedInput` rewrites the path to
          `.knowledge/surface/ENTRY.md`, one ~2 KB entry point listing the newest entries and
          the `ctx.py` commands. The agent asked a reasonable question and gets a
          useful answer, which is why this beats a refusal: a denial teaches the
          agent to route around the gate, a redirect teaches it where to look.

  Bash  → **denied**. `cat`/`head`/`sed` on a register is the obvious way around a
          Read gate, and there is no input to usefully rewrite.

Hooks also run inside subagents (the payload carries `agent_id`/`agent_type`), so a
Task-spawned agent with a fresh context is covered by the same rules.

Wire it up in .claude/settings.json:

    { "hooks": { "PreToolUse": [
        { "matcher": "Read", "hooks": [ { "type": "command",
            "command": "python3 scripts/knowledge/register_read_gate.py" } ] },
        { "matcher": "Bash", "hooks": [ { "type": "command",
            "command": "python3 scripts/knowledge/register_read_gate.py" } ] }
    ] } }

Fails open on anything unexpected: a broken hook must never block work.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import NoReturn

# Registers too large to ever be worth reading whole, and what now carries them.
GATED = {
    "FIX-REGISTER.md": "168 fix cards",
    "ISSUES-REGISTER.md": "49 issue cards",
    "IMPLEMENTATION-REGISTER.md": "23 phase cards + .planning/_register-parts/ shards",
    "TEST-REGISTER.md": "49 test cards",
    "REQUIREMENTS.md": "40 requirement cards",
    "SSE-QA-BUG-LOG.md": "bug cards (BUG-nnn-sse)",
    "RESUME-QA-BUG-LOG.md": "bug cards (BUG-Rnn-resume)",
    "ROADMAP.md": ".knowledge/INVARIANTS.md",
    # 180 KB, and all but ~1 KB of it is a per-phase metrics table that grows every
    # session. The milestone, status and current position are lifted into
    # ARCHITECTURE.md at build time, so they are current without the other 179 KB.
    "STATE.md": ".knowledge/surface/ARCHITECTURE.md (Stage section)",
}

ENTRY = Path(".knowledge/surface/ENTRY.md")

# An explicit escape hatch. The gate exists to stop the reflex, not to make the
# file unreachable — a human who means it should not have to fight the tooling.
# Which query to suggest for the register that was actually asked for. The entry
# point is shared; only this hint varies, which is why nine near-identical surface
# files were not worth keeping.
HINT = {
    "FIX-REGISTER.md": 'ctx.py "<symptom words>"',
    "ISSUES-REGISTER.md": 'ctx.py --type issue "<terms>"',
    "IMPLEMENTATION-REGISTER.md": 'ctx.py --type phase "<terms>"',
    "TEST-REGISTER.md": 'ctx.py --type test "<terms>"',
    "REQUIREMENTS.md": 'ctx.py --type req "<terms>"',
    "SSE-QA-BUG-LOG.md": 'ctx.py --type bug "<terms>"',
    "RESUME-QA-BUG-LOG.md": 'ctx.py --type bug "<terms>"',
    "ROADMAP.md": "read .knowledge/INVARIANTS.md",
    "STATE.md": "read .knowledge/surface/ARCHITECTURE.md — Stage section",
}

OVERRIDE = "READ_REGISTER_ANYWAY"

READERS = ("cat", "head", "tail", "less", "more", "sed", "awk", "nl", "strings", "bat")


def emit(payload: dict) -> NoReturn:
    print(json.dumps(payload))
    sys.exit(0)


def allow() -> NoReturn:
    emit({})


def gated_name(text: str) -> str | None:
    for name in GATED:
        if name in text:
            return name
    return None


def handle_read(args: dict) -> NoReturn:
    path = str(args.get("file_path") or args.get("path") or "")
    if not path:
        allow()

    norm = path.replace("\\", "/")
    # Surface files and cards live under .knowledge/ — never gate those.
    if "/.knowledge/" in norm or norm.startswith(".knowledge/"):
        allow()

    name = Path(path).name
    if name not in GATED:
        allow()

    # A bounded read is a deliberate, cheap act. Only the whole-file read costs.
    if args.get("limit") or args.get("offset"):
        allow()

    surface = ENTRY
    if not surface.is_file():
        # No surface built yet — deny with guidance rather than silently allowing
        # the very read this hook exists to prevent.
        emit(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"Reading {name} whole is what the knowledge store exists to avoid; "
                        f"it is carried as {GATED[name]}.\n"
                        f"No entry point built yet — run:\n"
                        f"  python3 scripts/knowledge/build_surface.py\n"
                        f'Then query: python3 scripts/knowledge/ctx.py "<symptom words>"'
                    ),
                }
            }
        )

    size = Path(path).stat().st_size / 1024 if Path(path).is_file() else 0
    emit(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "updatedInput": {**args, "file_path": str(surface)},
                "additionalContext": (
                    f"Redirected: {name} is {size:.0f} KB (~{size / 4:.0f}K tokens). "
                    f"It is carried as {GATED[name]}. You are reading {surface} instead — "
                    f"the single entry point for the knowledge store. "
                    f"Start with: {HINT.get(name, 'ctx.py \"<symptom words>\"')}. "
                    f"This is not a failure; do not retry the original path. "
                    f"For the raw file, re-read with a `limit`."
                ),
            }
        }
    )


def handle_bash(args: dict) -> NoReturn:
    cmd = str(args.get("command") or "")
    if not cmd or OVERRIDE in cmd:
        allow()

    name = gated_name(cmd)
    if not name or "/.knowledge/" in cmd or ".knowledge/surface" in cmd:
        allow()

    # Only intervene when the command is actually dumping the file. `grep`, `wc`,
    # `git log` and friends over a register are cheap and legitimate.
    first = re.findall(r"(?:^|[|;&]\s*)([a-z][\w.-]*)", cmd.lower())
    if not any(tok in READERS for tok in first):
        allow()

    emit(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"Blocked: dumping {name} through the shell bypasses the knowledge "
                    f"store. It is carried as {GATED[name]}.\n\n"
                    f"Use instead:\n"
                    f'  python3 scripts/knowledge/ctx.py "<symptom words>"\n'
                    f"  python3 scripts/knowledge/ctx.py --for <file you are about to edit>\n"
                    f"  python3 scripts/knowledge/ctx.py --show <ID>\n\n"
                    f"Read {ENTRY} for the overview. `grep` and `wc` over "
                    f"the register are still allowed; add {OVERRIDE} to force a dump."
                ),
            }
        }
    )


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow()

    if OVERRIDE in json.dumps(payload):
        allow()

    tool = payload.get("tool_name") or payload.get("tool") or ""
    args = payload.get("tool_input") or payload.get("input") or {}
    if not isinstance(args, dict):
        allow()

    if tool == "Read":
        handle_read(args)
    if tool == "Bash":
        handle_bash(args)
    allow()


if __name__ == "__main__":
    main()
