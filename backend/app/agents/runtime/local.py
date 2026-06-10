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
import resource
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from agents.capabilities.registry import register
from agents.runtime.base import ExecutionPolicy, RuntimeEnvironment, Workspace
from app.agents.sandbox import RunSandbox
from app.core.config import settings


# The v1 "ephemeral creds" posture: the child sees ONLY these env keys (constructed,
# NOT inherited). Excludes every host credential (AWS_*/ANTHROPIC_*/DATABASE_URL/
# *_TOKEN/*_PROXY) — T-10-01-03.
_SCRUBBED_ENV_KEYS = ("PATH", "HOME", "TMPDIR")

# 64KB/stream output truncation (T-10-01-06): only a bounded slice is returned, and
# only a truncated digest is ever audited (never the raw child output, which could
# carry a secret).
_OUTPUT_CAP = 65536


@dataclass(frozen=True)
class _ExecProfile:
    """The N3-locked exec profile — allow-list + caps. NEVER manifest-tunable."""

    exec_allow: tuple = ()
    exec_deny: tuple = ()
    cpu_seconds: int = 60
    mem_mb: int = 512
    wall_seconds: int = 120


# The single locked exec profile a security-gated, exec-granted workspace uses
# (per N3: Python toolchain allow-list; cpu=60s mem=512MB wall=120s). The caps are
# locked here, not tunable from a manifest.
DEFAULT_EXEC_PROFILE = _ExecProfile(
    exec_allow=("python", "python3", "pytest", "ruff"),
    exec_deny=(),
    cpu_seconds=60,
    mem_mb=512,
    wall_seconds=120,
)


def _noop_recorder(
    argv,
    *,
    outcome: str,
    exit_code: int | None = None,
    duration_ms: int | None = None,
    policy_snapshot=None,
    output_digest: str | None = None,
) -> None:  # default audit sink (no-op)
    """Default workspace recorder — a no-op so non-audited callers don't crash.

    Pins the SINGLE recorder contract every ``exec_command`` call site honors and
    every injected recorder must match (CR-01): ``argv`` positional + keyword-only
    ``outcome`` (required) and optional ``exit_code`` / ``duration_ms`` /
    ``policy_snapshot`` / ``output_digest``. The contract is step-FREE — the
    workspace has no concept of a step id; the engine's injected adapter (10-02
    host seam) captures the run-scoped step id and bridges to the async
    ``KernelServices.record_exec_run``. Until exec is granted this no-op is dormant.
    """
    return None


@dataclass
class LocalExecutionPolicy:
    """The capability gate — exec / network / secrets default OFF (until N3).

    Satisfies the ``ExecutionPolicy`` port structurally. ``allows`` returns the
    flag for the named action; unknown actions are denied by default. Phase 10
    grows the policy with the exec allow/deny lists + resource caps (the
    enforcement data the hardened ``exec_command`` reads); ``allows("exec")``
    still returns ``self.exec`` byte-identically (the deny default is unchanged).
    """

    exec: bool = False
    network: bool = False
    secrets: list = field(default_factory=list)
    # Phase 10 — exec allow/deny + caps (the EXEC-PROFILE / EXEC-POLICY data).
    exec_allow: tuple = ()
    exec_deny: tuple = ()
    cpu_seconds: int = 60
    mem_mb: int = 512
    wall_seconds: int = 120

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
        # The audit callback invoked on EVERY exec_command outcome (allowed/denied/
        # killed) — defaults to a no-op so non-audited callers don't crash; the live
        # recorder (KernelServices.record_exec_run) is injected at create_workspace
        # by 10-02's host seam. Bypass-proof: the recorder fires at the enforcement
        # point regardless of caller path (T-10-01-07).
        self._recorder = _noop_recorder

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

    # -- exec (hardened argv body — the SINGLE enforcement point) -------------

    def exec_command(self, argv: list[str]) -> str:
        """Run ``argv`` (no shell) under the policy — the bypass-proof enforcement.

        Layered enforcement (everything an exec-granted workspace reaches exec
        through; all downstream gates/validators come HERE):
          1. deny default (T-09-01-02 unchanged): exec OFF → record denied + raise.
          2. pre-spawn allow/deny (deny BEATS allow, T-10-01-02): argv[0] must be
             allow-listed and not deny-listed — recorded + raised BEFORE any spawn.
          3. scrubbed minimal env (T-10-01-03): the child sees only PATH/HOME/TMPDIR,
             never host creds.
          4. POSIX rlimits in a preexec_fn + wall-clock timeout + start_new_session
             (T-10-01-04): RLIMIT_CPU/RLIMIT_AS bound the child; a runaway is killed
             at the wall clock; start_new_session makes a forking runaway killable as
             a group.
          5. 64KB/stream truncation (T-10-01-06).

        ACCEPTED RESIDUAL (T-10-01-05 / EGRESS-DENY): an allow-listed interpreter can
        still open sockets at runtime — ``policy.network=False`` + the no-net-capable
        allow-list + the scrubbed env mitigate but do NOT hard-block egress. OS-level
        network-namespace enforcement is the v2 ECS seam; exec is engineer-only +
        ``security``-gated, so this residual is documented + accepted (per N3).
        """
        # (1) deny default — byte-identical to the pre-Phase-10 behavior (T-09-01-02).
        if not self.policy.allows("exec"):
            self._recorder(argv, outcome="denied", exit_code=None)
            raise PermissionError(
                "exec_command denied: ExecutionPolicy.exec is OFF "
                "(code execution stays disabled until N3 / Phase 4B)"
            )

        # (2) pre-spawn allow/deny — deny BEATS allow, recorded BEFORE any spawn.
        cmd = argv[0]
        if cmd in self.policy.exec_deny or cmd not in self.policy.exec_allow:
            self._recorder(argv, outcome="denied", exit_code=None)
            raise PermissionError(
                f"exec_command denied: {cmd!r} not permitted by ExecutionPolicy"
            )

        # (3) scrubbed minimal env — constructed, never inherited (no host creds).
        env = {k: os.environ[k] for k in _SCRUBBED_ENV_KEYS if k in os.environ}

        # (4) child-only resource caps (preexec_fn runs after fork, before exec).
        cpu = self.policy.cpu_seconds
        mem_bytes = self.policy.mem_mb * 1024 * 1024

        def _limits() -> None:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
            # RLIMIT_AS is hard-enforced on linux, best-effort on darwin (Pitfall 4).
            try:
                resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
            except (ValueError, OSError):
                pass  # darwin may refuse; the wall-clock timeout still bounds the run

        started = time.monotonic()
        try:
            proc = subprocess.run(
                argv,
                cwd=str(self._root),
                shell=False,  # shell=False is the IN-02 fix (no shell interpolation)
                env=env,
                capture_output=True,
                text=True,
                timeout=self.policy.wall_seconds,
                preexec_fn=_limits,
                start_new_session=True,  # so killpg can kill a forking runaway tree
            )
        except subprocess.TimeoutExpired:
            self._recorder(
                argv,
                outcome="killed",
                exit_code=None,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            raise  # the runaway was killed at the wall-clock timeout

        # (5) 64KB/stream truncation.
        out = (proc.stdout or "")[:_OUTPUT_CAP]
        self._recorder(
            argv,
            outcome="allowed",
            exit_code=proc.returncode,
            duration_ms=int((time.monotonic() - started) * 1000),
            output_digest=out[:256],
        )
        return out

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
        recorder=None,
    ) -> Workspace:
        """Provision a local-disk ``Workspace`` for one run.

        ``has_git`` is advisory (the local backend always supports git). ``exec``
        now flows LIVE into the policy: when ``True`` the workspace is granted the
        N3-locked ``DEFAULT_EXEC_PROFILE`` (allow-list + caps) behind the security
        gate; when ``False`` the policy is byte-identical to the pre-Phase-10 deny
        default (exec/network/secrets all OFF) so every existing non-exec run is
        unchanged (parity). ``recorder`` is the audit callback invoked on every
        ``exec_command`` outcome (defaults to a no-op so non-audited callers don't
        crash); 10-02's host seam injects ``KernelServices.record_exec_run``.
        """
        sandbox = RunSandbox(owner_id, workspace_id, runs_root=settings.RUNS_ROOT)
        if exec:
            policy = LocalExecutionPolicy(
                exec=True,
                network=False,
                secrets=[],
                exec_allow=DEFAULT_EXEC_PROFILE.exec_allow,
                exec_deny=DEFAULT_EXEC_PROFILE.exec_deny,
                cpu_seconds=DEFAULT_EXEC_PROFILE.cpu_seconds,
                mem_mb=DEFAULT_EXEC_PROFILE.mem_mb,
                wall_seconds=DEFAULT_EXEC_PROFILE.wall_seconds,
            )
        else:
            # Byte-identical to the pre-Phase-10 deny default (parity for every
            # existing non-exec run — the exec layer is dormant).
            policy = LocalExecutionPolicy(exec=False, network=False, secrets=[])
        ws = LocalWorkspace(  # type: ignore[return-value]
            owner_id=owner_id,
            workspace_id=workspace_id,
            runtime=self,
            policy=policy,
            sandbox=sandbox,
        )
        if recorder is not None:
            ws._recorder = recorder
        return ws

    def teardown(self, ws: Workspace) -> None:
        ws.teardown()
