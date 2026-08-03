"""A spec grader that splits the work by what each side is actually good at.

The problem this solves
-----------------------
`evals/minimal/judge.py` scored this spec 94.4 with `brief_intent_match: 100`,
while SKU GP-24701 is 42 cases on-hand on two pages and 28 on a third, and 18
daily picks on the Slot Grid against 115 on the Velocity Report — which the
brief explicitly required to be derivable from the grid. A free-form "score
these dimensions" prompt gets a reviewer's read-through, and a read-through
never cross-references page 1 against page 4.

A first attempt asked the model to extract facts and then compare them itself.
Extraction worked (46 facts). Comparison did not: it reported "Replenishment
shows 12 cards but Slot Grid shows 12 SKUs below reorder" as BLOCKING — those
are the same number — and "3 queued moves vs 15 total" when the spec says 3
queued + 12 completed. Two of four blocking findings were false, and it still
missed both real value mismatches.

The split
---------
- The MODEL transcribes facts and judges things that need judgement (missing
  rules, ambiguity, unbuildable instructions). It is good at this.
- PYTHON finds contradictions, by grouping facts on (entity, field) and
  flagging any group holding more than one value. It cannot hallucinate a
  conflict between two 12s, and it cannot fail to notice 42 vs 28.
- PYTHON prices severity, because a model asked for a number returns a
  comfortable one.

Contradictions the model reports are DISCARDED — that category belongs to
Python now. Everything else it says is kept.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
from collections import defaultdict

from pydantic import BaseModel, Field

import trial_paths

SEVERITY_COST = {"blocking": 45, "major": 18, "minor": 4}


class Fact(BaseModel):
    """One value the spec states about one entity on one page."""
    entity: str = Field(description="The subject, e.g. 'GP-24701', 'Slot Grid', 'A-07-2'")
    field: str = Field(description="The property, e.g. 'on-hand', 'daily picks', 'row count'")
    page: str = Field(description="Which page or section states it")
    value: str = Field(description="The value exactly as written, e.g. '42 cases'")


class Issue(BaseModel):
    severity: str = Field(description="blocking | major | minor")
    category: str = Field(description="missing | ambiguous | unbuildable | untraceable")
    what: str = Field(description="The defect in one sentence")
    where: str = Field(description="Page(s) and section(s)")
    evidence: str = Field(description="Quote from the spec, or the brief line not satisfied")


class SpecExtract(BaseModel):
    facts: list[Fact] = Field(
        description="EVERY value stated about a named entity, one row per page it appears on")
    issues: list[Issue] = Field(
        description="Defects needing judgement. Do NOT report contradictions here.")
    brief_requirements_missed: list[str] = Field(
        description="Requirements from the brief the spec does not satisfy")


PROMPT = """Read this specification as the engineer who has to BUILD it.

STEP 1 — facts. Transcribe every value the spec states about a named entity, as
(entity, field, page, value).

- One row per page the entity appears on. If SKU GP-24701 has an on-hand figure
  on three pages, that is THREE rows, even if the numbers look the same.
- `entity` is the domain object (a SKU code, a slot code, a page name), never a
  section heading.
- `field` MUST come from this list, exactly, with no additions or qualifiers:
{field_vocab}
  Never append context like "(replenishment card)" — a qualified name groups
  separately from the plain one and hides real conflicts. If a value does not
  fit any listed field, use "other".
- `value` verbatim, including units.

Be exhaustive. Missing a row means a real conflict goes unseen. This is
transcription, not analysis — do not judge anything in this step.

STEP 2 — issues. Report ONLY these categories:
- missing: a rule the build needs that is absent (how a value is computed, how a
  suggestion is generated, what an empty state shows).
- ambiguous: a builder must guess between two readings.
- unbuildable: two incompatible instructions for the same element, e.g. the same
  data specified as both a card grid and a table.
- untraceable: a requirement in the brief the spec does not satisfy. BLOCKING if
  the brief said "must".

DO NOT report contradictions between values — those are detected separately.
Say nothing about tone, polish, or wording.

=== BRIEF ===
{brief}

=== SPECIFICATION ===
{spec}
"""

_NUM = re.compile(r"-?\d[\d,]*\.?\d*")


def norm_key(text: str) -> str:
    """Entity/field key: parentheticals dropped, then alphanumerics only.

    Collapses 'On-Hand', 'on hand' and 'onHand' onto one bucket. The
    parenthetical strip matters more than it looks: the first real run
    extracted 'on-hand' on one page and 'on-hand (replenishment card)' on
    another, which grouped separately and hid a 42-vs-28 conflict. Models
    qualify field names with context unless stopped.
    """
    text = re.sub(r"\([^)]*\)", " ", text)
    return re.sub(r"[^a-z0-9]", "", text.lower())


def norm_value(text: str) -> str:
    """Comparable form of a value.

    Numeric values compare as numbers with units dropped — '42 cases' and '42'
    are the same fact, '42 cases' and '28 cases' are not. Non-numeric values
    compare as squashed lowercase text.
    """
    numbers = _NUM.findall(text)
    if numbers:
        return numbers[0].replace(",", "")
    return " ".join(text.lower().split())


def find_contradictions(facts: list[dict]) -> list[dict]:
    """Group facts on (entity, field); anything holding two values is a conflict.

    Deterministic, so it cannot invent the "12 cards vs 12 SKUs" conflict the
    model produced, and cannot overlook 42 vs 28.

    Single-page groups are skipped: one page restating its own number is
    formatting, not disagreement. A conflict needs two pages to be a conflict.
    """
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for fact in facts:
        if not (fact.get("entity") and fact.get("field") and fact.get("value")):
            continue
        # "other" is the vocabulary's escape hatch, so it collects unrelated
        # values — a page's purpose sentence and a nav flow both land there.
        # Comparing within it produced 20+ bogus "conflicts" between things
        # that were never the same property. Only NAMED fields are comparable.
        if norm_key(fact["field"]) == norm_key("other"):
            continue
        groups[(norm_key(fact["entity"]), norm_key(fact["field"]))].append(fact)

    found = []
    for (entity, field), rows in sorted(groups.items()):
        values = {norm_value(r["value"]) for r in rows}
        pages = {r.get("page", "?") for r in rows}
        if len(values) > 1 and len(pages) > 1:
            detail = "; ".join(f"{r.get('page')}: {r['value']}" for r in rows)
            found.append({
                "severity": "blocking",
                "category": "contradiction",
                "what": f"'{rows[0]['entity']}' has conflicting '{rows[0]['field']}' values across pages",
                "where": ", ".join(sorted(pages)),
                "evidence": detail,
            })
    return found


def price(issues: list[dict]) -> int:
    spent = sum(SEVERITY_COST.get(i.get("severity", "minor"), 4) for i in issues)
    return max(0, 100 - spent)


# The closed vocabulary. Same fix as the advisor's category list: free-text
# keys fragment, a fixed list groups. Sourced from the scenario contract that
# graded this trial, so it stays the same vocabulary the code grader checked
# coverage against — and so a mission-control spec is grouped on program fields
# rather than warehouse ones.
def field_vocabulary(trial: pathlib.Path) -> list[str]:
    base = ["row count", "route", "other"]
    return sorted(set((trial_paths.contract(trial).get("fields") or []) + base))


def grade(spec: str, brief: str, model: str = "mistral/mistral-large-latest",
          fields: list[str] | None = None) -> dict:
    import litellm

    vocab = "\n".join(f"    - {f}" for f in (fields or ["other"]))
    reply = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": PROMPT.format(
            brief=brief, spec=spec, field_vocab=vocab)}],
        response_format=SpecExtract,
        api_key=os.environ.get("MISTRAL_API_KEY"),
        timeout=900,
    )
    extract = json.loads(reply.choices[0].message.content)
    facts = extract.get("facts") or []

    contradictions = find_contradictions(facts)
    # Drop any contradiction the model reported anyway — Python owns that call.
    judged = [i for i in (extract.get("issues") or [])
              if i.get("category") != "contradiction"]
    issues = contradictions + judged

    return {
        "score": price(issues),
        "counts": {s: sum(1 for i in issues if i.get("severity") == s) for s in SEVERITY_COST},
        "contradictions_found_by_python": len(contradictions),
        "issues_found_by_model": len(judged),
        "issues": issues,
        "facts": facts,                       # persisted — the whole method rests on these
        "requirements_missed": extract.get("brief_requirements_missed") or [],
        "tokens_in": getattr(reply.usage, "prompt_tokens", 0),
        "tokens_out": getattr(reply.usage, "completion_tokens", 0),
    }


def main() -> int:
    import sys

    here = pathlib.Path(__file__).resolve().parent
    if len(sys.argv) > 1:
        spec_path = pathlib.Path(sys.argv[1])
    else:
        found = sorted((here / "jobs").glob("*/*/artifacts/app/spec.md"))
        if not found:
            raise SystemExit("no spec.md under jobs/ — run ./eval.sh first")
        spec_path = found[-1]

    # The brief comes from the task this trial ran, not a fixed path — grading a
    # spec against another scenario's brief produces confident, wrong findings.
    trial = trial_paths.trial_of(spec_path)
    brief = (trial_paths.task_dir(trial) / "instruction.md").read_text(encoding="utf-8")
    result = grade(spec_path.read_text(encoding="utf-8"), brief,
                    fields=field_vocabulary(trial))

    print(f"spec   : {spec_path}")
    print(f"score  : {result['score']}   {result['counts']}")
    print(f"facts  : {len(result['facts'])} extracted   "
          f"({result['contradictions_found_by_python']} contradictions by python, "
          f"{result['issues_found_by_model']} issues by model)")
    print()
    for issue in result["issues"]:
        cost = SEVERITY_COST.get(issue.get("severity", "minor"), 4)
        print(f"[{issue['severity']:<8} -{cost:>2}] {issue['category']}: {issue['what']}")
        print(f"           {issue['evidence'][:190]}")
    if result["requirements_missed"]:
        print("\nBRIEF REQUIREMENTS NOT MET:")
        for req in result["requirements_missed"]:
            print(f"  - {req}")
    print(f"\ntokens : in={result['tokens_in']} out={result['tokens_out']}")

    out = spec_path.parent.parent.parent / "spec_judge.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
