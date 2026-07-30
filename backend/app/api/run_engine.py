"""Transport-neutral run infrastructure shared by every run transport.

W4a (44-03): this module is the single home for the run-pipeline infrastructure
that must OUTLIVE the ``/ws/chat`` endpoint deletion (INV-12 extract-before-delete).
It holds the per-run event-queue / task / cancel-event registries, the auto-resume
registrars + cleanup hook (wired onto the engine at startup in ``app/main.py``), the
untrusted-ingress validators/fences the REST run commands reuse (images, model
overrides, persisted selections, owner/terminal gates, owned-parent resolution), and
the shared DB-session + JWT-auth helpers. It is transport-agnostic — it imports no
FastAPI transport surface — so both the (transitional) WS endpoint in
``app.api.websocket`` and the REST/SSE endpoints resolve these symbols from here.

Ports-and-adapters: this is an ``app.api`` module; the engine kernel never imports
``app.*`` (import-linter forbidden direction). The auto-resume bridge is a set of
callbacks INJECTED onto the engine instance in ``app/main.py`` at startup.
"""

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import decode_access_token, is_token_revoked
from app.models.database import SessionLocal
from app.models.user import User
from app.models.workflow import WorkflowRun

# ---------------------------------------------------------------------------
# Pipeline event queue registry
# ---------------------------------------------------------------------------
# Decouples pipeline execution from the WebSocket connection.
# Each running pipeline writes events to a queue keyed by pipeline_run_id.
# The WebSocket drains the queue. If the WS disconnects and reconnects,
# the new connection picks up the same queue and resumes streaming.
# A sentinel value of None signals the pipeline has finished.

_PIPELINE_QUEUES: dict[str, asyncio.Queue] = {}
_PIPELINE_TASKS: dict[str, asyncio.Task] = {}  # pipeline_run_id → background task
# ISS-007 (16-02): per-run COOPERATIVE cancel signal. The Stop button
# (``cancel_pipeline``) sets this event instead of destructively cancelling the
# drainer task; the engine observes it (per-chunk / pre-agent) and emits
# ``pipeline_cancelled`` through the normal persisted+drained path, so the live
# wire receives the terminal and the FE clears its in-flight cards. Keyed by
# pipeline_run_id only (SC-001 — no workflow/model name).
_CANCEL_EVENTS: dict[str, asyncio.Event] = {}

# ---------------------------------------------------------------------------
# Image-input ingress caps (IMAGE-INPUT §3 Layer 1 / §12 F3)
# ---------------------------------------------------------------------------
# Untrusted base64 image bytes cross the browser → WS `run_pipeline` boundary.
# `_validate_images` is the chokepoint (T-frv-01 DoS / T-frv-02 tampering):
# a decompression-flood / count / aggregate-size vector is rejected here BEFORE
# the multimodal HumanMessage is checkpointed + re-sent on model-fallback retry.
_IMAGE_ALLOWED_MIMES = frozenset(
    {"image/png", "image/jpeg", "image/webp", "image/gif"}
)
_IMAGE_MAX_BYTES_PER_IMAGE = int(3.75 * 1024 * 1024)  # ~3.75 MB raw per image
_IMAGE_MAX_COUNT = 20  # max images per run
_IMAGE_MAX_AGGREGATE_BYTES = 8 * 1024 * 1024  # ~8 MB raw across all images


def _get_or_create_queue(pipeline_run_id: str) -> asyncio.Queue:
    if pipeline_run_id not in _PIPELINE_QUEUES:
        _PIPELINE_QUEUES[pipeline_run_id] = asyncio.Queue(maxsize=0)  # unbounded
    return _PIPELINE_QUEUES[pipeline_run_id]


def _cleanup_pipeline(pipeline_run_id: str) -> None:
    _PIPELINE_QUEUES.pop(pipeline_run_id, None)
    _PIPELINE_TASKS.pop(pipeline_run_id, None)
    _CANCEL_EVENTS.pop(pipeline_run_id, None)


# ---------------------------------------------------------------------------
# Per-run SSE fan-out bus (KAN-134: Multi-Tab SSE Stream Silent Data Loss)
# ---------------------------------------------------------------------------
# Replaces the old single-queue-per-run model which caused round-robin event
# partitioning across concurrent SSE clients. Each subscriber (SSE connection)
# gets its own queue, fed by a shared pump (the engine). All subscribers see
# all events in order. Based on the sanctioned websocket_handoff.py pattern
# (Phase 44 survivor).
#
# run_id → list[asyncio.Queue]. Each queue belongs to one SSE client connection.
# ``defaultdict(list)`` keeps the producer side simple; the SSE handler is
# responsible for adding and removing its own queue via subscribe/unsubscribe.

_SUBSCRIBERS: dict[str, list[asyncio.Queue]] = defaultdict(list)
_SUBSCRIBERS_LOCK = asyncio.Lock()


async def _subscribe(run_id: str, queue_maxsize: int = 0) -> asyncio.Queue:
    """Subscribe an SSE client to the per-run fan-out bus.

    Creates a new queue and registers it for this run. The SSE handler
    must call unsubscribe() when the connection closes (in a finally block).

    Args:
        run_id: The workflow run ID.
        queue_maxsize: Maximum queue size (0 = unbounded; slow clients
                       over this threshold are evicted on put).

    Returns:
        An asyncio.Queue for the SSE handler to drain.
    """
    q: asyncio.Queue = asyncio.Queue(maxsize=queue_maxsize)
    async with _SUBSCRIBERS_LOCK:
        _SUBSCRIBERS[run_id].append(q)
    return q


async def _unsubscribe(run_id: str, q: asyncio.Queue) -> None:
    """Unsubscribe an SSE client from the per-run fan-out bus.

    Removes the queue from the subscriber list. Safe to call multiple times
    or if the queue was never registered (idempotent).

    Args:
        run_id: The workflow run ID.
        q: The queue to remove.
    """
    async with _SUBSCRIBERS_LOCK:
        if run_id in _SUBSCRIBERS:
            try:
                _SUBSCRIBERS[run_id].remove(q)
            except ValueError:
                pass
            if not _SUBSCRIBERS[run_id]:
                _SUBSCRIBERS.pop(run_id, None)


async def _dispatch_event_to_subscribers(run_id: str, event: dict[str, Any]) -> None:
    """Fan-out an event to every SSE subscriber on a run.

    Non-blocking: a queue with no consumer is fine (the handler disconnects
    and cleans up via unsubscribe). A queue with a slow consumer buffers;
    a queue at maxsize silently drops the event (slow client evicted on next
    reconnect, which replays from the durable tail via Last-Event-ID).

    Args:
        run_id: The workflow run ID.
        event: The event dict to dispatch.
    """
    async with _SUBSCRIBERS_LOCK:
        queues = list(_SUBSCRIBERS.get(run_id, ()))
    for q in queues:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass  # Slow client; evicted on next reconnect (durable replay via Last-Event-ID)


# ---------------------------------------------------------------------------
# Engine→WS live-task bridge for AUTO-RESUMED runs (12-09 Gap 2a)
# ---------------------------------------------------------------------------
# An auto-resumed run (engine.resume_run, driven by restore_non_terminal_runs
# on startup) was never registered in _PIPELINE_TASKS/_PIPELINE_QUEUES, so a
# reconnect during the resumed run took the live:false branch and never
# received the resumed tail (incl. pipeline_complete). These two functions are
# the app-layer half of the bridge: they are INJECTED onto the engine instance
# in app/main.py at startup (the single wiring site) — the engine never imports
# app.api (import-linter forbidden direction; the bridge is a callback). The
# bridge is purely ADDITIVE: the legacy run_pipeline registration path below is
# unchanged. Workflow-agnostic — keyed by run_id only (SC-001). Cleanup reuses
# _cleanup_pipeline (injected as the engine's _resume_cleanup hook).


def _register_resume_queue(pipeline_run_id: str) -> asyncio.Queue:
    """Return/create the live event queue for an auto-resumed run.

    Recorded in _PIPELINE_QUEUES so a reconnect_pipeline mid-resume finds a
    live queue and attaches its drainer (the live:true branch).
    """
    return _get_or_create_queue(pipeline_run_id)


def _register_resume_task(pipeline_run_id: str, task: asyncio.Task) -> None:
    """Record an auto-resumed run's driver task in _PIPELINE_TASKS.

    A reconnect_pipeline checks ``task.done()`` — a live resume driver makes
    _has_live_task true; a finished one naturally falls back to the durable
    replay + status branch.

    KAN-88: also register a cancel_event so cancel_pipeline can cooperatively
    stop a resumed run via the cooperative path instead of falling through to
    the destructive task.cancel() fallback (which leaves the run in a bad state).
    """
    _PIPELINE_TASKS[pipeline_run_id] = task
    # Register a cooperative cancel event for the resumed task so the Stop
    # button works correctly. The engine's resume_run checks this event in
    # its per-chunk / pre-agent cancel checks (the same mechanism as a
    # normally-started pipeline run). Only register if no event already exists
    # (idempotent — a double-register must not reset a set() event).
    if pipeline_run_id not in _CANCEL_EVENTS:
        _CANCEL_EVENTS[pipeline_run_id] = asyncio.Event()


def _validate_model_overrides(
    model_overrides: dict, run_agent_ids: set[str]
) -> str | None:
    """Allow-list-validate the per-run ``{agent_id → model_id}`` override map.

    The security chokepoint for MODEL-03 (Phase 6 D-07, [HIGH] threat T-06-06):
    ``model_overrides`` is UNTRUSTED run-payload input crossing into model
    selection. Each entry is checked against TWO allow-lists, both derived from
    authoritative sources (never an arbitrary string, Q2 trust):

      * ``model_id ∈ ModelCatalog.ids()`` — the kernel-pure model catalog (06-01)
        is the ONE authoritative model-id list (INV-12). An unknown/arbitrary
        model id (unknown-provider / cost-abuse / invalid-model-crash vector) is
        rejected here.
      * ``agent_id ∈ run_agent_ids`` — the resolved agent set for THIS run
        (``get_pipeline_agents`` / the custom ``agent_ids`` list). An override
        targeting a non-existent agent (silent no-op, T-06-07 [MED]) is rejected.

    Returns ``None`` when every entry is valid (or the map is empty — the
    no-override default the frontend sends until Phase 8). On the FIRST
    violation returns a human-readable error message naming the bad value; the
    caller emits the existing ``{"type":"error", ..., "code":"invalid_model_override"}``
    event and rejects the run BEFORE ``engine.execute`` is called.
    """
    if not model_overrides:
        return None
    # Type guard (CR-01): ``model_overrides`` is UNTRUSTED run-payload input. The
    # ``or {}`` normalisation at the call sites only swaps FALSY values for ``{}``;
    # a truthy non-dict ("evil_string", ["list"]) — or a dict with non-string
    # keys/values — passes through and would crash on ``.items()`` / the set
    # membership check, killing the asyncio task silently (no error event, leaked
    # _PIPELINE_TASKS). REJECT malformed input with the same str-return contract as
    # every other violation, so the caller emits ``code="invalid_model_override"``
    # and refuses the run before any WorkflowRun is created.
    if not isinstance(model_overrides, dict):
        return (
            f"model_overrides must be an object mapping agent_id to model_id "
            f"(got {type(model_overrides).__name__!r})"
        )
    # Import the kernel-pure catalog lazily (app → kernel import is allowed; the
    # catalog has no app.* reach so this stays import-clean).
    from agents.capabilities.model_catalog import ModelCatalog

    allowed_model_ids = set(ModelCatalog().ids())
    for agent_id, model_id in model_overrides.items():
        if not isinstance(agent_id, str) or not isinstance(model_id, str):
            return (
                f"model_overrides entries must be string agent_id → string "
                f"model_id; got {agent_id!r}: {model_id!r}"
            )
        if agent_id not in run_agent_ids:
            return (
                f"model_overrides targets agent {agent_id!r}, which is not part "
                f"of this run's agents"
            )
        if model_id not in allowed_model_ids:
            return (
                f"model_overrides for agent {agent_id!r} requests model "
                f"{model_id!r}, which is not an allowed model"
            )
    return None


def _validate_images(
    images: Any, *, effective_model_ids: set[str] | None = None
) -> str | None:
    """Cap- and vision-guard the UNTRUSTED per-run ``images`` ingress list.

    The security chokepoint for the image-input feature (IMAGE-INPUT §3 Layer 1/5,
    §12 F3). ``images`` is UNTRUSTED run-payload input crossing the browser → WS
    boundary into ``ExecutionContext.run_images``. Same ``str | None`` contract as
    ``_validate_model_overrides``: ``None`` when the set is valid (or empty — a
    no-op, like ``_validate_model_overrides({})``); on the FIRST violation a
    human-readable message. The caller emits ``code="invalid_image_input"`` and
    refuses the run BEFORE any ``WorkflowRun`` is created or ``engine.execute`` is
    called — never a silent drop.

    Enforced in order (T-frv-01 DoS / T-frv-02 tampering):
      * ``images`` must be a list;
      * each entry a dict with a string ``mime_type`` + string ``data`` (CR-01
        type guard — a malformed entry would otherwise crash the asyncio task);
      * ``mime_type`` in the {png, jpeg, webp, gif} allow-list;
      * per-image estimated raw bytes (``len(data) * 3 // 4``) ≤ 3.75 MB;
      * ``len(images)`` ≤ 20;
      * running aggregate raw bytes ≤ 8 MB (the checkpointed HumanMessage is
        re-sent on model-fallback retry — §12 F3);
      * vision guard: when ``effective_model_ids`` is provided, EVERY id must be a
        ``ModelCatalog`` entry with ``vision=True`` (closes the raw-config /
        non-vision-model escape hatch — T-frv-02).
    """
    if not images:
        return None
    if not isinstance(images, list):
        return (
            f"images must be a list of {{mime_type, data}} objects "
            f"(got {type(images).__name__!r})"
        )
    if len(images) > _IMAGE_MAX_COUNT:
        return (
            f"too many images: {len(images)} exceeds the maximum of "
            f"{_IMAGE_MAX_COUNT}"
        )
    aggregate_bytes = 0
    for index, image in enumerate(images):
        if not isinstance(image, dict):
            return (
                f"images[{index}] must be an object with string mime_type + data "
                f"(got {type(image).__name__!r})"
            )
        mime_type = image.get("mime_type")
        data = image.get("data")
        if not isinstance(mime_type, str) or not isinstance(data, str):
            return (
                f"images[{index}] must carry a string mime_type + string data"
            )
        if mime_type not in _IMAGE_ALLOWED_MIMES:
            return (
                f"images[{index}] has unsupported mime_type {mime_type!r}; "
                f"allowed: {sorted(_IMAGE_ALLOWED_MIMES)}"
            )
        raw_bytes = len(data) * 3 // 4
        if raw_bytes > _IMAGE_MAX_BYTES_PER_IMAGE:
            return (
                f"images[{index}] is too large (~{raw_bytes} bytes); the per-image "
                f"limit is {_IMAGE_MAX_BYTES_PER_IMAGE} bytes"
            )
        aggregate_bytes += raw_bytes
        if aggregate_bytes > _IMAGE_MAX_AGGREGATE_BYTES:
            return (
                f"images exceed the aggregate size limit of "
                f"{_IMAGE_MAX_AGGREGATE_BYTES} bytes (~{aggregate_bytes} bytes so far)"
            )
    # Vision guard: reject unless every effective run-level model is a vision-capable
    # catalog entry. Import the kernel-pure catalog lazily (app → kernel is allowed;
    # the catalog has no app.* reach so this stays import-clean).
    if effective_model_ids:
        from agents.capabilities.model_catalog import ModelCatalog

        catalog = ModelCatalog()
        for model_id in effective_model_ids:
            entry = catalog.get(model_id)
            if entry is None or not entry.vision:
                return (
                    f"image input requires a vision-capable model; "
                    f"{model_id!r} is not a vision-capable catalog model"
                )
    return None


def _revalidate_selections_trust_user(
    base_pipeline_type: str,
    agent_ids: list[str],
    selections: dict | None,
) -> str | None:
    """LAUNCH-side CAP-03 re-validation of persisted per-step selections (Pitfall 3).

    EMP-02 / T-22-04-02: the FE lock + the SAVE-time check are NOT sufficient — a
    saved row could be TAMPERED after save (its ``manifest_json`` mutated to
    reference a ``user_allowed=False`` capability). So the launch path re-synthesizes
    the SAME ``WorkflowManifest`` (the shared ``agents.workflows.selections`` synth
    seam — no duplicated logic) and re-compiles it with ``trust="user"`` BEFORE
    execute. The dormant ``_check_trust`` path rejects any non-user-allowed reference
    (or ceiling-raising Limits), so a tampered row is REJECTED at launch, not run.

    Returns ``None`` when the selections are clean (or empty — parity), else a
    human-readable error message naming the offending ``(kind, name)`` (the caller
    emits the existing error-event shape and refuses the run before execute).
    """
    from agents.workflows.selections import (
        has_selections,
        validate_selection_model_ids,
    )

    if not has_selections(selections):
        return None

    # CR-01: a per-step ``model`` selection takes a different route than the
    # ``model_overrides`` map and is never catalog-validated by the trust=user
    # compile (the compiler accepts any string model id). Enforce the SAME allow-list
    # the MODEL-03 chokepoint applies, at the LAUNCH chokepoint, before execute — so a
    # crafted ``run_pipeline`` selections payload cannot route to an unintended /
    # disallowed provider via ``build_model``.
    _model_error = validate_selection_model_ids(selections)
    if _model_error is not None:
        return _model_error

    from agents.capabilities.registry import CapabilityRegistry
    from agents.workflows.compiler import CompilerError, WorkflowCompiler
    from agents.workflows.selections import synthesize_manifest

    manifest = synthesize_manifest(base_pipeline_type, agent_ids, selections)
    try:
        WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust="user")
    except CompilerError as exc:
        return f"Rejected persisted selection: {exc}"
    return None


def _get_db() -> Session:
    """Create a new database session for WebSocket use."""
    return SessionLocal()


def _review_gate_owned_by(gate_key: str, user_id: str) -> bool:
    """True iff the run named in ``gate_key`` (``{run_id}:{agent_id}``) belongs
    to ``user_id``.

    The gate response is a cross-run WRITE — ``approved``/``edited_content``
    resolve the named run's HITL gate and are folded into its results — so it
    must be owner-gated like every other cross-run surface (13-REVIEW CR-01 /
    T-13-01-01). Ownership is matched on ``WorkflowRun.user_id``: it is set at
    every creation site, whereas ``owner_id`` is a nullable Phase-5 backfill
    the main WS creation path leaves unset. An unknown run and an unowned run
    are indistinguishable to the caller (no run-existence oracle) — both deny.
    """
    run_id = (gate_key or "").split(":", 1)[0]
    if not run_id:
        return False
    db = _get_db()
    try:
        row = (
            db.query(WorkflowRun.id)
            .filter(WorkflowRun.id == run_id, WorkflowRun.user_id == user_id)
            .first()
        )
    finally:
        db.close()
    return row is not None


def _review_gate_run_is_terminal(gate_key: str) -> bool:
    """True iff the run named in ``gate_key`` is in a terminal state.

    KAN-100: approve_review must be rejected for cancelled/failed runs so a
    Redo (or Approve/Reject) on a stopped pipeline cannot unblock the gate
    and resume agent execution. Keyed on the persisted WorkflowRun.status —
    not the in-memory state machine — so it is accurate across WS reconnects.
    Returns False (not terminal) when the row is absent or the status is not
    a known terminal value, preserving the normal run path.
    """
    run_id = (gate_key or "").split(":", 1)[0]
    if not run_id:
        return False
    db = _get_db()
    try:
        row = (
            db.query(WorkflowRun.status)
            .filter(WorkflowRun.id == run_id)
            .first()
        )
    finally:
        db.close()
    if row is None:
        return False
    return row.status in ("cancelled", "failed", "degraded")


def _authenticate_token(token: str, db: Session) -> User | None:
    """Validate JWT token and return the user, or None if invalid.

    Mirrors :func:`app.core.dependencies.get_current_user` — including the
    revocation checks introduced for /api/auth/logout — so a token that has
    been revoked over HTTP can no longer be used to open or keep a WebSocket.

    Called from both the open-time auth gate and the per-message re-validation
    in ``websocket_chat``; the latter is what catches a /logout that revoked
    the token mid-session.

    Args:
        token: The JWT token string.
        db: The database session.

    Returns:
        The authenticated User or None.
    """
    try:
        payload = decode_access_token(token)
    except JWTError:
        return None

    user_id: str | None = payload.get("sub")
    if user_id is None:
        return None

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        return None

    # Per-token revocation (logout)
    jti = payload.get("jti")
    if jti and is_token_revoked(jti, db):
        return None

    # Blanket revocation on password change: reject any JWT whose ``iat``
    # second is strictly before the password-rotation second. Comparison is
    # done at whole-second resolution to match JWT ``iat`` precision — see
    # the matching logic + rationale in app.core.dependencies.
    pwd_changed_at = user.password_changed_at
    if pwd_changed_at is not None and pwd_changed_at.tzinfo is None:
        pwd_changed_at = pwd_changed_at.replace(tzinfo=timezone.utc)
    iat_raw = payload.get("iat")
    if pwd_changed_at is not None and iat_raw is not None:
        if isinstance(iat_raw, (int, float)):
            iat_seconds = int(iat_raw)
        elif isinstance(iat_raw, datetime):
            iat_dt = iat_raw if iat_raw.tzinfo else iat_raw.replace(tzinfo=timezone.utc)
            iat_seconds = int(iat_dt.timestamp())
        else:
            iat_seconds = None
        if iat_seconds is not None and iat_seconds < int(pwd_changed_at.timestamp()):
            return None

    return user


def _resolve_owned_parent_run_id(
    db: Session, candidate_id: Optional[str], user_id: str
) -> Optional[str]:
    """Return ``candidate_id`` iff it names a WorkflowRun OWNED by ``user_id``.

    Both parent-link ingress sites — the ``run_pipeline``
    ``source_workflow_run_id`` link (``_handle_workflow_execution`` :1688) and
    the ``run_revision`` row-creation ``parent_run_id`` link
    (``_handle_revision_execution`` :2247) — route their parent linkage through
    this single ownership-checked resolver (POR §3).

    Why ownership, not mere existence: ``parent_run_id`` is an enforced FK
    (migration 0013), so a stale/foreign id would abort run creation — the old
    exists-only check degraded that to an unlinked run. But a FOREIGN row
    linkage is strictly worse than a missing one: the revision-family read walk
    (``runs.py`` ``/family`` + server-computed ``root_run_id``) follows
    ``parent_run_id`` edges, so a persisted foreign parent would leak another
    owner's run metadata into the family response. Engine ``assert_owns``
    (``engine.py:4455``) already gates content reads; this gates the persisted
    ROW linkage so the two defenses compose.

    Keyed on ``WorkflowRun.user_id`` — the Phase-13 CR-01 ownership precedent —
    NEVER the nullable backfilled ``owner_id`` (D-06). A falsy candidate issues
    NO query and returns ``None``; a missing row or a row owned by another user
    also returns ``None``; otherwise ``candidate_id`` is returned unchanged.
    """
    if not candidate_id:
        return None
    row = (
        db.query(WorkflowRun.id)
        .filter(
            WorkflowRun.id == candidate_id,
            WorkflowRun.user_id == user_id,
        )
        .first()
    )
    return candidate_id if row else None
