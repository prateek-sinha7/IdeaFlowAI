"""app/agents/tools/ledger_tools.py -- requirement-ledger consistency checks (P27 E5).

One read-only, deterministic, model-free tool, `ledger_check(mode)`, that compares the
goal-workflow artefacts in the run sandbox against `.goal/ledger.json`:

  harvest   IDs found in the extracted source text vs ledger rows
  coverage  every ledger ID in spec.md, tasks.json (+ build/parts-tasks.json, goal_v2) and (if testable)
            .goal/acceptance/
  trace     every ledger ID has exactly one valid result in .goal/trace.json
  report    every non-pass ID is named in .goal/report.md
  acceptance_schema  every acceptance file is valid v2 format; every testable ID has one (goal)
  trace_fresh        trace.json was written by run_acceptance over ALL ids, against the current page
                     (goal)
  gaps      every page of every requirements upload accounted for in .goal/pages.json, every
            requirement-like sentence in the ledger or excused, plus harvest (read-only preview)
  gaps_decide  the same check for the gap-analysis step: records one loop pass and WRITES
            .goal/gaps.json with the pass history and a code-made `next` (ok | retry) (goal)

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

MODES = (
    "harvest",
    "coverage",
    "trace",
    "report",
    "acceptance_schema",
    "trace_fresh",
    "gaps",
    "gaps_decide",
)
_TRACE_STATUSES = ("pass", "fail", "not-testable")
_MAX_GAPS = 200
_LEDGER = ".goal/ledger.json"
_SPEC = "spec.md"
_TASKS = "tasks.json"
# goal_v2: the shell task is in tasks.json, the parallel parts in this file; coverage counts both.
_PARTS_TASKS = "build/parts-tasks.json"
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
    parts_data, parts_problem = _read_json(sandbox, _PARTS_TASKS)
    if not parts_problem and isinstance(parts_data, dict):
        for t in parts_data.get("tasks") or []:
            if not isinstance(t, dict):
                continue
            for tid in t.get("ids") or []:
                task_ids.add(str(tid))
                if str(tid) not in testable:
                    gaps.append(
                        _gap(
                            str(tid),
                            f"{_PARTS_TASKS} task {t.get('id', '?')}",
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


# --------------------------------------------------------------------------- gaps

_INVENTORY = ".goal/inventory.json"
_PAGES = ".goal/pages.json"
_GAPS = ".goal/gaps.json"
# Wording that marks a sentence as a possible requirement. Deliberately broad: a false
# candidate costs one "not a requirement" line in pages.json; a missed one costs a
# requirement.
_REQ_WORDS = re.compile(
    r"\b(must|shall|should|required|requires|mandatory|needs? to|has to|have to|"
    r"is not allowed|are not allowed|may not|cannot|can not|never|always)\b",
    re.IGNORECASE,
)
_ID_LIKE = re.compile(r"(?<![\w-])[A-Z]{1,5}-?\d+(?:-[A-Z]?\d+)?(?![\w-])")
_STOP = frozenset(
    "the and for with that this from are was were will shall must should have has "
    "not but all any can may its their them they into than then when which while "
    "only also each such been being are".split()
)
_COVER_RATIO = 0.6


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2} - _STOP


def _requirement_docs(sandbox: Any) -> list[tuple[str, str, int]]:
    """(upload name, extract dir, page_count) for every `requirements` upload."""
    inv, _ = _read_json(sandbox, _INVENTORY)
    names = {
        str(f.get("name"))
        for f in (inv or {}).get("files", [])
        if isinstance(f, dict) and f.get("role") == "requirements"
    }
    docs: list[tuple[str, str, int]] = []
    root = sandbox.path_for(".")
    for m in _iter_files(sandbox, _EXTRACT, lambda p: p.name == "manifest.json"):
        try:
            man = json.loads(m.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(man, dict) or str(man.get("source")) not in names:
            continue
        count = man.get("page_count")
        if not isinstance(count, int):
            count = len(man.get("pages") or {})
        docs.append((str(man["source"]), m.parent.relative_to(root).as_posix(), count))
    return docs


def _page_texts(sandbox: Any, doc_dir: str) -> dict[int, str]:
    out: dict[int, str] = {}
    for p in _iter_files(sandbox, f"{doc_dir}/pages", lambda p: p.name == "text.md"):
        try:
            out[int(p.parent.name)] = p.read_text(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            continue
    return out


def _row_page(row: dict[str, Any], default: int) -> int:
    """The row's source page as an int; `default` when absent or not a number."""
    try:
        return int((row.get("source") or {}).get("page") or default)
    except (TypeError, ValueError):
        return default


def _candidates(text: str) -> list[str]:
    """Requirement-like sentences on one page.

    PDF text wraps mid-sentence, so a line that does not end a sentence is joined with
    the next one unless the next starts a new item (bullet, number, table row, heading).
    """
    paras: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        new_item = not line or re.match(r"([-*•#|]|\d+[.)]\s|[A-Z]{1,5}-?\d)", line)
        if (
            paras
            and paras[-1]
            and not new_item
            and not paras[-1].endswith((".", ";", ":", "!", "?"))
        ):
            paras[-1] += " " + line
        else:
            paras.append(line)
    found: list[str] = []
    for block in paras:
        block = block.strip().strip("|").strip()
        for part in re.split(r"(?<=[.;!?])\s+(?=[A-Z])", block):
            part = part.strip(" -*•\t")
            if len(part.split()) >= 4 and _REQ_WORDS.search(part):
                found.append(part)
    return found


def _gaps(
    sandbox: Any, ledger: dict[str, Any], decide: bool = False
) -> tuple[list[dict], dict, str | None]:
    """Page accounting + requirement-like sentences + ids.

    `gaps` (decide=False) is a read-only preview any step may run. `gaps_decide`
    (decide=True) is for the gap-analysis step only: it records one loop pass and WRITES
    `.goal/gaps.json` (all gaps, uncapped, plus the pass history) so the ledger step can
    work from it and progress is measured by code. Only decide calls enter the history,
    so a preview can never make a later pass look like "no progress". `next` is `ok`
    when nothing blocking is left, or when a pass made no progress (the rest goes to the
    human review); otherwise `retry`.
    """
    gaps: list[dict[str, Any]] = []
    rows = [r for r in ledger["rows"] if isinstance(r, dict)]
    pages_doc, problem = _read_json(sandbox, _PAGES)
    entries = (pages_doc or {}).get("pages") if isinstance(pages_doc, dict) else None
    if not isinstance(entries, list):
        entries = []
        gaps.append(_gap("-", _PAGES, f"pages.json {problem or 'has no pages list'}"))
    by_page: dict[tuple[str, int], dict] = {}
    for e in entries:
        if isinstance(e, dict) and isinstance(e.get("page"), int):
            by_page[(str(e.get("file")), e["page"])] = e

    docs = _requirement_docs(sandbox)
    if not docs:
        gaps.append(_gap("-", _INVENTORY, "no extracted requirements document found"))
    pages_total = pages_read = candidates_total = 0
    for name, doc_dir, count in docs:
        texts = _page_texts(sandbox, doc_dir)
        for page in range(1, max(count, max(texts, default=0)) + 1):
            pages_total += 1
            where = f"{name} p{page}"
            entry = by_page.get((name, page))
            if entry is None:
                gaps.append(
                    _gap(
                        "-",
                        where,
                        "page not read (not in pages.json)",
                        kind="page",
                        file=name,
                        page=page,
                    )
                )
                continue
            pages_read += 1
            near = [
                r
                for r in rows
                if str((r.get("source") or {}).get("file")) == name
                and abs(_row_page(r, page) - page) <= 1
            ]
            row_words = [_words(str(r.get("text", ""))) for r in near]
            excused = [_norm(str(s)) for s in entry.get("not_requirements") or []]
            excused = [s for s in excused if len(s) >= 15]
            for cand in _candidates(texts.get(page, "")):
                candidates_total += 1
                cw = _words(cand)
                if not cw:
                    continue
                if any(len(cw & rw) / len(cw) >= _COVER_RATIO for rw in row_words):
                    continue
                nc = _norm(cand)
                if any(s in nc for s in excused):
                    continue
                gaps.append(
                    _gap(
                        "-",
                        where,
                        "requirement-like sentence not in the "
                        "ledger and not listed under not_requirements",
                        kind="sentence",
                        file=name,
                        page=page,
                        text=cand[:300],
                    )
                )

    harvest_gaps, harvest_counts, note = _harvest(sandbox, ledger)
    for g in harvest_gaps:
        gaps.append({**g, "kind": "id"})

    # Id-like tokens the id_pattern does not match: a narrow pattern hides ids from harvest.
    pattern = ledger.get("id_pattern")
    if pattern:
        try:
            rx = re.compile(str(pattern))
        except re.error:
            rx = None
        if rx is not None:
            seen: dict[str, int] = {}
            for _rel, text in _source_texts(sandbox):
                if not _rel.startswith(_EXTRACT):
                    continue
                for tok in _ID_LIKE.findall(text):
                    seen[tok] = seen.get(tok, 0) + 1
            for tok, n in sorted(seen.items()):
                if n >= 2 and not rx.fullmatch(tok):
                    gaps.append(
                        _gap(
                            tok,
                            "id_pattern",
                            f"id-like token seen {n} times "
                            "but not matched by id_pattern",
                            kind="id_like",
                            severity="warning",
                        )
                    )

    blocking = sum(1 for g in gaps if g.get("severity") != "warning")
    if not decide:
        return (
            gaps,
            {
                "preview": True,
                "pages_total": pages_total,
                "pages_read": pages_read,
                "candidates": candidates_total,
                "ledger_rows": len(rows),
                "blocking": blocking,
                **{f"harvest_{k}": v for k, v in harvest_counts.items()},
            },
            note,
        )
    prev, _ = _read_json(sandbox, _GAPS)
    history = list((prev or {}).get("history") or []) if isinstance(prev, dict) else []
    if blocking == 0:
        decision = "ok"
    elif history and blocking >= history[-1]:
        decision = (
            "ok"  # no progress since the last pass: stop, the review shows the rest
        )
    else:
        decision = "retry"
    history.append(blocking)
    counts = {
        "pass": len(history),
        "pages_total": pages_total,
        "pages_read": pages_read,
        "candidates": candidates_total,
        "ledger_rows": len(rows),
        "blocking": blocking,
        "history": history,
        "next": decision,
        **{f"harvest_{k}": v for k, v in harvest_counts.items()},
    }
    try:
        out = sandbox.path_for(_GAPS)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({**counts, "gaps": gaps}, indent=1), encoding="utf-8")
    except (ValueError, OSError) as exc:
        gaps.append(_gap("-", _GAPS, f"could not write gaps.json: {exc}"))
    return gaps, counts, note


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
        elif mode in ("gaps", "gaps_decide"):
            gaps, counts, note = _gaps(sandbox, ledger, decide=mode == "gaps_decide")
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
    report (every non-pass ID named in report.md), acceptance_schema, trace_fresh,
    gaps (preview: unread pages and unaccounted requirement sentences), gaps_decide
    (gap-analysis step only: records the pass, writes .goal/gaps.json and returns
    counts.next = ok | retry). Returns JSON:
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
