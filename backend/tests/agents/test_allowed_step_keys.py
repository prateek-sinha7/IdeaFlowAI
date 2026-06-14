"""WIRE-03 / D-17 — the durable "no accepted-but-dropped step key" guard.

Parametrized over EVERY ``_ALLOWED_STEP_KEYS`` entry. For each key, a minimal
manifest declares that key with a representative value and the test asserts the
declaration is either:

  (a) REFLECTED on the compiled ``Step`` / ``CompiledWorkflow`` (consumed), or
  (b) REJECTED with a ``CompilerError`` (raises).

NO key may both compile-clean AND be absent from the compiled object — that is
the "accepted-but-dropped" failure this guard forbids (D-17). Driving the
parametrize directly off ``_ALLOWED_STEP_KEYS`` means a FUTURE key addition
automatically forces a consumed-or-raises decision: a newly-allow-listed key
with no disposition entry below fails the ``known`` membership assertion, and a
key materialized without a disposition here fails ``test_every_allowed_key_has_a_disposition``.

INV-5 is preserved: this guard does NOT loosen the allow-list. A NON-allow-listed
key still raises (asserted by ``test_non_allowlisted_key_raises``), so strict-key
rejection stays intact.
"""

from __future__ import annotations

import pytest

from agents.capabilities.registry import CapabilityRegistry
from agents.workflows.compiler import (
    CompilerError,
    WorkflowCompiler,
    _ALLOWED_STEP_KEYS,
)
from agents.workflows.manifest import WorkflowManifest


# ---------------------------------------------------------------------------
# Disposition table — one entry per _ALLOWED_STEP_KEYS entry.
# ---------------------------------------------------------------------------
#
# value:  the representative manifest value declared for the key.
# assert_consumed(step, compiled): returns True iff the declaration is REFLECTED
#                                  on the compiled Step / CompiledWorkflow.
#
# Every entry's value MUST compile clean AND its assert_consumed MUST hold — i.e.
# every allow-listed step key is CONSUMED (none is accepted-but-dropped). A key
# whose correct disposition is "raises" would instead live in a separate raises
# table; none of the current keys are reject-only (all 16 are consumed).

_VALID_GATE = "human"
_VALID_STRATEGY = "task_loop"
_VALID_HOOK = "secret_scan"
_VALID_VALIDATOR = "html_static"
_VALID_COMPACTION = "html_skeleton"
_VALID_POST_STEP = "revision_validation"
_VALID_PARSER = "heading_tasks"


# Each disposition: key -> (representative_value, predicate(step, compiled) -> bool)
_DISPOSITIONS: dict[str, tuple[object, object]] = {
    "agent": ("step-x", lambda s, c: s.agent_id == "step-x"),
    "strategy": (_VALID_STRATEGY, lambda s, c: s.strategy == _VALID_STRATEGY),
    "gates": ([_VALID_GATE], lambda s, c: s.gates == [_VALID_GATE]),
    "hooks": ([_VALID_HOOK], lambda s, c: s.hooks == [_VALID_HOOK]),
    "validators": ([_VALID_VALIDATOR], lambda s, c: s.validators == [_VALID_VALIDATOR]),
    "compaction": (_VALID_COMPACTION, lambda s, c: s.compaction == _VALID_COMPACTION),
    "task_source": (
        {"kind": "parsed", "parser": _VALID_PARSER},
        lambda s, c: s.task_source is not None and s.task_source.parser == _VALID_PARSER,
    ),
    "post_step": (_VALID_POST_STEP, lambda s, c: s.post_step == _VALID_POST_STEP),
    "tools": ({"read_files": True}, lambda s, c: s.tools.read_files is True),
    # WIRE-01: per-step model: → Step.model (coerced ModelPolicy)
    "model": (
        {"model": "claude-test-id"},
        lambda s, c: s.model is not None and s.model.model == "claude-test-id",
    ),
    # FixPolicy forward surface — materialized so it is not accepted-but-dropped.
    "fix": (
        {"mode": "internal", "max_attempts": 1},
        lambda s, c: s.fix is not None and s.fix.max_attempts == 1,
    ),
    "fanout": (
        {"mode": "parallel"},
        lambda s, c: s.fanout is not None and s.fanout.mode == "parallel",
    ),
    "on_conflict": ("abort", lambda s, c: s.on_conflict == "abort"),
    # WIRE-02: per-step retry: → Step.retry (coerced RetryPolicy)
    "retry": (
        {"max_attempts": 2},
        lambda s, c: s.retry is not None and s.retry.max_attempts == 2,
    ),
    # WIRE-03: per-step injects: → Step.injects (list[str])
    "injects": (["template"], lambda s, c: s.injects == ["template"]),
    # depends_on edges materialized onto the compiled Step (DAG-consumed). A dep on
    # a step absent from this one-step manifest is ignored by the DAG (no edge added)
    # but MUST still be reflected on Step.depends_on (else it is accepted-but-dropped).
    "depends_on": (
        ["upstream"],
        lambda s, c: list(getattr(s, "depends_on", [])) == ["upstream"],
    ),
}


def _manifest_one_step(step_key: str, value: object) -> WorkflowManifest:
    """A minimal one-step manifest declaring exactly ``step_key: value``.

    ``agent`` is always present (required); for the ``agent`` case the value IS
    the agent id, otherwise a stable id is used so other keys compile.
    """
    step: dict = {"agent": "step-x"}
    if step_key == "agent":
        step = {"agent": value}
    else:
        step[step_key] = value
    return WorkflowManifest(
        id="dispo",
        steps=[step],
        deliverable={"strategy": "single_file", "name": "out.html"},
        planner="run",
        clarify={"mode": "auto", "defaults": []},
        context_providers=[],
        seed_files={},
        version=1,
    )


def test_disposition_table_covers_every_allowed_key() -> None:
    """The disposition table MUST enumerate exactly _ALLOWED_STEP_KEYS.

    A future key added to _ALLOWED_STEP_KEYS without a disposition here fails this
    assertion — forcing an explicit consumed-or-raises decision (D-17).
    """
    assert set(_DISPOSITIONS) == set(_ALLOWED_STEP_KEYS), (
        "disposition table drifted from _ALLOWED_STEP_KEYS — every allow-listed "
        "step key needs a consumed-or-raises disposition (D-17): "
        f"missing={set(_ALLOWED_STEP_KEYS) - set(_DISPOSITIONS)}, "
        f"extra={set(_DISPOSITIONS) - set(_ALLOWED_STEP_KEYS)}"
    )


@pytest.mark.parametrize("key", sorted(_ALLOWED_STEP_KEYS))
def test_allowed_step_key_is_consumed_or_raises(key: str) -> None:
    """Each _ALLOWED_STEP_KEYS entry is REFLECTED on the compiled Step (consumed)
    OR raises CompilerError (rejected) — never accepted-but-dropped (D-17).
    """
    value, predicate = _DISPOSITIONS[key]
    manifest = _manifest_one_step(key, value)
    try:
        compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry())
    except CompilerError:
        # Rejected disposition is acceptable (consumed-OR-raises). No current key
        # is reject-only, but this branch keeps the guard honest for future keys.
        return
    step = compiled.steps[0]
    assert predicate(step, compiled), (
        f"step key {key!r} compiled clean but is NOT reflected on the compiled "
        f"Step/CompiledWorkflow — accepted-but-dropped is forbidden (D-17)"
    )


def test_non_allowlisted_key_raises() -> None:
    """INV-5: a key OUTSIDE _ALLOWED_STEP_KEYS is rejected (strict-key, not silent-accept)."""
    bogus = "definitely_not_allowed_xyz"
    assert bogus not in _ALLOWED_STEP_KEYS
    with pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(
            _manifest_one_step(bogus, "v"), CapabilityRegistry()
        )
    assert bogus in str(exc.value)
