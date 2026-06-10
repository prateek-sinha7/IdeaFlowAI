"""app/agents/runtime/local.py — the local-disk RuntimeEnvironment impl (RUNTIME-01).

``LocalSandboxRuntime`` provisions on-disk ``Workspace`` instances backed by the
per-run ``RunSandbox`` (the traversal-proof disk root + ``RUNS_ROOT`` reach — the
``app.*`` reason this lives app-side, NOT in the kernel). It is the SINGLE owner of
the git-subprocess surface for the repo workflows: ``clone_repo`` runs
``git clone <local-path>`` into the per-run dir, ``create_branch`` runs
``git checkout -b``, and ``git_diff`` runs ``git diff base..work``.

Security (this phase): exec stays OFF. The default ``ExecutionPolicy`` has
``exec=False`` / ``network=False`` / ``secrets=[]``, so ``exec_command`` raises
``PermissionError`` (T-09-01-02). It self-registers via
``@register("runtime_env", "local")`` — the distinct ``runtime_env`` kind (NOT the
``("runtime", "langchain_deepagents")`` agent-runtime adapter) — so the kernel
reaches it via the handle, never by import (the ECS-swap seam, D-01).
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from agents.capabilities.registry import register
from agents.runtime.base import ExecutionPolicy, RuntimeEnvironment, Workspace
from app.agents.sandbox import RunSandbox
from app.core.config import settings


@dataclass
class LocalExecutionPolicy:
    """The default capability gate — exec / network / secrets all OFF (until N3).

    Satisfies the ``ExecutionPolicy`` port structurally. ``allows`` returns the
    flag for the named action; unknown actions are denied by default.
    """

    exec: bool = False
    network: bool = False
    secrets: list = field(default_factory=list)

    def allows(self, action: str) -> bool:
        if action == "exec":
            return self.exec
        if action == "network":
            return self.network
        if action == "secrets":
            return bool(self.secrets)
        return False


class LocalWorkspace:
    """A local-disk ``Workspace`` rooted at a traversal-proof per-run dir.

    Wraps a :class:`RunSandbox` for the disk-safety (``path_for`` rejects ``..``
    escapes) and owns the git-subprocess surface (clone/branch/diff). The cloned
    repo lives directly at the run root so ``read_file``/``write_file``/``search``
    operate over the working tree.
    """

    def __init__(
        self,
        *,
        owner_id: str,
        workspace_id: str,
        runtime: "LocalSandboxRuntime",
        policy: ExecutionPolicy,
        sandbox: RunSandbox,
    ) -> None:
        self.owner_id = owner_id
        self.workspace_id = workspace_id
        self.runtime = runtime
        self.policy = policy
        self._sandbox = sandbox
        self._root: Path = sandbox.ensure()

    # -- filesystem (traversal-proof via RunSandbox.path_for) ----------------

    def read_file(self, relpath: str) -> str:
        path = self._sandbox.path_for(relpath)  # raises ValueError on escape
        return path.read_text(encoding="utf-8")

    def write_file(self, relpath: str, content: str) -> Path:
        path = self._sandbox.path_for(relpath)  # raises ValueError on escape
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def search(self, query: str) -> list[str]:
        """Return ``rel:line:text`` hits for ``query`` across the working tree.

        A simple stdlib content grep over the cloned tree (the grep-vs-index
        threshold, N6/N10, is decided downstream — this is the offline default).
        Skips the ``.git`` dir and unreadable/binary files.
        """
        hits: list[str] = []
        for path in sorted(self._root.rglob("*")):
            if not path.is_file() or ".git" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            rel = path.relative_to(self._root).as_posix()
            for lineno, line in enumerate(text.splitlines(), start=1):
                if query in line:
                    hits.append(f"{rel}:{lineno}:{line}")
        return hits

    # -- git (the SINGLE git-subprocess owner) -------------------------------

    def _git(self, *args: str, env: dict[str, str] | None = None) -> str:
        result = subprocess.run(
            [
                "git",
                "-c",
                "user.name=Flowin Runtime",
                "-c",
                "user.email=runtime@flowin.local",
                "-c",
                "commit.gpgsign=false",
                *args,
            ],
            cwd=str(self._root),
            check=True,
            capture_output=True,
            text=True,
            env=env,  # None ⇒ inherit; clone threads a GIT_ALLOW_PROTOCOL guard
        )
        return result.stdout

    def clone_repo(self, source: str) -> Path:
        """Clone ``source`` (a local path or URL) into the run root.

        For a local-path source, reject any traversal of the run root for the
        clone TARGET (the source may be an absolute fixture path outside the root,
        which is expected). The clone populates the run root in place.

        Security (WR-01): ``source`` is host-injected (the §15 RepoSpec seam) and
        must NOT be able to execute code despite exec=OFF. Two git-native escapes
        are closed here: (a) the ``ext::``/``fd::`` transports run arbitrary
        commands at clone time — ``GIT_ALLOW_PROTOCOL`` restricts the clone to
        ``file``/``https``/``ssh``; (b) a source beginning with ``-`` is parsed
        by git as an OPTION (argument injection) — rejected up front, and ``--``
        terminates option parsing as defence in depth.
        """
        if source.startswith("-"):
            raise ValueError(
                f"refusing clone source that parses as a git option: {source!r}"
            )
        env = {**os.environ, "GIT_ALLOW_PROTOCOL": "file:https:ssh"}  # no ext::/fd::
        # Clone into the run root itself (``git clone -- src .`` requires an empty
        # dir; the freshly-ensured run dir is empty).
        self._git("clone", "--", source, ".", env=env)
        return self._root

    def create_branch(self, name: str) -> str:
        return self._git("checkout", "-b", name)

    def git_diff(self, base: str, work: str) -> str:
        """Diff ``base`` → ``work`` WITHOUT committing (WR-03: read-path, no commit).

        The repo_diff deliverable resolver calls this as a READ — it must never
        create a commit (the previous dirty-path ``git commit`` could land the
        edit on whatever branch happened to be checked out, corrupting ``base``
        and the diff). When ``work`` is the checked-out branch, uncommitted
        working-tree edits (incl. untracked files) are surfaced by staging to
        the INDEX only and diffing the index against ``base`` — which subsumes
        the committed ``base..work`` deltas. When ``work`` is NOT checked out,
        the working tree belongs to another branch, so only the committed
        ref-to-ref deltas are meaningful.
        """
        current = self._git("rev-parse", "--abbrev-ref", "HEAD").strip()
        if current == work:
            # Stage (index only, NO commit) so untracked files appear in the diff.
            self._git("add", "-A")
            return self._git("diff", "--cached", base)
        return self._git("diff", f"{base}..{work}")

    # -- exec (DENIED under the default policy) -------------------------------

    def exec_command(self, command: str) -> str:
        if not self.policy.allows("exec"):
            raise PermissionError(
                "exec_command denied: ExecutionPolicy.exec is OFF "
                "(code execution stays disabled until N3 / Phase 4B)"
            )
        # Reached only if a future phase flips exec ON behind the security gate.
        result = subprocess.run(
            command, cwd=str(self._root), shell=True, check=True,
            capture_output=True, text=True,
        )
        return result.stdout

    def teardown(self) -> None:
        # Delegates to the SINGLE rmtree owner (RunSandbox.cleanup). The cleanup
        # never routes back through this teardown — that one-way direction is what
        # keeps the sandbox<->workspace pair cycle-free (CR-01).
        self._sandbox.cleanup()


@register("runtime_env", "local")
class LocalSandboxRuntime:
    """The local-disk ``RuntimeEnvironment`` — provisions ``LocalWorkspace``s.

    The ECS-swap seam's local backend (D-01): a future ``EcsRuntime`` registers a
    different ``runtime_env`` name and returns a remote-backed ``Workspace`` with
    zero engine change. Self-registered as ``("runtime_env", "local")`` — NOT
    user-allowed (a runtime backend is an operator concern, not a user palette
    item), distinct from the ``("runtime", "langchain_deepagents")`` agent adapter.
    """

    name = "local"

    def create_workspace(
        self,
        *,
        owner_id: str,
        workspace_id: str,
        has_git: bool = False,
        exec: bool = False,
    ) -> Workspace:
        """Provision a local-disk ``Workspace`` for one run.

        ``has_git`` is advisory (the local backend always supports git); ``exec``
        flows into the policy but stays OFF this phase (the security gate ignores a
        ``True`` until N3 — the caller cannot enable exec yet).
        """
        sandbox = RunSandbox(owner_id, workspace_id, runs_root=settings.RUNS_ROOT)
        policy = LocalExecutionPolicy(exec=False, network=False, secrets=[])
        return LocalWorkspace(  # type: ignore[return-value]
            owner_id=owner_id,
            workspace_id=workspace_id,
            runtime=self,
            policy=policy,
            sandbox=sandbox,
        )

    def teardown(self, ws: Workspace) -> None:
        ws.teardown()
