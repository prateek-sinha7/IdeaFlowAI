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
    ) -> None:
        """Store questionnaire responses and set the resume event."""
        self._questionnaire_responses[pipeline_run_id] = responses
        event = await self.get_resume_event(pipeline_run_id)
        event.set()
        logger.debug(
            "ArtifactStore: questionnaire responses set for run=%s (%d responses)",
            pipeline_run_id, len(responses),
        )

    async def get_questionnaire_responses(
        self,
        pipeline_run_id: str,
    ) -> list[dict] | None:
        """Retrieve questionnaire responses. None if not yet submitted."""
        return self._questionnaire_responses.get(pipeline_run_id)

    # ------------------------------------------------------------------
    # Review_Gate pause/resume — used by prototype spec/plan review gates
    # ------------------------------------------------------------------

    async def get_review_event(self, gate_key: str) -> asyncio.Event:
        """Get (or create) the asyncio.Event for a review gate. gate_key = '{pipeline_run_id}:{agent_id}'."""
        key = f"review:{gate_key}"
        if key not in self._resume_events:
            self._resume_events[key] = asyncio.Event()
        return self._resume_events[key]

    async def set_review_response(self, gate_key: str, approved: bool, edited_content: str | None = None) -> None:
        """Store review gate response (approved + optional edited content) and unblock the gate."""
        key = f"review:{gate_key}"
        self._questionnaire_responses[key] = [{"approved": approved, "edited_content": edited_content}]
        event = await self.get_review_event(gate_key)
        event.set()
        logger.debug("ArtifactStore: review gate response set for key=%s approved=%s", gate_key, approved)

    async def get_review_response(self, gate_key: str) -> dict | None:
        """Retrieve review gate response. None if not yet submitted."""
        key = f"review:{gate_key}"
        responses = self._questionnaire_responses.get(key)
        return responses[0] if responses else None


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
