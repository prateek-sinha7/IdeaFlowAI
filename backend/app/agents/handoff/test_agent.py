"""Test analysis agent for /flowin-handoff.

Examines the cloned repository (with the CodingAgent's edits already
applied, if any) and produces a structured test report: what tests
exist, which scenarios are covered, what is missing, and whether the
new behaviour from the coding step has accompanying tests.

This agent does NOT execute tests. Code execution happens nowhere in
the handoff pipeline — the user's CI runs the actual tests after the
PR is opened. Our job is to evaluate test quality and surface gaps so
the human reviewer can decide before merging.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.agents.cached_invoke import cached_invoke
from app.agents.model_factory import build_model

logger = logging.getLogger("app.agents.handoff.test")


_TEST_SYSTEM_PROMPT = """You are a senior test engineer producing a test-coverage analysis report.

You will receive:
1. The user's task description.
2. The repository tree.
3. Existing test files in the most relevant directories.
4. If a coding step ran first: the edit summary, the modified files, and any tests added by the coding agent.

Your job: evaluate test coverage and quality for the change at hand, surfacing gaps a human reviewer should care about. You are NOT running tests; you are reading code.

## What to evaluate

**Coverage of new behaviour.** Does every new branch, error path, and boundary in the changed code have at least one test? If not, name the specific uncovered case.

**Coverage of existing behaviour the change touches.** Identify any pre-existing call sites that are not protected by a test that would catch a regression in the changed function.

**Test quality.**
- Are tests deterministic (no time-of-day, no real network, no flaky retries)?
- Do tests assert behaviour, not implementation details (no asserting on internal call sequences)?
- Do tests follow Arrange/Act/Assert structure clearly?
- Are negative tests present (invalid input, missing permissions, empty cases)?

**Match repository test conventions.** Use the existing test framework, helpers, fixtures, and naming patterns. Note any deviations.

**Anti-patterns to flag.**
- Tests that pass by mocking the system under test.
- Tests that catch broad exceptions and assert nothing specific.
- Tests using ``time.sleep`` for synchronisation.
- Tests that depend on test-order or shared state.
- ``# type: ignore`` or ``pytest.skip`` without a one-line WHY.

## Output format

Return ONLY a valid JSON object. No markdown fences, no prose. Schema:

```
{
  "summary": "<one-sentence verdict, e.g. 'New tests cover the happy path but miss two error branches'>",
  "verdict": "pass" | "concerns" | "fail",
  "tests_present": [
    {"path": "<test-file-path>", "covers": "<what behaviour it covers>"}
  ],
  "missing_coverage": [
    {"area": "<what is uncovered>", "suggested_test": "<one-line description of the test to add>"}
  ],
  "quality_issues": [
    {"path": "<file:line if known>", "issue": "<description>", "severity": "low" | "medium" | "high"}
  ],
  "recommended_additions": [
    "<plain-English description of a test that should be added>"
  ]
}
```

``verdict`` rules:
- "pass" — change is well covered, no significant gaps.
- "concerns" — change is mostly covered but has notable gaps a reviewer should address.
- "fail" — change introduces or touches important untested behaviour and should not merge until tests are added.
"""


_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


def _extract_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = _JSON_OBJECT_RE.search(text)
    if match is None:
        raise ValueError("TestAgent returned no JSON object")
    return json.loads(match.group(0))


class TestAgent:
    """Test-coverage analysis agent (Haiku, structured JSON output)."""

    def __init__(self, usage_sink=None) -> None:
        self._max_tokens = 8000
        self.system_prompt = _TEST_SYSTEM_PROMPT
        # ISS-033: optional run-usage sink so this analysis' model-call tokens are
        # counted (via the shared cached_invoke) instead of silently dropped.
        self._usage_sink = usage_sink

    async def analyse(
        self,
        task: str,
        repo_tree: str,
        test_files: dict[str, str],
        coding_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        parts: list[str] = [f"TASK\n----\n{task}"]
        if coding_summary:
            parts.append(
                "\nCODING-AGENT EDIT PLAN\n----------------------\n"
                + json.dumps(coding_summary, indent=2)[:6000]
            )
        parts.append(f"\nREPOSITORY TREE\n---------------\n{repo_tree[:8000]}")
        for path, contents in test_files.items():
            snippet = contents
            if len(snippet) > 10000:
                snippet = snippet[:10000] + f"\n\n... (truncated, {len(contents)} total bytes)"
            parts.append(f"\n=== TEST FILE: {path} ===\n{snippet}")
        if not test_files:
            parts.append("\n=== NO TEST FILES PROVIDED ===\nReport this as the dominant missing-coverage item.")

        # ISS-033: route the direct ainvoke through the ONE shared cached-invoke helper
        # — the stable system prompt is the cache-eligible prefix and the tokens are
        # counted. build_model stays here (unchanged) so the model is built exactly as
        # before; only the invoke path is replaced (cache-point placement + counting).
        llm = build_model(max_tokens=self._max_tokens)
        raw, _usage = await cached_invoke(
            "\n".join(parts),
            system=self.system_prompt,
            model=llm,
            usage_sink=self._usage_sink,
        )
        try:
            report = _extract_json(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("TestAgent JSON parse failed: %s; raw=%s", exc, raw[:500])
            raise
        report.setdefault("summary", "")
        report.setdefault("verdict", "concerns")
        report.setdefault("tests_present", [])
        report.setdefault("missing_coverage", [])
        report.setdefault("quality_issues", [])
        report.setdefault("recommended_additions", [])
        return report
