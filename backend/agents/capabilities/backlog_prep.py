"""agents/capabilities/backlog_prep.py — two backlog steps done by code, not a model.

Both run through the ``mechanical: assemble_backlog`` step kind:
``MechanicalAssembleBacklogStrategy`` picks the job by the step's instance id
(``BACKLOG_CODE_JOBS``), so a new job needs no new engine dispatch.

``integrate_answers`` — the Answer Integrator (``us-close``). Folds the user's answers
from ``clarify/answers.json`` into ``validate.json`` (``filled_from: "user"``) and
``synthesis.md`` (one ``[user]`` line per answer under ``## Decisions from the user``,
and the gap's line out of ``## Open gaps``). Run c4cbd381 did this with a model:
126 single-line edits, 8.7M tokens, for work that has no judgment in it.

``build_writer_tasks`` — the Story Writers' task list (``us-writer-tasks``). Copies
``build/story-tasks.json`` to ``build/writer-tasks.json`` with every task's body
carrying the full model items it covers, the endpoints and rules around them, the
personas and an index of every endpoint id. Run c4cbd381's writers had only item ids,
so each spent ~15 calls finding the items in ``build/solution/`` — 40.5M tokens.

``tidy_json`` — every backlog code step (and ``us-json``, right after the API Designer)
re-indents the JSON the run has written, because models write it on one line.

Pure stdlib; reaches the sandbox only through ``sandbox.read``/``.write``.
"""

from __future__ import annotations

import json
import re
from typing import Any

from agents.capabilities.backlog_assemble import (
    BACKLOG_PLAN_PATH,
    SOLUTION_DIR,
    SOLUTION_KINDS,
    STORY_TASKS_PATH,
    REVIEW_PATH,
    STORIES_DIR,
    _item_title,
    _parse_json,
    collect_coverage_items,
    list_story_task_ids,
    parse_backlog_plan,
    parse_solution_kind,
)

ANSWERS_PATH = "clarify/answers.json"
VALIDATE_PATH = "validate.json"
SYNTHESIS_PATH = "synthesis.md"
WRITER_TASKS_PATH = "build/writer-tasks.json"
COVERAGE_ITEMS_PATH = "build/coverage-items.json"
DECISIONS_HEADING = "## Decisions from the user"
OPEN_GAPS_HEADING = "## Open gaps"
_OUT_OF_SCOPE = "not applicable"
_GAP_LINE_RE = re.compile(r"^\s*-\s*(gap-\d+)\s*:")
# Model ids: `SCR-quote-entry`, `ENT-01`, `API-12`, `BR-3` — a capitalised prefix, a
# hyphen, then letters/digits/hyphens that never end on a hyphen.
_ITEM_ID_RE = re.compile(r"\b[A-Z]{2,4}-[A-Za-z0-9-]*[A-Za-z0-9]")


# ── Answer Integrator ─────────────────────────────────────────────────────────────


def _answered(answers_text: str | None) -> dict[str, dict]:
    data = _parse_json(answers_text)
    entries = data.get("answers") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        return {}
    return {
        e["id"]: e
        for e in entries
        if isinstance(e, dict)
        and e.get("id")
        and e.get("answered")
        and e.get("answer") is not None
    }


def _without_section(lines: list[str], heading: str) -> list[str]:
    """``lines`` minus the section that starts at ``heading`` (to the next ``## ``)."""
    out: list[str] = []
    skipping = False
    for line in lines:
        if line.strip() == heading:
            skipping = True
            continue
        if skipping and line.startswith("## "):
            skipping = False
        if not skipping:
            out.append(line)
    return out


def fold_answers(
    synthesis: str, validate: dict, answered: dict[str, dict]
) -> tuple[str, dict, int]:
    """Pure core of ``integrate_answers``: (new synthesis, new validate, gaps closed).

    Idempotent: the decisions section is rebuilt from the answers every time."""
    decisions: list[str] = []
    closed: set[str] = set()
    for gap in validate.get("gaps") or []:
        entry = answered.get(gap.get("id")) if isinstance(gap, dict) else None
        if entry is None:
            continue
        answer = str(entry["answer"]).strip()
        gap["filled_from"] = "user"
        gap["answer"] = answer
        closed.add(gap["id"])
        question = str(gap.get("gap") or entry.get("question") or "").strip()
        if answer.lower().startswith(_OUT_OF_SCOPE):
            decisions.append(f"- Out of scope: {question} [user {gap['id']}]")
        else:
            decisions.append(f"- {question} — {answer} [user {gap['id']}]")

    lines = _without_section(synthesis.splitlines(), DECISIONS_HEADING)
    lines = [
        ln
        for ln in lines
        if not ((m := _GAP_LINE_RE.match(ln)) and m.group(1) in closed)
    ]
    if decisions:
        block = [DECISIONS_HEADING, "", *decisions, ""]
        at = next(
            (i for i, ln in enumerate(lines) if ln.strip() == OPEN_GAPS_HEADING),
            len(lines),
        )
        lines[at:at] = block
    return "\n".join(lines) + "\n", validate, len(closed)


def integrate_answers(sandbox: Any) -> str:
    answered = _answered(sandbox.read(ANSWERS_PATH))
    if not answered:
        return "No answers: the user was not asked, or skipped. synthesis.md and validate.json unchanged."
    validate = _parse_json(sandbox.read(VALIDATE_PATH))
    synthesis = sandbox.read(SYNTHESIS_PATH)
    if not isinstance(validate, dict) or synthesis is None:
        return "validate.json or synthesis.md is missing — nothing to fold the answers into."
    new_synthesis, new_validate, closed = fold_answers(synthesis, validate, answered)
    sandbox.write(SYNTHESIS_PATH, new_synthesis)
    sandbox.write(VALIDATE_PATH, pretty_json(new_validate))
    still_open = sum(
        1
        for g in new_validate.get("gaps") or []
        if isinstance(g, dict) and not g.get("filled_from")
    )
    return f"Answers folded in: {closed} gap(s) closed by the user, {still_open} still open."


# ── Story Writers' task list ──────────────────────────────────────────────────────


def _endpoint_line(e: dict) -> str:
    return f"{e.get('id')} {e.get('method')} {e.get('path')} — {e.get('name') or e.get('summary') or ''}".rstrip(
        " —"
    )


def enrich_task(
    task: dict,
    items: dict[str, dict],
    solution: dict[str, list[dict]],
    plan: dict,
    endpoint_index: str,
) -> dict:
    """One writer task → the same task, its body carrying everything the writer reads."""
    body = str(task.get("body") or "")
    covered = list(dict.fromkeys(m for m in _ITEM_ID_RE.findall(body) if m in items))
    ids = set(covered)
    related_eps = [
        e
        for e in solution.get("endpoints", [])
        if e.get("id") not in ids
        and (e.get("entity") in ids or ids & set(e.get("screens") or []))
    ]
    related_rules = [
        r
        for r in solution.get("rules", [])
        if r.get("id") not in ids and ids & set(r.get("applies_to") or [])
    ]
    sections = [
        body,
        "=== YOUR ITEMS — the full model item for every id your slice covers ===",
        *(json.dumps(items[i], ensure_ascii=False) for i in covered),
    ]
    if related_eps:
        sections += [
            "=== ENDPOINTS YOUR ITEMS USE (built by other slices) ===",
            *(_endpoint_line(e) for e in related_eps),
        ]
    if related_rules:
        sections += [
            "=== RULES ON YOUR ITEMS (covered by other slices) ===",
            *(
                f"{r.get('id')}: {r.get('statement')}"
                + (f" Message: {r['message']}" if r.get("message") else "")
                for r in related_rules
            ),
        ]
    sections += [
        "=== PERSONAS ===",
        *(json.dumps(p, ensure_ascii=False) for p in plan.get("personas") or []),
        '=== EVERY ENDPOINT ID — the only ids an "api" list may hold ===',
        endpoint_index,
    ]
    return {**task, "body": "\n".join(sections)}


def build_writer_tasks(sandbox: Any) -> str:
    tasks_doc = _parse_json(sandbox.read(STORY_TASKS_PATH))
    tasks = tasks_doc.get("tasks") if isinstance(tasks_doc, dict) else None
    if not isinstance(tasks, list) or not tasks:
        raise ValueError(
            f"{STORY_TASKS_PATH} is missing or holds no tasks — the Backlog Planner wrote none."
        )
    solution = {
        k: parse_solution_kind(sandbox.read(f"{SOLUTION_DIR}/{k}.json"))
        for k in SOLUTION_KINDS
    }
    items = {it["id"]: it for lst in solution.values() for it in lst if it.get("id")}
    plan = parse_backlog_plan(sandbox.read(BACKLOG_PLAN_PATH))
    endpoint_index = "\n".join(_endpoint_line(e) for e in solution.get("endpoints", []))
    out = [
        enrich_task(t, items, solution, plan, endpoint_index)
        for t in tasks
        if isinstance(t, dict)
    ]
    sandbox.write(WRITER_TASKS_PATH, pretty_json({"tasks": out}))
    return f"Wrote {WRITER_TASKS_PATH}: {len(out)} writer task(s), each carrying its model items in full."


# ── Indented JSON ─────────────────────────────────────────────────────────────────


def pretty_json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def json_paths(sandbox: Any) -> list[str]:
    """Every JSON file the backlog workflow writes, as far as the run has got."""
    paths = [
        "build/tasks.json",
        VALIDATE_PATH,
        ANSWERS_PATH,
        ".clarify/solution.json",
        ".clarify/api.json",
        ".clarify/architect.json",
        ".clarify/backlog.json",
        *(f"{SOLUTION_DIR}/{k}.json" for k in SOLUTION_KINDS),
        BACKLOG_PLAN_PATH,
        STORY_TASKS_PATH,
        WRITER_TASKS_PATH,
        REVIEW_PATH,
    ]
    reading = _parse_json(sandbox.read("build/tasks.json"))
    for task in (reading.get("tasks") if isinstance(reading, dict) else None) or []:
        for target in (task.get("targets") if isinstance(task, dict) else None) or []:
            if isinstance(target, str) and target.endswith("status.json"):
                paths += [target, target[: -len("status.json")] + "gaps.json"]
    plan = parse_backlog_plan(sandbox.read(BACKLOG_PLAN_PATH))
    story_ids = list_story_task_ids(sandbox.read(STORY_TASKS_PATH))
    story_ids += [
        f"review-{e['id']}"
        for e in plan["epics"]
        if isinstance(e, dict) and e.get("id")
    ]
    paths += [f"{STORIES_DIR}/{i}.json" for i in story_ids]
    return list(dict.fromkeys(paths))


def tidy_json(sandbox: Any) -> int:
    """Re-indent every JSON file the run has written; same content, 2-space indent.

    Models write JSON on one line whatever the prompt asks (run c4cbd381: every file,
    endpoints.json 88KB on one line — past read_file's ~80,000-character page, so the
    steps after it never read its tail). A file that is missing or does not parse is
    left alone. Returns how many files it rewrote."""
    rewritten = 0
    for path in json_paths(sandbox):
        text = sandbox.read(path)
        data = _parse_json(text)
        if data is None:
            continue
        laid = pretty_json(data)
        if laid != text:
            sandbox.write(path, laid)
            rewritten += 1
    return rewritten


def write_coverage_items(sandbox: Any) -> str:
    """The Backlog Planner's checklist: every coverage item, one line each.

    Built with the same ``collect_coverage_items`` the final assembly counts, so the
    plan is checked against exactly what coverage is measured on. Run 3976f8ce's
    planner paged endpoints.json (6,485 lines) only to ~line 3000 and never saw
    API-34..API-76; this file carries every id in one short read."""
    solution = {
        kind: parse_solution_kind(sandbox.read(f"{SOLUTION_DIR}/{kind}.json"))
        for kind in SOLUTION_KINDS
    }
    items = collect_coverage_items(solution)
    rows = [
        json.dumps(
            {
                "id": item_id,
                "type": item["kind"],
                "title": " ".join(_item_title(item).split()),
                "provenance": item.get("provenance", "evidenced"),
            },
            ensure_ascii=False,
        )
        for item_id, item in items.items()
    ]
    sandbox.write(COVERAGE_ITEMS_PATH, '{"items": [\n' + ",\n".join(rows) + "\n]}\n")
    return f"Wrote {COVERAGE_ITEMS_PATH}: {len(rows)} coverage item(s)."


# Step instance id → the job it runs. Every other ``assemble_backlog`` step assembles.
# Every backlog code step then re-indents the run's JSON (tidy_json, in the adapter).
BACKLOG_CODE_JOBS = {
    "us-close": integrate_answers,
    "us-json": lambda sandbox: (
        f"JSON files indented for the steps that read them. "
        f"{write_coverage_items(sandbox)}"
    ),
    "us-writer-tasks": build_writer_tasks,
}
