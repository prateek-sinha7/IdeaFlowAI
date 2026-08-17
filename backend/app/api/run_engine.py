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
import itertools
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import decode_access_token, is_token_revoked
from app.models.database import SessionLocal
from app.models.user import User
from app.models.workflow import WorkflowRun

logger = logging.getLogger("app.api.run_engine")

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


# C-06b: monotonic generation token, bumped every time a NEW producer queue is
# CREATED for a run_id (never on a reused/idempotent get). Object identity of the
# queue would also work as a generation token, but an explicit counter is cheaper
# to log/compare and survives the queue object being garbage-collected. Keyed on
# run_id only (SC-001); never cleared on cleanup — a later resume simply gets a
# strictly higher number, which is all the comparisons below need.
_QUEUE_GENERATIONS: dict[str, int] = {}
_GENERATION_SEQ = itertools.count(1)


def _get_or_create_queue(pipeline_run_id: str) -> asyncio.Queue:
    if pipeline_run_id not in _PIPELINE_QUEUES:
        _PIPELINE_QUEUES[pipeline_run_id] = asyncio.Queue(maxsize=0)  # unbounded
        _QUEUE_GENERATIONS[pipeline_run_id] = next(_GENERATION_SEQ)
    return _PIPELINE_QUEUES[pipeline_run_id]


def _cleanup_pipeline(pipeline_run_id: str) -> None:
    """Drop a run's live registrations AND release anyone attached to its queue.

    A3. Popping ``_PIPELINE_QUEUES`` is only half of "this run is no longer live":
    an SSE client that attached while the entry existed is parked in
    ``run_stream._iter_sse_frames`` at ``await live_queue.get()`` (``run_stream.py:197``)
    holding a direct reference to the queue OBJECT, so the dict pop does not reach it.
    Of the twelve paths that reach this function, only three (the launch driver's
    ``finally`` at ``run_commands.py:2185-2186``, the revision driver's at ``:2488-2489``,
    and ``engine._drive_resumed_stream``'s at ``engine.py:7823+7830``) send the ``None``
    sentinel first; the nine resume/re-arm paths that reach it through
    ``engine._fire_resume_cleanup`` do not, and their attached client hangs until the
    socket drops. Sending the sentinel HERE makes "stop tracking this run" and "release
    its readers" one atomic operation instead of two things every caller must remember.

    The sentinel goes onto the SOURCE queue we just popped, never to a consumer, so it
    QUEUES BEHIND anything still pending: on the three already-sentinelled paths this is
    a harmless second sentinel the reader never reaches (it returns on the first), and no
    tail is truncated. ``put_nowait`` is used because this function is synchronous and is
    called from both sync and async contexts; the queue is unbounded (``maxsize=0``,
    ``_get_or_create_queue``) so ``QueueFull`` is unreachable -- the guard is there only so
    a future bound queue degrades instead of raising inside a cleanup path. The pops stay
    unconditional (Phase-12 WR-01: every exit path must drop the task entry) and the
    function stays idempotent -- a second call pops ``None`` and sends nothing.

    C-06: since the KAN-134 fan-out bus landed, the reader parked on THIS queue is
    usually the per-run pump (``_pump_run_events``), not the SSE client directly. The
    sentinel still reaches the client -- the pump forwards it to every subscriber via
    ``_dispatch_sentinel_to_subscribers`` -- just via one extra hop. If no pump was ever
    started for this run (no subscriber ever attached), the sentinel sits in the queue
    object until it is garbage-collected, which is harmless.
    """
    queue = _PIPELINE_QUEUES.pop(pipeline_run_id, None)
    _PIPELINE_TASKS.pop(pipeline_run_id, None)
    _CANCEL_EVENTS.pop(pipeline_run_id, None)
    if queue is not None:
        try:
            queue.put_nowait(None)
        except Exception:  # noqa: BLE001 -- releasing readers must never raise in cleanup
            pass

    # D4/D5 (KAN-139): evict singleton in-memory state for the completed run so the
    # ArtifactStore HITL dicts and StateMachine._states do not grow without bound for
    # the process lifetime. Imports are lazy (avoids circular-import risk at module
    # load). Both forget_run() methods are idempotent.
    try:
        from agents.artifact_store.store import get_artifact_store
        get_artifact_store().forget_run(pipeline_run_id)
    except Exception:  # noqa: BLE001 — best-effort, never block cleanup
        pass
    try:
        from agents.execution_engine.state_machine import get_state_machine
        get_state_machine().forget_run(pipeline_run_id)
    except Exception:  # noqa: BLE001 — best-effort, never block cleanup
        pass


def _is_run_live(run_id: str) -> bool:
    """True iff ``run_id`` has a LIVE in-process driver task.

    Replaces the two ``run_id in _PIPELINE_QUEUES`` membership tests that treated a
    surviving registry entry as proof a run is live. Membership is NOT liveness: a
    driver that raises before its cleanup runs (``engine.resume_run``'s unguarded DB
    read; a ``CancelledError`` at any of its pre-drive awaits) leaves the queue + task
    entries behind for the process lifetime, which made the run permanently
    un-attachable (the SSE attach blocks on a queue nobody feeds) and permanently
    un-resumable (``POST /{id}/resume`` → 409 forever).

    The authoritative signal is the DRIVER TASK, because every one of the seven
    registration sites registers the queue and the task with NO ``await`` between them
    (run_commands.py :399/:421, :991/:1003, :1204/:1216, :1775/:1796, :2383/:2395;
    engine.py :5372/:5388, :5440/:5457) -- so on a single-threaded event loop a
    registered queue is never observable without its task. And every driver's cleanup
    (``_cleanup_pipeline`` / the engine's injected ``_fire_resume_cleanup``) runs INSIDE
    the driver, i.e. strictly before its task transitions to ``done()``. A ``done()``
    task whose registry entries survive is therefore unambiguously stale.

    SIDE EFFECT (deliberate, and the reason this is not named ``_run_is_live``): a stale
    registration is SELF-HEALED here via ``_cleanup_pipeline`` -- the single registry
    teardown (INV-12). After A3, ``_cleanup_pipeline`` also sentinels the run's pump, so
    the heal additionally releases any client already blocked on the orphaned queue.

    Fail-safe: anything we cannot PROVE is finished is reported LIVE. A task object with
    no callable ``done`` (``tests/unit/test_rest_resume.py:260`` seeds a bare ``object()``
    sentinel and expects the overlap mutex to still return 409) and a ``done()`` that
    raises both take the live branch -- never self-heal something whose state is unknown.

    SC-001: keyed on ``run_id`` only. No workflow name, no pipeline type.
    Synchronous by contract: ``resume_run_endpoint``'s double-POST atomicity argument
    (run_commands.py:346) requires NO ``await`` between the overlap mutex and the
    registration that closes it. Do not make this a coroutine.
    """
    task = _PIPELINE_TASKS.get(run_id)
    if task is not None:
        done = getattr(task, "done", None)
        if not callable(done):
            # Un-introspectable sentinel -> assume live (never heal what we cannot prove).
            return True
        try:
            finished = bool(done())
        except Exception:  # noqa: BLE001 - an unreadable task is treated as live
            return True
        if not finished:
            return True

    # Not live. Self-heal any surviving registration. Evidence is the QUEUE or TASK entry
    # only -- NOT _CANCEL_EVENTS: ``launch_run`` registers the cancel event at :1734
    # before the queue at :1775, so a lone cancel-event entry is a legitimate mid-launch
    # state, not staleness. ``_cleanup_pipeline`` pops all three, which is correct once a
    # queue/task entry has proven the run dead.
    if run_id in _PIPELINE_QUEUES or run_id in _PIPELINE_TASKS:
        logger.warning(
            "stale run registration self-healed: run=%s task_present=%s "
            "task_done=%s queue_present=%s",
            run_id,
            task is not None,
            None if task is None else getattr(task, "done", lambda: None)(),
            run_id in _PIPELINE_QUEUES,
        )
        _cleanup_pipeline(run_id)
    return False


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

# Each entry is ``(queue, generation)``. ``generation`` is the ``_QUEUE_GENERATIONS``
# token of the producer queue that was live at SUBSCRIBE time (C-06b). It is what
# lets a pump bound to an OLDER generation avoid broadcasting its own stray sentinel
# to a subscriber that actually belongs to a newer resume's queue -- the two are
# never confused even though they share the same ``run_id`` key.
_SUBSCRIBERS: dict[str, list[tuple[asyncio.Queue, int]]] = defaultdict(list)
_SUBSCRIBERS_LOCK = asyncio.Lock()


async def _subscribe(run_id: str, queue_maxsize: int = 0) -> asyncio.Queue:
    """Subscribe an SSE client to the per-run fan-out bus.

    Creates a new queue and registers it for this run, tagged with the CURRENT
    producer-queue generation (C-06b) so it is only ever fed by a pump bound to
    that same generation. The SSE handler must call unsubscribe() when the
    connection closes (in a finally block).

    Args:
        run_id: The workflow run ID.
        queue_maxsize: Maximum queue size (0 = unbounded; slow clients
                       over this threshold are evicted on put, H-09).

    Returns:
        An asyncio.Queue for the SSE handler to drain.
    """
    q: asyncio.Queue = asyncio.Queue(maxsize=queue_maxsize)
    generation = _QUEUE_GENERATIONS.get(run_id)
    async with _SUBSCRIBERS_LOCK:
        _SUBSCRIBERS[run_id].append((q, generation))
    if not await _ensure_pump(run_id):
        # C-06: no live producer queue exists for this run (it finished in the race
        # window between the caller's _is_run_live check and this subscribe call —
        # _cleanup_pipeline already popped _PIPELINE_QUEUES[run_id] before we got
        # here). Nothing will ever feed this queue, so close it now instead of
        # leaving the SSE generator parked forever on `await live_queue.get()`.
        q.put_nowait(None)
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
            _SUBSCRIBERS[run_id] = [
                entry for entry in _SUBSCRIBERS[run_id] if entry[0] is not q
            ]
            if not _SUBSCRIBERS[run_id]:
                _SUBSCRIBERS.pop(run_id, None)


async def _evict_subscriber(run_id: str, q: asyncio.Queue) -> None:
    """H-09: force-close a subscriber whose queue hit ``maxsize`` instead of
    silently dropping the event that overflowed it.

    Silently dropping (the old behaviour) is worse than it looks: the client's
    ``Last-Event-ID`` cursor keeps advancing as it drains whatever DID make it
    through, so the gap left by the drop is never seen as a gap and is never
    replayed on a future reconnect. Evicting instead removes the subscriber and
    forces its SSE drain loop to observe a close (a dropped-then-recreated
    ``None`` slot) so the client reconnects and replays from the durable log
    starting at its LAST successfully consumed cursor -- no silent, permanent
    gap.

    M-04: eviction previously had zero observability of its own -- unlike the
    stale-registration self-heal above, which logs. Log at WARNING (one line per
    eviction, not per dropped event -- an eviction is already the rare/backpressure
    case, so this is naturally rate-limited by the eviction rate itself, never by
    per-event volume) so a slow-client pattern is visible in CloudWatch instead of
    only being inferable from a client-side reconnect it cannot itself explain.
    """
    logger.warning(
        "SSE subscriber evicted: run=%s queue_maxsize=%s qsize=%s "
        "reason=queue_full_on_dispatch",
        run_id,
        q.maxsize,
        q.qsize(),
    )
    await _unsubscribe(run_id, q)
    # Free a slot for the terminal marker. Best-effort: if a concurrent consumer
    # already drained the queue below maxsize this is a harmless no-op cost.
    try:
        q.get_nowait()
    except asyncio.QueueEmpty:
        pass
    try:
        q.put_nowait(None)
    except asyncio.QueueFull:
        # Vanishingly unlikely (would need a second concurrent producer racing
        # the same queue); the client's own disconnect detection / the
        # keepalive ping eventually surfaces the stall.
        pass


async def _dispatch_event_to_subscribers(
    run_id: str, event: dict[str, Any], generation: int | None
) -> None:
    """Fan-out an event to every SSE subscriber ON THIS GENERATION of a run.

    Non-blocking: a queue with no consumer is fine (the handler disconnects
    and cleans up via unsubscribe). A queue with a slow consumer buffers; a
    queue at maxsize is EVICTED (H-09) rather than silently dropped, so the
    client reconnects and replays the gap instead of never knowing it exists.

    Args:
        run_id: The workflow run ID.
        event: The event dict to dispatch.
        generation: Only subscribers tagged with this producer-queue
            generation (C-06b) receive the event — a subscriber that attached
            to a NEWER (or older) generation under the same run_id is never
            fed by a pump that does not own its generation.
    """
    async with _SUBSCRIBERS_LOCK:
        queues = [
            q for (q, gen) in _SUBSCRIBERS.get(run_id, ()) if gen == generation
        ]
    for q in queues:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            await _evict_subscriber(run_id, q)


async def _dispatch_sentinel_to_subscribers(
    run_id: str, generation: int | None
) -> None:
    """Forward the producer's terminal ``None`` sentinel to subscribers of ONE generation.

    Mirrors ``_dispatch_event_to_subscribers`` but for the close signal: each
    subscriber's drain loop (``run_stream._iter_sse_frames``'s
    ``await live_queue.get()``) checks for ``None`` to end the stream cleanly.

    C-06b: scoped to ``generation`` for the same reason as the event fan-out —
    a STALE pump (bound to an old, already-superseded producer queue) must
    never close a subscriber that attached to the NEW generation's queue.
    """
    async with _SUBSCRIBERS_LOCK:
        queues = [
            q for (q, gen) in _SUBSCRIBERS.get(run_id, ()) if gen == generation
        ]
    for q in queues:
        try:
            q.put_nowait(None)
        except asyncio.QueueFull:
            await _evict_subscriber(run_id, q)


# ---------------------------------------------------------------------------
# C-06 fix (KAN-134 fan-out bus had no producer): the pump that bridges the
# existing per-run producer queue (``_PIPELINE_QUEUES``, fed by every launch /
# revision / resume driver) into the per-subscriber fan-out bus (``_SUBSCRIBERS``,
# fed only by ``_dispatch_event_to_subscribers``, which had zero callers). Every
# real event producer writes ONLY to ``_PIPELINE_QUEUES``; every SSE subscriber
# reads ONLY from its own ``_SUBSCRIBERS`` queue. Without this pump nothing
# connects the two, so every live attach parks on ``live_queue.get()`` forever.
#
# One pump task per run GENERATION, started lazily by the FIRST subscriber to
# attach (``_ensure_pump``, called from ``_subscribe``) rather than at launch
# time, so a run nobody is watching costs nothing extra. Guarded by
# ``_PUMP_TASKS_LOCK`` so two SSE clients attaching concurrently never spawn two
# pumps racing to drain the same producer queue (which would silently split
# events between them — the exact round-robin bug KAN-134 replaced the
# single-queue model to fix).
#
# C-06b: keyed by ``run_id`` alone (bare-``run_id`` keying was the root cause —
# ``_PUMP_TASKS[run_id]`` is checked for "un-``done()``" liveness with no binding
# to WHICH producer-queue generation it is draining. A resumed run installs a
# brand-new queue under the same ``run_id`` while the OLD pump — still draining
# its own now-superseded queue, not yet at its terminal sentinel — is still
# registered, so ``_ensure_pump`` sees a live-looking entry and starts NOTHING
# for the new generation. ``_PUMP_TASKS`` now stores ``(task, generation)`` so a
# stale pump from an older generation is recognised as such and replaced.
_PUMP_TASKS: dict[str, tuple[asyncio.Task, int]] = {}
_PUMP_TASKS_LOCK = asyncio.Lock()


async def _pump_run_events(run_id: str, queue: asyncio.Queue, generation: int) -> None:
    """Drain one run GENERATION's producer queue into its own attached subscribers.

    Terminates on the producer's ``None`` sentinel — sent by the driver's own
    ``finally`` (launch/revision) or by ``_cleanup_pipeline`` (resume / gate-re-arm
    paths) — which it forwards (scoped to ``generation``, C-06b) to every
    subscriber of that generation so their drain loops return instead of
    hanging. A dispatch failure for one event is logged and does not kill the
    pump; a failure that escapes the loop entirely still closes out every
    attached subscriber (via the sentinel) instead of leaving them parked
    forever.
    """
    try:
        while True:
            event = await queue.get()
            if event is None:
                await _dispatch_sentinel_to_subscribers(run_id, generation)
                return
            try:
                await _dispatch_event_to_subscribers(run_id, event, generation)
            except Exception:  # noqa: BLE001 - one bad event must not kill the pump
                logger.exception(
                    "SSE pump: failed to dispatch event for run=%s gen=%s",
                    run_id, generation,
                )
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - the pump must not strand its subscribers
        logger.exception("SSE pump crashed for run=%s gen=%s", run_id, generation)
        await _dispatch_sentinel_to_subscribers(run_id, generation)
    finally:
        # C-06b: pop OUR OWN registry entry only if it still points at THIS task.
        # A newer generation's pump may already have overwritten the entry (the
        # replacement path below is synchronous-until-create_task, so this is a
        # defensive check, not the primary guard) — never let an exiting stale
        # pump clobber a fresher pump's live registration.
        existing = _PUMP_TASKS.get(run_id)
        if existing is not None and existing[0] is asyncio.current_task():
            _PUMP_TASKS.pop(run_id, None)


async def _ensure_pump(run_id: str) -> bool:
    """Start the fan-out pump for ``run_id`` if a live producer queue exists.

    Returns ``False`` when ``run_id`` has no entry in ``_PIPELINE_QUEUES`` — the
    run finished (and was cleaned up) in the window between the caller's liveness
    check and this call, so there is nothing left to pump. The caller
    (``_subscribe``) uses this to close a subscriber queue immediately instead of
    leaving it parked with no producer that will ever feed it.

    C-06b: idempotent PER GENERATION, not merely per ``run_id``. A registered
    pump whose recorded generation no longer matches the CURRENT producer
    queue's generation is stale — its own queue was replaced (a resume/launch
    installed a new one under the same ``run_id``) — so it is superseded with a
    pump bound to the new generation instead of being treated as "already
    covered". The stale pump keeps draining its OLD queue harmlessly to
    completion (it owns no subscribers of the new generation to strand) and
    self-unregisters in its own ``finally`` without clobbering the replacement
    (guarded above). Two SSE clients attaching concurrently to the SAME
    generation never race into starting two pumps (checked under
    ``_PUMP_TASKS_LOCK``).
    """
    queue = _PIPELINE_QUEUES.get(run_id)
    if queue is None:
        return False
    generation = _QUEUE_GENERATIONS.get(run_id)
    async with _PUMP_TASKS_LOCK:
        existing = _PUMP_TASKS.get(run_id)
        if existing is None or existing[0].done() or existing[1] != generation:
            task = asyncio.create_task(_pump_run_events(run_id, queue, generation))
            _PUMP_TASKS[run_id] = (task, generation)
    return True


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


def _resume_cancel_event(pipeline_run_id: str) -> asyncio.Event:
    """Return THE per-run cooperative cancel Event — the one ``POST /cancel`` sets.

    ISS-084: this is the app half of the engine's ``_resume_cancel_event`` hook (wired in
    ``app/main.py``, the single wiring site — the kernel never imports ``app.api``). It is
    also the ONLY place a resume-path Event is minted (INV-12), which is the whole point:
    for three years' worth of resume drivers ``_register_resume_task`` minted an Event that
    nothing downstream ever read, so ``cancel_run`` found it, set it, and answered
    ``cancelled: true`` while the run carried on billing. Get-or-create, so the engine
    resolving it later gets the SAME object the endpoint already holds — and so a
    double-register can never reset an Event a Stop has already set.
    """
    event = _CANCEL_EVENTS.get(pipeline_run_id)
    if event is None:
        event = asyncio.Event()
        _CANCEL_EVENTS[pipeline_run_id] = event
    return event


def _register_resume_task(pipeline_run_id: str, task: asyncio.Task) -> None:
    """Record an auto-resumed run's driver task in _PIPELINE_TASKS.

    A reconnect_pipeline checks ``task.done()`` — a live resume driver makes
    _has_live_task true; a finished one naturally falls back to the durable
    replay + status branch.

    KAN-88: also arm the run's cooperative cancel_event so a Stop takes the cooperative
    path (clean ``pipeline_cancelled`` terminal) rather than a destructive task kill.
    ISS-084 corrected KAN-88's premise — the engine did NOT read this Event until
    ``_resume_cancel_event`` was wired onto it in ``app/main.py``.
    """
    _PIPELINE_TASKS[pipeline_run_id] = task
    # Arm the run's cooperative cancel Event BEFORE its driver starts, so a Stop that
    # arrives during the drive's DB round-trips is not lost. Registration alone is not a
    # stop mechanism — ISS-084 — it only works because the engine resolves THIS object
    # through the injected ``_resume_cancel_event`` hook and threads it into every
    # cooperative boundary.
    _resume_cancel_event(pipeline_run_id)


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


def _review_gate_advertises_update_specs(gate_key: str) -> bool:
    """True unless the gate named by ``gate_key`` PUBLISHED ``update_specs_eligible:
    False`` on its most recent ``review_gate_ready``.

    ISS-053 layer 1. The engine already decides eligibility once, in
    ``ExecutionEngine._update_specs_eligible``, and stamps that verdict onto the durable
    ``review_gate_ready`` payload. This reads the verdict back so an ingress can answer a
    caller with a 409 instead of a silently-ignored 200. It does NOT restate the rule —
    there is exactly one rule and this is not it (INV-3 / INV-12).

    Returns False ONLY on an explicit published ``False`` for exactly this ``gate_key``.
    Every other shape ABSTAINS (returns True):

      * no ``review_gate_ready`` row — event persistence is best-effort
        (``_RunEventSink.persist`` degrades a DB failure to a warning), so a missing row
        means "unknown", never "ineligible";
      * the latest ready is for a DIFFERENT gate_key — not the gate being resolved;
      * the payload has no ``update_specs_eligible`` key — a pre-KAN-101 row.

    Abstaining is safe, and it is deliberate: a fabricated denial would 409 a LEGITIMATE
    revision whenever a persist degraded. It is only safe because the engine-side fence in
    ``_run_review_gate`` re-checks the same verdict from memory and never abstains — this
    layer is caller feedback, that layer is the guarantee.

    NOT owner-scoped, mirroring ``_review_gate_run_is_terminal``: every caller has already
    passed the ownership boundary, and filtering on ``run_events.owner_id`` here would risk
    a FALSE 409 (which blocks legitimate work) the moment that column diverged from
    ``WorkflowRun.user_id``.
    """
    from app.models.run_event import RunEvent

    run_id = (gate_key or "").split(":", 1)[0]
    if not run_id:
        return True
    db = _get_db()
    try:
        row = (
            db.query(RunEvent.payload_json)
            .filter(RunEvent.run_id == run_id, RunEvent.type == "review_gate_ready")
            .order_by(RunEvent.seq.desc())
            .first()
        )
    finally:
        db.close()
    if row is None:
        return True
    payload = row.payload_json if isinstance(row.payload_json, dict) else {}
    if payload.get("gate_key") != gate_key:
        return True
    if "update_specs_eligible" not in payload:
        return True
    return bool(payload["update_specs_eligible"])


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
