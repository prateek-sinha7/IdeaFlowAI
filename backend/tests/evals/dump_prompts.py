"""Dump the EXACT prompts the revision pipeline sends to the model.

Run via ``./run-eval.sh prompts`` (or ``python3.11 -m tests.evals.dump_prompts``
from ``backend/``). Writes, per agent, the fully composed system prompt (the
same ``_compose_system_prompt`` output ``create_runner`` hands the model) plus
the runtime dispatch message (the user turn after the previous_run provider
slims the framed request), into:

    .investigations/revision-pipeline-thinking-issue/prompt-dumps/

Read these files BEFORE spending a token on the live tier — this is the
"what does Haiku actually see" ground truth for prompt iteration. 0 tokens.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

AGENTS = ("prototype-revision-agent", "prototype-revision-validate")
INSTRUCTION = "Make the Save button on Settings actually save"

OUT_DIR = (
    _BACKEND.parent
    / ".investigations"
    / "revision-pipeline-thinking-issue"
    / "prompt-dumps"
)
FIXTURES = _BACKEND / "tests" / "evals" / "workflow" / "prototype" / "revision" / "fixtures"


def main() -> None:
    from agents.factory import AgentContext, _compose_system_prompt
    from agents.loader import load_agent_spec
    from agents.capabilities.context_providers.previous_run import (
        _extract_revision_instruction,
        _slim_revision_message,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Per-agent composed system prompts ────────────────────────────────────
    for agent_id in AGENTS:
        spec = load_agent_spec(agent_id)
        ctx = AgentContext(user_request=INSTRUCTION)
        prompt = _compose_system_prompt(spec, ctx)

        header = (
            f"<!-- SYSTEM PROMPT — {agent_id}\n"
            f"     name: {spec.name} | role: {spec.role}\n"
            f"     tools: {spec.tools} | guardrails: {spec.guardrails}\n"
            f"     pipeline: {spec.pipeline_type} order {spec.order}\n"
            f"     composed by agents.factory._compose_system_prompt — the exact\n"
            f"     string create_runner hands the model. {len(prompt)} chars.\n"
            f"-->\n\n"
        )
        out = OUT_DIR / f"{agent_id}.system-prompt.md"
        out.write_text(header + prompt, encoding="utf-8")
        print(f"  wrote {out}  ({len(prompt)} chars)")

    # ── The dispatch message (user turn) ─────────────────────────────────────
    mini_html = (
        (FIXTURES / "prototype_multi_issue_repair.html").read_text(encoding="utf-8").strip()
    )
    framed = (
        "=== REVISION REQUEST ===\n"
        f"{INSTRUCTION}\n"
        "=== END REQUEST ===\n\n"
        "=== EXISTING PROTOTYPE HTML ===\n"
        f"{mini_html}\n"
        "=== END EXISTING HTML ==="
    )
    slimmed = _slim_revision_message(framed, "prototype.html")
    extracted = _extract_revision_instruction(framed)

    dispatch = (
        "<!-- DISPATCH MESSAGE (the user turn the revision agent receives)\n"
        "     The frontend sends the FRAMED request below; the previous_run\n"
        "     provider seeds prototype.html into the sandbox, stashes the\n"
        "     instruction, and slims the message to the SLIMMED form — that\n"
        "     slimmed text is what the model actually gets as its user turn.\n"
        "-->\n\n"
        "## 1. What the frontend sends (framed)\n\n"
        "```\n" + framed[:800] + "\n… (inline HTML truncated for readability; "
        f"full framed message is {len(framed)} chars)\n```\n\n"
        f"## 2. Extracted instruction (→ ctx.revision_instruction)\n\n"
        f"```\n{extracted}\n```\n\n"
        f"## 3. SLIMMED user turn — what the model receives ({len(slimmed)} chars)\n\n"
        "```\n" + slimmed + "\n```\n"
    )
    out = OUT_DIR / "dispatch-message.md"
    out.write_text(dispatch, encoding="utf-8")
    print(f"  wrote {out}")

    print(f"\nPrompt dumps ready under {OUT_DIR}")


if __name__ == "__main__":
    main()
