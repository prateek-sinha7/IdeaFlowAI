"""AI Workflow Builder HTTP layer.

``router`` is the one router ``app.main`` registers: the REST routes
(``routes.py``) and the Session stream (``stream.py``), both under
``/api/workflow-builder``. Startup, Turn start and shutdown are in
``lifecycle.py``.
"""

from fastapi import APIRouter

from app.api.workflow_builder.routes import router as _routes_router
from app.api.workflow_builder.stream import router as _stream_router

router = APIRouter()
router.include_router(_routes_router)
router.include_router(_stream_router)

__all__ = ["router"]
