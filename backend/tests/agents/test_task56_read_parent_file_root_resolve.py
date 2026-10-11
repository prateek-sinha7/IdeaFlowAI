"""Task 5.6 acceptance tests — read_parent_file root-resolves cross-run reads.

Requirement 5 AC3: ``kernel_services.KernelServices.read_parent_file`` MUST
root-resolve its target id before constructing the ``RunSandbox`` — a raw
``parent_run_id`` is wrong at chain depth two or deeper.

The canonical case is run-C (a revision of run-B which revised run-A).  The
shared sandbox directory is keyed on run-A (the chain root).  Before task 5.6,
``read_parent_file(run_B_id, ...)`` would look under ``RUNS_ROOT/user/run-B/``,
a directory nothing writes to — silently returning ``None``.  After the fix it
resolves run-B → run-A and reads from ``RUNS_ROOT/user/run-A/``.

These tests are pure unit tests.  They:
  * Bypass ``KernelServices.__init__`` (the offline harness pattern).
  * Patch ``_resolve_root_id`` at the source module so the deferred-import path
    in ``read_parent_file`` is intercepted without a real DB.
  * Patch ``RunSandbox.__init__`` to record what key was used, and
    ``RunSandbox.read`` to return a fixed payload.

No LLM calls, no real database, no filesystem access.

Requirement 5 ACs exercised:
  AC3  — read_parent_file root-resolves to the correct sandbox key.
  AC4  — graceful-degradation (genuine missing payloads) is NOT masked;
         the depth-2+ resolution failure that produced a silent empty read is
         fixed at the root, not patched by a broader try/except.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

if TYPE_CHECKING:
    from agents.execution_engine.kernel_services import KernelServices


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ks(*, disk_principal: str = "user-1") -> "KernelServices":
    """Build a KernelServices instance that bypasses __init__ (offline harness)."""
    from agents.execution_engine.kernel_services import KernelServices

    ks = KernelServices.__new__(KernelServices)

    class _Ectx:
        pass

    ectx = _Ectx()
    ectx.disk_principal = disk_principal
    ks._ectx = ectx
    return ks


def _patch_root_resolve(mapping: dict[str, str]):
    """Patch _resolve_root_id so that root_ids[run_id] is returned.

    The deferred import inside ``read_parent_file`` does:
        from agents.execution_engine.engine import _resolve_root_id
    We patch at that import source.
    """

    def _fake_resolve(run_id: str, owner_id: str) -> str:
        return mapping.get(run_id, run_id)

    return patch(
        "agents.execution_engine.engine._resolve_root_id",
        side_effect=_fake_resolve,
    )


def _patch_sandbox(*, reads: dict[str, str] | None = None):
    """Patch RunSandbox so __init__ records the run_id used and read() returns
    the provided ``reads`` mapping (keyed by file name)."""
    reads = reads or {}
    sandbox_inits: list[tuple[str, str]] = []  # [(disk_principal, run_id), ...]

    class _FakeSandbox:
        def __init__(self, disk_principal: str, run_id: str, **kwargs: object) -> None:
            sandbox_inits.append((disk_principal, run_id))
            self._run_id = run_id

        def read(self, name: str) -> str | None:
            return reads.get(name)

    return (
        patch("agents.execution_engine.kernel_services.RunSandbox", _FakeSandbox),
        sandbox_inits,
    )


# ---------------------------------------------------------------------------
# Tests — depth-2+ root resolution
# ---------------------------------------------------------------------------


class TestReadParentFileRootResolution:
    """read_parent_file must use the chain root id, not the raw parent id."""

    def test_depth1_chain_passes_root_unchanged(self) -> None:
        """At depth 1 (run-B → run-A is the root), the resolved id is run-A.

        When the chain walk resolves run-B to run-A, the sandbox is keyed on
        run-A — same behaviour as before for the depth-1 path.
        """
        ks = _make_ks(disk_principal="user-1")
        patch_ctx, inits = _patch_sandbox(reads={"spec.md": "spec content"})

        with _patch_root_resolve({"run-B": "run-A"}):
            with patch_ctx:
                result = ks.read_parent_file("run-B", "spec.md")

        assert result == "spec content", "file content must be returned"
        assert len(inits) == 1, "exactly one RunSandbox constructed"
        principal, sandbox_run_id = inits[0]
        assert sandbox_run_id == "run-A", (
            "RunSandbox must be keyed on the chain root (run-A), not the raw "
            "parent id (run-B)"
        )
        assert principal == "user-1"

    def test_depth2_chain_resolves_to_root(self) -> None:
        """At depth 2 (run-C revises run-B which revised run-A), run-B resolves
        to run-A.

        This is the core bug scenario from Requirement 5 AC3:
        read_parent_file("run-B", ...) used to look in run-B's sandbox (empty),
        now it follows the chain to run-A's sandbox (the shared family dir).
        """
        ks = _make_ks(disk_principal="user-1")
        patch_ctx, inits = _patch_sandbox(reads={"design.md": "design content"})

        # Chain: run-C's parent is run-B; run-B resolves to root run-A.
        with _patch_root_resolve({"run-B": "run-A", "run-C": "run-A"}):
            with patch_ctx:
                result = ks.read_parent_file("run-B", "design.md")

        assert result == "design content"
        principal, sandbox_run_id = inits[0]
        assert (
            sandbox_run_id == "run-A"
        ), "depth-2 chain: RunSandbox must use chain root run-A, not mid-chain run-B"

    def test_solo_run_resolves_to_itself(self) -> None:
        """A run with no chain (root = itself) is unchanged: self → self."""
        ks = _make_ks(disk_principal="user-1")
        patch_ctx, inits = _patch_sandbox(reads={"tasks.md": "tasks"})

        # No mapping entry → _resolve_root_id returns the id unchanged.
        with _patch_root_resolve({}):
            with patch_ctx:
                result = ks.read_parent_file("run-solo", "tasks.md")

        assert result == "tasks"
        _, sandbox_run_id = inits[0]
        assert sandbox_run_id == "run-solo"

    def test_resolve_root_id_called_with_correct_owner(self) -> None:
        """_resolve_root_id receives (parent_run_id, disk_principal), not owner_id.

        disk_principal is the decoupled on-disk sandbox key (D-09).  The IDOR
        guard inside _resolve_root_id is owner-scoped — passing disk_principal
        here is correct for authenticated runs where disk_principal == owner_id.
        """
        ks = _make_ks(disk_principal="user-42")
        patch_ctx, _ = _patch_sandbox()

        calls_made: list[tuple[str, str]] = []

        def _fake_resolve(run_id: str, owner_id: str) -> str:
            calls_made.append((run_id, owner_id))
            return run_id  # identity — no chain to follow

        with patch(
            "agents.execution_engine.engine._resolve_root_id", side_effect=_fake_resolve
        ):
            with patch_ctx:
                ks.read_parent_file("run-X", "spec.md")

        assert len(calls_made) == 1
        assert calls_made[0] == (
            "run-X",
            "user-42",
        ), "_resolve_root_id must be called with (parent_run_id, disk_principal)"

    def test_raw_parent_id_never_used_as_sandbox_key_at_depth2(self) -> None:
        """Regression guard: the raw mid-chain id must NEVER reach RunSandbox.

        Before the fix, RunSandbox was constructed with parent_run_id directly.
        This test asserts the resolved root id is used, not the raw input.
        """
        ks = _make_ks(disk_principal="user-1")
        patch_ctx, inits = _patch_sandbox(reads={"spec.md": "x"})

        with _patch_root_resolve({"run-mid": "run-root"}):
            with patch_ctx:
                ks.read_parent_file("run-mid", "spec.md")

        _, sandbox_run_id = inits[0]
        assert (
            sandbox_run_id != "run-mid"
        ), "raw mid-chain id 'run-mid' must NEVER be passed to RunSandbox"
        assert sandbox_run_id == "run-root"

    def test_missing_file_returns_none_not_masked(self) -> None:
        """Requirement 5 AC4: graceful-degradation for genuinely missing payloads
        must NOT be masked.  A file absent in the resolved sandbox returns None —
        _resolve_root_id resolving correctly is not a substitute for the file
        existing.
        """
        ks = _make_ks(disk_principal="user-1")
        # Sandbox exists (chain resolves correctly) but the file is absent.
        patch_ctx, inits = _patch_sandbox(reads={})  # no files

        with _patch_root_resolve({"run-B": "run-A"}):
            with patch_ctx:
                result = ks.read_parent_file("run-B", "nonexistent.md")

        # RunSandbox.read returns None for absent files — propagate that, don't mask it.
        assert (
            result is None
        ), "a genuinely absent file must return None, not a fabricated empty string"
        # Chain root was still resolved correctly.
        _, sandbox_run_id = inits[0]
        assert sandbox_run_id == "run-A"

    def test_disk_principal_passed_to_runsandbox(self) -> None:
        """The disk_principal (not owner_id) must be used as the RunSandbox user key."""
        ks = _make_ks(disk_principal="user-99")
        patch_ctx, inits = _patch_sandbox()

        with _patch_root_resolve({"run-B": "run-A"}):
            with patch_ctx:
                ks.read_parent_file("run-B", "spec.md")

        principal, _ = inits[0]
        assert (
            principal == "user-99"
        ), "RunSandbox must be keyed on disk_principal, not owner_id"
