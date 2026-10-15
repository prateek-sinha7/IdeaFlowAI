"""Merge a user's override steps onto a file-compiled plan (spec 016).

THE RULE: an override row supplies ``steps`` and nothing else. Every
workflow-level field — ``deliverable``, ``context_providers``, ``planner``,
``clarify``, ``seed_files``, ``limits`` — comes from the FILE manifest on every
resolve and is never user-editable.

That is not tidiness, it is what makes the feature possible at all. A
``user``/``db`` manifest is not fully trusted (``_TRUSTED_SOURCES = {file,
builtin}``; ADR-0054 restored this after ADR-0039 had widened it), and
``WorkflowCompiler._check_trust`` rejects any capability not registered
``user_allowed=True`` (or, for ``db`` only, ``saved_workflow_allowed=True``).
Sourcing workflow-level fields from the file means an override never needs
either flag for them. Omitting
``opendesign`` instead is worse: ``load_ppt_od_context`` never runs and the deck
is built with no template.

Sourcing those fields from the file sidesteps the whole problem WITHOUT making
any capability user-grantable. The steps themselves need no exemption:
``single_shot``, ``human``, ``before-human``, ``conditional`` and ``validation``
are already ``user_allowed=True``; ``approval`` and ``security`` are not, and a
row smuggling one is correctly rejected below.

CACHE SAFETY — the single highest-risk property in this module.
``compile_for_run`` is ``lru_cache(maxsize=None)`` and the ``CompiledWorkflow``
it returns is SHARED across every user and every run in the process. Mutating it
would leak one user's customisation into everybody else's runs, silently, until
restart. So this module only ever returns a NEW object via
``dataclasses.replace`` — the same discipline ``engine._apply_selections``
already follows.
"""

from __future__ import annotations

import copy
import dataclasses
import logging

logger = logging.getLogger(__name__)

# Placeholder workflow-level fields for the ISOLATED compile below. The manifest
# validator requires id/steps/deliverable/planner/clarify, but we discard
# everything except ``steps``, so these exist only to satisfy the shape.
# ``streamed_text`` is deliberately a user-allowed resolver: the isolated compile
# runs at trust="user" and must not fail on a placeholder we are about to throw
# away.
_PLACEHOLDER_DELIVERABLE = {"strategy": "streamed_text", "name": "output.md"}
_PLACEHOLDER_CLARIFY = {"mode": "skip", "defaults": []}

# ISS-1118: the step keys whose reference an override may inherit from its target.
_INHERITABLE_KEYS = ("compaction", "post_step")


def _flatten(raws):
    for raw in raws:
        if isinstance(raw, dict):
            yield raw
            sub = raw.get("subagents")
            if isinstance(sub, dict):
                yield from _flatten(sub.get("steps") or [])


def _split_inherited(overrides: str, steps: list):
    """Take off ``steps`` (a copy) what the override target's own plan declares.

    Returns ``(steps, admitted)``: a ``compaction`` / ``post_step`` reference moves to
    ``admitted[agent_id]`` iff the step with the same ``agent`` id in ``overrides``'
    file plan (``compile_for_run``, so aliases resolve) declares the identical name.
    Nested ``subagents.steps`` share that namespace. Everything else stays where the
    trust check sees it. The baseline is loaded only when a step carries such a key.
    """
    steps = copy.deepcopy(steps)
    carrying = [
        r
        for r in _flatten(steps)
        if isinstance(r.get("agent"), str)
        and any(r.get(k) is not None for k in _INHERITABLE_KEYS)
    ]
    if not carrying:
        return steps, {}
    from agents.execution_engine.engine import compile_for_run

    try:
        baseline = {s.agent_id: s for s in compile_for_run(overrides).steps}
    except FileNotFoundError:  # a pipeline type with no manifest: nothing to inherit
        return steps, {}
    admitted: dict = {}
    for raw in carrying:
        # ponytail: matched on the raw ``agent`` id, so a custom-agent step (compiled
        # as custom-agent:<instance_id>) never inherits; no built-in puts these keys on one.
        base = baseline.get(raw["agent"])
        for key in _INHERITABLE_KEYS:
            if (
                base is not None
                and raw.get(key) is not None
                and raw[key] == getattr(base, key)
            ):
                admitted.setdefault(base.agent_id, {})[key] = raw.pop(key)
    return steps, admitted


def compile_with_baseline(manifest, registry, *, trust: str, overrides: str | None):
    """Compile ``manifest`` at ``trust``, letting an override row keep its target's refs.

    ISS-1118: the canvas sends a built-in's own ``compaction`` / ``post_step`` back
    unchanged, and at ``trust="user"`` they are not user-allowed, so an unchanged
    "Save as my version" was refused. With ``overrides`` (the row's target built-in)
    set, a reference that target declares on the same step is taken off before the
    compile and put back on the compiled step after; every other reference, grant,
    gate and hook still meets ``WorkflowCompiler._check_trust`` as before.
    ``overrides=None`` is a plain compile. Every door that compiles an override row
    comes through here: the writers and the merge (``compile_override_steps``),
    launch by id, the route trigger, and resume.
    """
    from agents.workflows.compiler import WorkflowCompiler

    admitted: dict = {}
    if overrides:
        steps, admitted = _split_inherited(overrides, manifest.steps)
        manifest = dataclasses.replace(manifest, steps=steps)
    compiled = WorkflowCompiler().compile(manifest, registry, trust=trust)
    if not admitted:
        return compiled
    return dataclasses.replace(
        compiled,
        steps=[
            dataclasses.replace(s, **admitted[s.agent_id])
            if s.agent_id in admitted
            else s
            for s in compiled.steps
        ],
    )


def compile_override_steps(workflow_id: str, steps: list, registry):
    """Compile an override row's ``steps`` alone, at ``trust="user"``.

    The ONE check every reader and writer of an override row shares: the merge
    below and the saves in ``app/api/user_workflows.py`` (ISS-1092, ISS-1112), so
    a save can never store steps the merge would refuse. ``trust="user"`` applies
    CAP-03, the exec/network/secrets/spawn grant rejection and the untrusted
    permission cap (ISS-1111). A reference ``workflow_id``'s own plan declares on
    the same step is admitted (ISS-1118, ``compile_with_baseline``). Raises
    ``ManifestValidationError`` / ``CompilerError`` naming the refusal.
    """
    from agents.workflows.manifest import build_manifest_from_dict

    raw = {
        "id": workflow_id,
        "steps": steps,
        "deliverable": _PLACEHOLDER_DELIVERABLE,
        "planner": "skip",
        "clarify": _PLACEHOLDER_CLARIFY,
    }
    parsed = build_manifest_from_dict(raw, f"override:{workflow_id}")
    return compile_with_baseline(parsed, registry, trust="user", overrides=workflow_id)


def merge_override_steps(compiled, steps: list, registry):
    """Return a NEW ``CompiledWorkflow`` carrying ``steps`` from an override row.

    ``compiled`` is the file-compiled plan and MUST NOT be mutated (see the
    module docstring). ``steps`` is the raw step list off
    ``workflows.manifest_json``; ``registry`` is the capability registry the
    caller already holds.

    Degrades to ``compiled`` unchanged — with a warning — when the override
    cannot be compiled. A tampered or stale row must not take a run down, and
    the file plan is always a safe fallback.
    """
    if not steps:
        return compiled

    # Every entry must be a mapping BEFORE the compiler sees it. Neither
    # ``build_manifest_from_dict`` nor the compiler type-checks a step entry:
    # ``_validate_step_identity_tree`` -> ``_step_where`` calls ``raw.get("agent")``
    # straight away, so a bare string in the list raises AttributeError — which is
    # not one of the two rejections caught below and would take the run down
    # instead of degrading. Reachable only from a hand-edited row, but this is the
    # boundary where untrusted JSON enters, so it is checked here.
    if not all(isinstance(s, dict) for s in steps):
        logger.warning(
            "override: %s has a non-mapping step entry — running the file plan instead",
            compiled.id,
        )
        return compiled

    # Imported here rather than at module scope: this module is reached from the
    # kernel, and the compiler/manifest imports are heavier than the no-override
    # path (the overwhelming majority of runs) should have to pay for.
    from agents.workflows.compiler import CompilerError
    from agents.workflows.manifest import ManifestValidationError

    try:
        # The save already ran this check, but a row can be tampered with directly
        # in the database, so it is re-run here. The compiler's per-step
        # capability checks at trust="user" are the real boundary.
        user_compiled = compile_override_steps(compiled.id, steps, registry)
    except (ManifestValidationError, CompilerError) as exc:
        # Narrow catch, matching engine._apply_selections' posture: these two are
        # the ONLY expected rejections. Anything else is a programmer error and
        # must propagate rather than fail open invisibly.
        logger.warning(
            "override: %s failed to compile — running the file plan instead (%s)",
            compiled.id,
            exc,
        )
        return compiled

    if not user_compiled.steps:
        logger.warning(
            "override: %s compiled to zero steps — running the file plan instead",
            compiled.id,
        )
        return compiled

    logger.info(
        "override: %s running %d user-authored step(s) in place of %d file step(s)",
        compiled.id,
        len(user_compiled.steps),
        len(compiled.steps),
    )
    # ONLY .steps is taken. deliverable / context_providers / clarify / planner /
    # seed_files / limits all stay as the file manifest compiled them.
    return dataclasses.replace(compiled, steps=list(user_compiled.steps))
