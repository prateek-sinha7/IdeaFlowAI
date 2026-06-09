"""agents/capabilities/context_providers/previous_run.py — the ``previous_run`` provider.

Seeds the parent run's spec.md / design.md / tasks.md into THIS run's sandbox
(the prototype revision path) as a declared ``ContextProvider`` capability
(PARITY-03). Lift of the engine's L4 parent-run seeding (engine.py:862-922).

DECLARED revision-intent gate (07-10 / WR-06): the seed (and the assert_owns it
fronts) fires ONLY when the run DECLARES it revises an existing artifact
(``ctx.is_revision_workflow``, sourced from ``compiled.deliverable.revises_existing``)
— NOT on raw ``parent_run_id`` presence. This tightens the trust boundary: a
forward build carrying a stray ``parent_run_id`` can no longer trigger an
unintended cross-run seed.

CRITICAL ownership gate (V4 / INV-8 / L16 — Highest-Risk Behavior 4):
``ScopedStore.assert_owns`` is called on the parent run BEFORE seeding ANY parent
context. An owner may only seed from a parent run it OWNS; a cross-owner
``PermissionError`` PROPAGATES out of ``load`` and is NEVER swallowed (the L16
ratchet, ``test_parent_run_ownership.py``). Any OTHER error during seeding (a
TTL-swept parent dir, an unreadable file) degrades gracefully — a missing parent
must never break a revision (CTX-05 parity) — but the ownership denial is the one
error that always wins.

Import purity (import-linter): the store is reached via ``ctx.scoped_store`` (the
object-typed field) and the parent files via the ``ctx.runner`` handle — no
``app.*`` / kernel import. ``seed_files.from_run`` is the declared surface this
provider honors; per Pitfall 2 the manifests stay ``{}`` and the behavior rides
here.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_SEED_FILES = ("spec.md", "design.md", "tasks.md")


class PreviousRunProvider:
    """Ownership-checked parent-run seed (``name='previous_run'``).

    Satisfies the ``ContextProvider`` port (``name`` + ``async load``). Returns an
    empty block map (its effect is the sandbox seed, not injected text blocks).
    """

    name = "previous_run"

    async def load(self, ctx: Any) -> dict[str, str]:
        # ── DECLARED revision-intent gate (07-10 / WR-06) ───────────────────────
        # Re-couple the seed + assert_owns to the DECLARED revision-intent signal
        # (``ctx.is_revision_workflow``, sourced from
        # ``compiled.deliverable.revises_existing``), NOT to raw ``parent_run_id``
        # presence. A forward build that happens to carry a stray ``parent_run_id``
        # in its payload must NEVER trigger a cross-run seed (it would seed another
        # run's spec/design/tasks into a non-revision sandbox). Only a workflow that
        # DECLARES it revises an existing artifact may seed from a parent. Read the
        # flag off ctx the same dynamic-attr way as ``parent_run_id``/``scoped_store``
        # so this module imports no kernel/app type (import-linter).
        revises_existing = bool(getattr(ctx, "is_revision_workflow", False))
        if not revises_existing:
            # Not a declared in-place revision — never seed a parent run, never run
            # assert_owns (no parent context belongs in a forward build).
            return {}

        parent_run_id = getattr(ctx, "parent_run_id", None)
        if not parent_run_id:
            # No parent (a declared revision with no recorded parent) — nothing to
            # seed (same-owner graceful-degrade path).
            return {}

        # ── L16 ownership gate (AUTHZ-02 / INV-8) — BEFORE any seed ──────────────
        # The cross-owner PermissionError PROPAGATES; it is NEVER swallowed. A
        # cross-owner parent must never be silently seeded (Highest-Risk Behavior 4).
        scoped_store = getattr(ctx, "scoped_store", None)
        if scoped_store is not None:
            try:
                await scoped_store.assert_owns(parent_run_id)
            except PermissionError:
                raise  # cross-owner denial — propagate (L16, never swallow)
            except Exception as authz_exc:  # noqa: BLE001 — DB/schema → degrade
                logger.warning(
                    "previous_run: assert_owns lookup failed for parent %s (%s) — "
                    "degrading to same-owner seed (CTX-05 parity)",
                    parent_run_id, authz_exc,
                )

        # ── Seed the parent run's reference files into this run's sandbox ────────
        # Reach the parent files + the current sandbox through the handle (no app.*
        # import). Any read/write failure degrades — a missing parent must never
        # break a revision.
        runner = getattr(ctx, "runner", None)
        if runner is None:
            return {}

        sandbox = getattr(runner, "sandbox", None)
        seeded: list[str] = []
        for name in _SEED_FILES:
            try:
                content = runner.read_parent_file(parent_run_id, name)
            except Exception as read_exc:  # noqa: BLE001
                logger.warning(
                    "previous_run: could not read parent %s (%s) — skipping",
                    name, read_exc,
                )
                continue
            if content and sandbox is not None:
                try:
                    sandbox.write(name, content)
                    seeded.append(name)
                except Exception as write_exc:  # noqa: BLE001 — never break a revision
                    logger.warning(
                        "previous_run: failed writing seeded %s (%s) — skipping",
                        name, write_exc,
                    )

        logger.info(
            "previous_run: seeded parent reference files from run %s: %s",
            parent_run_id, ", ".join(seeded) or "(none found)",
        )
        return {}
