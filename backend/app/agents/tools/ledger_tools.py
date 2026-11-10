"""app/agents/tools/ledger_tools.py -- requirement-ledger consistency checks (P27 E5).

One read-only, deterministic, model-free tool, `ledger_check(mode)`, that compares the
goal-workflow artefacts in the run sandbox against `.goal/ledger.json`:

  harvest   IDs found in the extracted source text vs ledger rows
  coverage  every ledger ID in spec.md, tasks.json and (if testable) .goal/acceptance/
  trace     every ledger ID has exactly one valid result in .goal/trace.json
  report    every non-pass ID is named in .goal/report.md
  acceptance_schema  every acceptance file is valid v2 format; every testable ID has one (goal_v2)
  trace_fresh        trace.json was written by run_acceptance over ALL ids, against the current page
                     (goal_v2)

Sandbox binding mirrors file_extract_tools: the factory calls `bind_sandbox(sandbox)` per
run and every path goes through RunSandbox.path_for (traversal-proof). Files reached by
walking a directory are additionally resolved and must stay inside the sandbox root, so a
symlink planted in .extract/ or .uploads/ is never followed out.

Never-raise discipline: every failure comes back as a gap in the JSON result.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from langchain_core.tools import tool

LEDGER_CHECK = "ledger_check"

MODES = ("harvest", "coverage", "trace", "report", "acceptance_schema", "trace_fresh")
_TRACE_STATUSES = ("pass", "fail", "not-testable")
_MAX_GAPS = 200
_LEDGER = ".goal/ledger.json"
_SPEC = "spec.md"
_TASKS = "tasks.json"
_TRACE = ".goal/trace.json"
_REPORT = ".goal/report.md"
_ACCEPTANCE_DIR = ".goal/acceptance"
_UPLOADS = ".uploads"
_EXTRACT = ".extract"

_SANDBOX: Any = None


def bind_sandbox(sandbox: Any) -> None:
    """Bind the run sandbox (called by the factory at tool-resolution time)."""
    global _SANDBOX
    _SANDBOX = sandbox


# --------------------------------------------------------------------------- helpers


def _read(sandbox: Any, rel: str) -> str | None:
    """Text of a sandbox-relative file, or None if absent/unsafe/unreadable."""
    try:
        p = sandbox.path_for(rel)
        if not p.is_file():
            return None
        return p.read_text(encoding="utf-8", errors="replace")
    except (ValueError, OSError):
        return None


def _read_json(sandbox: Any, rel: str) -> tuple[Any, str | None]:
    """(parsed, problem). `problem` is 'missing' or 'invalid JSON' on failure."""
    text = _read(sandbox, rel)
    if text is None:
        return None, "missing"
    try:
        return json.loads(text), None
    except ValueError:
        return None, "invalid JSON"


def _word_re(literal: str) -> re.Pattern[str]:
    # Hyphen counts as a word character so R-1 does not match inside R-10 or R-1-2.
    return re.compile(r"(?<![\w-])" + re.escape(literal) + r"(?![\w-])")


def _gap(gid: str, where: str, reason: str, **extra: Any) -> dict[str, Any]:
    return {"id": gid, "where": where, "reason": reason, **extra}


def _iter_files(
    sandbox: Any, base_rel: str, accept: Callable[[Path], bool]
) -> list[Path]:
    """Regular files under base_rel that stay inside the sandbox root, sorted."""
    try:
        root = sandbox.path_for(".")
        base = sandbox.path_for(base_rel)
    except ValueError:
        return []
    if not base.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(base.rglob("*")):
        try:
            if p.is_symlink() or not p.is_file() or not accept(p):
                continue
            if not p.resolve().is_relative_to(root):
                continue
        except OSError:
            continue
        out.append(p)
    return out


def _source_texts(sandbox: Any) -> list[tuple[str, str]]:
    """(sandbox-relative path, text) for extracted text and plain-text uploads."""
    root = sandbox.path_for(".")

    def is_extract_text(p: Path) -> bool:
        return p.name == "document.md" or (
            p.name == "text.md" and p.parent.parent.name == "pages"
        )

    def is_upload_text(p: Path) -> bool:
        return p.name != "manifest.json"

    found: list[tuple[str, str]] = []
    for p in _iter_files(sandbox, _EXTRACT, is_extract_text) + _iter_files(
        sandbox, _UPLOADS, is_upload_text
    ):
        try:
            raw = p.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw[:4096]:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        found.append((p.relative_to(root).as_posix(), text))
    return found


def _load_ledger(sandbox: Any) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    data, problem = _read_json(sandbox, _LEDGER)
    if problem:
        return None, [_gap("-", _LEDGER, f"ledger {problem}")]
    if not isinstance(data, dict) or not isinstance(data.get("rows"), list):
        return None, [_gap("-", _LEDGER, "ledger has no 'rows' list")]
    return data, []


def _row_ids(ledger: dict[str, Any]) -> list[str]:
    return [str(r["id"]) for r in ledger["rows"] if isinstance(r, dict) and r.get("id")]


def _is_testable(ledger: dict[str, Any]) -> dict[str, bool]:
    return {
        str(r["id"]): r.get("testable", True) is not False
        for r in ledger["rows"]
        if isinstance(r, dict) and r.get("id")
    }


def _load_trace(
    sandbox: Any,
) -> tuple[dict[str, list[Any]] | None, list[dict[str, Any]]]:
    data, problem = _read_json(sandbox, _TRACE)
    if problem:
        return None, [_gap("-", _TRACE, f"trace {problem}")]
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        return None, [_gap("-", _TRACE, "trace has no 'results' list")]
    by_id: dict[str, list[Any]] = {}
    for r in results:
        if isinstance(r, dict) and r.get("id"):
            by_id.setdefault(str(r["id"]), []).append(r.get("status"))
    return by_id, []


# --------------------------------------------------------------------------- modes


def _harvest(
    sandbox: Any, ledger: dict[str, Any]
) -> tuple[list[dict], dict, str | None]:
    ids = set(_row_ids(ledger))
    pattern = ledger.get("id_pattern")
    counts: dict[str, Any] = {"ledger_rows": len(ids)}
    if not pattern:
        return [], counts, "id_pattern is null: harvest relies on the re-read loop"

    expr = str(pattern)
    if expr.startswith("^"):
        expr = expr[1:]
    if expr.endswith("$") and not expr.endswith("\\$"):
        expr = expr[:-1]
    try:
        rx = re.compile(r"(?<![\w-])(?:" + expr + r")(?![\w-])")
    except re.error as exc:
        return [_gap("-", _LEDGER, f"invalid id_pattern: {exc}")], counts, None

    sources = _source_texts(sandbox)
    counts["source_files"] = len(sources)
    if not sources:
        return (
            [
                _gap(
                    "-",
                    f"{_EXTRACT}/ or {_UPLOADS}/",
                    "no extracted or plain-text source found",
                )
            ],
            counts,
            None,
        )

    where_by_id: dict[str, list[str]] = {}
    for rel, text in sources:
        for m in rx.finditer(text):
            locs = where_by_id.setdefault(m.group(0), [])
            if rel not in locs:
                locs.append(rel)

    gaps: list[dict[str, Any]] = []
    for sid in sorted(where_by_id):
        if sid not in ids:
            gaps.append(
                _gap(
                    sid, ", ".join(where_by_id[sid][:3]), "in source but not in ledger"
                )
            )
    for lid in sorted(ids - set(where_by_id)):
        gaps.append(_gap(lid, _LEDGER, "not found in source", severity="warning"))
    counts["distinct_source_ids"] = len(where_by_id)
    counts["unmapped"] = sum(1 for g in gaps if "severity" not in g)
    return gaps, counts, None


def _coverage(sandbox: Any, ledger: dict[str, Any]) -> tuple[list[dict], dict]:
    gaps: list[dict[str, Any]] = []
    rows = _row_ids(ledger)
    testable = _is_testable(ledger)
    ids = list(testable)

    seen: set[str] = set()
    for rid in rows:
        if rid in seen:
            gaps.append(_gap(rid, _LEDGER, "duplicate ledger id"))
        seen.add(rid)

    spec = _read(sandbox, _SPEC)
    if spec is None:
        gaps.append(_gap("-", _SPEC, "missing file"))
    tasks_data, problem = _read_json(sandbox, _TASKS)
    task_ids: set[str] = set()
    if problem:
        gaps.append(
            _gap("-", _TASKS, f"{problem} file" if problem == "missing" else problem)
        )
    else:
        tasks = tasks_data.get("tasks") if isinstance(tasks_data, dict) else None
        if not isinstance(tasks, list):
            gaps.append(_gap("-", _TASKS, "no 'tasks' list"))
        else:
            for t in tasks:
                if not isinstance(t, dict):
                    continue
                for tid in t.get("ids") or []:
                    task_ids.add(str(tid))
                    if str(tid) not in testable:
                        gaps.append(
                            _gap(
                                str(tid),
                                f"{_TASKS} task {t.get('id', '?')}",
                                "task id not in ledger",
                            )
                        )

    for rid in ids:
        if spec is not None and not _word_re(rid).search(spec):
            gaps.append(_gap(rid, _SPEC, "not mentioned in spec.md"))
        if not problem and rid not in task_ids:
            gaps.append(_gap(rid, _TASKS, "not in any task"))
        if testable[rid]:
            rel = f"{_ACCEPTANCE_DIR}/{rid}.json"
            try:
                present = sandbox.path_for(rel).is_file()
            except (ValueError, OSError):
                gaps.append(
                    _gap(rid, _ACCEPTANCE_DIR, "unsafe id for acceptance filename")
                )
                continue
            if not present:
                gaps.append(_gap(rid, rel, "missing acceptance file"))
    return gaps, {
        "ledger_rows": len(rows),
        "testable": sum(testable.values()),
        "task_ids": len(task_ids),
    }


def _trace(sandbox: Any, ledger: dict[str, Any]) -> tuple[list[dict], dict]:
    by_id, gaps = _load_trace(sandbox)
    testable = _is_testable(ledger)
    counts: dict[str, Any] = {"ledger_rows": len(testable)}
    if by_id is None:
        return gaps, counts
    tally = {s: 0 for s in _TRACE_STATUSES}
    for rid, can_test in testable.items():
        statuses = by_id.get(rid, [])
        if not statuses:
            gaps.append(_gap(rid, _TRACE, "no result in trace.json"))
            continue
        if len(statuses) > 1:
            gaps.append(
                _gap(rid, _TRACE, f"{len(statuses)} results (expected exactly one)")
            )
            continue
        status = statuses[0]
        if status not in _TRACE_STATUSES:
            gaps.append(_gap(rid, _TRACE, f"invalid status {status!r}"))
            continue
        tally[status] += 1
        if status == "fail":
            gaps.append(_gap(rid, _TRACE, "failing"))
        elif status == "not-testable" and can_test:
            gaps.append(
                _gap(rid, _TRACE, "marked not-testable but ledger row is testable")
            )
    for rid in sorted(set(by_id) - set(testable)):
        gaps.append(_gap(rid, _TRACE, "trace id not in ledger"))
    counts.update(tally)
    return gaps, counts


def _report(sandbox: Any, ledger: dict[str, Any]) -> tuple[list[dict], dict]:
    by_id, gaps = _load_trace(sandbox)
    ids = list(_is_testable(ledger))
    counts: dict[str, Any] = {"ledger_rows": len(ids)}
    report = _read(sandbox, _REPORT)
    if report is None:
        gaps.append(_gap("-", _REPORT, "missing file"))
    if by_id is None or report is None:
        return gaps, counts
    not_pass = [i for i in ids if by_id.get(i, [None]) != ["pass"]]
    counts["not_pass"] = len(not_pass)
    for rid in not_pass:
        if not _word_re(rid).search(report):
            gaps.append(_gap(rid, _REPORT, "non-pass id not named in report"))
    return gaps, counts


def _acceptance_schema(sandbox: Any, ledger: dict[str, Any]) -> tuple[list[dict], dict]:
    from app.agents.tools import acceptance_tools as at

    gaps: list[dict[str, Any]] = []
    testable = _is_testable(ledger)
    files = _iter_files(sandbox, _ACCEPTANCE_DIR, lambda p: p.suffix == ".json")
    seen: set[str] = set()
    for f in files:
        rid = f.stem
        seen.add(rid)
        rel = f"{_ACCEPTANCE_DIR}/{f.name}"
        doc, problem = _read_json(sandbox, rel)
        if problem:
            gaps.append(_gap(rid, rel, f"acceptance file {problem}"))
            continue
        for msg in at.validate_acceptance_doc(sandbox, doc, rid):
            gaps.append(_gap(rid, rel, msg))
        if rid not in testable:
            gaps.append(
                _gap(
                    rid,
                    rel,
                    "acceptance file for an id not in the ledger",
                    severity="warning",
                )
            )
        elif not testable[rid]:
            gaps.append(
                _gap(
                    rid,
                    rel,
                    "acceptance file for a not-testable ledger row",
                    severity="warning",
                )
            )
    for rid, can_test in testable.items():
        if can_test and rid not in seen:
            gaps.append(
                _gap(rid, f"{_ACCEPTANCE_DIR}/{rid}.json", "missing acceptance file")
            )
    return gaps, {
        "ledger_rows": len(testable),
        "testable": sum(testable.values()),
        "acceptance_files": len(files),
    }


def _trace_fresh(sandbox: Any, ledger: dict[str, Any]) -> tuple[list[dict], dict]:
    from app.agents.tools import acceptance_tools as at

    data, problem = _read_json(sandbox, _TRACE)
    if problem:
        return [_gap("-", _TRACE, f"trace {problem}")], {}
    if not isinstance(data, dict):
        return [_gap("-", _TRACE, "trace is not a JSON object")], {}
    gaps: list[dict[str, Any]] = []
    if data.get("runner") != at.RUN_ACCEPTANCE:
        gaps.append(
            _gap("-", _TRACE, "trace was not written by run_acceptance (runner field)")
        )
    if data.get("partial") is not False:
        gaps.append(
            _gap(
                "-",
                _TRACE,
                "trace is partial (or lacks 'partial'): run run_acceptance with ids='all'",
            )
        )
    page = (
        data.get("page")
        if isinstance(data.get("page"), str) and data.get("page")
        else at.DEFAULT_PAGE
    )
    if page != at.DEFAULT_PAGE:
        gaps.append(
            _gap(
                "-",
                page,
                f"trace tested {page}, not the deliverable {at.DEFAULT_PAGE}: rerun run_acceptance",
            )
        )
        page = at.DEFAULT_PAGE
    current = at.page_sha256(sandbox, page)
    if current is None:
        gaps.append(_gap("-", page, "page missing"))
    elif data.get("page_sha256") != current:
        gaps.append(
            _gap(
                "-",
                page,
                "page changed since the trace was written (page_sha256 differs): rerun run_acceptance",
            )
        )
    results = data.get("results")
    have = (
        {str(r["id"]) for r in results if isinstance(r, dict) and r.get("id")}
        if isinstance(results, list)
        else set()
    )
    testable = _is_testable(ledger)
    for rid, can_test in testable.items():
        if can_test and rid not in have:
            gaps.append(_gap(rid, _TRACE, "no result in trace.json"))
    return gaps, {
        "ledger_rows": len(testable),
        "results": len(have),
        "pass": data.get("pass"),
    }


def run_ledger_check(sandbox: Any, mode: str) -> dict[str, Any]:
    """Pure core of the tool: returns the result dict (never raises)."""
    if mode not in MODES:
        return {
            "ok": False,
            "mode": mode,
            "counts": {},
            "gaps": [
                _gap("-", "mode", f"unknown mode; valid modes: {', '.join(MODES)}")
            ],
        }
    ledger, gaps = _load_ledger(sandbox)
    counts: dict[str, Any] = {}
    note: str | None = None
    if ledger is not None:
        if mode == "harvest":
            gaps, counts, note = _harvest(sandbox, ledger)
        elif mode == "coverage":
            gaps, counts = _coverage(sandbox, ledger)
        elif mode == "trace":
            gaps, counts = _trace(sandbox, ledger)
        elif mode == "acceptance_schema":
            gaps, counts = _acceptance_schema(sandbox, ledger)
        elif mode == "trace_fresh":
            gaps, counts = _trace_fresh(sandbox, ledger)
        else:
            gaps, counts = _report(sandbox, ledger)

    ok = not any(g.get("severity") != "warning" for g in gaps)
    result: dict[str, Any] = {"ok": ok, "mode": mode, "counts": counts}
    if note:
        result["note"] = note
    if len(gaps) > _MAX_GAPS:
        result["truncated"] = len(gaps) - _MAX_GAPS
        gaps = gaps[:_MAX_GAPS]
    result["gaps"] = gaps
    return result


@tool
def ledger_check(mode: str) -> str:
    """Check the requirement ledger against the goal-workflow artefacts (read-only).

    mode is one of: harvest (source IDs vs ledger), coverage (ledger IDs in spec.md,
    tasks.json and acceptance files), trace (one valid result per ID in trace.json),
    report (every non-pass ID named in report.md). Returns JSON:
    {"ok": bool, "mode", "counts", "gaps": [{"id", "where", "reason"}]}.
    """
    if _SANDBOX is None:
        return json.dumps(
            {
                "ok": False,
                "mode": mode,
                "counts": {},
                "gaps": [_gap("-", "sandbox", "no run sandbox bound")],
            }
        )
    try:
        return json.dumps(
            run_ledger_check(
                _SANDBOX, mode.strip().lower() if isinstance(mode, str) else mode
            )
        )
    except Exception as exc:  # never kill the step
        return json.dumps(
            {
                "ok": False,
                "mode": mode,
                "counts": {},
                "gaps": [_gap("-", "ledger_check", f"internal error: {exc}")],
            }
        )
