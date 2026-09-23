"""agents/capabilities/hooks/provenance_audit.py — provenance audit observer (task 9.1).

A non-blocking ``HookHandler`` that fires on ``post_commit`` and writes one
``run_provenance_audits`` row per commit that carries a non-None
``audit_operation``.  ``audit_operation=None`` means "not an audited operation
class" — the observer writes no row and returns normally.

Retention policy
----------------
Rows are append-only and intended for a **13-month** rolling window.
Deletion is operator-run (e.g. a scheduled SQL job or manual purge).
Automated retention is **out of scope** for this spec — the policy is
documented here so it is discoverable and does not require re-reading the
requirements to implement later.

Observation-only contract
--------------------------
* This observer CANNOT block a commit.  The ``handle`` method is wrapped in
  ``try/except`` so a raise inside it — including a DB failure — never
  propagates to the commit path.
* A missing ``ctx.runner`` (offline unit tests) is a silent no-op.
* A ``record_provenance_audit`` failure inside ``KernelServices`` is also
  swallowed (it follows the same BLE001 + logger.warning pattern as every
  other audit write in the codebase).

What each ``audit_operation`` value means
------------------------------------------
``snapshot_commit``   — the step-boundary / finalizer payload snapshot commit
``recovery_commit``   — a crash-reconciliation commit (non-success finalizer path)
``fragment_merge``    — the inter-fragment commit inside a fan-out merge
``merge_agent_commit``— a conflict-resolution agent's clean-verified commit
``restore``           — a ``POST /runs/{id}/restore`` forward-materialisation commit

Non-commit operations (``run_ref_created``, ``run_ref_idempotent``,
``run_ref_conflict``, ``tag_created``, ``tag_mapped``, ``status_published``,
``chain_source_selected``, ``chain_payload_installed``, ``chain_refused``,
``legacy_migrated``, ``commit_blocked``, ``legacy_context_block_stripped``) are
written at their own call sites and do NOT go through this observer.

Import purity (import-linter): imports ONLY the registry decorator, the hook
base types, and stdlib.  No kernel/app import.
"""

from __future__ import annotations

import logging
from typing import Any

from agents.capabilities.hooks.base import HOOK_CONTINUE, HookOutcome
from agents.capabilities.registry import register

logger = logging.getLogger(__name__)


@register(
    "hook",
    "provenance_audit",
    user_allowed=False,
    description=(
        "Post-commit provenance audit observer: writes one run_provenance_audits "
        "row per audited commit class (snapshot_commit, recovery_commit, "
        "fragment_merge, merge_agent_commit, restore). Observation-only — "
        "never blocks the commit or the finalizer."
    ),
)
class ProvenanceAuditObserver:
    """Non-blocking post_commit observer that persists a provenance audit row.

    Registered as ``("hook", "provenance_audit")`` — task 9.1 (Requirement 19).

    ``events = ["post_commit"]``: the observer only fires after a commit
    succeeds.  It is deliberately NOT in ``events = ["pre_commit"]`` because
    it writes a *success* record — a blocked commit is recorded separately via
    the ``commit_blocked`` call site.

    The ``run_id`` stamped on the row is ``ctx.run_id`` — the run the row
    **explains**.  For chain operations the receiving run's id is always what
    ``ctx.run_id`` holds (the source run is captured via ``source_ref`` from
    ``audit_detail``).

    Typed columns only — no free-form ``detail`` blob survives to the row.
    The ``audit_detail`` arriving in the ``post_commit`` event has already been
    filtered through ``_AUDIT_DETAIL_ALLOWLIST`` in ``commit_in_sandbox``
    (keys: ``tag_name``, ``source_ref``, ``idempotency_key``).
    """

    name = "provenance_audit"
    events = ["post_commit"]
    required_permission = None  # observation-only, no privilege required

    async def handle(self, event: Any, ctx: Any) -> HookOutcome:
        """Write one ``run_provenance_audits`` row (best-effort, never raises).

        Parameters
        ----------
        event:
            The ``extra`` dict from ``commit_in_sandbox``'s ``post_commit``
            dispatch, containing at minimum:
              ``commit_sha``       — the SHA of the just-created commit
              ``audit_operation``  — the operation class string, or ``None``
              ``audit_detail``     — already-filtered dict with at most
                                    ``tag_name``, ``source_ref``,
                                    ``idempotency_key``
        ctx:
            The per-run ``ExecutionContext``.  ``ctx.runner`` is the
            ``KernelServices`` handle; ``ctx.run_id``, ``ctx.user_id``,
            and ``ctx.workspace_id`` are used as the row's identity columns.
        """
        try:
            audit_operation: str | None = _extract(event, "audit_operation")
            if audit_operation is None:
                # Not an audited operation class — no row written; this is the
                # deliberate "not audited" marker, not an error.
                return HookOutcome(outcome=HOOK_CONTINUE)

            commit_sha: str = _extract(event, "commit_sha") or ""
            audit_detail: dict = _extract(event, "audit_detail") or {}

            tag_name: str | None = audit_detail.get("tag_name")
            source_ref: str | None = audit_detail.get("source_ref")
            idempotency_key: str | None = audit_detail.get("idempotency_key")

            run_id: str = getattr(ctx, "run_id", "") or ""

            runner = getattr(ctx, "runner", None)
            if runner is None:
                # Offline harness — no runner means no DB; silent no-op.
                return HookOutcome(outcome=HOOK_CONTINUE)

            record_fn = getattr(runner, "record_provenance_audit", None)
            if not callable(record_fn):
                # KernelServices version predates this observer — degrade
                # gracefully rather than crashing (forward-compatibility).
                logger.warning(
                    "ProvenanceAuditObserver: ctx.runner has no "
                    "record_provenance_audit; skipping row for run=%s op=%s",
                    run_id,
                    audit_operation,
                )
                return HookOutcome(outcome=HOOK_CONTINUE)

            await record_fn(
                run_id=run_id,
                operation=audit_operation,
                commit_sha=commit_sha or None,
                tag_name=tag_name,
                source_ref=source_ref,
                idempotency_key=idempotency_key,
            )

        except Exception as _exc:  # noqa: BLE001
            # Observation-only: a DB failure or unexpected exception must NEVER
            # propagate to the commit path or the finalizer (Requirement 19 /
            # task 9.1 — "a raising observer cannot abort the commit or the
            # finalizer").
            logger.warning(
                "ProvenanceAuditObserver.handle failed for run=%s: %s — "
                "commit stands; observer failure is isolated",
                getattr(ctx, "run_id", "?"),
                _exc,
            )

        return HookOutcome(outcome=HOOK_CONTINUE)


def _extract(event: Any, key: str) -> Any:
    """Extract ``key`` from an event that may be a dict or an object."""
    if isinstance(event, dict):
        return event.get(key)
    return getattr(event, key, None)
