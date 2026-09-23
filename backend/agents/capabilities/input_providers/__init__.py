"""agents.capabilities.input_providers — the ``InputContentProvider`` capabilities.

Each provider turns run-supplied binary/multimodal input carried on the per-run
``ExecutionContext`` into a list of content-blocks appended to an opted-in agent's
model dispatch (image-input Wave 1). Providers this wave:

  * ``run_images`` — reads the normalized ``ctx.run_images`` carrier and returns
    ``{"type":"image","source_type":"base64",...}`` blocks (or ``[]`` when empty).
  * ``pdf_pages`` — reads materialised PDF page images from .pdf/ and returns image
    content blocks (or ``[]`` when absent/empty).

Each satisfies the ``InputContentProvider`` port (``name`` attr + ``async def
load(self, ctx) -> list``) and imports ONLY the registry + stdlib — no kernel/app
import (import-linter).
"""

from agents.capabilities.input_providers import pdf_pages  # noqa: F401 — import side effect: @register
from agents.capabilities.input_providers import run_images  # noqa: F401 — import side effect: @register

__all__ = ["pdf_pages", "run_images"]
