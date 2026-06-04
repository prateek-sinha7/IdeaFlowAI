"""Coding agent for /flowin-handoff.

Reads the user's task and the relevant slices of the cloned repo,
returns a structured JSON object describing the file edits to make.
The pipeline applies those edits (with path-traversal validation) and
hands the result to the TestAgent and ComplianceAgent for review.

The agent NEVER executes shell commands or arbitrary code. Its only
output is a JSON edit-plan; everything else is supervised by the
pipeline.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.model_factory import build_model
from app.core.config import settings

logger = logging.getLogger("app.agents.handoff.coding")


def _extract_text(content: Any) -> str:
    """Pull plain text out of a chat-model response ``content`` payload.

    Anthropic returns a ``str``; Bedrock returns a list of content blocks
    (e.g. ``[{"type": "text", "text": "..."}]``). Mirrors
    ``app.agents.deep_agent_runner._extract_text`` so this one-shot call decodes
    model output identically to the agent runtime.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


_CODING_SYSTEM_PROMPT = """You are a senior software engineer producing a single, focused code change.

You will receive:
1. A task description from the user.
2. A repository snapshot: a tree listing plus the full contents of the files the orchestrator selected as most relevant.

Your job: propose the minimal set of file edits that satisfies the task, following the best practices below.

## Best practices you MUST follow

**Match the repository conventions.** Read the file headers, imports, indentation, type-hint style, and naming. Mirror them. Do not introduce new patterns when an existing one in the same file/directory fits.

**Minimal diff.** Change only what the task requires. Do not refactor surrounding code, rename unrelated variables, fix unrelated lint issues, or "clean up while you're in there." Three similar lines is better than a premature abstraction.

**No dead code.** Do not add scaffolding, unused helpers, "future-proof" parameters, or commented-out alternatives.

**Comments are last-resort.** Write a comment only when the WHY is non-obvious — a hidden constraint, an invariant a reader could not derive from the code, or a workaround for a specific bug. Never explain WHAT the code does. Never reference the task, PR number, or author.

**Security.** Validate at trust boundaries (HTTP/CLI input, third-party APIs) — never inside internal helpers. Reject path traversal, SQL injection, command injection, and XSS by construction (parameterised queries, allowlisted paths, escape-on-output). Never log secrets. Never hard-code credentials. Treat user-supplied URLs, file paths, and identifiers as adversarial.

**Errors.** Fail fast at boundaries with actionable messages. Do not add try/except around code that cannot fail, and do not catch broad exceptions to "be safe." Let internal invariants raise.

**Tests.** If the task is a behaviour change, modify or add tests in the same diff. If the task is a bug fix, add a regression test that fails without the fix. Place tests in the existing test tree following its conventions. Never add tests that pass by skipping or by mocking the system under test.

**Type and lint cleanliness.** Match the repository's type-hint conventions exactly. Do not introduce ``Any`` where a precise type is available. Do not add ``# type: ignore`` or ``# noqa`` without a one-line WHY immediately above.

**Imports.** Use the import style already in the file (relative vs absolute, sorted vs not). Do not reorder imports unless the task requires it.

**Do not break public APIs** unless the task says so. Adding a required positional argument to a function called from elsewhere in the repo IS a breaking change.

## Output format

Return ONLY a valid JSON object. No markdown fences, no prose, no leading or trailing text. Schema:

```
{
  "summary": "<one sentence describing the change>",
  "rationale": "<2-5 sentences explaining why this approach was chosen and what alternatives were considered>",
  "edits": [
    {
      "path": "<repository-relative path, forward slashes only, no '..'>",
      "operation": "create" | "modify" | "delete",
      "old_string": "<for modify only: the exact substring to replace; for create/delete: empty string>",
      "new_string": "<for modify and create: the replacement / new file contents; for delete: empty string>"
    }
  ],
  "tests_added": ["<paths of new or modified test files, if any>"],
  "follow_ups": ["<optional list of clearly out-of-scope items the user should know about>"]
}
```

For ``modify`` operations the ``old_string`` MUST appear EXACTLY ONCE in the named file — verbatim, including whitespace. If you need to change something that appears multiple times, include enough surrounding context to make the match unique.

For ``create`` operations the path MUST NOT already exist.

If the task cannot be completed safely from the provided context, return ``{"summary": "...", "rationale": "...", "edits": [], "tests_added": [], "follow_ups": ["<what's missing>"]}`` and explain in the rationale. Do NOT guess.
"""


_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


def _extract_json(raw: str) -> dict[str, Any]:
    """Best-effort JSON extraction.

    The system prompt asks for "ONLY a valid JSON object", but real LLM
    outputs occasionally arrive wrapped in ``” ``json`` fences or with a
    one-line preamble. We strip the fences, then fall back to grabbing
    the largest ``{...}`` span and parsing that. If both fail, the
    pipeline treats it as an agent error.
    """
    text = raw.strip()
    if text.startswith("```"):
        # Trim the first fence line and a trailing fence if present.
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = _JSON_OBJECT_RE.search(text)
    if match is None:
        raise ValueError("CodingAgent returned no JSON object")
    return json.loads(match.group(0))


class CodingAgent:
    """Coding agent — Sonnet-preferred, structured edit-plan output."""

    def __init__(self) -> None:
        # Resolution order for the coding model: explicit BEDROCK_CODING_MODEL_ID
        # if set, otherwise fall back to the default profile (which is Haiku in
        # the shipped config). This lets operators promote Sonnet without code
        # changes — see app.core.config.Settings.BEDROCK_CODING_MODEL_ID.
        self._model_override = (settings.BEDROCK_CODING_MODEL_ID or "").strip() or None
        self._max_tokens = 16000
        self.system_prompt = _CODING_SYSTEM_PROMPT

    async def propose_edits(
        self,
        task: str,
        repo_tree: str,
        relevant_files: dict[str, str],
        transcript_excerpt: str | None = None,
    ) -> dict[str, Any]:
        """Run the agent and return a parsed edit plan."""
        context_lines: list[str] = [f"TASK\n----\n{task}"]
        if transcript_excerpt:
            context_lines.append(f"\nRECENT IDE CONVERSATION\n-----------------------\n{transcript_excerpt[-4000:]}")
        context_lines.append(f"\nREPOSITORY TREE\n---------------\n{repo_tree[:8000]}")
        for path, contents in relevant_files.items():
            snippet = contents
            if len(snippet) > 12000:
                snippet = snippet[:12000] + f"\n\n... (truncated, {len(contents)} total bytes)"
            context_lines.append(f"\n=== FILE: {path} ===\n{snippet}")

        user_message = "\n".join(context_lines)
        llm = build_model(model=self._model_override, max_tokens=self._max_tokens)
        resp = await llm.ainvoke(
            [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=user_message),
            ]
        )
        raw = _extract_text(resp.content)
        try:
            plan = _extract_json(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("CodingAgent JSON parse failed: %s; raw=%s", exc, raw[:500])
            raise

        edits = plan.get("edits")
        if not isinstance(edits, list):
            raise ValueError("CodingAgent edit-plan is missing 'edits' array")
        plan.setdefault("summary", "")
        plan.setdefault("rationale", "")
        plan.setdefault("tests_added", [])
        plan.setdefault("follow_ups", [])
        return plan
