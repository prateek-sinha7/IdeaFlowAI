"""agents/execution_engine/authz.py — the L16 parent-run ownership seam (CTX-03 / INV-8).

A single small, PURE ownership predicate. The ``ExecutionEngine`` seeds a
``prototype_revision`` run's ``spec.md`` / ``design.md`` / ``tasks.md`` from a
``parent_run_id``'s on-disk run sandbox. Without an explicit check, owner A could
implicitly seed from owner B's run sandbox (the L16 unenforced-ownership leak / the
INV-8 violation). ``assert_owns`` makes the same-owner assumption a HARD gate: it raises
a typed denial (``PermissionError``) when the seeding owner does not own the parent run.

The check runs in ``execute()`` LEXICALLY ABOVE the graceful-degrade ``try/except`` at the
seed block (D-07), so a cross-owner parent **raises and propagates out of ``execute()``** —
it is NOT swallowed by the broad ``except Exception`` that exists only to tolerate a
legitimate same-owner missing / TTL-swept parent.

By-convention in 0B: a parent sandbox is keyed on disk under ``(<owner>, parent_run_id)``,
so the parent's owner is — by convention — the principal the caller is about to read the
parent under (``user_id or "anon"``). 0B passes that conventional owner; Phase 5 (AUTHZ-02)
replaces the by-convention derivation with a real store lookup and RELOCATES this helper
into its store-layer scoped-query helper as a mechanical MOVE (D-06 / INV-12). Keep this
module lean and PURE (no persistence access, no sandbox access, no I/O) so that move stays
mechanical.

Anonymous-principal rule (D-04): ``owner_id`` is always a REAL principal string
(``user_id or "anon"``, never ``None``). ``"anon"`` is a real owner — it must be subject to
the check exactly like any named owner, never a fallback that bypasses it.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def assert_owns(owner_id: str, parent_run_id: str, parent_owner_id: str) -> None:
    """Raise ``PermissionError`` iff ``owner_id`` does not own ``parent_run_id``.

    Pure string compare — NO persistence access, NO sandbox access, NO I/O (D-06; Phase 5
    AUTHZ-02 relocates this into the scoped-query helper). ``"anon"`` is treated as a real
    owner: an anon run is denied a non-matching parent exactly like any named owner.

    Returns ``None`` when ``parent_owner_id == owner_id`` (same owner → allowed). The
    raised ``PermissionError`` propagates out of ``execute()`` — it is deliberately placed
    ABOVE the seed graceful-degrade ``try`` so it is NOT swallowed (D-07).
    """
    if parent_owner_id != owner_id:
        raise PermissionError(
            f"owner {owner_id!r} may not seed from parent run {parent_run_id!r} "
            f"(owned by {parent_owner_id!r})"
        )
