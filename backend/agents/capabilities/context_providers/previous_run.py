"""agents/capabilities/context_providers/previous_run.py — the ``previous_run`` provider.

Seeds the parent run's spec.md / design.md / tasks.md into THIS run's sandbox
(the prototype revision path) as a declared ``ContextProvider`` capability
(PARITY-03). Lift of the engine's L4 parent-run seeding (engine.py:862-922).

Existing-artifact seed (07-10 / CR-06): when the run declares revision-intent,
this provider ALSO seeds the EXISTING artifact as an in-place-editable file —
relocated out of the kernel ``execute()`` (the self-described "DELIBERATE
EXCEPTION"). It extracts the prior artifact from the user message (the
deliverable-agnostic ``=== EXISTING PROTOTYPE HTML ===`` framing the frontend
emits), writes it to the sandbox under ``deliverable.name`` (NOT a hardcoded
``prototype.html`` const), captures the ``=== REVISION REQUEST ===`` instruction,
slims the message to a file pointer, and stashes ``revision_original_html`` /
``revision_instruction`` on ctx for the single_file fallback + the post-step
fix-loop capability. Byte-identical to the deleted inline kernel block (same
markers, same slimmed wording, same captured values).

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
import re
from typing import Any

from agents.capabilities.registry import register

logger = logging.getLogger(__name__)

_SEED_FILES = ("spec.md", "design.md", "tasks.md")


def _declared_seed_files(ctx: Any) -> tuple[str, ...]:
    """Read the DECLARED seed-file list off ctx with the legacy fallback (CR-07).

    The compiled ``seed_files`` dict is threaded onto ``ctx.seed_files`` at run entry.
    Per the ``seed_files.from_run`` declared surface, the parent-run seed list is the
    dict's ``from_run`` value when present + non-empty; otherwise fall back to the
    legacy ``_SEED_FILES`` triple. All authored manifests are ``{}`` (Pitfall 2) so the
    fallback fires → byte-identical to today. INV-5: the manifest only DECLARES the
    list; this control flow lives in the provider, never the compiler.
    """
    declared = getattr(ctx, "seed_files", None) or {}
    if isinstance(declared, dict):
        from_run = declared.get("from_run")
        if from_run:
            return tuple(str(n) for n in from_run)
    return _SEED_FILES

# Default editable-artifact filename when the deliverable declares no name. The
# behavior is parameterized by ``deliverable.name`` — this is only the fallback
# (matches the legacy ``REVISION_FILE_NAME`` default, byte-identical).
_DEFAULT_ARTIFACT_NAME = "prototype.html"


# ── Existing-artifact extraction (relocated from engine, CR-06) ─────────────────
# Workflow-agnostic: keys on the ``=== EXISTING PROTOTYPE HTML ===`` framing the
# frontend wraps a revision request with — deliverable-agnostic markers, NOT a
# workflow-name branch. Single home for this regex (no dual implementation).
def _extract_existing_artifact(user_message: str) -> str:
    """Pull the current artifact out of a revision request (returns "" if absent)."""
    m = re.search(
        r"=== EXISTING PROTOTYPE HTML ===\s*([\s\S]*?)\s*=== END EXISTING HTML ===",
        user_message, re.IGNORECASE,
    )
    return m.group(1).strip() if m else ""


def _extract_revision_instruction(user_message: str) -> str | None:
    """Pull the ``=== REVISION REQUEST ===`` instruction (None if the markers absent)."""
    m = re.search(
        r"=== REVISION REQUEST ===\s*([\s\S]*?)\s*=== END REQUEST ===",
        user_message, re.IGNORECASE,
    )
    return m.group(1).strip() if m else None


def _slim_revision_message(user_message: str, artifact_name: str) -> str:
    """Replace the inlined EXISTING artifact block with a one-line file pointer.

    Byte-identical to the legacy ``ExecutionEngine._slim_revision_message`` (same
    pointer wording), parameterized by ``artifact_name`` instead of the hardcoded
    ``REVISION_FILE_NAME`` const.
    """
    return re.sub(
        r"=== EXISTING PROTOTYPE HTML ===[\s\S]*?=== END EXISTING HTML ===",
        f"The current prototype is in the workspace file `{artifact_name}`. "
        "Call read_file to read it before editing.",
        user_message, count=1, flags=re.IGNORECASE,
    ).strip()


@register("context_provider", "previous_run")
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

        # ── Seed the EXISTING artifact as an in-place-editable file (CR-06) ──────
        # Relocated from the kernel's "DELIBERATE EXCEPTION" block. Parameterized by
        # ``deliverable.name`` (NOT a hardcoded const). Works off the user message
        # (independent of a parent_run_id), so it runs BEFORE the parent-seed gate.
        # Byte-identical to the legacy inline block: same extraction, same slimmed
        # message, same stashed ``revision_original_html`` / ``revision_instruction``.
        self._seed_existing_artifact(ctx)

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
            except Exception as authz_exc:  # noqa: BLE001 — WR-04: fail CLOSED
                # WR-04 (fail-closed): an UNEXPECTED store error (DB outage, schema
                # mismatch, transient store bug) means the ownership check could NOT
                # be completed. We must NOT proceed to seed the parent run's
                # spec/design/tasks on an unconfirmed ownership check — degrading OPEN
                # here risks cross-run data exposure (the blast radius is authz, not
                # cosmetic). Skip the parent seed entirely; a genuinely-absent parent
                # is already handled by the `if not parent_run_id` graceful path above,
                # and individual unreadable / TTL-swept parent files still degrade
                # per-file in the seed loop below. Only the cross-owner PermissionError
                # ever propagates (L16); every other error fails closed (no seed).
                logger.warning(
                    "previous_run: assert_owns lookup failed for parent %s (%s) — "
                    "FAILING CLOSED: skipping parent-run seed (ownership unconfirmed)",
                    parent_run_id, authz_exc,
                )
                return {}

        # ── Seed the parent run's reference files into this run's sandbox ────────
        # Reach the parent files + the current sandbox through the handle (no app.*
        # import). Any read/write failure degrades — a missing parent must never
        # break a revision.
        runner = getattr(ctx, "runner", None)
        if runner is None:
            return {}

        sandbox = getattr(runner, "sandbox", None)
        seeded: list[str] = []
        # CR-07: honor the DECLARED seed list (seed_files.from_run) with _SEED_FILES
        # fallback — NOT the hardcoded triple.
        for name in _declared_seed_files(ctx):
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

    # ── Existing-artifact seed (relocated from the kernel, CR-06) ───────────────
    @staticmethod
    def _seed_existing_artifact(ctx: Any) -> None:
        """Seed the prior artifact as an in-place-editable sandbox file.

        Byte-identical to the deleted inline kernel block: extract the artifact
        from the user message, write it under ``deliverable.name`` (default
        ``prototype.html``), capture the revision instruction, slim the message to
        a file pointer, and stash ``revision_original_html`` / ``revision_instruction``
        on ctx (for the single_file fallback + the post-step fix-loop capability).

        Reaches the message + sandbox via the ``ctx.runner`` handle (no app.* /
        kernel import). Degrades quietly when there is no handle, no message, or no
        EXISTING-artifact markers — the agent then works from the prompt alone.
        """
        runner = getattr(ctx, "runner", None)
        if runner is None:
            return

        user_message = getattr(runner, "user_message", None) or ""
        existing = _extract_existing_artifact(user_message)
        if not existing:
            logger.warning(
                "previous_run: no existing artifact found in request — agent will "
                "work from the prompt only"
            )
            return

        # Filename is parameterized by the declared deliverable.name (NOT a const).
        deliverable = getattr(ctx, "deliverable", None)
        artifact_name = getattr(deliverable, "name", None) or _DEFAULT_ARTIFACT_NAME

        # Stash the original for the single_file revision fallback.
        ctx.revision_original_html = existing

        sandbox = getattr(runner, "sandbox", None)
        if sandbox is not None:
            try:
                sandbox.write(artifact_name, existing)
            except Exception as write_exc:  # noqa: BLE001 — never break a revision
                logger.warning(
                    "previous_run: failed seeding existing artifact %s (%s)",
                    artifact_name, write_exc,
                )

        # Capture the user's revision instruction; slim the message to a pointer.
        # Fall back to the slimmed message when the REVISION REQUEST markers are
        # absent so the fix prompt always has SOMETHING to re-inject (byte-identical
        # to the legacy block, which used the slimmed message as the fallback).
        instruction = _extract_revision_instruction(user_message)
        slimmed = _slim_revision_message(user_message, artifact_name)
        runner.user_message = slimmed
        ctx.revision_instruction = instruction if instruction is not None else slimmed
