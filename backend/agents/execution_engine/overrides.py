"""Merge a user's override steps onto a file-compiled plan (spec 016).

THE RULE: an override row supplies ``steps`` and nothing else. Every
workflow-level field — ``deliverable``, ``context_providers``, ``planner``,
``clarify``, ``seed_files``, ``limits`` — comes from the FILE manifest on every
resolve and is never user-editable.

That is not tidiness, it is what makes the feature possible at all. A
``user``/``db`` manifest is untrusted (``_TRUSTED_SOURCES = {file, builtin}``),
and ``WorkflowCompiler._check_trust`` rejects any capability not registered
``user_allowed=True``. Two of ``ppt``'s workflow-level declarations fail that
check — ``deliverable: ppt`` and ``context_providers: [opendesign]`` are both
registered without the flag, and ``is_user_allowed`` defaults to False. Omitting
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

import dataclasses
import logging

logger = logging.getLogger(__name__)

# Placeholder workflow-level fields for the ISOLATED compile below. The manifest
# validator requires id/steps/deliverable/planner/clarify, but we discard
# everything except ``steps``, so these exist only to satisfy the shape.
# ``streamed_text`` is deliberately a user-allowed resolver: the isolated compile
# runs at trust="db" and must not fail on a placeholder we are about to throw
# away.
_PLACEHOLDER_DELIVERABLE = {"strategy": "streamed_text", "name": "output.md"}
_PLACEHOLDER_CLARIFY = {"mode": "skip", "defaults": []}


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
    from agents.workflows.compiler import CompilerError, WorkflowCompiler
    from agents.workflows.manifest import (
        ManifestValidationError,
        build_manifest_from_dict,
    )

    raw = {
        "id": compiled.id,
        "steps": steps,
        "deliverable": _PLACEHOLDER_DELIVERABLE,
        "planner": "skip",
        "clarify": _PLACEHOLDER_CLARIFY,
    }

    try:
        parsed = build_manifest_from_dict(raw, f"override:{compiled.id}")
        # trust="db" — the row was validated at save time but is re-checked here
        # because a row can be tampered with directly in the database. The
        # compiler's per-step capability checks are the real boundary.
        user_compiled = WorkflowCompiler().compile(parsed, registry, trust="db")
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
