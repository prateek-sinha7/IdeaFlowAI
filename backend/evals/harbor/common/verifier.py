"""Helpers every stage verifier needs, so no stage reimplements them.

Runs INSIDE the container, copied to /tests/verifier.py by sync_common.sh.
Harbor copies a task's whole tests/ directory in, so shared code has to be
physically present in each task — hence the sync rather than an import path.

What lives here is the machinery that was identical between the specify and
plan verifiers: contract loading, whitespace-insensitive matching, coverage
counting, and the guarded main. What stays in each task's test_outputs.py is
only what differs — which fields gate, what a "task header" looks like, how a
page heading is spelled.

Two invariants this file exists to enforce, both learned by breaking them:

1. reward.json is ALWAYS written, including on failure. A verifier that raises
   makes Harbor score the trial as an *exception* rather than a zero, so the
   failure disappears from the aggregate instead of dragging it down.
2. Nothing runs at import time. The first contract-driven verifier loaded its
   JSON at module level, outside the guard, and a missing file took the whole
   trial down rather than scoring 0.
"""

import json
import pathlib
import re

TESTS = pathlib.Path("/tests")
LOGS = pathlib.Path("/logs/verifier")


def contract() -> dict:
    """Shared domain vocabulary merged with this stage's own additions.

    `contract.common.json` carries pages/routes/entities/fields/formats — the
    things that describe the product and must mean the same at every stage.
    `contract.json` carries only what one stage adds (min_tasks, say). The
    stage file wins on conflict, so a stage can narrow the vocabulary without
    editing the shared one.
    """
    merged: dict = {}
    for name in ("contract.common.json", "contract.json"):
        path = TESTS / name
        if path.exists():
            merged.update(json.loads(path.read_text(encoding="utf-8")))
    return merged


def squash(text: str) -> str:
    """Lowercase with runs of whitespace collapsed — the comparison form."""
    return " ".join(text.lower().split())


def hit(haystack_squashed: str, needle: str) -> bool:
    """Deliberately generous substring match.

    These verifiers are a FLOOR. A false pass is caught by the judges above and
    the render gate below; a false FAIL blocks output that was fine. When in
    doubt this says yes.
    """
    return squash(needle) in haystack_squashed


def coverage(text: str, wanted: list) -> tuple:
    """(fraction present, list of the ones missing). Empty `wanted` scores 1.0."""
    if not wanted:
        return 1.0, []
    low = squash(text)
    missing = [w for w in wanted if not hit(low, w)]
    return round((len(wanted) - len(missing)) / len(wanted), 3), missing


def absent(**extra) -> dict:
    """The reward shape for "the agent produced nothing".

    A shared shape matters: the columns have to line up across stages, and a
    missing deliverable that reports `{}` reads as a pass in the aggregate.
    """
    return {"reward": 0.0, "missing_artifact": 1.0, **extra}


def emit(measure) -> None:
    """Run `measure`, always write reward.json, echo it for the log.

    Values must be numeric — Harbor validates reward.json through a pydantic
    model of floats/ints, and one diagnostic string field fails float_parsing
    and takes the trial down as an exception. Diagnostics go to stdout, which
    Harbor captures to verifier/test-stdout.txt.
    """
    try:
        result = measure()
    except Exception as exc:  # noqa: BLE001 - the trial must never vanish
        print("VERIFIER ERROR:", exc)
        result = {"reward": 0.0, "verifier_error": 1.0}
    result = {k: v for k, v in result.items() if isinstance(v, (int, float))}
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / "reward.json").write_text(json.dumps(result), encoding="utf-8")
    print(json.dumps(result, indent=2))


def headings(text: str, pattern: str) -> list:
    """Regex-extract headings, stripped and de-blanked. Shared because both
    stages parse structure out of markdown the agent wrote."""
    return [h.strip() for h in re.findall(pattern, text, re.M) if h.strip()]
