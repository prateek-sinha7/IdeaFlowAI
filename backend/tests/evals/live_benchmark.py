"""LIVE multi-sample benchmark — what's the real pass rate, not just one roll?

Run via ``./run-eval.sh benchmark [s1|s2|example1|both|all] [N]`` (default:
both, N=10), or directly:
``python3.11 -m tests.evals.live_benchmark --scenario s1 --n 10`` from
``backend/``. ``both`` = s1+s2 (cheap, ~3KB fixture each); ``all`` also
includes ``example1`` (real ~124KB fixture — materially more tokens per run,
never included by default).

A single live test (``test_live_s1.py``/``test_live_s2.py``) tells you
pass-or-fail on ONE roll of the dice — Haiku is probabilistic, so one pass
proves little about reliability. This script runs the SAME driver
(``revision_fulfillment/live_driver.py`` — same production prompt surface,
same real model) N times per scenario, sequentially, and reports a pass rate:
how often the current prompt gets Haiku to actually satisfy the instruction,
vs. how often nothing catches a miss (which is exactly what the pipeline-level
S1/S2 evals prove the pipeline itself doesn't do).

Consumes real tokens: N runs x ~2-5k tokens each for s1/s2. ``example1`` is
NOT comparable — its ~124KB real-world fixture has driven a single run to
8.1M input tokens (see ``tests/evals/logs/260727144722-live-example1-5bb95f21``).
``--scenario all`` therefore caps example1 at ``--n-example1`` (default: 3,
see ``_EXPENSIVE_DEFAULT_N``) regardless of ``--n``, and ``--skip-expensive``
drops it from ``all`` entirely — request ``--scenario example1`` by name (or
pass ``--n-example1`` explicitly) to run its full requested count on purpose.

Never wired into any default/CI mode — always an explicit, opt-in invocation.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def _has_llm_credentials() -> bool:
    from app.core.config import settings

    import os

    return bool(
        settings.ANTHROPIC_API_KEY
        or settings.AWS_BEARER_TOKEN_BEDROCK
        or os.environ.get("AWS_ACCESS_KEY_ID")
        or os.environ.get("AWS_PROFILE")
    )


_EXPENSIVE_SCENARIOS = {"example1"}
# example1's fixture (~124KB) drove a single run to 8.1M input tokens
# (tests/evals/logs/260727144722-live-example1-5bb95f21) — an order of
# magnitude past s1/s2. `benchmark all` defaults to a much smaller N for any
# expensive scenario so a stray invocation can't silently repeat that run
# several times; `--skip-expensive` drops them entirely; an explicit
# `--n-example1` (or requesting the scenario directly, e.g. `--scenario
# example1 --n 10`) overrides the cap for a deliberate, informed run.
_EXPENSIVE_DEFAULT_N = 3


async def _run_benchmark(scenario_id: str, n: int) -> None:
    from tests.evals.revision_fulfillment.live_driver import run_live_scenario_once

    print(f"\n=== LIVE BENCHMARK: {scenario_id.upper()} — {n} run(s) ===")
    passed = 0
    errored = 0
    total_in = 0
    total_out = 0
    misses: list[str] = []
    errors: list[str] = []

    for i in range(1, n + 1):
        t0 = time.monotonic()

        def _progress(line: str, _i: int = i) -> None:
            # Prefixed with the run index so interleaved output across a
            # multi-run benchmark stays readable; chunk text truncated (tool
            # calls stay full-length — they're already short + the useful part).
            print(f"  [{_i}/{n}] {line[:200]}")

        result = await run_live_scenario_once(scenario_id, on_event=_progress)
        dt = time.monotonic() - t0
        total_in += result.tokens_in
        total_out += result.tokens_out
        if result.errored:
            status = "ERROR"
            errored += 1
            errors.append(f"run {i}: {result.reason}")
        elif result.passed:
            status = "PASS"
            passed += 1
        else:
            status = "MISS"
            misses.append(f"run {i}: {result.reason}")
        print(
            f"  [{i}/{n}] {status}  ({dt:.1f}s, in={result.tokens_in} "
            f"out={result.tokens_out})"
            + ("" if result.passed else f"  — {result.reason}")
        )
        print(f"  [{i}/{n}] run folder: {result.run_dir}")

    # Errored runs (infra failures — auth, network, etc.) never got a real
    # model attempt, so they'd silently deflate/pollute a rate meant to
    # measure prompt quality. Excluded from the rate denominator; reported
    # separately instead of being folded into "misses".
    scored = n - errored
    rate = (passed / scored) * 100 if scored else 0.0
    print(f"\n  pass rate: {passed}/{scored} ({rate:.0f}%)" + (
        f"  [{errored} run(s) excluded — infra error, not a model attempt]"
        if errored else ""
    ))
    print(f"  tokens: in={total_in} out={total_out} total={total_in + total_out}")
    if misses:
        print("  miss detail:")
        for m in misses:
            print(f"    - {m}")
    if errors:
        print("  error detail (infrastructure — investigate separately, not a prompt issue):")
        for e in errors:
            print(f"    - {e}")
    print(f"=== END {scenario_id.upper()} ===\n")


async def _main_async(scenarios: list[str], n_by_scenario: dict[str, int]) -> None:
    for scenario_id in scenarios:
        await _run_benchmark(scenario_id, n_by_scenario[scenario_id])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario", choices=["s1", "s2", "example1", "both", "all"], default="both",
        help="which scenario to benchmark (default: both = s1+s2)",
    )
    parser.add_argument(
        "--n", type=int, default=10,
        help="number of live samples per scenario (default: 10)",
    )
    parser.add_argument(
        "--skip-expensive", action="store_true",
        help="drop expensive scenarios (currently: example1) from --scenario all",
    )
    parser.add_argument(
        "--n-example1", type=int, default=None,
        help=(
            f"override example1's sample count explicitly (default when reached "
            f"via 'all': capped at {_EXPENSIVE_DEFAULT_N} regardless of --n, since "
            f"one example1 run can cost millions of tokens — see "
            f"_EXPENSIVE_DEFAULT_N). Has no effect with --skip-expensive."
        ),
    )
    args = parser.parse_args()

    if not _has_llm_credentials():
        print("No LLM credentials configured — set ANTHROPIC_API_KEY or AWS creds.")
        raise SystemExit(1)

    # No pytest ``runs_root`` fixture outside the test suite — RunSandbox would
    # otherwise default to settings.RUNS_ROOT (/app/runs, not writable locally,
    # per CLAUDE.md). Point it at a throwaway temp dir for this process only.
    import tempfile

    from app.core.config import settings

    tmp_runs_root = tempfile.mkdtemp(prefix="live-benchmark-runs-")
    settings.RUNS_ROOT = tmp_runs_root

    if args.scenario == "both":
        scenarios = ["s1", "s2"]
    elif args.scenario == "all":
        scenarios = ["s1", "s2"] if args.skip_expensive else ["s1", "s2", "example1"]
    else:
        scenarios = [args.scenario]

    n_by_scenario: dict[str, int] = {}
    for scenario_id in scenarios:
        if scenario_id in _EXPENSIVE_SCENARIOS and args.scenario == "all":
            # Reached via the broad "all" alias, not requested by name — cap
            # unless the caller explicitly overrode it via --n-example1.
            n_by_scenario[scenario_id] = (
                args.n_example1 if args.n_example1 is not None else min(args.n, _EXPENSIVE_DEFAULT_N)
            )
        elif scenario_id == "example1" and args.n_example1 is not None:
            n_by_scenario[scenario_id] = args.n_example1
        else:
            n_by_scenario[scenario_id] = args.n

    capped = [
        s for s in scenarios
        if s in _EXPENSIVE_SCENARIOS and args.scenario == "all" and args.n_example1 is None
        and args.n > _EXPENSIVE_DEFAULT_N
    ]
    print(
        f">>> LIVE benchmark: {[(s, n_by_scenario[s]) for s in scenarios]} — "
        f"this consumes real LLM tokens."
    )
    if capped:
        print(
            f">>> {capped} capped at N={_EXPENSIVE_DEFAULT_N} (requested {args.n}) — "
            f"expensive scenario reached via 'all'. Use --scenario example1 --n {args.n} "
            f"or --n-example1 {args.n} to run the full count deliberately."
        )
    asyncio.run(_main_async(scenarios, n_by_scenario))


if __name__ == "__main__":
    main()
