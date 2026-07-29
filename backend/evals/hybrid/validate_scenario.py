"""Offline, 0-token sanity check for a live scenario (opt-out safety net).

Run via ``./evals/hybrid/eval.sh <scenario-id>`` WITHOUT ``--live`` (that's the whole
point — this is what runs by default so a bare scenario name never
accidentally reaches a real model), or directly:
``python3.11 -m evals.hybrid.validate_scenario prototype_multi_issue_repair``
from ``backend/``.

Confirms the scenario's YAML loads, its fixture files exist and are
readable, and — the actual signal, not just plumbing — that its checker
correctly reports the RAW (unfixed) fixture as NOT satisfying the
instruction. That last part matters: a scenario whose checker already
passes on the untouched fixture can never demonstrate a real fix, which
means either the fixture or the checker has a bug, and a ``--live`` run
against it would be spending real tokens to test nothing.

Scenarios are discovered across EVERY pipeline's eval coverage (any
``workflow/<domain>/<variant>/scenarios/*.yaml``) — see
``common/scenario_discovery.py``.

Never calls a model. Never wired into any default/CI mode.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: validate_scenario.py <scenario-id>", file=sys.stderr)
        raise SystemExit(2)

    scenario_id = sys.argv[1]
    from evals.hybrid.common.scenario_discovery import discover_all_scenarios

    all_scenarios = discover_all_scenarios()

    if scenario_id not in all_scenarios:
        print(
            f"Unknown scenario '{scenario_id}' (known: {sorted(all_scenarios)})",
            file=sys.stderr,
        )
        raise SystemExit(1)

    scenario = all_scenarios[scenario_id]
    print(f">>> LOCAL validation of '{scenario_id}' — 0 tokens, no model call.")
    print(f"    instruction: {scenario.instruction[:200]}")
    print(
        f"    fixture: {len(scenario.html)} chars html, "
        f"design_md={'yes' if scenario.design_md else 'no'}"
    )

    passed, reason = scenario.checker(scenario.html)
    if passed:
        print(
            "    UNEXPECTED: the checker already PASSES on the raw, unfixed "
            "fixture — this scenario can never demonstrate a real fix "
            "(fixture or checker bug — investigate before trusting a --live "
            "run against it)."
        )
        raise SystemExit(1)

    print(f"    OK: checker correctly flags the raw fixture as unmet — {reason}")
    print(">>> Scenario is wired correctly. Pass --live to run it against the real model:")
    print(f"      ./evals/hybrid/eval.sh {scenario_id} --live")


if __name__ == "__main__":
    main()
