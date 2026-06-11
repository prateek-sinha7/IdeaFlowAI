"""Handoff coder for /flowin-handoff — the UNIFIED-runtime edit-plan producer (09-06 / D-09).

Supersedes the deleted ``CodingAgent`` bypass. The old ``CodingAgent.propose_edits``
called ``build_model(...).ainvoke([...])`` directly — a one-shot LLM call that SKIPPED
``create_deep_agent``/``create_runner`` (the INV-13 gap D-09 named). This module produces
the SAME structured JSON edit-plan but routes the model invocation through the sanctioned
deepagents runtime (``DeepAgentRunner`` → ``create_deep_agent``), so the handoff coding step
runs on the canonical LangChain ``deepagents`` runtime like every other agent (INV-13).

The agent NEVER executes shell commands or arbitrary code. Its only output is a JSON
edit-plan (text-only, no tools); everything else — applying the edits with path-traversal
validation, the commit/PR — is supervised by ``run_handoff_pipeline``.

Bound in ``app.services.handoff_pipeline`` under the name ``CodingAgent`` (an alias) so the
retained ``/api/handoff`` pipeline + its contract test seam are unchanged; the deleted bypass
class is gone (the migration-ledger grep gate counts zero ``class``-defined bypass).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.config import settings

logger = logging.getLogger("app.agents.handoff.coder")


def _extract_text(content: Any) -> str:
    """Pull plain text out of a chat-model response ``content`` payload.

    Anthropic returns a ``str``; Bedrock returns a list of content blocks
    (e.g. ``[{"type": "text", "text": "..."}]``). Mirrors
    ``app.agents.deep_agent_runner._extract_text`` so the decoded output matches
    the agent runtime exactly.
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

Return ONLY a valid JSON object. No markdown fences, no prose, no leading or trailing text.

You have NO tools in this session. You must NOT emit `<function_calls>`, `<invoke>`, `write_todos`, or tool-call XML of any kind — there are no tools to call, and any such syntax corrupts the output. The ENTIRE response must be the single JSON object: nothing before it, nothing after it.

Schema:

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

# F4 (13-02): fabricated tool-call XML pollution — live Haiku has returned
# ``<function_calls><invoke name=read_file>...`` instead of (or wrapped around) the
# JSON edit-plan. Non-greedy ``[\s\S]*?`` span (linear on max_tokens-capped output —
# T-13-02-04); the strip only NARROWS what reaches the parser, never widens it
# (T-13-02-01 — the downstream path-traversal validation on edits is unchanged).
_FABRICATED_TOOL_XML_RE = re.compile(r"<function_calls>[\s\S]*?</function_calls>")


def _extract_json(raw: str) -> dict[str, Any]:
    """Best-effort JSON extraction.

    The system prompt asks for "ONLY a valid JSON object", but real LLM
    outputs occasionally arrive wrapped in ``` ```json ``` fences or with a
    one-line preamble. Fabricated ``<function_calls>`` XML spans (the F4 live
    failure) are stripped FIRST, then fences, then we fall back to grabbing
    the largest ``{...}`` span and parsing that. If all fail, the
    pipeline treats it as an agent error.
    """
    text = _FABRICATED_TOOL_XML_RE.sub("", raw).strip()
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
        raise ValueError("handoff coder returned no JSON object")
    return json.loads(match.group(0))


# F4 (13-02): hard bound on parse-driven re-prompts — 2 TOTAL attempts (the original
# plus ONE corrective retry). Never raised; never made configurable (T-13-02-02 DoS
# disposition: persistent parse failure must fail loudly, not loop).
_MAX_PARSE_ATTEMPTS = 2

# The corrective suffix appended to the user message on the retry attempt — names the
# failure and restates the output contract.
_CORRECTIVE_SUFFIX = (
    "\n\nIMPORTANT: your previous response was NOT a valid JSON object and could not "
    "be parsed. Respond again with ONLY the single JSON object matching the schema in "
    "the system prompt — no tool-call XML (no <function_calls>, no <invoke>), no "
    "prose, no markdown fences, nothing before or after the JSON object."
)


class HandoffCoder:
    """Handoff coder — produces a structured edit-plan through the deepagents runtime.

    Sonnet-preferred (the ``BEDROCK_CODING_MODEL_ID`` operator override is honored).
    The model invocation flows through the sanctioned ``DeepAgentRunner`` →
    ``create_deep_agent`` runtime (INV-13) — NOT the deleted ``build_model().ainvoke``
    bypass. Text-only (no tools): the agent emits the JSON edit-plan as its stream; the
    pipeline applies it under path-traversal validation.
    """

    def __init__(self) -> None:
        # Resolution order for the coding model: explicit BEDROCK_CODING_MODEL_ID if
        # set, otherwise the default profile (Haiku in the shipped config). Lets
        # operators promote Sonnet without code changes (app.core.config.Settings).
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
        """Run the coder through the deepagents runtime and return a parsed edit plan."""
        context_lines: list[str] = [f"TASK\n----\n{task}"]
        if transcript_excerpt:
            context_lines.append(
                f"\nRECENT IDE CONVERSATION\n-----------------------\n{transcript_excerpt[-4000:]}"
            )
        context_lines.append(f"\nREPOSITORY TREE\n---------------\n{repo_tree[:8000]}")
        for path, contents in relevant_files.items():
            snippet = contents
            if len(snippet) > 12000:
                snippet = snippet[:12000] + f"\n\n... (truncated, {len(contents)} total bytes)"
            context_lines.append(f"\n=== FILE: {path} ===\n{snippet}")

        user_message = "\n".join(context_lines)

        # ── INV-13: run on the sanctioned deepagents runtime (create_deep_agent) ──
        # A text-only DeepAgentRunner (no tools, no sandbox) — the same runtime every
        # other agent uses — replaces the deleted build_model().ainvoke one-shot. We
        # drive its event stream and accumulate the agent's chunked output, then parse
        # the JSON edit-plan exactly as before. Lazy import keeps the module light.
        from app.agents.deep_agent_runner import DeepAgentRunner

        # F4 (13-02): bounded parse-retry. Live Haiku has returned fabricated tool-call
        # XML instead of the JSON edit-plan; one corrective re-prompt (naming the
        # failure) recovers it. The one-shot stream + parse runs at most
        # ``_MAX_PARSE_ATTEMPTS`` times; a FRESH runner is constructed per attempt
        # (no checkpointer state to reuse — each attempt is an independent one-shot,
        # never a re-implemented agent loop, INV-13). A RuntimeError from a runner
        # ``error`` event is a runtime fault, NOT a parse fault — it propagates
        # immediately and is never retried.
        plan: dict[str, Any] | None = None
        for attempt in range(1, _MAX_PARSE_ATTEMPTS + 1):
            message = user_message if attempt == 1 else user_message + _CORRECTIVE_SUFFIX
            runner = DeepAgentRunner(
                system_prompt=self.system_prompt,
                tools=[],
                model=self._model_override,
                max_tokens=self._max_tokens,
                exclude_builtin_tools=True,  # text-only: no fs/native tools, pure edit-plan stream
            )

            # The runner streams ``{"type":"chunk","chunk":str}`` tokens and a terminal
            # ``{"type":"done","output":str}`` carrying the full accumulated text. Prefer the
            # ``done`` output (the authoritative full message) and fall back to the joined
            # chunks if no ``done`` arrived (defensive — an error event would raise upstream).
            parts: list[str] = []
            final_output: str | None = None
            async for event in runner.astream_events(message):
                etype = event.get("type")
                if etype == "chunk":
                    parts.append(event.get("chunk", ""))
                elif etype == "done":
                    final_output = event.get("output", "")
                elif etype == "error":
                    raise RuntimeError(
                        f"handoff coder runtime error: {event.get('error')}"
                    )
            raw = final_output if final_output is not None else "".join(parts)

            try:
                plan = _extract_json(raw)
                break
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning(
                    "handoff coder JSON parse failed: %s; raw=%s", exc, raw[:500]
                )
                if attempt >= _MAX_PARSE_ATTEMPTS:
                    raise
        assert plan is not None  # the loop either bound ``plan`` or raised

        edits = plan.get("edits")
        if not isinstance(edits, list):
            raise ValueError("handoff coder edit-plan is missing 'edits' array")
        plan.setdefault("summary", "")
        plan.setdefault("rationale", "")
        plan.setdefault("tests_added", [])
        plan.setdefault("follow_ups", [])
        return plan
