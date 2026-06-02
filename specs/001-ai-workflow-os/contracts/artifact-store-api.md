# Artifact Store API Contract

Module: `backend/agents/artifact_store/store.py`

Interface is identical in Phase 1 (in-memory) and Phase 3 (DB-backed).

```python
class ArtifactStore:

    async def store(
        self,
        run_id: str,
        artifact_type: str,
        name: str,
        content: str,
        producing_agent_id: str,
        schema_version: str = "1.0",
        derived_from_id: str | None = None,
    ) -> str:
        """Persist an Artifact. Returns artifact_id. Raises on write failure."""

    async def retrieve_latest(
        self,
        run_id: str,
        artifact_type: str,
    ) -> dict | None:
        """Return the latest version of an Artifact by type. None if not found."""

    async def retrieve_version(
        self,
        artifact_id: str,
    ) -> dict | None:
        """Return a specific Artifact version by ID. None if not found."""

    async def list_by_type(
        self,
        run_id: str,
        artifact_type: str,
    ) -> list[dict]:
        """Return all versions of an Artifact type for a run, oldest first."""

    async def list_lineage(
        self,
        run_id: str,
    ) -> list[dict]:
        """Return all Artifacts in the run lineage (same run + parent runs)."""

    async def get_resume_event(
        self,
        pipeline_run_id: str,
    ) -> asyncio.Event:
        """Get (or create) the asyncio.Event for pause/resume. Always returns an event."""

    async def set_questionnaire_responses(
        self,
        pipeline_run_id: str,
        responses: list[dict],
    ) -> None:
        """Store questionnaire responses and set the resume event."""

    async def get_questionnaire_responses(
        self,
        pipeline_run_id: str,
    ) -> list[dict] | None:
        """Retrieve questionnaire responses. None if not yet submitted."""


def get_artifact_store() -> ArtifactStore:
    """Module-level singleton accessor."""
```

## Error Handling

- `store()` raises `ArtifactStoreWriteError` on failure — caller must NOT mark agent step complete
- `retrieve_*` methods return `None` (not raise) when not found
- `get_resume_event()` always returns an event (creates if absent)
- All methods are async and safe to call concurrently
