"""app/agents/tools/prototype.py — Backward-compatibility shim.

All prototype tool code has moved to agents/prototype/tools.py and
agents/prototype/artifact_store.py.

This file re-exports the public API so existing imports continue to work
without changes.
"""

from agents.prototype.artifact_store import PrototypeArtifactStore as ArtifactStore  # noqa: F401
from agents.prototype.tools import make_prototype_tools  # noqa: F401

__all__ = ["ArtifactStore", "make_prototype_tools"]
