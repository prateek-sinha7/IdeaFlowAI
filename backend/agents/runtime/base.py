"""agents/runtime/base.py — runtime port layer (RUNTIME-01 / §6 / D-01).

The hexagonal port boundary (Ports & Adapters) for workspace provisioning +
isolation: the kernel depends ONLY on these ``typing.Protocol`` ports; the
concrete impl (``LocalSandboxRuntime``, app-side) self-registers and satisfies
them structurally. Adding a runtime backend = add a module that implements
``RuntimeEnvironment`` + register it — no kernel edit (the ECS-swap seam, D-01:
a later ``EcsRuntime.create_workspace()`` returns a remote-backed ``Workspace``
with zero engine change).

Scope (Phase 09):
  - Interface-only. No bodies, no implementations (the local impl lands app-side
    in ``app/agents/runtime/local.py``).
  - This module imports ONLY stdlib ``typing``. It must NOT import the kernel
    engine package (``agents.execution_engine``) or the web/app layer (``app``)
    — the 4th import-linter contract (T-09-01-03) keeps the kernel->ports
    direction one-way.

The runtime objects a port method receives/returns (per-run dirs, diff strings,
search hits) are concrete in the impl; to keep this port module free of inbound
dependencies, signature positions that would otherwise reference impl types are
typed ``Any``.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ExecutionPolicy(Protocol):
    """The capability gate for a Workspace (security defaults OFF until N3).

    ``exec`` / ``network`` / ``secrets`` default to OFF/none; ``allows(action)``
    returns ``False`` for ``exec`` / ``network`` / ``secrets`` by default. The
    no-exec invariant for this phase is enforced here: a ``Workspace`` consults
    its ``policy.allows("exec")`` before ``exec_command`` and raises when denied.
    """

    exec: bool
    network: bool
    secrets: list

    def allows(self, action: str) -> bool:
        """Return ``True`` iff ``action`` is permitted under this policy."""
        ...


@runtime_checkable
class Workspace(Protocol):
    """A provisioned, isolated workspace facade (the RunSandbox successor surface).

    Carries its ``owner_id`` / ``workspace_id``, a back-ref to the provisioning
    ``runtime`` (the ``RuntimeEnvironment``), and the ``policy`` gating exec. All
    untrusted relpaths cross the read/write/search/clone boundary and must stay
    repo-relative under the run root (traversal-rejection, T-09-01-01).
    """

    owner_id: str
    workspace_id: str
    runtime: Any  # back-ref to the RuntimeEnvironment that provisioned this
    policy: ExecutionPolicy

    def read_file(self, relpath: str) -> Any:
        """Read a file under the run root (rejects path escapes)."""
        ...

    def write_file(self, relpath: str, content: str) -> Any:
        """Write a file under the run root (rejects path escapes)."""
        ...

    def search(self, query: str) -> Any:
        """Search the workspace tree for ``query``, returning the hits."""
        ...

    def clone_repo(self, source: str) -> Any:
        """Clone a repo (local path or URL) into the run root."""
        ...

    def create_branch(self, name: str) -> Any:
        """Create + check out a local branch in the cloned repo."""
        ...

    def git_diff(self, base: str, work: str) -> Any:
        """Return the unified diff between two refs (``git diff base..work``)."""
        ...

    def exec_command(self, argv: list[str]) -> Any:
        """Run an argv command (no shell — the IN-02 fix; Phase 10 / EXEC-01).

        DENIED under the default policy (raises ``PermissionError`` when exec is
        OFF). When exec is granted, ``argv[0]`` must be allow-listed (deny beats
        allow), the child runs with a scrubbed minimal env + POSIX rlimits + a
        wall-clock timeout, and output is truncated at 64KB/stream. EVERY outcome
        (allowed/denied/killed) is audited at this enforcement point (T-10-01-07).
        """
        ...

    def teardown(self) -> Any:
        """Remove the workspace's on-disk run dir (idempotent)."""
        ...


@runtime_checkable
class RuntimeEnvironment(Protocol):
    """Provisioner of ``Workspace`` instances — the ECS-swap seam (D-01).

    ``create_workspace`` returns a backend-specific ``Workspace`` (local disk
    now; remote-backed later) with zero engine change. The kernel imports only
    this port; the concrete impl is reached via the ``ctx.runner`` handle.
    """

    name: str

    def create_workspace(
        self,
        *,
        owner_id: str,
        workspace_id: str,
        has_git: bool = False,
        exec: bool = False,
    ) -> Workspace:
        """Provision + return an isolated ``Workspace`` for one run."""
        ...

    def teardown(self, ws: Any) -> None:
        """Tear down a previously provisioned ``Workspace`` (idempotent)."""
        ...


@runtime_checkable
class IsolationProvider(Protocol):
    """Allocates a ``Workspace`` for an isolation scope (N2 — granularity MVP).

    Scopes (all three now LIVE as of Phase 11 / FANOUT-05):
      * ``shared_read`` — per-run scope (09-02): the worker shares the parent run
        workspace; no per-worker isolation.
      * ``sub_sandbox`` — an isolated child dir ``{run}/subagents/{step}/{i}/`` under
        the run root; reads are shared-read of the parent refs, WRITES are isolated to
        the child dir (the no-git fan-out isolation default).
      * ``worktree`` — a git worktree off the run's working branch on a per-worker
        branch ``fanout/{step}/{i}``; the spawn-point HEAD commit is captured for the
        11-03 3-way merge-base. Used when the base workspace ``has_git=True``.

    The ENGINE (INV-7) selects the scope in ``run_fanout`` — it is NEVER read from
    the manifest. The local impl (``LocalWorkspace.allocate_sub_sandbox`` /
    ``allocate_worktree``) is the SINGLE git-subprocess owner for the worktree ops
    (Phase-9 D-10). The port signature is unchanged — this is additive doc only.
    """

    name: str

    def allocate(self, scope: str) -> Workspace:
        """Allocate a ``Workspace`` for ``scope`` (shared_read / sub_sandbox / worktree)."""
        ...
