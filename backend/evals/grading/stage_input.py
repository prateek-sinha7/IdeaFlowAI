"""Build each row's prompt for one stage. Pure — no I/O, no model calls.

Owns the five input shapes and the skip policy. This is where a chained
workflow's fan-in join lives, and where a silent row drop would make row counts
stop matching across stages.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from evals.grading import hooks

PLACEHOLDER_PATTERN = re.compile(r"\{([^{}\s]+)\}")
WORKFLOW_FILENAME = "workflow.yaml"


# A row withheld because it is a NEGATIVE TEST — the eval working, not a
# problem. Named so the reporting layer can classify it without matching prose.
EXPECTED_FAIL_SKIP = "expect: fail row is not propagated to a downstream stage"


@dataclass(frozen=True)
class StageInput:
    """One row, ready to dispatch — or marked to skip, with the reason."""

    row_id: str
    prompt: str
    seed_files: dict[str, str] = field(default_factory=dict)
    deliverable_file: str | None = None
    industry: str = ""
    tags: list[str] = field(default_factory=list)
    expect: str = "pass"
    upstream_chain: list[dict] = field(default_factory=list)
    skip_reason: str | None = None


def build_stage_inputs(
    stage: dict,
    *,
    dataset: dict,
    upstream_outputs: dict[str, dict],
    config_dir: Path | None = None,
) -> list[StageInput]:
    """Compose one StageInput per row for this stage.

    The five shapes:

    - `source: dataset` -> one input per dataset row, prompt verbatim.
    - `source: upstream` with one `from:` -> that upstream's response verbatim.
    - `source: upstream` with several `from:` + `template:` -> FAN-IN, an INNER
      JOIN on the stable row id. `len(from) > 1` REQUIRES `template` (error if
      absent — never concatenate in list order). `{agent-id}` placeholders are
      validated against `from:` at load time. A row missing from ANY upstream
      gets a StageInput with `skip_reason`, never a silent drop.
    - `adapter: ./file.py:func` -> applied AFTER template composition.
      Signature `(row: dict, upstreams: dict[str, str]) -> str`.
    - `seed_files: {filename: upstream_agent_id | ./file.py:func}` -> resolved
      per row to that upstream's text, or through the derivation hook.

    Skip policy: an errored upstream row is always skipped (there is no text to
    forward). A row whose upstream failed precheck follows the stage's
    `on_upstream_failure: skip | run_anyway` (default skip). `expect: fail` rows
    are skipped for any non-root stage — a row meant to be rejected must never
    propagate downstream. Every skipped row carries `upstream_chain` so a later
    score drop is attributable.
    """

    config = stage.get("input") or {}
    source = config.get("source", "dataset")
    from_agents = list(config.get("from") or [])
    template = config.get("template")
    _validate_template(template, from_agents)

    adapter = _resolve_hook(config.get("adapter"), config_dir=config_dir)
    seed_sources = dict(config.get("seed_files") or {})
    seed_hooks = {
        filename: _resolve_hook(value, config_dir=config_dir)
        for filename, value in seed_sources.items()
        if _is_hook_reference(value)
    }
    seed_agents = [
        value for value in seed_sources.values() if not _is_hook_reference(value)
    ]

    is_root = source == "dataset"
    policy = _failure_policy(stage)
    indexes = {agent: _index_rows(output) for agent, output in upstream_outputs.items()}
    needed_agents = _unique(from_agents + seed_agents)

    stage_inputs = []
    for row in dataset.get("rows") or []:
        texts, chain, upstream_reason = _gather_upstreams(
            str(row.get("id", "")), needed_agents, indexes, policy
        )
        prompt, adapter_reason = _compose_prompt(
            row,
            texts,
            from_agents=from_agents,
            template=template,
            adapter=adapter,
            is_root=is_root,
        )
        reason = _expect_reason(row, is_root=is_root) or upstream_reason or adapter_reason
        stage_inputs.append(
            StageInput(
                row_id=str(row.get("id", "")),
                prompt=prompt,
                seed_files=_resolve_seed_files(row, texts, seed_sources, seed_hooks),
                deliverable_file=stage.get("deliverable_file"),
                industry=str(row.get("industry", "")),
                tags=list(row.get("tags") or []),
                expect=str(row.get("expect", "pass")),
                upstream_chain=chain,
                skip_reason=reason,
            )
        )
    return stage_inputs


def _validate_template(template: str | None, from_agents: list[str]) -> None:
    """Check the fan-in template at load time: required, and exactly covering `from:`."""
    if len(from_agents) > 1 and not template:
        raise ValueError(
            f"stage input lists {len(from_agents)} upstreams "
            f"({', '.join(from_agents)}) but declares no 'template': a fan-in must "
            "state its own ordering, never fall back to the order of 'from'"
        )
    if not template:
        return

    placeholders = set(PLACEHOLDER_PATTERN.findall(template))
    unknown = sorted(placeholders - set(from_agents))
    if unknown:
        raise ValueError(
            f"stage input template names unknown placeholder(s) {unknown} — "
            f"'from' declares {from_agents}"
        )
    unused = sorted(set(from_agents) - placeholders)
    if unused:
        raise ValueError(
            f"stage input 'from' lists {unused} with no placeholder in the "
            "template — every upstream must appear in the composed prompt"
        )


def _failure_policy(stage: dict) -> str:
    """Read `on_upstream_failure` (stage level or input level), defaulting to skip."""
    config = stage.get("input") or {}
    policy = stage.get("on_upstream_failure") or config.get("on_upstream_failure") or "skip"
    if policy not in ("skip", "run_anyway"):
        raise ValueError(
            f"on_upstream_failure must be 'skip' or 'run_anyway', got '{policy}'"
        )
    return policy


def _is_hook_reference(value: str) -> bool:
    """A `./file.py:func` reference, as opposed to a bare upstream agent id."""
    return ":" in str(value)


def _resolve_hook(reference: str | None, *, config_dir: Path | None):
    """Resolve an adapter or derivation hook at load time, or return None."""
    if not reference:
        return None
    if config_dir is None:
        raise ValueError(
            f"stage input declares hook '{reference}' but no config_dir was given "
            "to resolve it against"
        )
    return hooks.load_callable(reference, relative_to=config_dir / WORKFLOW_FILENAME)


def _index_rows(output: dict) -> dict[str, dict]:
    """Index one upstream `output.json` envelope by its stable row id."""
    return {str(row.get("id", "")): row for row in output.get("rows") or []}


def _unique(agents: list[str]) -> list[str]:
    """De-duplicate agent ids while keeping first-seen order."""
    seen: dict[str, None] = {}
    for agent in agents:
        seen.setdefault(agent, None)
    return list(seen)


def _gather_upstreams(
    row_id: str,
    agents: list[str],
    indexes: dict[str, dict[str, dict]],
    policy: str,
) -> tuple[dict[str, str], list[dict], str | None]:
    """Inner-join this row across every upstream it needs; report the first blocker.

    Returns the usable text per upstream, the `upstream_chain` entries for every
    upstream that has this row, and a skip reason when the row cannot run.
    """
    texts: dict[str, str] = {}
    chain: list[dict] = []
    reason: str | None = None

    for agent in agents:
        index = indexes.get(agent)
        if index is None:
            reason = reason or f"upstream '{agent}' did not run for this dataset"
            continue

        row = index.get(row_id)
        if row is None:
            reason = reason or f"row missing from upstream '{agent}'"
            continue

        precheck_passed = bool(row.get("upstream_precheck_passed", True))
        chain.append(
            {
                "agent": agent,
                "precheck_passed": precheck_passed,
                "score": row.get("upstream_score"),
            }
        )

        text = str(row.get("prompt") or "")
        if row.get("errored"):
            reason = reason or f"upstream '{agent}' errored"
            continue
        if not text.strip():
            reason = reason or f"upstream '{agent}' produced no text"
            continue

        texts[agent] = text
        if not precheck_passed and policy == "skip":
            reason = reason or f"upstream '{agent}' failed precheck"

    return texts, chain, reason


def _expect_reason(row: dict, *, is_root: bool) -> str | None:
    """`expect: fail` rows run at the root stage only — never downstream."""
    if is_root or str(row.get("expect", "pass")) != "fail":
        return None
    return EXPECTED_FAIL_SKIP


def _compose_prompt(
    row: dict,
    texts: dict[str, str],
    *,
    from_agents: list[str],
    template: str | None,
    adapter,
    is_root: bool,
) -> str:
    """Build this row's prompt: dataset verbatim, or upstream text through the template.

    Returns `(prompt, skip_reason)`. An adapter that cannot parse its upstream —
    prototype-build reads `## Task N:` headers out of the plan — is ONE ROW's
    problem, not the run's: the upstream agent produced something malformed,
    which is a result to record, not a usage error that should kill every other
    row and every later stage.
    """
    if is_root:
        upstreams: dict[str, str] = {}
        prompt = str(row.get("prompt") or "")
    else:
        if any(agent not in texts for agent in from_agents):
            return "", None
        upstreams = {agent: texts[agent] for agent in from_agents}
        prompt = _apply_template(template, upstreams) if template else upstreams[from_agents[0]]

    if adapter is None:
        return prompt, None
    try:
        return adapter(row, upstreams), None
    except Exception as error:  # noqa: BLE001 - a bad upstream skips its row, not the run
        return "", f"upstream could not be adapted: {error}"


def _apply_template(template: str, upstreams: dict[str, str]) -> str:
    """Substitute each `{agent-id}` placeholder with that agent's text for this row."""
    prompt = template
    for agent, text in upstreams.items():
        prompt = prompt.replace(f"{{{agent}}}", text)
    return prompt


def _resolve_seed_files(
    row: dict,
    texts: dict[str, str],
    seed_sources: dict[str, str],
    seed_hooks: dict[str, object],
) -> dict[str, str]:
    """Resolve each seeded filename to an upstream's text or a derivation hook's output."""
    resolved: dict[str, str] = {}
    for filename, value in seed_sources.items():
        hook = seed_hooks.get(filename)
        if hook is not None:
            resolved[filename] = hook(row, dict(texts))
        elif value in texts:
            resolved[filename] = texts[value]
    return resolved
