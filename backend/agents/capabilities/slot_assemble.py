"""agents/capabilities/slot_assemble.py — the ``mechanical: assemble_slots`` step kind (goal_v2).

Code, not a model, pours parallel-built parts into the shell page:

  * the shell (``prototype.html``, written by ONE builder) carries one marker pair per part:
    ``<!-- part:<ID> -->`` where the part's screens belong and ``/* part:<ID> */`` inside the
    app script where the part's code belongs;
  * each part builder wrote ``parts/<ID>.html`` (markup, may carry its own ``<style>``) and
    ``parts/<ID>.js`` (plain script, no ``<script>`` tags);
  * every marker is replaced by its part, wrapped in begin/end comments so a person (or the
    fix step) can see where each part sits;
  * ``build/assembly.json`` records what was filled, what is missing (a marker with no part)
    and what is unused (a part with no marker). A missing part leaves its marker in place and
    the run continues: the integrate and fix steps see the gap; it does not die here.

Why code: the parts were written in parallel precisely so the page is not re-typed by a
model; a model-run merge would re-emit every part as output tokens and give back the time.

Same adapter shape as ``backlog_assemble.MechanicalAssembleBacklogStrategy``. Pure stdlib;
reaches the sandbox only through ``ctx.runner.sandbox``.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, AsyncIterator

from agents.capabilities.registry import register

PAGE = "prototype.html"
PARTS_DIR = "parts"
REPORT = "build/assembly.json"

_MARKUP_RE = re.compile(r"<!--\s*part:([A-Za-z0-9_-]+)\s*-->")
_SCRIPT_RE = re.compile(r"/\*\s*part:([A-Za-z0-9_-]+)\s*\*/")


class AssembleSlotsFailed(Exception):
    """The shell is missing or carries no part markers — nothing can be assembled."""


def _read(sandbox: Any, rel: str) -> str | None:
    try:
        text = sandbox.read(rel)
    except Exception:  # noqa: BLE001 — unreadable counts as absent
        return None
    return text if isinstance(text, str) else None


def _part_ids(sandbox: Any) -> set[str]:
    try:
        root = sandbox.path_for(PARTS_DIR)
    except Exception:  # noqa: BLE001
        return set()
    if not root.is_dir():
        return set()
    return {
        p.stem for p in root.iterdir() if p.is_file() and p.suffix in (".html", ".js")
    }


def assemble_slots_text(
    page: str, parts: dict[str, dict[str, str | None]]
) -> tuple[str, dict]:
    """Replace every marker in ``page`` with its part. Pure; returns (new page, report)."""
    filled: list[str] = []
    missing: list[str] = []
    problems: list[str] = []

    def markup(m: re.Match) -> str:
        pid = m.group(1)
        body = (parts.get(pid) or {}).get("html")
        if body is None or not body.strip():
            missing.append(f"{pid}.html")
            return m.group(0)
        filled.append(f"{pid}.html")
        return f"<!-- part:{pid} begin -->\n{body.rstrip()}\n<!-- part:{pid} end -->"

    def script(m: re.Match) -> str:
        pid = m.group(1)
        body = (parts.get(pid) or {}).get("js")
        if body is None or not body.strip():
            missing.append(f"{pid}.js")
            return m.group(0)
        if re.search(r"</script", body, re.IGNORECASE):
            # would end the app script early and break every part after it
            problems.append(f"{pid}.js contains </script> — not inserted")
            missing.append(f"{pid}.js")
            return m.group(0)
        filled.append(f"{pid}.js")
        return f"/* part:{pid} begin */\n{body.rstrip()}\n/* part:{pid} end */"

    out = _MARKUP_RE.sub(markup, page)
    out = _SCRIPT_RE.sub(script, out)
    markers = set(_MARKUP_RE.findall(page)) | set(_SCRIPT_RE.findall(page))
    unused = sorted(
        f"{pid}.{kind}"
        for pid, files in parts.items()
        for kind in ("html", "js")
        if files.get(kind) is not None and pid not in markers
    )
    report = {
        "markers": sorted(markers),
        "filled": sorted(filled),
        "missing": sorted(missing),
        "unused": unused,
        "problems": problems,
        "complete": not missing and not unused and not problems,
    }
    return out, report


def assemble_slots(sandbox: Any) -> str:
    """Assemble ``parts/*`` into ``prototype.html`` in place; write the report; return a summary."""
    page = _read(sandbox, PAGE)
    if page is None or not page.strip():
        raise AssembleSlotsFailed(
            f"{PAGE} does not exist — the shell builder did not write it"
        )
    if not (_MARKUP_RE.search(page) or _SCRIPT_RE.search(page)):
        raise AssembleSlotsFailed(
            f"{PAGE} carries no part markers (<!-- part:ID --> or /* part:ID */)"
        )
    ids = (
        _part_ids(sandbox)
        | set(_MARKUP_RE.findall(page))
        | set(_SCRIPT_RE.findall(page))
    )
    parts = {
        pid: {
            "html": _read(sandbox, f"{PARTS_DIR}/{pid}.html"),
            "js": _read(sandbox, f"{PARTS_DIR}/{pid}.js"),
        }
        for pid in sorted(ids)
    }
    out, report = assemble_slots_text(page, parts)
    sandbox.write(PAGE, out)
    sandbox.write(REPORT, json.dumps(report, indent=2) + "\n")
    summary = (
        f"Assembled {len(report['filled'])} part file(s) into {PAGE} "
        f"({len(report['markers'])} part(s) in the shell)."
    )
    if report["missing"]:
        summary += f" Missing: {', '.join(report['missing'])}."
    if report["unused"]:
        summary += f" Unused (no marker in the shell): {', '.join(report['unused'])}."
    if report["problems"]:
        summary += f" Problems: {'; '.join(report['problems'])}."
    return summary + f" Report: {REPORT}."


@register(
    "mechanical",
    "assemble_slots",
    user_allowed=True,
    description=(
        "Pours parallel-built parts into the shell page: every <!-- part:ID --> marker in "
        "prototype.html takes parts/ID.html and every /* part:ID */ marker takes parts/ID.js. "
        "Pure code, no AI; writes build/assembly.json (filled, missing, unused)."
    ),
    reads=["prototype.html", "parts/"],
    process=(
        "Replaces each part marker in the shell with its part file, wrapped in begin/end "
        "comments, and records which markers were filled and which parts were missing or unused."
    ),
    writes=["prototype.html", "build/assembly.json"],
)
class _AssembleSlotsRegistryStub:
    """Registry stub (capability palette). Dispatch uses MechanicalAssembleSlotsStrategy."""

    name = "assemble_slots"


class MechanicalAssembleSlotsStrategy:
    """``strategy``-shaped adapter for ``mechanical: assemble_slots``."""

    name = "assemble_slots"

    def __init__(self, *, spec: Any, index: int, total: int, results: list) -> None:
        self._spec = spec
        self._index = index
        self._total = total
        self._results = results

    async def run(self, step: Any, ctx: Any) -> AsyncIterator[dict]:
        spec = self._spec
        yield {
            "type": "agent_start",
            "data": {
                "agent_id": spec.id,
                "name": spec.name,
                "role": getattr(spec, "role", None),
                "icon": getattr(spec, "icon", None),
                "index": self._index,
                "total": self._total,
            },
        }
        started = time.time()
        try:
            content = assemble_slots(ctx.runner.sandbox)
        except AssembleSlotsFailed as exc:
            yield {
                "type": "agent_error",
                "data": {"agent_id": spec.id, "error": str(exc), "recoverable": False},
            }
            raise
        if " Missing: " in content or " Problems: " in content or " Unused " in content:
            yield {
                "type": "validation_warning",
                "data": {
                    "step": spec.id,
                    "issues": [
                        {
                            "validator": "assembly",
                            "severity": "MEDIUM",
                            "warning": True,
                            "message": content,
                        }
                    ],
                },
            }
        yield {"type": "agent_chunk", "data": {"agent_id": spec.id, "chunk": content}}
        duration = time.time() - started
        self._results.append(
            {
                "agent_id": spec.id,
                "name": spec.name,
                "role": getattr(spec, "role", None),
                "icon": getattr(spec, "icon", None),
                "output": content,
                "duration": duration,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
            }
        )
        yield {
            "type": "agent_complete",
            "data": {
                "agent_id": spec.id,
                "name": spec.name,
                "duration": round(duration, 2),
                "output_length": len(content),
                "index": self._index,
                "total": self._total,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            },
        }
