"""agents/capabilities/context_providers/chain_context.py — the ``chain_context`` provider.

Copies the chain payload from a source run's flat ``.chain/`` ref (V2) or from
a validated legacy ``.chain-legacy/{id}/`` directory (legacy) into the receiving
sandbox's ``.context/`` directory as raw bytes, making it available to agents
before step 1.

Gate (V2-Q8 / Requirement 6 AC 13-15)
--------------------------------------
``ectx.compiled_plan.deliverable.chains_from`` — fires ONLY when the compiled
workflow manifest declares a chain capability.  A run whose manifest does not
declare ``chains_from: true`` is entirely unaffected — provider is dormant,
returns ``{}``, INV-3 byte-parity holds.

A second gate: ``ctx.chain_source_run_id`` must be non-empty.  Neither gate
alone is sufficient: the declaration confirms the *workflow* accepts chain
context; the source run id confirms *this particular launch* actually carries
one.

Selection dispatch (task 6.5 / task 6.6)
-----------------------------------------
``ctx.chain_selection`` carries a ``V2Selection`` or ``LegacySelection``
pre-validated at admission time (task 6.3/6.5).  When it is ``None`` and the
run was admitted under ``chain_policy: degrade``, ``emit_chain_context_unavailable``
fires and the run continues without context.

-  ``V2Selection`` (``is_legacy=False``): ``ref`` points at the snapshot commit
   containing the flat ``.chain/`` payload.  Three files are read via
   ``ctx.runner.open_source_sandbox(...).read_bytes_at_ref(ref, path)`` and
   written atomically into ``.context/`` of the receiving sandbox.

-  ``LegacySelection`` (``is_legacy=True``): delegated to
   ``install_legacy_chain_context`` from ``app.agents.sandbox`` (NOT imported
   here directly — reached via ``ctx.runner`` attributes or a deferred callable
   supplied by the kernel).  The receiving sandbox's ``.context/`` root gains the
   three flat files as bytes.

Shared tail (both branches)
-----------------------------
After a successful byte copy ``_mark_chain_context_installed`` upserts the
``run_finalizations`` row setting ``chain_context_installed=True`` (Requirement
21 AC 8).  A best-effort ``chain_payload_installed`` audit row is written
immediately after.

TOCTOU guard (departure N3 / Requirement 6 AC 16)
--------------------------------------------------
If the validated payload bytes vanish between admission and install
(``chain_context_unavailable``), the provider emits the event and then:
- Under ``chain_policy: degrade`` — the run continues without context (normal
  AC 10 degrade path).
- Under ``chain_policy: refuse`` — the run is failed via
  ``ctx.runner.fail_run("chain_context_unavailable")``.  The edge
  (``source_run_id``) is preserved and ``chain_context_installed = false``
  is the durable discriminator (departure N3).

Import purity (import-linter)
------------------------------
This module imports ONLY stdlib and ``agents.capabilities.registry`` (for
``@register``).  All kernel/app access goes through ``ctx.runner``
(``KernelServices`` handle) — NO ``agents.execution_engine.*`` or ``app.*``
import anywhere in this file.

``install_legacy_chain_context`` and ``LegacySelection`` are NOT imported here.
They live in ``app.agents.sandbox``, which is an app-layer module; importing it
directly would violate the import-linter gate.  The kernel supplies them via
``ctx.runner.install_legacy_chain_context`` and makes the function discoverable
through that handle.
"""

from __future__ import annotations

import logging
import os as _os  # aliased to keep the module-level namespace clean
import pathlib as _pathlib
import tempfile as _tempfile
from typing import Any

from agents.capabilities.registry import register

logger = logging.getLogger(__name__)

# Destination prefix inside the receiving sandbox where context files land.
_CONTEXT_DEST_PREFIX = ".context"

# The three flat filenames that live at the root of .chain/ and are copied
# verbatim into .context/.
_V2_FIXED_FILES = ("logs.jsonl", "summary.md")

# Reason code emitted when the payload is unavailable at install time.
_REASON_UNAVAILABLE = "chain_context_unavailable"


@register(
    "context_provider",
    "chain_context",
    user_allowed=True,
    description=(
        "Byte-copy the chain payload from the source run's exact ref into "
        "the receiving sandbox's .context/ directory before step 1.  "
        "V2 reads three flat files from an immutable Git ref; legacy reads "
        "from a validated nested .chain-legacy/ directory.  "
        "Dormant (returns {}) on any run that does not declare chains_from."
    ),
)
class ChainContextProvider:
    """File-based chain payload provider (``name='chain_context'``).

    Satisfies the ``ContextProvider`` port (``name`` + ``async load``). Its
    effect is the sandbox seed — it returns an empty block map (``{}``) so no
    text is injected into the agent message (agents read from ``.context/``
    directly).

    V2 contract (Requirement 6 / 21):
      * Declaration gate on ``compiled_plan.deliverable.chains_from`` — NEVER on
        workflow name or type (SC-001 / V2-Q8).
      * ``ctx.chain_selection`` carries the pre-validated selection from the
        admission gate (task 6.3/6.5); this provider is a pure byte copier —
        provenance decisions are NOT made here.
      * Discriminates on ``selection.is_legacy`` to choose V2 vs legacy path.
      * ``mark_chain_context_installed`` is the sole writer of
        ``chain_context_installed`` (Requirement 21 AC 8).
      * ``chain_payload_installed`` audit row written best-effort after install.
      * TOCTOU guard: missing bytes → emit + degrade or refuse per policy.
    """

    name = "chain_context"

    async def load(self, ctx: Any) -> dict[str, str]:
        """Copy chain payload files into the receiving sandbox's .context/ dir.

        Returns an empty block map in all cases — the side-effect is the file
        copy, not injected text.
        """
        # ── Declaration gate (V2-Q8 / Requirement 6 AC 13) ───────────────────
        # Read ``chains_from`` from the compiled plan's deliverable spec.
        # A stray ``chain_source_run_id`` on a workflow that does not declare
        # chaining triggers ZERO cross-run reads (guard matches task 6.3
        # admit_chain_launch step 1).
        compiled_plan = getattr(ctx, "compiled_plan", None)
        if compiled_plan is None:
            # Fall back to ctx.deliverable for compatibility with the dynamic-attr
            # thread used by existing tests and the engine.
            deliverable = getattr(ctx, "deliverable", None)
        else:
            deliverable = getattr(compiled_plan, "deliverable", None)

        # Guard: accept only a literal bool ``True``.  A MagicMock or any other
        # truthy non-bool value does NOT pass the declaration gate (V2-Q8: zero
        # cross-run reads for workflows that have not explicitly declared chaining).
        _chains_from_raw = getattr(deliverable, "chains_from", False)
        chains_from: bool = _chains_from_raw is True
        chain_policy_raw = getattr(deliverable, "chain_policy", "refuse")
        chain_policy: str = (
            chain_policy_raw
            if isinstance(chain_policy_raw, str)
            else "refuse"
        ) or "refuse"

        if not chains_from:
            return {}

        # ── Source gate ───────────────────────────────────────────────────────
        source_run_id: str | None = getattr(ctx, "chain_source_run_id", None)
        if not source_run_id:
            return {}

        # ── Selection gate ────────────────────────────────────────────────────
        # ``ctx.chain_selection`` is set by the launch path (task 6.5) once
        # ExecutionContext.chain_selection is wired.  Until then it falls back
        # to None — treated as admitted-under-degrade (same as an explicit
        # degrade admission with no payload).
        selection: Any = getattr(ctx, "chain_selection", None)

        if selection is None:
            # Admitted under ``chain_policy: degrade`` with no payload, or the
            # admission-wiring TODO has not yet landed.
            logger.info(
                "chain_context: chain_selection is None for source=%s "
                "(admitted under degrade or pre-6.5 wiring) — emitting "
                "chain_context_unavailable",
                source_run_id,
            )
            _emit_chain_context_unavailable(
                ctx,
                source_run_id=source_run_id,
                reason="source_payload_missing",
                chain_policy=chain_policy,
            )
            return {}

        # ── Resolve runner ────────────────────────────────────────────────────
        runner = getattr(ctx, "runner", None)
        if runner is None:
            logger.warning(
                "chain_context: ctx.runner is None — cannot install chain context "
                "for source=%s; emitting chain_context_unavailable",
                source_run_id,
            )
            _emit_chain_context_unavailable(
                ctx,
                source_run_id=source_run_id,
                reason="source_payload_missing",
                chain_policy=chain_policy,
            )
            return {}

        # ── Resolve destination directory ─────────────────────────────────────
        sandbox = getattr(runner, "sandbox", None)
        if sandbox is not None:
            base_path: _pathlib.Path | None = _resolve_sandbox_base(sandbox)
        else:
            base_path = None

        if base_path is None:
            logger.warning(
                "chain_context: cannot resolve receiving sandbox base path for "
                "source=%s — emitting chain_context_unavailable",
                source_run_id,
            )
            _emit_chain_context_unavailable(
                ctx,
                source_run_id=source_run_id,
                reason="source_payload_missing",
                chain_policy=chain_policy,
            )
            return {}

        dest_dir = base_path / _CONTEXT_DEST_PREFIX

        # ── Dispatch to V2 or legacy byte copier ──────────────────────────────
        is_legacy: bool = bool(getattr(selection, "is_legacy", False))

        installed = False
        try:
            if is_legacy:
                installed = _install_legacy(
                    ctx=ctx,
                    runner=runner,
                    selection=selection,
                    source_run_id=source_run_id,
                    dest_dir=dest_dir,
                    chain_policy=chain_policy,
                )
            else:
                installed = _install_v2(
                    ctx=ctx,
                    runner=runner,
                    selection=selection,
                    source_run_id=source_run_id,
                    dest_dir=dest_dir,
                    chain_policy=chain_policy,
                )
        except _TocTouError as toctou:
            # Bytes vanished between admission and install — departure N3.
            logger.warning(
                "chain_context: TOCTOU: payload validated at admission but "
                "absent at install for source=%s ref=%s — emitting %s",
                source_run_id,
                toctou.ref,
                _REASON_UNAVAILABLE,
            )
            _emit_chain_context_unavailable(
                ctx,
                source_run_id=source_run_id,
                reason=_REASON_UNAVAILABLE,
                chain_policy=chain_policy,
            )
            _mark_chain_context_installed(ctx, runner, installed=False)
            return {}

        if not installed:
            return {}

        # ── Shared tail: mark installed + write audit row ─────────────────────
        _mark_chain_context_installed(ctx, runner, installed=True)
        _write_chain_payload_installed_audit(ctx, runner, selection, source_run_id)

        logger.info(
            "chain_context: chain payload installed from source=%s "
            "is_legacy=%s into %s",
            source_run_id,
            is_legacy,
            dest_dir,
        )
        return {}


# ---------------------------------------------------------------------------
# V2 byte copier
# ---------------------------------------------------------------------------

def _install_v2(
    *,
    ctx: Any,
    runner: Any,
    selection: Any,
    source_run_id: str,
    dest_dir: _pathlib.Path,
    chain_policy: str,
) -> bool:
    """Read three flat ``.chain/`` files from the exact ref and write to dest_dir.

    Reads via ``ctx.runner.open_source_sandbox(source_run_id).read_bytes_at_ref``
    so the bytes pass through the owner-scoped ``ReadOnlySandbox`` and the
    traversal-proof path guard.

    Returns ``True`` on full success, ``False`` if the payload is unavailable
    (TOCTOU handled by the caller).  Raises ``_TocTouError`` when a file that
    was present at admission is missing at copy time.
    """
    ref: str = getattr(selection, "ref", "") or ""
    basename: str = getattr(selection, "basename", "") or ""

    if not ref or not basename:
        logger.error(
            "chain_context: V2Selection has empty ref=%r or basename=%r "
            "for source=%s — cannot install",
            ref,
            basename,
            source_run_id,
        )
        _emit_chain_context_unavailable(
            ctx,
            source_run_id=source_run_id,
            reason="source_provenance_conflict",
            chain_policy=chain_policy,
        )
        return False

    # The three exact paths inside .chain/ at the ref.
    files_to_copy = [
        (f".chain/{name}", name)
        for name in (*_V2_FIXED_FILES, basename)
    ]

    # Open the source sandbox once.
    try:
        source_sb = runner.open_source_sandbox(source_run_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "chain_context: open_source_sandbox failed for source=%s: %s — "
            "emitting chain_context_unavailable",
            source_run_id,
            exc,
        )
        _emit_chain_context_unavailable(
            ctx,
            source_run_id=source_run_id,
            reason="source_payload_missing",
            chain_policy=chain_policy,
        )
        return False

    # Read all three files first (fail fast before any write).
    file_bytes: dict[str, bytes] = {}
    for chain_path, dest_name in files_to_copy:
        try:
            raw: bytes = source_sb.read_bytes_at_ref(ref, chain_path)
        except Exception as exc:  # noqa: BLE001
            # File was present at admission but is gone now — TOCTOU.
            raise _TocTouError(ref=ref, path=chain_path) from exc
        file_bytes[dest_name] = raw

    # Atomic write: stage into a temp sibling, then replace dest_dir.
    _atomic_write_context_dir(dest_dir, file_bytes)

    logger.debug(
        "chain_context: V2 install complete source=%s ref=%s files=%s",
        source_run_id,
        ref,
        list(file_bytes),
    )
    return True


# ---------------------------------------------------------------------------
# Legacy byte copier
# ---------------------------------------------------------------------------

def _install_legacy(
    *,
    ctx: Any,
    runner: Any,
    selection: Any,
    source_run_id: str,
    dest_dir: _pathlib.Path,
    chain_policy: str,
) -> bool:
    """Delegate to the kernel-supplied ``install_legacy_chain_context`` function.

    The function lives in ``app.agents.sandbox`` (an app-layer module) and must
    NOT be imported here directly.  The kernel exposes it through
    ``ctx.runner.install_legacy_chain_context``.  If the attribute is absent
    (older KernelServices version), fall back gracefully.

    Returns ``True`` on success, ``False`` when the install cannot proceed.
    Raises ``_TocTouError`` when the payload was present at admission but
    missing at copy time.
    """
    install_fn = getattr(runner, "install_legacy_chain_context", None)
    if not callable(install_fn):
        # KernelServices predates task 6.6 — degrade.
        logger.warning(
            "chain_context: runner has no install_legacy_chain_context; "
            "degrading for source=%s",
            source_run_id,
        )
        _emit_chain_context_unavailable(
            ctx,
            source_run_id=source_run_id,
            reason="source_payload_missing",
            chain_policy=chain_policy,
        )
        return False

    # open_source_sandbox is also needed for the source ReadOnlySandbox handle.
    try:
        source_sb = runner.open_source_sandbox(source_run_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "chain_context: open_source_sandbox failed for legacy source=%s: "
            "%s — emitting chain_context_unavailable",
            source_run_id,
            exc,
        )
        _emit_chain_context_unavailable(
            ctx,
            source_run_id=source_run_id,
            reason="source_payload_missing",
            chain_policy=chain_policy,
        )
        return False

    dest_dir.mkdir(parents=True, exist_ok=True)

    try:
        install_fn(selection, source_sb, dest_dir)
    except FileNotFoundError as exc:
        # File was present at admission but is gone now — TOCTOU.
        ref_val: str = getattr(selection, "ref", "") or ""
        raise _TocTouError(ref=ref_val, path=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "chain_context: install_legacy_chain_context failed for "
            "source=%s: %s",
            source_run_id,
            exc,
        )
        _emit_chain_context_unavailable(
            ctx,
            source_run_id=source_run_id,
            reason="source_payload_missing",
            chain_policy=chain_policy,
        )
        return False

    return True


# ---------------------------------------------------------------------------
# Atomic directory write helper
# ---------------------------------------------------------------------------

def _atomic_write_context_dir(
    dest_dir: _pathlib.Path,
    file_bytes: dict[str, bytes],
) -> None:
    """Atomically MERGE ``file_bytes`` into ``dest_dir``.

    Writes each file to a temp sibling inside ``dest_dir``, then renames it
    into place via ``os.replace`` — atomic on POSIX and atomic on Windows for
    files on the same volume.  Pre-existing files under ``dest_dir`` (e.g.
    ``.context/design/`` and ``.context/selections.json`` written by the
    opendesign provider) are **never touched**.

    Staging the temp inside ``dest_dir`` (rather than in the parent) guarantees
    src and dst are on the same filesystem mount, which is required for
    ``os.replace`` to be atomic.

    Only the three flat payload files are written — no subdirectories.

    BUG-126 / B24: the previous implementation called ``shutil.rmtree(dest_dir)``
    before renaming a staging directory over it, destroying any pre-existing
    content.  This merge strategy replaces that wholesale swap.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    for name, data in file_bytes.items():
        dest_file = dest_dir / name
        tmp_path: _pathlib.Path | None = None
        try:
            fd, tmp_str = _tempfile.mkstemp(
                prefix=f".chain-stage-{name}-",
                dir=str(dest_dir),
            )
            tmp_path = _pathlib.Path(tmp_str)
            with _os.fdopen(fd, "wb") as fh:
                fh.write(data)
            tmp_path.replace(dest_file)
            tmp_path = None  # replace succeeded — nothing left to clean up
        except Exception:
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:  # noqa: BLE001
                    pass
            raise


# ---------------------------------------------------------------------------
# mark_chain_context_installed
# ---------------------------------------------------------------------------

def _mark_chain_context_installed(
    ctx: Any,
    runner: Any,
    *,
    installed: bool,
) -> None:
    """Upsert the ``run_finalizations`` row with ``chain_context_installed``.

    This is the ONE writer of the ``chain_context_installed`` flag
    (Requirement 21 AC 8).  It upserts the receiving run's row at install
    time, BEFORE agent 1, so the column is durable regardless of whether the
    run later finalizes normally.

    Best-effort: a DB failure is logged but never propagated.  The run
    continues whether or not the mark persists.

    Reached via deferred import of ``finalization.py`` inside the function body
    so this capability module stays free of all ``app.*`` and
    ``agents.execution_engine.*`` imports at module level.
    """
    run_id: str = getattr(ctx, "run_id", "") or ""
    owner_id: str = getattr(ctx, "owner_id", "") or ""
    workspace_id: str = getattr(ctx, "workspace_id", "") or ""

    if not run_id:
        logger.warning(
            "chain_context: _mark_chain_context_installed: ctx.run_id is empty — "
            "cannot upsert chain_context_installed=%s",
            installed,
        )
        return

    # Delegate to a kernel-exposed helper when available (preferred path).
    mark_fn = getattr(runner, "mark_chain_context_installed", None)
    if callable(mark_fn):
        try:
            mark_fn(run_id, installed=installed)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "chain_context: runner.mark_chain_context_installed(run=%s "
                "installed=%s) failed: %s",
                run_id,
                installed,
                exc,
            )
        return

    # mark_chain_context_installed is not available on this runner.
    # Log and return — the column will be updated by the finalizer's
    # persist_finalization_record call when the run completes.
    logger.warning(
        "chain_context: runner.mark_chain_context_installed not available for "
        "run=%s installed=%s — update deferred to finalization",
        run_id,
        installed,
    )


# ---------------------------------------------------------------------------
# Audit row
# ---------------------------------------------------------------------------

def _write_chain_payload_installed_audit(
    ctx: Any,
    runner: Any,
    selection: Any,
    source_run_id: str,
) -> None:
    """Write a best-effort ``chain_payload_installed`` audit row.

    Non-commit operation — written directly at this call site, NOT via the
    ``ProvenanceAuditObserver`` (per the comment in ``provenance_audit.py``).

    Uses ``runner.record_provenance_audit`` when available, falling back to a
    no-op gracefully.  A failure never aborts the run or the install.
    """
    record_fn = getattr(runner, "record_provenance_audit", None)
    if not callable(record_fn):
        return

    ref_val: str | None = getattr(selection, "ref", None)
    reason_class: str | None = getattr(selection, "reason_class", None)

    import asyncio as _asyncio  # noqa: PLC0415

    async def _write() -> None:
        try:
            await record_fn(
                run_id=getattr(ctx, "run_id", "") or "",
                operation="chain_payload_installed",
                source_ref=ref_val,
                tag_name=reason_class,  # re-used column for reason label
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "chain_context: chain_payload_installed audit write failed "
                "for source=%s: %s",
                source_run_id,
                exc,
            )

    # Fire-and-forget into the running loop.  If there is no running loop
    # (tests / offline) the coroutine is simply discarded.
    try:
        loop = _asyncio.get_running_loop()
        loop.create_task(_write())
    except RuntimeError:
        pass  # No running event loop — offline harness, no-op.


# ---------------------------------------------------------------------------
# Event emission helpers
# ---------------------------------------------------------------------------

def _emit_chain_context_unavailable(
    ctx: Any,
    *,
    source_run_id: str,
    reason: str,
    chain_policy: str,
) -> None:
    """Emit a ``chain_context_unavailable`` event and optionally fail the run.

    Under ``chain_policy: degrade``: emits the event, logs a warning, returns.
    Under ``chain_policy: refuse``: emits the event, then calls
    ``ctx.runner.fail_run`` if available — the run fails with the edge intact
    and ``chain_context_installed = false`` as the durable discriminator
    (departure N3 / Requirement 6 AC 16).

    Event format matches Requirement 20 AC 4-5:
    - No file contents, diffs, secrets, internal paths, or another owner's id.
    - One of the five bounded reason codes.
    - Non-color-only, programmatically associated.
    """
    run_id: str = getattr(ctx, "run_id", "") or ""
    runner = getattr(ctx, "runner", None)

    event_payload: dict[str, object] = {
        "event": _REASON_UNAVAILABLE,
        "source_run_id": source_run_id,
        "reason": reason,
    }

    # Try to enqueue via the engine's event queue (same path as emit_hook_event).
    queue = getattr(ctx, "event_queue", None)
    if queue is None and runner is not None:
        queue = getattr(getattr(runner, "_ectx", None), "event_queue", None)

    if queue is not None:
        try:
            queue.put_nowait({
                "type": _REASON_UNAVAILABLE,
                "data": event_payload,
            })
        except Exception:  # noqa: BLE001
            pass

    logger.warning(
        "chain_context: %s for run=%s source=%s reason=%s policy=%s",
        _REASON_UNAVAILABLE,
        run_id,
        source_run_id,
        reason,
        chain_policy,
    )

    # Under refuse policy: fail the run so the edge is preserved but the run
    # does not proceed without context (departure N3).
    if chain_policy == "refuse":
        fail_fn = getattr(runner, "fail_run", None) if runner is not None else None
        if callable(fail_fn):
            try:
                fail_fn(
                    _REASON_UNAVAILABLE,
                    detail={"source_run_id": source_run_id, "reason": reason},
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "chain_context: fail_run(%s) raised for run=%s: %s",
                    _REASON_UNAVAILABLE,
                    run_id,
                    exc,
                )
        else:
            logger.error(
                "chain_context: chain_policy=refuse but ctx.runner.fail_run "
                "is not available — run=%s will continue without chain context "
                "(departure N3 enforcement point missing)",
                run_id,
            )


def _resolve_install_toctou(
    ctx: Any,
    *,
    source_run_id: str,
    chain_policy: str,
    ref: str,
    path: str,
) -> None:
    """Handle the one remaining in-run failure: validated bytes vanished.

    Logs, emits ``chain_context_unavailable``, and marks ``installed=False``.
    The caller determines whether to fail or continue per policy.
    """
    runner = getattr(ctx, "runner", None)
    logger.warning(
        "chain_context: TOCTOU — ref=%r path=%r absent for source=%s",
        ref,
        path,
        source_run_id,
    )
    _emit_chain_context_unavailable(
        ctx,
        source_run_id=source_run_id,
        reason=_REASON_UNAVAILABLE,
        chain_policy=chain_policy,
    )
    _mark_chain_context_installed(ctx, runner, installed=False)


# ---------------------------------------------------------------------------
# Internal exception for TOCTOU
# ---------------------------------------------------------------------------

class _TocTouError(Exception):
    """Raised when a file present at admission is absent at copy time."""

    def __init__(self, *, ref: str, path: str) -> None:
        super().__init__(f"TOCTOU: ref={ref!r} path={path!r}")
        self.ref = ref
        self.path = path


# ---------------------------------------------------------------------------
# Sandbox base-path resolver
# ---------------------------------------------------------------------------

def _resolve_sandbox_base(sandbox: Any) -> _pathlib.Path | None:
    """Return the absolute base path of *sandbox*, or ``None`` if unresolvable.

    Tries ``sandbox.root`` first (``RunSandbox`` v2 attribute), then
    ``sandbox.base_path``.  Falls back to ``None`` rather than raising, so
    the caller can degrade gracefully.
    """
    for attr in ("root", "base_path"):
        val = getattr(sandbox, attr, None)
        if val is not None:
            try:
                return _pathlib.Path(str(val))
            except Exception:  # noqa: BLE001
                continue
    return None


# ---------------------------------------------------------------------------
# Legacy helper (kept for tests that call it directly)
# ---------------------------------------------------------------------------

def _list_chain_files(sandbox: Any, prefix: str) -> list[str]:
    """Return relative paths of all files under ``prefix`` inside ``sandbox``.

    Tries the sandbox's ``list_files`` method first (which returns paths
    relative to the sandbox root).  Falls back to a best-effort directory walk
    via the sandbox's ``base_path`` attribute when ``list_files`` is absent
    (e.g. in tests using a lightweight stub sandbox).

    Returns paths relative to ``prefix/`` — e.g. ``"summary.md"`` and
    ``"logs/run-abc.jsonl"``.  Raises on any unrecoverable error so the caller
    can apply graceful degradation.

    .. note::
        This helper is preserved as a public-ish helper for tests in
        ``tests/agents/test_phase5_chaining.py`` (``TestListChainFiles``).
        The ``load()`` path no longer uses it — it goes through the selection
        dispatch introduced by task 6.6.
    """
    # Normalise prefix: no trailing slash.
    prefix = prefix.rstrip("/")

    # Path A: sandbox exposes list_files (RunSandbox does).
    list_files_fn = getattr(sandbox, "list_files", None)
    if list_files_fn is not None:
        try:
            all_paths: list[str] = list(list_files_fn() or [])
        except Exception:  # noqa: BLE001
            all_paths = []

        matching: list[str] = []
        for p in all_paths:
            norm = p.lstrip("/")
            if norm.startswith(f"{prefix}/"):
                rel = norm[len(prefix) + 1:]
                if rel:
                    matching.append(rel)
        return matching

    # Path B: sandbox exposes a base_path (test stubs, LocalWorkspace).
    base_path = getattr(sandbox, "base_path", None)
    if base_path is None:
        # No list_files and no base_path — nothing to walk.
        return []

    abs_prefix = _os.path.join(str(base_path), *prefix.split("/"))
    if not _os.path.isdir(abs_prefix):
        return []

    result: list[str] = []
    for dirpath, _dirnames, filenames in _os.walk(abs_prefix):
        for fname in filenames:
            abs_file = _os.path.join(dirpath, fname)
            rel = _os.path.relpath(abs_file, abs_prefix)
            # Normalise to forward slashes for consistency.
            result.append(rel.replace(_os.sep, "/"))
    return result
