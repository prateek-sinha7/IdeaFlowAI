"""agents/capabilities/input_providers/run_images.py — the ``run_images`` provider.

Turns the per-run ``ExecutionContext.run_images`` carrier (a list of normalized
``{mime_type, data(base64)}`` entries) into multimodal image content-blocks appended
to an opted-in agent's model dispatch (image-input Wave 1, Locked Decision #1/#2).

DORMANT this wave: no manifest declares ``input_providers:`` and no AGENT.md
declares ``injects:[images]``, so the engine's ``_compose_input_blocks`` gate never
resolves this capability. The capability is registered + resolvable for a later wave.

Import boundary: this module imports ONLY the registry + stdlib ``typing.Any`` — no
kernel/app import (import-linter). Gating is the CALLER's job (engine
``_compose_input_blocks``); this capability MUST NOT read ``ctx.current_spec_injects``
(the stale-field F1 leak vector).
"""

from __future__ import annotations

from typing import Any

from agents.capabilities.registry import register


@register(
    "input_provider",
    "run_images",
    user_allowed=True,
    description="Attach the run's user-supplied images (base64) as multimodal content-blocks to the agent prompt.",
    config_schema={},
)
class RunImagesProvider:
    """Compose base64 image content-blocks from ``ctx.run_images`` (``name='run_images'``).

    Satisfies the ``InputContentProvider`` port (``name`` attr + ``async def load``).
    Reads the transient per-run carrier only; returns ``[]`` when it is empty/absent.
    """

    name = "run_images"

    async def load(self, ctx: Any) -> list:
        images = getattr(ctx, "run_images", None) or []
        return [
            {
                "type": "image",
                "source_type": "base64",
                "mime_type": img["mime_type"],
                "data": img["data"],
            }
            for img in images
        ]
