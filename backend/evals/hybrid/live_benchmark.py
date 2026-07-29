"""LIVE multi-sample benchmark — what's the real pass rate, not just one roll?

Run via ``./evals/hybrid/eval.sh benchmark [<scenario-id>|cheap|all] [N]`` (default:
cheap, N=10), or directly:
``python3.11 -m evals.hybrid.live_benchmark --scenario prototype_multi_issue_repair --n 5``
from ``backend/``. ``cheap`` = every discovered scenario NOT marked
``expensive: true`` in its YAML; ``all`` also includes scenarios marked
``expensive`` (materially more tokens per run, never included by default).

A single live test (``test_live.py``) tells you pass-or-fail on ONE roll of
the dice — Haiku is probabilistic, so one pass proves little about
reliability. This script runs the SAME driver
(``common/live_scenario.py`` — same production prompt surface, same real
model) N times per scenario, sequentially, and reports a pass rate: how
often the current prompt gets the model to actually satisfy the
instruction, vs. how often nothing catches a miss.

Scenarios are discovered across EVERY pipeline's eval coverage (any
``workflow/<domain>/<variant>/scenarios/*.yaml``), not just one — see
``common/scenario_discovery.py``. Scenario ids are globally unique across
every pipeline (enforced by ``discover_all_scenarios``), so a scenario is
always referred to the SAME way everywhere: by its yaml file's ``id``
(equivalently, its filename stem) — no per-pipeline prefix or lookup table
needed as more pipelines/scenarios are added.

Consumes real tokens: N runs x tokens per scenario (varies with fixture size
and how many issues a single turn has to find and fix — see each scenario's
own YAML for its ``benchmark.default_n``). Scenarios can mark themselves
``expensive`` in their YAML for fixtures materially more costly than normal.
``--scenario all`` caps any expensive scenario at its YAML-declared
``default_n`` regardless of ``--n``, and ``--skip-expensive`` drops all such
scenarios from ``all`` entirely — request the scenario by name (or pass
``--n-override <id>=<n>``) to run its full requested count on purpose.

Adding a new scenario (a new ``workflow/<domain>/<variant>/scenarios/<id>.yaml``,
with a sibling ``checkers.py`` in its phase folder) makes it show up here
automatically — no code change needed in this file.

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

from evals.hybrid.common.scenario_discovery import discover_all_scenarios  # noqa: E402

ALL_SCENARIOS = discover_all_scenarios()


def _has_llm_credentials() -> bool:
    from app.core.config import settings

    import os

    return bool(
        settings.ANTHROPIC_API_KEY
        or settings.AWS_BEARER_TOKEN_BEDROCK
        or os.environ.get("AWS_ACCESS_KEY_ID")
        or os.environ.get("AWS_PROFILE")
        or settings.MISTRAL_API_KEY
    )


def _parse_n_overrides(raw: list[str]) -> dict[str, int]:
    overrides: dict[str, int] = {}
    for item in raw:
        if "=" not in item:
            raise SystemExit(f"--n-override expects <scenario-id>=<n>, got: {item!r}")
        scenario_id, _, n_str = item.partition("=")
        if scenario_id not in ALL_SCENARIOS:
            raise SystemExit(
                f"--n-override: unknown scenario '{scenario_id}' "
                f"(known: {sorted(ALL_SCENARIOS)})"
            )
        overrides[scenario_id] = int(n_str)
    return overrides


async def _run_benchmark(
    scenario_id: str,
    n: int,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> None:
    from evals.hybrid.common.live_scenario import run_live_scenario_once

    scenario = ALL_SCENARIOS[scenario_id]
    provider_note = f" [provider={provider} model={model or '(default)'}]" if provider else ""
    print(f"\n=== LIVE BENCHMARK: {scenario_id.upper()} — {n} run(s){provider_note} ===")
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

        result = await run_live_scenario_once(
            scenario, on_event=_progress, provider=provider, model=model
        )
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


async def _main_async(
    scenarios: list[str],
    n_by_scenario: dict[str, int],
    *,
    provider: str | None = None,
    model: str | None = None,
) -> None:
    for scenario_id in scenarios:
        await _run_benchmark(
            scenario_id, n_by_scenario[scenario_id], provider=provider, model=model
        )


def main() -> None:
    scenario_ids = sorted(ALL_SCENARIOS)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario", choices=[*scenario_ids, "cheap", "all"], default="cheap",
        help=(
            "which scenario to benchmark (default: cheap = every discovered "
            "scenario not marked 'expensive: true')"
        ),
    )
    parser.add_argument(
        "--n", type=int, default=10,
        help="number of live samples per scenario (default: 10)",
    )
    parser.add_argument(
        "--skip-expensive", action="store_true",
        help=(
            "drop scenarios marked 'expensive: true' in their YAML "
            f"(currently: {sorted(s for s in scenario_ids if ALL_SCENARIOS[s].expensive)}) "
            "from --scenario all"
        ),
    )
    parser.add_argument(
        "--n-override", action="append", default=[], metavar="ID=N",
        help=(
            "override a specific scenario's sample count, e.g. "
            "--n-override example1=10 (repeatable). Overrides the YAML "
            "default_n cap applied when that scenario is reached via 'all'."
        ),
    )
    parser.add_argument(
        "--provider", choices=["mistral"], default=None,
        help=(
            "force a specific provider for this run instead of the default "
            "Haiku/Bedrock path. Forces "
            "build_model(provider=...), which works even when ANTHROPIC_API_KEY "
            "is set. 'mistral' uses Mistral's free tier — NOTE: free-tier "
            "inputs/outputs are used for Mistral's model training BY DEFAULT "
            "unless you opt out at console.mistral.ai (Admin Console > Privacy)."
        ),
    )
    parser.add_argument(
        "--model", default=None,
        help=(
            "model id override, used together with --provider (e.g. "
            "--provider mistral --model mistral-small-latest). Defaults to "
            "the provider's own default model id when omitted."
        ),
    )
    args = parser.parse_args()
    n_overrides = _parse_n_overrides(args.n_override)

    if not _has_llm_credentials():
        print(
            "No LLM credentials configured — set ANTHROPIC_API_KEY, AWS creds, "
            "or MISTRAL_API_KEY."
        )
        raise SystemExit(1)

    # No pytest ``runs_root`` fixture outside the test suite — RunSandbox would
    # otherwise default to settings.RUNS_ROOT (/app/runs, not writable locally,
    # per CLAUDE.md). Point it at a throwaway temp dir for this process only.
    import tempfile

    from app.core.config import settings

    tmp_runs_root = tempfile.mkdtemp(prefix="live-benchmark-runs-")
    settings.RUNS_ROOT = tmp_runs_root

    if args.scenario == "cheap":
        scenarios = [s for s in scenario_ids if not ALL_SCENARIOS[s].expensive]
    elif args.scenario == "all":
        scenarios = [
            s for s in scenario_ids
            if not (args.skip_expensive and ALL_SCENARIOS[s].expensive)
        ]
    else:
        scenarios = [args.scenario]

    n_by_scenario: dict[str, int] = {}
    for scenario_id in scenarios:
        spec = ALL_SCENARIOS[scenario_id]
        if scenario_id in n_overrides:
            n_by_scenario[scenario_id] = n_overrides[scenario_id]
        elif spec.expensive and args.scenario == "all":
            # Reached via the broad "all" alias, not requested by name — cap
            # at the YAML-declared default rather than the (possibly much
            # larger) --n, unless explicitly overridden above.
            n_by_scenario[scenario_id] = min(args.n, spec.default_n)
        else:
            n_by_scenario[scenario_id] = args.n

    capped = [
        s for s in scenarios
        if ALL_SCENARIOS[s].expensive and args.scenario == "all"
        and s not in n_overrides and args.n > ALL_SCENARIOS[s].default_n
    ]
    print(
        f">>> LIVE benchmark: {[(s, n_by_scenario[s]) for s in scenarios]} — "
        f"this consumes real LLM tokens."
    )
    if capped:
        print(
            f">>> {capped} capped at their YAML default_n (requested {args.n}) — "
            f"expensive scenario reached via 'all'. Use --scenario <id> --n {args.n} "
            f"or --n-override <id>={args.n} to run the full count deliberately."
        )
    asyncio.run(
        _main_async(scenarios, n_by_scenario, provider=args.provider, model=args.model)
    )


if __name__ == "__main__":
    main()
