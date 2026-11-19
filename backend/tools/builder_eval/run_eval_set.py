"""Run the builder eval set live and print the summary tables (operator-run, never CI).

For one intake effort setting it runs every request of ``eval_set.json`` twice:

1. ``defaults``: turn 1 is the request, turn 2 is "defaults" (a request that builds
   on turn 1 stops there);
2. ``scripted``: turn 2 is letter codes chosen from the request's ``plan`` against
   the actual round-one questions, compared with the defaults run of the same
   request (requests with ``plan: null`` are skipped).

Each session is one ``builder_eval_live`` subprocess; at most ``--parallel`` run
at once. It calls a paid model.

Usage (from ``backend/``)::

    uv run python -m tools.builder_eval.run_eval_set --out OUT [--effort default|highest]
        [--critic] [--parallel 8] [--only R3 H1]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from tools.builder_eval import report

__all__ = ["main"]

_HERE: Final = Path(__file__).resolve().parent
_BACKEND: Final = _HERE.parents[1]


async def _session(argv: list[str], log: Path, gate: asyncio.Semaphore) -> int:
    async with gate:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("w", encoding="utf-8") as out:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "tools.builder_eval.builder_eval_live",
                *argv,
                cwd=_BACKEND,
                stdout=out,
                stderr=asyncio.subprocess.STDOUT,
            )
            return await proc.wait()


def _common(args: argparse.Namespace, request: dict[str, Any], out: Path) -> list[str]:
    argv = [
        "--intake",
        "--intake-effort",
        args.effort,
        "--stop-when-built",
        "--model",
        args.model,
        "--critic-model",
        args.model,
        "--id",
        request["id"],
        "--text",
        request["text"],
        "--out",
        str(out),
    ]
    return [*argv, "--critic"] if args.critic else argv


async def _run(args: argparse.Namespace) -> int:
    data = json.loads(args.set.read_text(encoding="utf-8"))
    requests = [r for r in data["requests"] if not args.only or r["id"] in args.only]
    gate = asyncio.Semaphore(args.parallel)
    root = args.out / args.effort
    defaults_dir, scripted_dir = root / "defaults", root / "scripted"
    await asyncio.gather(
        *(
            _session(
                [*_common(args, r, defaults_dir), "--followup", "defaults"],
                defaults_dir / f"{r['id']}.log",
                gate,
            )
            for r in requests
        )
    )
    jobs = []
    for r in requests:
        if not r.get("plan"):
            continue
        plan_file = scripted_dir / f"plan-{r['id']}.json"
        plan_file.parent.mkdir(parents=True, exist_ok=True)
        plan_file.write_text(json.dumps(r["plan"]), encoding="utf-8")
        # Up to 2 answers: the plan's codes, then the second answer ("defaults" unless set).
        second = str(r.get("second_answer") or "defaults")
        jobs.append(
            _session(
                [
                    *_common(args, r, scripted_dir),
                    "--answer-plan",
                    str(plan_file),
                    "--followup",
                    second,
                    "--compare-with",
                    str(defaults_dir / r["id"]),
                ],
                scripted_dir / f"{r['id']}.log",
                gate,
            )
        )
    await asyncio.gather(*jobs)
    expect = frozenset(r["id"] for r in requests if r.get("expect") == "build")
    sets = {
        f"{args.effort}/{d.name}": report.summarize(d, expect)
        for d in (defaults_dir, scripted_dir)
    }
    table = report.render(sets)
    (root / "summary.md").write_text(table + "\n", encoding="utf-8")
    print(table)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--set", type=Path, default=_HERE / "eval_set.json")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--effort", choices=("default", "highest"), default="default")
    parser.add_argument(
        "--model",
        default="eu.anthropic.claude-haiku-5-5",
        help="builder chat model and critic model (default Haiku 5.5, for cost)",
    )
    parser.add_argument("--critic", action="store_true")
    parser.add_argument("--parallel", type=int, default=8)
    parser.add_argument("--only", nargs="*", default=None)
    args = parser.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
