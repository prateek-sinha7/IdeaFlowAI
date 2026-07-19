"""agents/artifact_store/store.py — in-memory HITL pause/resume registry.

Phase 5 (PERSIST-02, 05-07) DELETED the artifact-persistence half of this module
(``store`` / ``retrieve_latest`` / ``retrieve_version`` / ``list_by_type`` /
``list_lineage`` + their ``WorkflowArtifact`` DB usage). Every artifact consumer was
migrated onto the typed ``agents.artifacts.ArtifactGraph`` + the persisted
``artifact_refs`` layer (via ``agents.authz.ScopedStore``) in 05-06, and the thin
``workflow_artifacts`` table was dropped in alembic ``0015``.

What REMAINS is the per-process Human-in-the-loop (HITL) pause/resume mechanism:
``asyncio.Event`` registries for the questionnaire and review gates. These are
per-process (single-asyncio-deployment) and intentionally NOT DB-backed — Phase 8
owns the HITL subsystem. ``websocket.py`` ``submit_questionnaire`` /
``approve_review`` and the engine's review gate depend on this half.

Public API:
    ArtifactStore         — the (now HITL-only) store class
    get_artifact_store()  — module-level singleton accessor
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class ArtifactStore:
    """In-memory HITL pause/resume registry (Phase 8 owns HITL).

    Holds the per-process ``asyncio.Event`` registries for the questionnaire and
    review gates. All methods are async and safe to call concurrently in a
    single-process asyncio deployment.

    (The artifact-persistence half was deleted in 05-07 — artifacts now live in the
    typed ``ArtifactGraph`` + persisted ``artifact_refs`` layer.)
    """

    def __init__(self) -> None:
        # asyncio.Event registry for Human_Gate pause/resume (in-memory, per-process)
        self._resume_events: dict[str, asyncio.Event] = {}
        self._questionnaire_responses: dict[str, list[dict]] = {}
        # Per-run force-proceed flag (ISS-027): set when the user chose
        # "Skip all & run directly". The ClarifyEngine reads it after the resume
        # event fires to break out of the clarify loop immediately instead of
        # re-asking the same questions for the remaining rounds.
        self._questionnaire_force_proceed: dict[str, bool] = {}

    # ------------------------------------------------------------------
    # Human_Gate pause/resume (in-memory — per-process asyncio.Events)
    # ------------------------------------------------------------------
    async def get_resume_event(
        self,
        pipeline_run_id: str,
    ) -> asyncio.Event:
        """Get (or create) the asyncio.Event for pause/resume. Always returns an event."""
        if pipeline_run_id not in self._resume_events:
            self._resume_events[pipeline_run_id] = asyncio.Event()
        return self._resume_events[pipeline_run_id]

    async def set_questionnaire_responses(
        self,
        pipeline_run_id: str,
        responses: list[dict],
        skip_clarification: bool = False,
    ) -> None:
        """Store questionnaire responses and set the resume event.

        Args:
            skip_clarification: ISS-027 force-proceed. When True the user chose
                "Skip all & run directly"; the ClarifyEngine reads this flag once
                the resume event fires and proceeds immediately (PROCEED) rather
                than re-evaluating and re-asking for the remaining rounds. The
                flag is keyed per-run and consumed by the clarify loop; it stays
                False for ordinary answer submissions (byte-identical default).
        """
        self._questionnaire_responses[pipeline_run_id] = responses
        self._questionnaire_force_proceed[pipeline_run_id] = bool(skip_clarification)
        event = await self.get_resume_event(pipeline_run_id)
        event.set()
        logger.debug(
            "ArtifactStore: questionnaire responses set for run=%s (%d responses, "
            "skip_clarification=%s)",
            pipeline_run_id, len(responses), skip_clarification,
        )

    async def get_questionnaire_responses(
        self,
        pipeline_run_id: str,
    ) -> list[dict] | None:
        """Retrieve questionnaire responses. None if not yet submitted."""
        return self._questionnaire_responses.get(pipeline_run_id)

    async def get_questionnaire_force_proceed(
        self,
        pipeline_run_id: str,
    ) -> bool:
        """Whether the last questionnaire submission requested force-proceed (ISS-027).

        False when no submission has set it (the byte-identical default), so the
        clarify loop only short-circuits when the user explicitly chose
        "Skip all & run directly".
        """
        return self._questionnaire_force_proceed.get(pipeline_run_id, False)

    # ------------------------------------------------------------------
    # Review_Gate pause/resume — used by prototype spec/plan review gates
    # ------------------------------------------------------------------

    async def get_review_event(self, gate_key: str) -> asyncio.Event:
        """Get (or create) the asyncio.Event for a review gate. gate_key = '{pipeline_run_id}:{agent_id}'."""
        key = f"review:{gate_key}"
        if key not in self._resume_events:
            self._resume_events[key] = asyncio.Event()
        return self._resume_events[key]

    async def set_review_response(
        self,
        gate_key: str,
        approved: bool,
        edited_content: str | None = None,
        action: str = "approve",
        instructions: str | None = None,
    ) -> None:
        """Store review gate response and unblock the gate.

        ``action`` / ``instructions`` are ADDITIVE (REDO-GATE): a ``"redo"`` action
        carries optional free-text ``instructions`` for an in-place re-run of the
        gated agent (decision keyed on the generic ``action`` discriminator, read by
        ``_run_review_gate`` via ``.get(...)``). Both default to the prior
        approve/reject behavior, so every existing caller (WS approve/reject, the
        characterization live_harness, the declared-gate tests) is byte-identical —
        the extra keys are inert for any reader that does not look for them.
        """
        key = f"review:{gate_key}"
        self._questionnaire_responses[key] = [{
            "approved": approved,
            "edited_content": edited_content,
            "action": action,
            "instructions": instructions,
        }]
        event = await self.get_review_event(gate_key)
        event.set()
        logger.debug(
            "ArtifactStore: review gate response set for key=%s approved=%s action=%s",
            gate_key, approved, action,
        )

    async def get_review_response(self, gate_key: str) -> dict | None:
        """Retrieve review gate response. None if not yet submitted."""
        key = f"review:{gate_key}"
        responses = self._questionnaire_responses.get(key)
        return responses[0] if responses else None

    def review_event_pending(self, gate_key: str) -> bool:
        """True iff a review gate for ``gate_key`` is armed and awaiting a response.

        IN-02: the public read of the per-process HITL event registry — an armed
        (created) but not-yet-set ``review:{gate_key}`` event is the ground truth
        that a pause is genuinely pending (KAN-94). Closes the ``run_commands.
        _gate_is_pending`` private-dict peek (``store._resume_events`` no longer leaks
        into the app layer). Unknown key ⇒ ``False``. Read-only — never mutates.
        """
        event = self._resume_events.get(f"review:{gate_key}")
        return event is not None and not event.is_set()


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------

_STORE: ArtifactStore | None = None


def get_artifact_store() -> ArtifactStore:
    """Return the module-level ArtifactStore singleton.

    Creates the singleton on first call. Safe for single-process asyncio use.
    """
    global _STORE
    if _STORE is None:
        _STORE = ArtifactStore()
    return _STORE
