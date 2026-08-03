"""Build-readiness floor for `specify`. Stage logic only, and stage logic is
SCENARIO-INDEPENDENT: nothing here names a page, a route or a product. The
vocabulary arrives from the scenario contract that sync_common.sh copied in, so
this one file grades warehouse-slotting and mission-control alike. Contract
loading, matching, coverage and the guarded main live in verifier.py.

`specify` emits prose, so there is no render gate; in `evals/minimal` its
checks column reads `checks n/a`. What IS checkable is whether the spec carries
everything the build agent needs BY NAME.

The gating split is the one thing here worth reading, and it was found
empirically rather than assumed:

  NOUNS gate. Pages, routes, entity names, field names and code formats are
  stated verbatim when covered, so substring matching is reliable — all five
  scored 1.0 on the reference spec.

  VERBS do not. Interactions get paraphrased. The reference spec scored 0.5 on
  them because the contract said "filter by aisle" / "sku search" while the
  spec said "Filterable by aisle" / "SKU text search" — the same interactions,
  fully specified, marked missing. Gating on verb phrases produces false
  failures, so interactions are measured and reported, never gating.

Judging whether an interaction is properly specified needs a model; that is
`spec_judge.py`, not this file.
"""

import pathlib

import verifier

GATING = ("pages", "routes", "entities", "fields", "formats")
ADVISORY = ("interactions",)
SPEC = pathlib.Path("/app/spec.md")


def measure() -> dict:
    if not SPEC.exists():
        return verifier.absent(build_ready=0.0, pages=0.0, routes=0.0,
                                entities=0.0, fields=0.0, formats=0.0,
                                interactions=0.0, words=0)

    text = SPEC.read_text(encoding="utf-8")
    contract = verifier.contract()

    scores, missing = {}, []
    for key in GATING + ADVISORY:
        fraction, absent_items = verifier.coverage(text, contract.get(key) or [])
        scores[key] = fraction
        if key in GATING:
            missing += [f"{key}:{m}" for m in absent_items]

    print("MISSING:", ", ".join(missing) or "(none)")
    return {
        "reward": 0.0 if missing else 1.0,
        "build_ready": 0.0 if missing else 1.0,
        **scores,
        "missing_count": len(missing),
        "words": len(text.split()),
        "missing_artifact": 0.0,
    }


if __name__ == "__main__":
    verifier.emit(measure)
