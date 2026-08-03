"""Build-readiness floor for `plan`, checked against the SPEC it came from.
Stage logic only, and scenario-independent: the pages and routes come from the
scenario contract, so this file grades every scenario. Shared machinery lives in
verifier.py.

The reason a chained stage is worth the extra plumbing: its output can be
graded against its own input, which a single-stage eval cannot do. The agent
uploads `spec.md` into the container alongside `tasks.md` precisely so this
file can compare them.

Three coverage numbers, and the third is the one that earns its keep:

  page_coverage      — the contract's pages appear in some task. Static; the
                       same check the specify stage runs.
  route_coverage     — routes survive from contract into plan.
  spec_page_coverage — every page the SPEC ACTUALLY DEFINED appears in some
                       task. Dynamic: the spec may define pages the contract
                       never named, and a plan that quietly drops one of those
                       is dropping real work. No static contract can catch it.

                       KNOWN HOLE: this scores a free 1.0 when SPEC_PAGE_HEADING
                       matches nothing, because "no pages found" and "all pages
                       covered" are the same number. warehouse-slotting's
                       reference spec heads pages as `### Slot Grid` with no
                       `(#/route)`, so it has always scored 1.0 here without the
                       check ever running — which is why the number looked fine
                       and meant nothing. mission-control's spec uses
                       `### Dashboard (`#/dashboard`)` and is the first case
                       where this check does real work (7 headings found).
                       Failing closed instead would fail every well-formed spec
                       that heads its pages differently, so the fraction is left
                       generous and `spec_pages_missing` reports the raw count.

`plan` emits prose, so this is a floor. A task list can name all six pages and
still be unbuildable.
"""

import pathlib
import re

import verifier

TASKS = pathlib.Path("/app/tasks.md")
SPEC = pathlib.Path("/app/spec.md")

# How the specify agent heads a page: `### Slot Grid (`#/`)`.
SPEC_PAGE_HEADING = r"^###\s+([^(\n]+?)\s*\(`?#/"
TASK_HEADER = r"^##\s*Task\s*\d+"


def measure() -> dict:
    if not TASKS.exists():
        return verifier.absent(plan_ready=0.0, task_count=0, page_coverage=0.0,
                                route_coverage=0.0, spec_page_coverage=0.0,
                                has_tasks_block=0.0, words=0)

    text = TASKS.read_text(encoding="utf-8")
    contract = verifier.contract()

    page_coverage, missing_pages = verifier.coverage(text, contract.get("pages") or [])
    route_coverage, _ = verifier.coverage(text, contract.get("routes") or [])
    tasks = re.findall(TASK_HEADER, text, re.M | re.I)

    spec_page_coverage, spec_missing = 1.0, []
    if SPEC.exists():
        spec_pages = verifier.headings(SPEC.read_text(encoding="utf-8"), SPEC_PAGE_HEADING)
        if spec_pages:
            spec_page_coverage, spec_missing = verifier.coverage(text, spec_pages)

    ready = (
        not missing_pages
        and not spec_missing
        and len(tasks) >= int(contract.get("min_tasks") or 1)
    )
    print("MISSING contract pages:", ", ".join(missing_pages) or "(none)")
    print("MISSING spec pages    :", ", ".join(spec_missing) or "(none)")
    print("tasks found           :", len(tasks))
    return {
        "reward": 1.0 if ready else 0.0,
        "plan_ready": 1.0 if ready else 0.0,
        "task_count": len(tasks),
        "has_tasks_block": 1.0 if re.search(r"<tasks>", text, re.I) else 0.0,
        "page_coverage": page_coverage,
        "route_coverage": route_coverage,
        "spec_page_coverage": spec_page_coverage,
        "spec_pages_missing": len(spec_missing),
        "words": len(text.split()),
        "missing_artifact": 0.0,
    }


if __name__ == "__main__":
    verifier.emit(measure)
