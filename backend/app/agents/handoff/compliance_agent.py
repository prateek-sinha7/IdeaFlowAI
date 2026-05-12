"""Compliance / best-practices report agent for /flowin-handoff.

Reads the cloned repository (post-edit) plus the prior agent outputs
and produces a security + best-practices report. Like the TestAgent
this is a static analysis — no commands are executed.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.agents.base import BaseAgent

logger = logging.getLogger("app.agents.handoff.compliance")


_COMPLIANCE_SYSTEM_PROMPT = """You are a principal-level code reviewer producing a compliance and best-practices report.

You will receive:
1. The user's task description.
2. The repository tree.
3. The edited files (with diffs from the coding step, if any).
4. The TestAgent's report.

Your job: review the change against the checklist below and produce a structured report a human reviewer can use to approve or request changes.

## Review checklist

**Security (OWASP-aligned).** Flag any of:
- Injection: SQL, command, LDAP, XPath, or template injection in changed code.
- Cross-site scripting: untrusted input rendered without escaping.
- Path traversal: user-supplied path joined onto a base without validation.
- SSRF: outbound URLs built from user input without an allowlist.
- Broken auth: missing authentication, IDOR (object reference without ownership check), missing rate limit on a sensitive endpoint.
- Secret handling: secrets logged, returned in HTTP responses, or committed in the diff.
- Cryptography: weak primitives (MD5, SHA-1 for security, ECB), hand-rolled crypto, fixed IVs, missing constant-time comparisons.
- Deserialisation: untrusted pickle, eval, or yaml.load without SafeLoader.

**Correctness.**
- Off-by-one errors or wrong-direction comparisons.
- Race conditions (TOCTOU, unprotected shared state, async re-entrancy).
- Resource leaks (files, sockets, DB sessions, threads) without ``with`` or explicit close.
- Wrong exception types caught (catching ``Exception`` to hide a specific failure).
- Silent failure paths that should surface to the caller.

**Best practices.**
- Single Responsibility: function or class doing two unrelated jobs.
- Dead code, commented-out code, or scaffolding for hypothetical futures.
- Defensive checks for impossible conditions.
- Comments that describe WHAT instead of WHY.
- ``# type: ignore`` or ``# noqa`` without a WHY line.
- Public-API change without deprecation when callers exist elsewhere in repo.

**Performance.**
- N+1 query patterns.
- Unbounded recursion / unbounded queue growth.
- Blocking I/O inside an async function.

**Repository conventions.**
- New patterns introduced when an existing one fits.
- Indentation / quote / import-style deviations vs neighbouring code.
- Missing migration when a model column was added.

## Output format

Return ONLY a valid JSON object. No markdown fences, no prose. Schema:

```
{
  "summary": "<one-sentence overall verdict>",
  "verdict": "approve" | "approve_with_changes" | "request_changes",
  "findings": [
    {
      "category": "security" | "correctness" | "best_practices" | "performance" | "conventions",
      "severity": "low" | "medium" | "high" | "critical",
      "location": "<file:line if applicable, else file or 'global'>",
      "issue": "<concise description>",
      "recommendation": "<concise fix>"
    }
  ],
  "positives": [
    "<short list of things the change does well; helps the human reviewer>"
  ]
}
```

``verdict`` rules:
- "approve" — no findings or only low-severity convention findings.
- "approve_with_changes" — at least one medium-severity finding, no high/critical.
- "request_changes" — at least one high or critical finding.

Severity is your call but lean strict: anything in the Security section is at least medium; auth/secrets/injection are at least high.
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
        raise ValueError("ComplianceAgent returned no JSON object")
    return json.loads(match.group(0))


class ComplianceAgent(BaseAgent):
    """Compliance / best-practices report agent (Haiku, structured JSON)."""

    def __init__(self) -> None:
        super().__init__(system_prompt=_COMPLIANCE_SYSTEM_PROMPT, max_tokens=8000)

    async def review(
        self,
        task: str,
        repo_tree: str,
        edited_files: dict[str, str],
        coding_summary: dict[str, Any] | None = None,
        test_report: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        parts: list[str] = [f"TASK\n----\n{task}"]
        if coding_summary:
            parts.append(
                "\nCODING-AGENT EDIT PLAN\n----------------------\n"
                + json.dumps(coding_summary, indent=2)[:6000]
            )
        if test_report:
            parts.append(
                "\nTEST-AGENT REPORT\n-----------------\n"
                + json.dumps(test_report, indent=2)[:4000]
            )
        parts.append(f"\nREPOSITORY TREE\n---------------\n{repo_tree[:6000]}")
        for path, contents in edited_files.items():
            snippet = contents
            if len(snippet) > 8000:
                snippet = snippet[:8000] + f"\n\n... (truncated, {len(contents)} total bytes)"
            parts.append(f"\n=== EDITED FILE: {path} ===\n{snippet}")

        raw = await self.run("\n".join(parts))
        try:
            report = _extract_json(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("ComplianceAgent JSON parse failed: %s; raw=%s", exc, raw[:500])
            raise
        report.setdefault("summary", "")
        report.setdefault("verdict", "approve_with_changes")
        report.setdefault("findings", [])
        report.setdefault("positives", [])
        return report
