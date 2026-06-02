"""agents/artifact_store — Persistent, versioned, lineage-tracked Artifact_Store.

Phase 1: in-memory implementation.
Phase 3: migrated to DB-backed implementation (public interface unchanged).

Public API:
    get_artifact_store() -> ArtifactStore   # module-level singleton
"""

from agents.artifact_store.store import ArtifactStore, get_artifact_store

__all__ = ["ArtifactStore", "get_artifact_store"]
