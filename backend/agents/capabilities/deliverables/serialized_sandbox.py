"""agents/capabilities/deliverables/serialized_sandbox.py — code-gen bundle.

Lift of the engine's code-gen branch (engine.py:520-525):

    if count_sandbox_deliverables(sandbox.root) > 0:
        return serialize_sandbox_deliverable(sandbox.root)

The ``filename:``-block bundle is the UI contract (FilesTab / AppBuilderPreview
parse it) — it is NOT reformatted. ``count_sandbox_deliverables`` /
``serialize_sandbox_deliverable`` are reached through ``ctx.runner`` (the D-03
handle), never a direct ``app.*`` import (Pitfall 4). When the sandbox holds 0
deliverable files the resolver does NOT claim the deliverable (returns ``None``)
— matching the ``count > 0`` guard so the engine's downstream text/PPT branch can
take over.
"""

from __future__ import annotations

from typing import Any

from agents.capabilities.deliverables._mimetype import default_mimetype
from agents.capabilities.registry import register


@register(
    "deliverable",
    "serialized_sandbox",
    user_allowed=True,
    description="Resolve the deliverable as the whole run sandbox serialized into filename-block output (code-gen bundle).",
)
class SerializedSandboxResolver:
    """Serialize the run sandbox to the ``filename:``-block bundle (``name='serialized_sandbox'``).

    Satisfies the ``DeliverableResolver`` port. No workflow-name branch — it
    claims the deliverable iff the sandbox holds >=1 deliverable file.
    """

    name = "serialized_sandbox"

    @staticmethod
    def default_mimetype(deliverable_name: str | None = None) -> str:
        """Default deliverable shape hint (ISS-021): a sandbox bundle → application/zip."""
        return default_mimetype("serialized_sandbox", deliverable_name)

    def resolve(self, ctx: Any) -> Any:
        runner = ctx.runner
        root = runner.sandbox.root
        if runner.count_sandbox_deliverables(root) > 0:
            return runner.serialize_sandbox_deliverable(root)
        # 0 deliverable files → do not claim it (count > 0 guard, engine parity).
        return None
