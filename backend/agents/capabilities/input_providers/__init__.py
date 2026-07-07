"""agents.capabilities.input_providers — the ``InputContentProvider`` capabilities.

Each provider turns run-supplied binary/multimodal input carried on the per-run
``ExecutionContext`` into a list of content-blocks appended to an opted-in agent's
model dispatch (image-input Wave 1). The sole provider this wave:

  * ``run_images`` — reads the normalized ``ctx.run_images`` carrier and returns
    ``{"type":"image","source_type":"base64",...}`` blocks (or ``[]`` when empty).

Each satisfies the ``InputContentProvider`` port (``name`` attr + ``async def
load(self, ctx) -> list``) and imports ONLY the registry + stdlib — no kernel/app
import (import-linter).
"""
