"""Dispatch: one row -> agent -> response -> artifact. The only module here
that touches the agent runtime.

A config names an ordered chain of stages (`{stage_name: agent_id}`) over one
dataset. `run()` drives either the whole chain (`stage=None`) or one isolated
stage (`stage=X`), optionally seeded from a stored upstream run rather than
re-sampling everything before it (R-01).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Literal

import yaml

import agents.factory
import agents.loader
import app.agents.model_factory
import app.agents.sandbox

from evals.minimal import store

HERE = Path(__file__).resolve().parent
USER_ID = "eval-minimal"

# Evals pin Mistral for BOTH tracks — the pipeline dispatch here and the judge
# (judge.py) — so a run's cost and behaviour never depend on whatever the
# ambient ANTHROPIC_API_KEY/Bedrock chain happens to resolve to on this
# machine. Override per call (`run(..., provider="anthropic")`) from code when
# you deliberately want a different provider under test.
DEFAULT_PROVIDER = "mistral"

Origin = Literal["dispatched", "replayed", "seeded"]


def run(
    config: str | Path | dict,
    *,
    stage: str | None = None,
    from_run: str | None = None,
    into: str | None = None,
    repeats: int = 1,
    provider: str | None = DEFAULT_PROVIDER,
    model: str | None = None,
) -> str:
    """Run a config's dataset through one stage or the whole chain.

    `stage=None` runs every configured stage in order, per row, sharing one
    sandbox per row across the chain (as production does). `stage=X` runs
    only X; if X is not the chain's first stage, `from_run` must name a run
    that already produced the immediately-prior stage, whose stored per-row
    artifacts reseed a fresh sandbox for this dispatch.

    `into=RUN_ID` appends this stage to an EXISTING run instead of minting a
    new one, so a chain driven one stage at a time still lands in a single
    folder with one report row. The storage was already shaped for this —
    every kind file is keyed by phase — so appending is a merge, not a
    special case. `from_run` then defaults to that same run: the natural
    reading of "run the next stage of THIS run" is to seed from what this run
    already produced.
    """
    resolved = _load_config(config)
    order: list[str] = resolved["order"]
    stage_defs: dict[str, dict] = resolved["agents"]
    stages_to_run = [stage] if stage is not None else order
    for name in stages_to_run:
        if name not in stage_defs:
            raise ValueError(f"config has no stage {name!r}; known stages: {order}")

    rows = _load_dataset(resolved["dataset"])
    if into:
        run_id = into
        from_run = from_run or into
        _merge_config(run_id, resolved, stage=stage, from_run=from_run, repeats=repeats)
    else:
        run_id = store.new_run_id(resolved.get("dataset_id", "eval"))
        store.snapshot_config(run_id, {**resolved, "stage": stage, "from_run": from_run,
                                        "repeats": repeats})

    seed_stage = _preceding_stage(order, stages_to_run[0]) if stage is not None else None
    upstream_artifacts = (
        _upstream_artifacts(from_run, seed_stage) if seed_stage is not None else {}
    )

    single = len(rows) == 1 and repeats == 1

    # Every completed stage's TEXT output, per row — the other half of the
    # chain. Sandbox files alone are not enough: specify/plan/analyze are
    # text-only agents (`tools: []`) that write nothing to disk, so a chain
    # seeded purely from `artifacts` handed them nothing and every stage ran
    # on the bare brief. Runs 260731-104736 and -113247 both show
    # `specify artifacts=[]` followed by `plan artifacts=[]`.
    completed: dict[str, dict[tuple, str]] = _prior_outputs(run_id, order, stages_to_run[0]) \
        if into else {}

    total_dispatches = len(rows) * repeats
    for name in stages_to_run:
        stage_def = stage_defs[name]
        stage_rows = []
        _report(f"[{name}] dispatching {total_dispatches} row(s) via {stage_def['agent_id']}")
        for row in rows:
            for repeat in range(repeats):
                sandbox_run_id = f"{run_id}-{row['id']}" if repeats == 1 else (
                    f"{run_id}-{row['id']}-r{repeat}"
                )
                # Sandbox FILES, not just context text. prototype-build's
                # AGENT.md opens with `read_file("spec.md")`; seeded with
                # nothing it found nothing and wrote its OWN spec (run
                # 260731-133221: specify/plan/analyze all wrote 0 files, build
                # then produced a spec.md 0.87-similar to specify's — a
                # paraphrase it then built from). The stage was scoring its
                # own invention, not the pipeline's. Production's engine
                # materialises upstream artifacts to disk before dispatch;
                # `seed_as` in the config is where each stage's output lands.
                seed_files = dict(upstream_artifacts.get((row["id"], repeat), {}))
                seed_files.update(
                    _canonical_seeds(stage_defs, order, completed, (row["id"], repeat), name)
                )
                message = _compose_message(
                    row["prompt"], stage_def["agent_id"], stage_defs, order, completed,
                    (row["id"], repeat),
                )
                index = len(stage_rows) + 1
                _report(f"[{name}] ({index}/{total_dispatches}) {row['id']} repeat {repeat} — dispatching…")
                record = _dispatch_row(
                    row, agent_id=stage_def["agent_id"], sandbox_run_id=sandbox_run_id,
                    seed_files=seed_files, deliverable=stage_def.get("deliverable"),
                    repeat=repeat, repeats=repeats, run_id=run_id, stage=name,
                    provider=provider, model=model, single=single, message=message,
                )
                stage_rows.append(record)
                store.write_phase(run_id, "run", name, stage_rows)
                status = "ERROR: " + record["error_reason"] if record["errored"] else "ok"
                tokens = f"in={record['tokens_in']} out={record['tokens_out']}"
                _report(f"[{name}] ({index}/{total_dispatches}) {row['id']} repeat {repeat} — {status} ({tokens})")
        # the next configured stage (when running the whole chain) reseeds from
        # what THIS stage's rows just wrote, keyed by (row id, repeat) so
        # parallel repeats never bleed into each other downstream
        upstream_artifacts = {(r["row_id"], r["repeat"]): r["artifacts"] for r in stage_rows}
        completed[name] = {(r["row_id"], r["repeat"]): r["response"] for r in stage_rows}

    return run_id


def _canonical_seeds(
    stage_defs: dict, order: list[str], completed: dict[str, dict[tuple, str]],
    key: tuple, upto: str,
) -> dict[str, str]:
    """Upstream stage output written under the filename the next agent reads.

    Driven by each stage's `seed_as:` in the config rather than by hardcoded
    agent knowledge here — the AGENT.md files say which paths they open, and
    the config is where that mapping belongs. Every prior stage is included,
    not just the immediately preceding one, because production shares ONE
    sandbox across the whole chain: build reads `spec.md` (from specify) long
    after plan has run.
    """
    files: dict[str, str] = {}
    for prior in order:
        if prior == upto:
            break
        path = (stage_defs.get(prior) or {}).get("seed_as")
        text = (completed.get(prior) or {}).get(key)
        if path and text:
            files[str(path)] = text
    return files


def _prior_outputs(run_id: str, order: list[str], upto: str) -> dict[str, dict[tuple, str]]:
    """Every already-stored stage output for this run, for `--into` chaining.

    A stage appended to an existing run has no in-memory history to consume,
    so it is read back off disk — the same text a whole-chain run would have
    been holding at that point.
    """
    outputs: dict[str, dict[tuple, str]] = {}
    for name in order:
        if name == upto:
            break
        try:
            rows = store.read_phase(run_id, "run", name)
        except FileNotFoundError:
            continue
        outputs[name] = {(r["row_id"], r["repeat"]): r.get("response") or "" for r in rows}
    return outputs


def _compose_message(
    brief: str, agent_id: str, stage_defs: dict, order: list[str],
    completed: dict[str, dict[tuple, str]], key: tuple,
) -> str:
    """The brief plus whatever upstream output THIS agent declares it consumes.

    Routing is production's own contract — an upstream agent is included iff
    its `produces` intersects this agent's `consumes` (agents/loader.py's
    AgentSpec; the same rule engine.py's `_filter_consumed_outputs` applies).
    Reading the contract off the real AGENT.md keeps the eval measuring what
    production routes, rather than a second opinion about what it should.
    """
    consumes = set(getattr(agents.loader.load_agent_spec(agent_id), "consumes", []) or [])
    if not consumes:
        return brief
    blocks = []
    for name in order:
        if name not in completed:
            continue
        upstream_id = (stage_defs.get(name) or {}).get("agent_id")
        if not upstream_id:
            continue
        produces = set(getattr(agents.loader.load_agent_spec(upstream_id), "produces", []) or [])
        text = completed[name].get(key)
        if produces & consumes and text:
            blocks.append(f"=== OUTPUT FROM {upstream_id} ===\n{text}\n=== END ===")
    return "\n\n".join([brief, *blocks]) if blocks else brief


def _merge_config(run_id: str, resolved: dict, *, stage, from_run, repeats) -> None:
    """Fold this invocation's config into the run's existing snapshot.

    Appending a stage must not erase the stages already recorded: `_advise`
    and the report both resolve an agent_id out of this snapshot, so a
    stage-by-stage chain would lose the ability to explain its own earlier
    phases if the last invocation simply overwrote it. `agents` and `order`
    accumulate; everything else takes the current invocation's value.
    """
    try:
        stored = store.read_config(run_id)
    except FileNotFoundError:
        stored = {}
    order = list(stored.get("order") or [])
    order += [name for name in (resolved.get("order") or []) if name not in order]
    store.snapshot_config(run_id, {
        **stored, **resolved,
        "agents": {**(stored.get("agents") or {}), **(resolved.get("agents") or {})},
        "order": order,
        "stage": stage, "from_run": from_run, "repeats": repeats,
    })


def _report(message: str) -> None:
    """Progress to stderr, unbuffered — visible even when a caller (eval.sh,
    `X=$(...)`) captures stdout, since `$()` only ever captures stdout."""
    print(message, file=sys.stderr, flush=True)


def compose_agent_prompt(agent_id: str, ctx: "agents.factory.AgentContext | None" = None) -> str:
    """The REAL composed system prompt for an agent — same call `create_runner`
    makes. Reused by `cli.py`'s advisor so advice targets the actual current
    prompt, not a stale mirror."""
    ctx = ctx or agents.factory.AgentContext(user_request="", user_id=USER_ID)
    spec = agents.loader.load_agent_spec(agent_id)
    custom_tools, exclude_builtin = agents.factory._resolve_runner_tools(spec, ctx)
    return agents.factory._compose_system_prompt(spec, ctx, no_tools=exclude_builtin and not custom_tools)


def _artifact_suffix(row_id: str, repeat: int, *, repeats: int, single: bool) -> str:
    """Empty for the common one-row-one-repeat case (`artifacts/build.html`);
    disambiguated by row id (and repeat, if >1) for a multi-row dataset."""
    if single:
        return ""
    suffix = f"-{row_id}"
    return suffix if repeats == 1 else f"{suffix}-r{repeat}"


def _artifact_ext(response: str, deliverable: str | None) -> str:
    """`.html` for an HTML deliverable/response, `.md` for everything else."""
    if deliverable and deliverable.lower().endswith((".html", ".htm")):
        return "html"
    if response.strip().lower().startswith(("<!doctype html", "<html")):
        return "html"
    return "md"


def _dispatch_row(
    row: dict, *, agent_id: str, sandbox_run_id: str, seed_files: dict[str, str],
    deliverable: str | None, repeat: int, repeats: int, run_id: str, stage: str,
    provider: str | None, model: str | None, single: bool, message: str | None = None,
) -> dict:
    """Dispatch one row through `create_runner`, or seed it with a fixture answer.

    A dataset row carrying `seed_response` is never dispatched — zero tokens,
    `origin: seeded` — so a fixture row's absence of cost is never mistaken
    for under-reporting (R-04).
    """
    if "seed_response" in row:
        response = row["seed_response"]
        store.write_artifact(
            run_id, stage, _artifact_ext(response, deliverable), response,
            suffix=_artifact_suffix(row["id"], repeat, repeats=repeats, single=single),
        )
        return {
            "row_id": row["id"], "repeat": repeat, "agent_id": agent_id,
            "prompt": row["prompt"], "response": response,
            "tokens_in": 0, "tokens_out": 0, "model_id": "seeded",
            "system_prompt_hash": None, "origin": "seeded",
            "errored": False, "error_reason": None, "artifacts": dict(seed_files),
        }
    return asyncio.run(
        _dispatch_row_async(
            row, agent_id=agent_id, sandbox_run_id=sandbox_run_id,
            seed_files=seed_files, deliverable=deliverable, repeat=repeat, repeats=repeats,
            run_id=run_id, stage=stage, provider=provider, model=model, single=single,
            message=message,
        )
    )


async def _dispatch_row_async(
    row: dict, *, agent_id: str, sandbox_run_id: str, seed_files: dict[str, str],
    deliverable: str | None, repeat: int, repeats: int, run_id: str, stage: str,
    provider: str | None, model: str | None, single: bool, message: str | None = None,
) -> dict:
    """The real dispatch: build a sandbox, run the agent, capture the response.

    Preserves the production invariants `evals.grading.model.dispatch` also
    preserves: one sandbox per row (keyed by `sandbox_run_id`), the
    `{sandbox_run_id}:{agent_id}` thread id, and empty-response-is-an-error.
    """
    sandbox = app.agents.sandbox.RunSandbox(USER_ID, sandbox_run_id)
    sandbox.ensure()
    for relpath, content in seed_files.items():
        sandbox.write(relpath, content)

    # provider is not None -> a built model INSTANCE (bypasses the ambient
    # Anthropic/Bedrock chain entirely); else the raw model id/None, resolved
    # by build_model's own chain inside create_runner. Mirrors
    # evals.grading.model.dispatch._resolve_model.
    resolved_model = (
        app.agents.model_factory.build_model(model, provider=provider)
        if provider is not None else model
    )
    dispatch_message = message or row["prompt"]
    ctx = agents.factory.AgentContext(
        user_request=dispatch_message, user_id=USER_ID, run_id=sandbox_run_id,
        model=resolved_model,
    )
    system_prompt = compose_agent_prompt(agent_id, ctx)
    runner = agents.factory.create_runner(
        agent_id, ctx, thread_id=f"{sandbox_run_id}:{agent_id}", run_sandbox=sandbox,
    )
    resolved_model_id = getattr(runner, "model_id", None) or "unknown"

    streamed: list[str] = []
    log_lines: list[str] = []
    tokens_in = tokens_out = 0
    error_reason: str | None = None

    async for event in runner.astream_events(dispatch_message):
        etype = event.get("type")
        if etype == "chunk":
            streamed.append(event["chunk"])
            log_lines.append(event["chunk"])
        elif etype == "usage":
            tokens_in += event.get("input_tokens", 0)
            tokens_out += event.get("output_tokens", 0)
        elif etype == "error":
            error_reason = str(event.get("error", "")) or "(no error detail)"
            log_lines.append(f"\n>>> RUNNER ERROR: {error_reason}\n")

    response = "".join(streamed)
    errored = error_reason is not None

    if deliverable and not errored:
        content = sandbox.read(deliverable)
        if content is not None:
            response = content

    if not errored and not response.strip():
        errored = True
        error_reason = "empty response: the agent produced no text"

    # ONE log file per phase (not per row): every row/repeat's transcript is
    # appended, header first, so the whole phase reads as one document.
    store.append_log(run_id, stage, (
        f"=== {row['id']} (repeat {repeat}) — {agent_id} — "
        f"{time.strftime('%Y-%m-%d %H:%M:%S')} ===\n"
        f"{''.join(log_lines)}\n"
        f"--- result: {'ERROR' if errored else 'CAPTURED'} — "
        f"tokens in={tokens_in} out={tokens_out} ---\n\n"
    ))
    store.write_artifact(
        run_id, stage, _artifact_ext(response, deliverable), response,
        suffix=_artifact_suffix(row["id"], repeat, repeats=repeats, single=single),
    )
    # The DISPATCH call, into the same `logs/calls.jsonl` the judge and advisor
    # already append to. It was missing: a 5-stage run logged 10 records (5
    # judge + 5 advise) and zero dispatches, so the one prompt you actually
    # want to inspect after a prompt-override experiment was the one prompt
    # not written down. `system_prompt_hash` on the run row proves WHETHER the
    # prompt changed; only this proves WHAT was sent.
    store.log_call(run_id, stage, {
        "kind": "dispatch", "stage": stage, "row_id": row["id"], "repeat": repeat,
        "agent_id": agent_id, "model": resolved_model_id,
        "system_prompt": system_prompt,
        "system_prompt_hash": _hash_prompt(system_prompt),
        "prompt": dispatch_message, "raw": response,
        "tokens_in": tokens_in, "tokens_out": tokens_out,
        "error": error_reason,
    })

    return {
        "row_id": row["id"], "repeat": repeat, "agent_id": agent_id,
        "prompt": row["prompt"], "response": response,
        "tokens_in": tokens_in, "tokens_out": tokens_out, "model_id": resolved_model_id,
        "system_prompt_hash": _hash_prompt(system_prompt), "origin": "dispatched",
        "errored": errored, "error_reason": error_reason,
        "artifacts": _snapshot_sandbox(sandbox),
    }


def _snapshot_sandbox(sandbox) -> dict[str, str]:
    """Every text file the agent wrote this stage, keyed by its sandbox-relative path.

    Captured so an isolated re-run of the NEXT stage can reseed without the
    ephemeral sandbox (which is TTL-swept) — the chain's own memory of itself.
    """
    files: dict[str, str] = {}
    if not sandbox.root.exists():
        return files
    for path in sandbox.root.rglob("*"):
        if path.is_file():
            try:
                files[str(path.relative_to(sandbox.root))] = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
    return files


def _hash_prompt(system_prompt: str) -> str:
    return f"sha256:{hashlib.sha256(system_prompt.encode('utf-8')).hexdigest()}"


def _preceding_stage(order: list[str], stage: str) -> str | None:
    index = order.index(stage)
    return order[index - 1] if index > 0 else None


def _upstream_artifacts(
    from_run: str | None, seed_stage: str,
) -> dict[tuple[str, int], dict[str, str]]:
    if from_run is None:
        raise ValueError(f"--from is required to isolate a stage after {seed_stage!r}")
    rows = store.read_phase(from_run, "run", seed_stage)
    return {(row["row_id"], row["repeat"]): row.get("artifacts", {}) for row in rows}


def _load_config(config: str | Path | dict) -> dict:
    if isinstance(config, dict):
        return config
    path = Path(config)
    if not path.is_absolute():
        path = HERE / path
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_dataset(dataset: str) -> list[dict]:
    path = Path(dataset)
    if not path.is_absolute():
        path = HERE / "datasets" / dataset
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["rows"]
