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

import logging
import os
import re
import shutil

try:
    import resource  # Unix-only (Linux/macOS); not available on Windows
except ImportError:
    resource = None  # type: ignore[assignment]  # exec_command resource limits disabled on Windows
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from agents.capabilities.registry import register
from agents.runtime.base import ExecutionPolicy, Workspace
from app.agents.sandbox import RESERVED_PATHS, RunSandbox
from app.core.config import settings


class MergeRefusedError(Exception):
    """Raised when git refuses to start a merge (distinct from ran-and-found-conflicts).

    A refused merge means the working tree or index was not clean, git held a lock,
    HEAD was unborn, or another precondition prevented git from even beginning the
    merge operation.  Crucially, MERGE_HEAD is NOT written — so ``--diff-filter=U``
    returns nothing, and the result must NEVER be treated as ``conflicts: []``.
    """

    def __init__(self, branch: str, reason: str = "") -> None:
        self.branch = branch
        self.reason = reason
        super().__init__(f"git refused to start merge of {branch!r}: {reason}")


class GitCommandError(Exception):
    """Raised when a Git subprocess exits non-zero for any reason other than
    a clean no-change-to-commit outcome.

    Requirement 10 AC 7: ``commit_all`` must distinguish a genuine no-change
    exit (``NoChangeToCommit``) from every other Git failure.  Swallowing
    a real error as ``""`` makes a failed commit look identical to a clean tree,
    which silently loses worker output and makes finalization proceed past a
    broken state.
    """

    def __init__(self, argv: list[str], returncode: int, stderr: str = "") -> None:
        self.argv = argv
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(
            f"git command failed (exit {returncode}): {argv!r}; stderr: {stderr[:256]!r}"
        )


@dataclass(frozen=True)
class RefResult:
    """Typed return value from :meth:`LocalWorkspace.create_run_ref`.

    Requirement 5 AC 3 step 7 / V2-Q3: create-only compare-and-set semantics
    for the internal run ref ``refs/ideaflow/runs/{run_id}``.

    ``state`` is one of four values:
    - ``"created"``   — the ref did not exist and was just created.
    - ``"idempotent"`` — the ref already exists and points to the same commit.
    - ``"conflict"``  — the ref already exists but points to a different commit;
                        the ref is NOT moved.
    - ``"advanced"``  — returned only by :meth:`LocalWorkspace.advance_run_ref`:
                        the ref was moved via an explicit, caller-verified CAS
                        (the finalizer's legitimate-resume path).

    ``name``     — the full ref path (``refs/ideaflow/runs/{run_id}``).
    ``sha``      — the HEAD SHA at the time of the call.
    ``existing`` — the SHA the ref already pointed to on a ``"conflict"`` outcome;
                   ``None`` for ``"created"`` and ``"idempotent"``.
    """

    state: str  # "created" | "idempotent" | "conflict" | "advanced"
    name: str
    sha: str
    existing: str | None = None


@dataclass(frozen=True)
class CommitResult:
    """Typed return value from :meth:`LocalWorkspace.commit_all`.

    Requirement 10 AC 7: ``no_change`` surfaces the genuine no-change outcome
    without throwing, so callers can distinguish it from both success and error.
    ``sha`` is the full commit hash on a successful commit, ``""`` when
    ``no_change`` is True.
    """

    no_change: bool = False
    sha: str = ""


@dataclass(frozen=True)
class MaterializeResult:
    """Typed return value from :meth:`LocalWorkspace.materialize_tree_at_ref`.

    Requirement 9 (task 8.3): forward materialization of the tracked tree at a
    given ref without moving HEAD or any branch pointer.

    ``status`` is one of three values:
    - ``"materialized"``  — the tracked tree was written to the working directory.
    - ``"no_change"``     — the working tree already matches the ref; nothing was
                            written.
    - ``"error"``         — a git command failed; this state is only produced when
                            :class:`GitCommandError` cannot be raised (it should
                            always be raised instead, so this value is a defensive
                            sentinel).

    ``commit_sha`` is the full SHA that ``ref`` resolves to.  ``""`` on error.
    """

    status: str  # "materialized" | "no_change" | "error"
    commit_sha: str


logger = logging.getLogger("app.agents.runtime.local")

# Map a step id / worker-index into ONE safe path segment for the isolation child
# dir + the worktree branch (mirrors RunSandbox._safe_segment so an agent id with a
# slash/space can never introduce a path separator or a traversal sequence).
_UNSAFE_SEG = re.compile(r"[^A-Za-z0-9._-]")


def _seg(value: str) -> str:
    seg = _UNSAFE_SEG.sub("_", (value or "").strip()).strip(".")
    return (seg or "x")[:128]


class _ChildSandbox:
    """A RunSandbox-shaped facade rooted at an isolated child/worktree dir.

    Exposes exactly the ``Workspace``-backing surface ``LocalWorkspace`` consumes
    (``root`` / ``ensure`` / ``path_for`` / ``user_seg`` / ``run_seg`` / ``cleanup``)
    but rooted at an arbitrary dir UNDER the parent run root (the sub_sandbox child
    or the git worktree). Path-traversal safety is preserved: ``path_for`` rejects any
    escape of THIS child root. ``cleanup`` removes only the child dir (never the
    parent), so a worker teardown can never delete sibling/parent work.
    """

    def __init__(
        self, *, parent: RunSandbox, root: Path, user_seg: str, run_seg: str
    ) -> None:
        self._parent = parent
        self.root = root.resolve()
        self.user_seg = user_seg
        self.run_seg = run_seg

    def ensure(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    def path_for(self, relpath: str) -> Path:
        candidate = (self.root / str(relpath).lstrip("/")).resolve()
        # Structural containment via `is_relative_to` — a hardcoded "/" separator
        # string-prefix check never matches on Windows (`\` separators), which would
        # silently defeat this path-traversal confinement guard on that platform.
        if candidate != self.root and not candidate.is_relative_to(self.root):
            raise ValueError(f"path escapes isolated workspace: {relpath!r}")
        return candidate

    def cleanup(self) -> None:
        _rmtree_best_effort(self.root)


def _rmtree_best_effort(path: Path) -> None:
    """``shutil.rmtree`` that is best-effort like ``ignore_errors=True`` but first
    retries a read-only entry after clearing its write bit.

    Windows marks files under a cloned ``.git`` tree read-only, which makes a plain
    ``ignore_errors=True`` silently leave the whole tree behind (no exception, no
    deletion) — a real cross-platform cleanup gap, not just a test artifact.
    """
    import shutil

    def _on_rm_error(func, child_path, exc) -> None:
        try:
            os.chmod(child_path, 0o700)
            func(child_path)
        except OSError:
            pass

    shutil.rmtree(str(path), ignore_errors=False, onexc=_on_rm_error)


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
        has_git: bool = True,
    ) -> None:
        self.owner_id = owner_id
        self.workspace_id = workspace_id
        self.runtime = runtime
        self.policy = policy
        self._sandbox = sandbox
        self._root: Path = sandbox.ensure()
        # Phase 11 / FANOUT-05 (CR-06): whether this workspace is a git checkout.
        # STORED (not discarded) — the engine's isolation-scope selection
        # (``fanout._select_isolation_scope``) keys on this to pick ``worktree``
        # over ``sub_sandbox``. Set True by ``create_workspace(has_git=True)``,
        # by ``clone_repo`` (a clone IS a git checkout), and on every
        # ``allocate_worktree`` child.
        self.has_git = has_git
        # The audit callback invoked on EVERY exec_command outcome (allowed/denied/
        # killed) — defaults to a no-op so non-audited callers don't crash; the live
        # recorder (KernelServices.record_exec_run) is injected at create_workspace
        # by 10-02's host seam. Bypass-proof: the recorder fires at the enforcement
        # point regardless of caller path (T-10-01-07).
        self._recorder = _noop_recorder
        # Set by allocate_worktree on an isolated worktree workspace so the parent's
        # remove_worktree can delete the per-worker branch + dir (Phase 11 / FANOUT-05).
        self._worktree_branch: str | None = None
        self._worktree_path: Path | None = None

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

    def _git_env(self, env: dict[str, str] | None = None) -> dict[str, str]:
        # ISS-671/ISS-672: a ceiling at the root's parent stops git's upward repo
        # search, so a sandbox with no .git of its own fails closed ("not a git
        # repository") instead of reading tags/files from — and committing into —
        # whatever checkout encloses RUNS_ROOT.
        return {
            **(os.environ if env is None else env),
            "GIT_CEILING_DIRECTORIES": str(self._root.parent),
        }

    def _git(self, *args: str, env: dict[str, str] | None = None) -> str:
        result = subprocess.run(
            [
                "git",
                "-c",
                "user.name=Velocity Runtime",
                "-c",
                "user.email=runtime@velocity.local",
                "-c",
                "commit.gpgsign=false",
                *args,
            ],
            cwd=str(self._root),
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=self._git_env(
                env
            ),  # None ⇒ inherit; clone threads a GIT_ALLOW_PROTOCOL guard
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
        # A successful clone makes this workspace a git checkout (CR-06) — the
        # engine's fan-out isolation selection now sees has_git=True → worktree.
        self.has_git = True
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
        network-namespace enforcement is the v2 ECS seam; exec is engineer- or
        Composer-only (ISS-1114) + ``security``-gated, so this residual is documented
        + accepted (per N3).
        """
        # (1) deny default — byte-identical to the pre-Phase-10 behavior (T-09-01-02).
        if not self.policy.allows("exec"):
            self._recorder(argv, outcome="denied", exit_code=None)
            raise PermissionError(
                "exec_command denied: ExecutionPolicy.exec is OFF "
                "(code execution stays disabled until N3 / Phase 4B)"
            )

        # (2) pre-spawn allow/deny — deny BEATS allow, recorded BEFORE any spawn.
        # WR-02: guard empty argv BEFORE indexing argv[0] — an empty argv on an
        # exec-granted workspace must be a clean, AUDITED PermissionError, not an
        # unrecorded IndexError that escapes the single enforcement point.
        if not argv:
            self._recorder([], outcome="denied", exit_code=None)
            raise PermissionError("exec_command denied: empty argv")
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
            if resource is None:
                return  # Windows — resource limits not available; exec is disabled anyway
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
            # RLIMIT_AS is hard-enforced on linux, best-effort on darwin (Pitfall 4).
            try:
                resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
            except (ValueError, OSError):
                pass  # darwin may refuse; the wall-clock timeout still bounds the run

        started = time.monotonic()
        # POSIX-only Popen kwargs: `preexec_fn` and `start_new_session` (process-group
        # containment for os.killpg below) are rejected outright by CPython on Windows
        # (`ValueError: preexec_fn is not supported on Windows platforms`). Production
        # targets Linux (see module docstring); on Windows these are simply omitted —
        # the child then has no rlimits/group-kill containment, matching the fact that
        # this code path is dev-only there (exec is off by default; T-09-01-02).
        is_posix = os.name == "posix"
        popen_kwargs: dict = {}
        if is_posix:
            # WR-01: spawn via Popen + communicate(timeout=...) (NOT subprocess.run) so
            # the pid is RETAINED on TimeoutExpired — start_new_session=True puts the
            # child in its own process group, and on timeout we kill the WHOLE group
            # (os.killpg) so a forking runaway (e.g. pytest spawning workers) cannot
            # leave orphaned descendants past the wall-clock cap. subprocess.run only
            # SIGKILLs the direct child, defeating the documented group containment.
            popen_kwargs["preexec_fn"] = _limits
            popen_kwargs["start_new_session"] = (
                True  # so killpg can kill a forking runaway tree
            )
        proc = subprocess.Popen(
            argv,
            cwd=str(self._root),
            shell=False,  # shell=False is the IN-02 fix (no shell interpolation)
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",  # never crash the reader thread on a stray non-UTF-8 byte
            **popen_kwargs,
        )
        try:
            stdout, _stderr = proc.communicate(timeout=self.policy.wall_seconds)
        except subprocess.TimeoutExpired:
            # Kill the ENTIRE process group, not just the direct child (WR-01). On
            # Windows there is no process group to target — kill the direct child only.
            if is_posix:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass  # already gone / not permitted — best-effort group kill
            else:
                proc.kill()
            # Drain any partial output so the pipes close and the child reaps
            # cleanly; discard it (a killed run returns no stdout to the caller).
            try:
                proc.communicate(timeout=5)
            except (subprocess.TimeoutExpired, ValueError, OSError):
                pass
            self._recorder(
                argv,
                outcome="killed",
                exit_code=None,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            raise  # the runaway was killed at the wall-clock timeout

        # (5) 64KB/stream truncation.
        out = (stdout or "")[:_OUTPUT_CAP]
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

    # -- Phase-11 isolation scopes (FANOUT-05) -------------------------------
    #
    # Two engine-selected isolation scopes for a fan-out worker. The ENGINE (INV-7,
    # never the manifest) picks the scope in ``run_fanout``: ``worktree`` when this
    # base workspace ``has_git=True``, else ``sub_sandbox``. Both stamp the parent's
    # ``owner_id``/``workspace_id`` (T-11-02-05) and isolate worker WRITES so two
    # parallel workers cannot cross-contaminate before the 11-03 merge (T-11-02-02).
    # ``LocalWorkspace`` stays the SINGLE git-subprocess owner — the worktree git ops
    # live HERE (Phase-9 D-10), never capability-side.

    def allocate_sub_sandbox(self, step: str, worker_index: int) -> "LocalWorkspace":
        """Allocate an isolated child-dir workspace ``{run}/subagents/{step}/{i}/``.

        A ``has_git=False`` child rooted at a fresh dir UNDER the parent run root,
        reached through the traversal-proof ``path_for`` primitive (the step +
        worker-index segments are sanitised by the same RunSandbox safety the parent
        uses). Reads are shared-read of the parent run refs (Q20 — the child may read
        the parent run dir); WRITES land in the child dir ONLY, so two workers writing
        the SAME relpath never collide (T-11-02-02). The child is stamped with the
        SAME ``owner_id``/``workspace_id`` as the parent (T-11-02-05) and inherits the
        deny-default exec policy (exec=off).
        """
        rel = f"subagents/{_seg(step)}/{_seg(str(worker_index))}"
        child_root = self._sandbox.path_for(rel)  # raises on escape
        child_root.mkdir(parents=True, exist_ok=True)
        child_sandbox = _ChildSandbox(
            parent=self._sandbox,
            root=child_root,
            user_seg=self._sandbox.user_seg,
            run_seg=self._sandbox.run_seg,
        )
        return LocalWorkspace(  # type: ignore[return-value]
            owner_id=self.owner_id,
            workspace_id=self.workspace_id,
            runtime=self.runtime,
            policy=LocalExecutionPolicy(exec=False, network=False, secrets=[]),
            sandbox=child_sandbox,
        )

    def allocate_worktree(self, step: str, worker_index: int) -> "LocalWorkspace":
        """Allocate a git-worktree workspace on a per-worker branch.

        Runs ``git worktree add`` off the working branch onto a NEW branch
        ``fanout/{step}/{worker_i}`` via the ``_git`` owner (the ONLY place git is
        shelled — Phase-9 D-10). Returns a ``has_git=True`` ``LocalWorkspace`` rooted
        at the worktree dir, stamped owner/workspace. The worktree branch isolates the
        worker's commits/edits from the parent and from siblings (T-11-02-02). git ops
        reuse the SAME protocol/option guards the clone/branch path uses.
        """
        branch = f"fanout/{_seg(step)}/{_seg(str(worker_index))}"
        # The worktree dir lives under the run root (traversal-proof) but OUTSIDE the
        # tracked tree's working files — under ``.worktrees/`` so it is not picked up
        # as repo content. ``git worktree add`` requires the target dir NOT to exist.
        wt_rel = f".worktrees/{_seg(step)}/{_seg(str(worker_index))}"
        wt_root = self._sandbox.path_for(wt_rel)  # raises on escape
        wt_root.parent.mkdir(parents=True, exist_ok=True)
        # ``-b <branch>`` creates the per-worker branch at the worktree add.
        self._git("worktree", "add", "-b", branch, str(wt_root))
        wt_sandbox = _ChildSandbox(
            parent=self._sandbox,
            root=wt_root,
            user_seg=self._sandbox.user_seg,
            run_seg=self._sandbox.run_seg,
        )
        ws = LocalWorkspace(  # type: ignore[return-value]
            owner_id=self.owner_id,
            workspace_id=self.workspace_id,
            runtime=self.runtime,
            policy=LocalExecutionPolicy(exec=False, network=False, secrets=[]),
            sandbox=wt_sandbox,
            has_git=True,  # a worktree child IS a git checkout (CR-06)
        )
        # Stamp the per-worker branch so remove_worktree can delete it (happy path).
        ws._worktree_branch = branch
        ws._worktree_path = wt_root
        return ws

    def changed_since(self, base_commit: str) -> list[str]:
        """Relpaths changed in THIS checkout since ``base_commit`` (WR-03).

        The worktree fragment-scoping read: a worktree checkout contains the WHOLE
        repo, so the fan-out fragment collection must be restricted to the paths
        the worker actually touched. Returns the union of committed/staged/working
        deltas vs ``base_commit`` (``git diff --name-only``) plus untracked files
        (``git ls-files --others``), sorted. An empty ``base_commit`` or a git
        failure degrades to ``[]`` (no fragment — never a whole-repo fragment).
        """
        paths: set[str] = set()
        try:
            if base_commit:
                out = self._git("diff", "--name-only", base_commit)
                paths.update(p.strip() for p in out.splitlines() if p.strip())
            untracked = self._git("ls-files", "--others", "--exclude-standard")
            paths.update(p.strip() for p in untracked.splitlines() if p.strip())
        except subprocess.CalledProcessError:
            return []
        return sorted(paths)

    def git_init_sandbox(self) -> None:
        """Initialise the sandbox as a git repository with an initial commit.

        Idempotent: if ``.git/`` already exists the call returns immediately —
        a re-provisioned or resumed sandbox is never double-initialised.

        The initial commit is mandatory (Requirement 6 AC 2-3): ``git merge
        --no-ff`` into an unborn HEAD exits non-zero, and the existing
        ``merge_worktree`` implementation classifies that error as a refused
        merge (``MergeRefusedError``). Without at least one commit, every
        fan-out step on a has_git=True sandbox would fail at the first merge.

        Extension seam for task 2.2: ``_write_gitignore()`` is called between
        ``git init`` and the commit so that task 2.2 can seed the eight reserved
        paths in the same logical git-init call without restructuring this method.
        When ``.gitignore`` is present after ``_write_gitignore()`` the commit
        stages and captures it; when absent a ``--allow-empty`` sentinel commit
        is made instead so the branch has a valid HEAD either way.
        """
        if (self._root / ".git").exists():
            return  # already a git repo — idempotent, nothing to do

        self._git("init")
        self._write_gitignore()

        # Commit .gitignore if it was seeded; fall back to an empty sentinel
        # so HEAD is always born before any merge operation is attempted.
        gitignore_path = self._root / ".gitignore"
        if gitignore_path.exists():
            self._git("add", ".gitignore")
            self._git("commit", "-m", "chore: initialise sandbox")
        else:
            self._git("commit", "--allow-empty", "-m", "chore: initialise sandbox")

    # Requirement 8 AC 1 / Requirement 18 AC 1: derive from the canonical
    # RESERVED_PATHS registry so that adding a reserved path is a single edit
    # (V2-Q7). The tuple is sorted for a stable, deterministic .gitignore output.
    # ``conversation_history/`` was absent from the v1 literal list — proof of
    # the drift this registry exists to prevent. ``.chain-legacy/`` is the v2
    # addition for relocated legacy nested payloads, and is automatically included
    # because RESERVED_PATHS already contains it.
    _GITIGNORE_PATHS: tuple[str, ...] = tuple(sorted(RESERVED_PATHS))

    def _write_gitignore(self) -> None:
        """Write the sandbox ``.gitignore`` file covering all reserved prefixes.

        Called by :meth:`git_init_sandbox` between ``git init`` and the initial
        commit so that the reserved paths are captured in the same logical
        git-init operation (Requirement 18 AC 4 — seeded inside the same call,
        never in a separate step).

        The reserved paths are derived from ``RESERVED_PATHS`` (the canonical
        registry, V2-Q7 / Requirement 18 AC 1), so adding a new reserved path is
        a single edit to that registry. The current set (v2):
          .uploads/, .logs/, .verify/, .browser/, .agents/,
          .chain/, .context/, skills/, conversation_history/, .chain-legacy/

        ``.chain/`` is mandatory: without it the next revision's ``git add -A``
        would sweep the previous revision's chain payload into permanent history
        (Requirement 18 AC 4).  ``skills/`` is mandatory: ``stage_skills`` prunes
        and rewrites this directory on every invocation and it accumulates history
        if unignored (Requirement 18 AC 3).
        """
        content = "\n".join(self._GITIGNORE_PATHS) + "\n"
        # Also gitignore .figma/ — binary PNG design assets that should not be
        # git-tracked (agents write there but the files are not deliverable content;
        # leaving them untracked causes "degraded" finalization status).
        content += ".figma/\n"
        (self._root / ".gitignore").write_text(content, encoding="utf-8")

    def is_dirty(self) -> bool:
        """Return ``True`` when the working tree has uncommitted changes.

        Runs ``git status --porcelain`` and returns ``True`` when the output is
        non-empty — meaning staged, unstaged, or untracked files exist.  Returns
        ``False`` on a clean tree or when the repo has no commits yet (a fresh
        ``git init`` before the first commit is treated as clean for this check).
        Never raises: any git error (not a repo, I/O failure) is treated as
        "not dirty" so callers never abort on a best-effort status probe.
        Used by the wip-commit path (Requirement 26 / Requirement 27).
        """
        try:
            out = self._git("status", "--porcelain")
            return bool(out.strip())
        except Exception:  # noqa: BLE001 — probe is best-effort
            return False

    def commit_all(
        self,
        message: str,
        *,
        paths: list[str] | None = None,
        force_add: frozenset[str] | None = None,
    ) -> CommitResult:
        """Commit working-tree changes on THIS workspace's checked-out branch.

        The fan-out worker-teardown commit (CR-06): a worktree worker's edits must
        be COMMITTED on its per-worker branch before ``merge_worktree`` runs, or
        the 3-way merge reports "already up to date" and the uncommitted edits are
        destroyed by the ``remove_worktree --force`` teardown (worker output
        silently lost).

        Staging behaviour (Requirement 4 AC 11, Requirement 18 AC 5):
        - When ``paths`` is ``None`` (default) stages **all** changes with
          ``git add -A``, respecting the sandbox ``.gitignore`` — so reserved
          paths are excluded by the seeded gitignore, not by an ad-hoc filter.
        - When ``paths`` is a list, stages only those specific paths (``git add
          -- <paths>``), which lets the commit primitive stage exactly what it
          intends without sweeping unrelated changes.
        - ``force_add`` must be a frozenset returned by ``payload_allowlist()``
          — exactly three normalized paths, no arbitrary ``.chain`` prefix.
          Each path is staged with ``git add --force``.  Any path in
          ``force_add`` that is NOT in the frozenset produced by
          ``payload_allowlist`` with *some* valid basename is refused: this
          guard catches a caller that tries to smuggle an arbitrary reserved path
          through the force-add exception.

        Return value (Requirement 10 AC 7):
        - A successful commit returns ``CommitResult(no_change=False, sha=<sha>)``.
        - A genuine no-change (``git commit`` exits 1 with "nothing to commit")
          returns ``CommitResult(no_change=True, sha="")``.
        - Any other Git failure raises ``GitCommandError`` — a failed Git
          invocation must NEVER be indistinguishable from a clean tree.
        """
        # ── Validate force_add entries against the allowlist contract ────────
        # The force-add allowlist is exactly the three paths produced by
        # payload_allowlist(some_valid_basename). We validate by confirming every
        # entry starts with ".chain/" and has one of the three structural forms,
        # not by re-running payload_allowlist (which would require knowing the
        # basename). The structural check is sufficient: it prevents a caller from
        # passing an arbitrary reserved path (e.g. ".logs/secret") through the
        # force-add gate.
        if force_add is not None:
            for entry in force_add:
                if not entry.startswith(".chain/"):
                    raise ValueError(
                        f"commit_all: force_add entry {entry!r} is not a .chain/ "
                        f"payload path and cannot be force-staged (Requirement 18 AC 5)"
                    )
                # Normalize and confirm no path separator beyond the .chain/ prefix
                tail = entry[len(".chain/") :]
                if "/" in tail or "\\" in tail:
                    raise ValueError(
                        f"commit_all: force_add entry {entry!r} contains a nested "
                        f"path separator — only the three exact allowlist paths may be "
                        f"force-staged (Requirement 4 AC 14)"
                    )

        # ── Stage: force-add allowlist entries first, then the main set ─────
        # Force-add must precede the main stage so that a `.chain/` entry that
        # the gitignore would otherwise exclude is already in the index before
        # the non-force stage runs. Order is deterministic and idempotent.
        if force_add:
            for path in sorted(force_add):  # sorted for determinism
                self._git("add", "--force", "--", path)

        if paths is None:
            # Stage ALL changes — gitignore excludes reserved paths naturally.
            self._git("add", "-A")
        else:
            # Stage only the explicitly named paths.
            if paths:
                self._git("add", "--", *paths)

        # ── Commit ─────────────────────────────────────────────────────────
        try:
            sha_out = self._git("commit", "-m", message)
            # Extract the commit SHA from git's output if present; fall back to
            # rev-parse so callers always get a usable identifier.
            sha = ""
            try:
                sha = self._git("rev-parse", "HEAD").strip()
            except subprocess.CalledProcessError:
                # rev-parse failing after a successful commit is extremely unlikely;
                # return the raw commit output as the sha string so the caller is
                # not left with an empty identifier on a real commit.
                sha = sha_out.strip()[:40]
            return CommitResult(no_change=False, sha=sha)
        except subprocess.CalledProcessError as exc:
            # Distinguish a genuine "nothing to commit" from any real failure.
            # git exits 1 in both cases, but only the no-change case produces
            # one of two well-known phrases in its output.
            combined = (exc.stdout or "") + (exc.stderr or "")
            if "nothing to commit" in combined or "nothing added to commit" in combined:
                return CommitResult(no_change=True, sha="")
            raise GitCommandError(
                argv=["git", "commit", "-m", message],
                returncode=exc.returncode,
                stderr=(exc.stderr or "").strip(),
            ) from exc

    def create_tag(self, name: str) -> str:
        """Create a lightweight git tag named ``name`` on HEAD (Requirement 15).

        Reached by ``getattr`` duck-typing — the same pattern as ``commit_all``
        and ``allocate_worktree``.  NOT added to the ``Workspace`` Protocol so
        that three import-linter contracts remain green.

        Raises on failure (e.g. the tag already exists, no commits yet).  A tag
        creation failure must be VISIBLE — best-effort is explicitly wrong here
        because a tag is the permanent record that a version was produced.

        Returns the tag name on success so callers can write it to the DB column
        in one step (``git_tag = workspace.create_tag(name)``).
        """
        self._git("tag", name)
        return name

    def list_tags(self) -> list[str]:
        """List all lightweight and annotated tags in the sandbox (Requirement 15).

        Reached by ``getattr`` duck-typing — the same pattern as ``commit_all``
        and ``allocate_worktree``.  NOT added to the ``Workspace`` Protocol.

        Returns a sorted list of tag name strings.  Returns ``[]`` on any error
        (best-effort, non-raising) — callers such as the ref-validation gate
        (Requirement 16) receive an empty list and will correctly reject every
        ref when the tag list cannot be read.
        """
        try:
            out = self._git("tag", "--list")
            tags = sorted(t.strip() for t in out.splitlines() if t.strip())
            return tags
        except Exception:  # noqa: BLE001 — best-effort, must never raise
            return []

    # ── Internal run-ref namespace (refs/ideaflow/runs/) ────────────────────
    # V2-Q3 / Requirement 5 AC 3 step 7 / Requirement 7:
    # These three methods manage the trusted internal ref namespace.
    # They are reached via ``getattr`` duck-typing — NOT on the Workspace Protocol.

    _INTERNAL_REF_PREFIX = "refs/ideaflow/runs/"

    @staticmethod
    def _validate_run_id(run_id: str) -> None:
        """Validate that ``run_id`` is a safe, owned UUID suitable for ref construction.

        Guards the ref path against injection: the run_id must not be empty, must
        not be ``.`` or ``..``, and must not contain any path separator (``/`` or
        ``\\``) that would let a caller escape the ``refs/ideaflow/runs/`` namespace
        or introduce a traversal sequence.  Only UUID-shaped values (hex chars and
        hyphens) are accepted — no arbitrary strings are allowed through.

        Raises ``ValueError`` on any violation.
        """
        if not run_id:
            raise ValueError("run_id must not be empty")
        if run_id in (".", ".."):
            raise ValueError(f"run_id must not be '.' or '..': {run_id!r}")
        if "/" in run_id or "\\" in run_id:
            raise ValueError(f"run_id must not contain path separators: {run_id!r}")
        # Accept only UUID-shaped identifiers: hex digits and hyphens.
        if not re.fullmatch(r"[0-9a-fA-F-]+", run_id):
            raise ValueError(
                f"run_id must be a UUID (hex digits and hyphens only): {run_id!r}"
            )

    def create_run_ref(self, run_id: str) -> "RefResult":
        """Create the internal run ref ``refs/ideaflow/runs/{run_id}`` on HEAD.

        Implements create-only compare-and-set semantics (V2-Q3 / Requirement 5
        AC 3 step 7):
        - Absent  → create the ref, return ``state="created"``.
        - Present and pointing to the same commit as HEAD → return
          ``state="idempotent"`` (idempotent re-entry, no write).
        - Present and pointing to a DIFFERENT commit → return
          ``state="conflict"`` and do NOT move the ref.

        The ``run_id`` is validated before use: must be a UUID (hex chars and
        hyphens only), must not be ``.`` or ``..``, must contain no path
        separators.  It is NEVER accepted as a caller-supplied revspec.

        Reached by ``getattr`` duck-typing — NOT added to the ``Workspace``
        Protocol so that import-linter boundaries remain green.

        Returns a :class:`RefResult` with ``state``, ``name``, ``sha``, and
        (on conflict) ``existing``.

        Raises:
            ValueError: if ``run_id`` fails validation.
            subprocess.CalledProcessError: on an unexpected git failure.
        """
        self._validate_run_id(run_id)
        ref_name = f"{self._INTERNAL_REF_PREFIX}{run_id}"

        # Resolve HEAD SHA — required before we can check idempotency or write.
        head_sha = self._git("rev-parse", "HEAD").strip()

        # Check whether the ref already exists.
        existing_sha: str | None = None
        try:
            existing_sha = self._git("rev-parse", ref_name).strip()
        except subprocess.CalledProcessError:
            existing_sha = None  # ref does not exist yet

        if existing_sha is not None:
            # Ref already exists — check if it points to HEAD.
            if existing_sha == head_sha:
                return RefResult(
                    state="idempotent",
                    name=ref_name,
                    sha=head_sha,
                    existing=None,
                )
            # Points to a different commit — conflict, do not move the ref.
            return RefResult(
                state="conflict",
                name=ref_name,
                sha=head_sha,
                existing=existing_sha,
            )

        # Ref does not exist — create it with --create-reflog so the reflog
        # namespace is established (git requires --create-reflog for refs that
        # have no reflog yet; without it some git versions reject the write).
        self._git("update-ref", "--create-reflog", ref_name, head_sha)
        return RefResult(
            state="created",
            name=ref_name,
            sha=head_sha,
            existing=None,
        )

    def advance_run_ref(
        self, run_id: str, *, expected_sha: str, new_sha: str
    ) -> "RefResult":
        """Move the internal run ref from ``expected_sha`` to ``new_sha`` (CAS).

        Unlike :meth:`create_run_ref` (create-only, never moves an existing
        ref), this DOES move the ref — but only through git's own
        compare-and-swap (``update-ref <ref> <new> <old>``), which fails
        closed if the ref does not currently point at ``expected_sha``. The
        caller (the finalizer) is responsible for proving ``expected_sha`` is
        the run's own legitimate prior terminal commit — via a durable
        finalization record naming a resumable published status — before
        calling this. Reserved for the one case a run legitimately reaches a
        terminal state twice: cancelled/failed/degraded, then resumed
        (RESUME-18, ``POST /{run_id}/resume``) to a later, different terminal
        outcome.

        Raises ``ValueError`` on an invalid ``run_id``. Raises
        ``subprocess.CalledProcessError`` if the CAS fails (the ref no longer
        points at ``expected_sha``, or does not exist).
        """
        self._validate_run_id(run_id)
        ref_name = f"{self._INTERNAL_REF_PREFIX}{run_id}"
        self._git("update-ref", ref_name, new_sha, expected_sha)
        return RefResult(
            state="advanced", name=ref_name, sha=new_sha, existing=expected_sha
        )

    def resolve_ref_commit(self, run_id: str) -> str | None:
        """Return the commit SHA that ``refs/ideaflow/runs/{run_id}`` points to.

        Returns ``None`` when the ref does not exist.  Raises ``ValueError`` when
        ``run_id`` fails validation.  Raises ``subprocess.CalledProcessError`` on
        any unexpected git failure other than a missing ref.

        Requirement 7 / V2-Q3: used by the finalizer to read back the stored
        ref during idempotent re-entry.
        """
        self._validate_run_id(run_id)
        ref_name = f"{self._INTERNAL_REF_PREFIX}{run_id}"
        try:
            return self._git("rev-parse", ref_name).strip()
        except subprocess.CalledProcessError:
            return None  # ref does not exist

    def has_internal_run_ref(self, run_id: str) -> bool:
        """Return ``True`` if ``refs/ideaflow/runs/{run_id}`` exists.

        Best-effort: returns ``False`` on any git error (non-raising) so that
        callers such as the finalization idempotency gate never abort on a probe.
        Raises ``ValueError`` when ``run_id`` fails validation (caller error,
        not a git error — propagate so the caller can fix its input).

        Requirement 7 / V2-Q3.
        """
        self._validate_run_id(run_id)
        return self.resolve_ref_commit(run_id) is not None

    def read_file_at_ref(self, ref: str, relpath: str) -> bytes:
        """Return the raw bytes of ``relpath`` at ``ref`` without touching HEAD.

        Uses ``git show <ref>:<relpath>`` — the working tree NEVER moves
        (Requirement 17 AC3 / Requirement 18 AC1).

        ``ref`` MUST be pre-validated by the caller (e.g. ``_validate_ref`` in
        ``run_files.py``) before this is called — a free-form revspec from user
        input must NEVER reach a git subprocess directly (Requirement 16).

        Raises:
            subprocess.CalledProcessError: when ``git show`` fails (ref or path
            does not exist in that ref, or not a git repo).
        """
        out_bytes = subprocess.check_output(
            ["git", "show", f"{ref}:{relpath}"],
            cwd=self._root,
            stderr=subprocess.DEVNULL,
            env=self._git_env(),
        )
        return out_bytes

    def list_files_at_ref(self, ref: str) -> list[str]:
        """Return the list of file relpaths tracked at ``ref``.

        Uses ``git ls-tree -r <ref> --name-only`` — HEAD NEVER moves
        (Requirement 17 AC2 / Requirement 18 AC1).

        ``ref`` MUST be pre-validated by the caller before this is called
        (Requirement 16).

        Returns an empty list on any error (best-effort, non-raising).
        """
        try:
            out = subprocess.check_output(
                ["git", "ls-tree", "-r", ref, "--name-only"],
                cwd=self._root,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=self._git_env(),
            )
            return [p.strip() for p in out.splitlines() if p.strip()]
        except Exception:  # noqa: BLE001 — non-raising: callers handle empty list
            return []

    def file_sizes_at_ref(self, ref: str) -> dict[str, int]:
        """Return ``{relpath: byte size}`` for the blobs tracked at ``ref``.

        Uses ``git ls-tree -r -l <ref>`` — the long format appends an object-size
        column that ``--name-only`` (``list_files_at_ref``) drops. HEAD NEVER
        moves (Requirement 17 AC2 / Requirement 18 AC1).

        Keys are formatted exactly as ``list_files_at_ref`` returns them (same
        git path quoting), so the two line up key-for-key.

        Non-blob entries (submodules) carry ``-`` in the size column and are
        omitted — callers fall back to 0 for a path absent from this map.

        ``ref`` MUST be pre-validated by the caller before this is called
        (Requirement 16).

        Returns an empty dict on any error (best-effort, non-raising).
        """
        try:
            out = subprocess.check_output(
                ["git", "ls-tree", "-r", "-l", ref],
                cwd=self._root,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=self._git_env(),
            )
        except Exception:  # noqa: BLE001 — non-raising: callers handle an empty map
            return {}
        sizes: dict[str, int] = {}
        for line in out.splitlines():
            # "<mode> <type> <sha> <size>\t<path>" — size is "-" for submodules.
            meta, tab, path = line.partition("\t")
            fields = meta.split()
            if tab and path and len(fields) == 4 and fields[3].isdigit():
                sizes[path] = int(fields[3])
        return sizes

    def archive_at_ref(self, ref: str) -> bytes:
        """Build an in-memory zip archive of the sandbox at ``ref``.

        Uses ``git archive <ref> --format=zip`` entirely in memory — no
        temporary directory is created and HEAD NEVER moves (Requirement 17
        AC2 / Requirement 18 AC1).

        ``ref`` MUST be pre-validated by the caller before this is called
        (Requirement 16).

        Returns raw zip bytes.  Raises ``subprocess.CalledProcessError`` on
        any git error (e.g. ref does not exist).
        """
        return subprocess.check_output(
            ["git", "archive", ref, "--format=zip"],
            cwd=self._root,
            stderr=subprocess.DEVNULL,
            env=self._git_env(),
        )

    def materialize_tree_at_ref(self, ref: str) -> "MaterializeResult":
        """Materialize the tracked tree at ``ref`` into the working directory.

        Implements **forward materialization** (Requirement 9 / task 8.3):
        writes the file contents tracked at ``ref`` into the live working tree,
        then restores the index to HEAD — so the caller's subsequent
        ``commit_all`` / ``commit_in_sandbox`` call sees the new working-tree
        content as unstaged changes and can commit them as the next forward
        commit.

        Invariants that MUST hold after this call:
        - HEAD is unchanged — ``git rev-parse HEAD`` returns the same SHA as
          before the call.
        - No branch pointer has moved.
        - The index reflects HEAD (not ``ref``), so ``git status`` shows the
          materialized files as uncommitted working-tree modifications.

        Implementation strategy:
        1. Resolve ``ref`` to its commit SHA via ``git rev-parse <ref>^{commit}``
           — validates that the ref exists and is a commit (not a loose tree).
        2. Detect a genuine no-change: if ``ref`` resolves to the same SHA as
           HEAD the working tree already matches the ref.  Return early with
           ``status="no_change"`` — performing a no-op restore that leaves
           dozens of "modified" status lines would confuse the caller.
        3. Write the tracked tree using ``git restore --source=<sha> --worktree
           --no-overlay -- .``  (Git ≥ 2.23).  This command:
           - Writes the working-tree files tracked at ``<sha>`` into the
             current working directory.
           - Does NOT touch HEAD, any branch ref, or the index.
           - ``--no-overlay`` removes files that are tracked in the current
             HEAD commit but absent from ``ref``, so the working tree is an
             exact copy of ``ref``'s tracked content.
           Git 2.23+ is required; older versions do not have ``git restore``.
           The fallback (``git read-tree --reset <sha> && git checkout-index
           -a -f``) is deliberately NOT used: ``read-tree --reset`` replaces
           the index, and while ``reset_index`` would restore it, the sequence
           is non-atomic and harder to reason about under error conditions.
        4. Restore the index to HEAD via ``reset_index()`` so the newly
           materialized files appear as working-tree changes, not staged
           changes.  If this step fails after a successful ``git restore``, the
           GitCommandError is still raised — the caller must not commit from a
           corrupted index state.

        ``ref`` MUST be pre-validated by the caller (e.g. confirmed to be a
        known tag via ``list_tags()`` before being passed here) — a
        caller-supplied free-form revspec must NEVER reach a git subprocess
        without prior validation (Requirement 16 / task 8.1 gating contract).

        Returns:
            :class:`MaterializeResult` with:
            - ``status="materialized"`` and the resolved ``commit_sha`` on
              success.
            - ``status="no_change"`` and the resolved ``commit_sha`` when the
              working tree already matches the ref (HEAD == ref).

        Raises:
            :class:`GitCommandError`: on any git subprocess failure.  A failed
                git invocation is NEVER swallowed or returned as ``status="error"``
                — this matches the contract of ``commit_all`` (Requirement 10
                AC 7) and ensures restore failures are never silently ignored.
            subprocess.CalledProcessError: on unexpected git failures that do not
                fit the ``GitCommandError`` contract (e.g. rev-parse on a
                non-existent ref).
        """
        # Step 1 — Resolve the ref to a commit SHA.
        # ``<ref>^{commit}`` peels tags to their target commit and fails fast
        # if the ref does not exist or does not resolve to a commit.
        try:
            commit_sha = self._git("rev-parse", f"{ref}^{{commit}}").strip()
        except subprocess.CalledProcessError as exc:
            raise GitCommandError(
                argv=["git", "rev-parse", f"{ref}^{{commit}}"],
                returncode=exc.returncode,
                stderr=(exc.stderr or "").strip(),
            ) from exc

        # Step 2 — Detect genuine no-change: HEAD already equals ref.
        head_sha = self.head_commit()
        if head_sha and head_sha == commit_sha:
            return MaterializeResult(status="no_change", commit_sha=commit_sha)

        # Step 3 — Materialize the tracked tree without moving HEAD or the index.
        # ``git restore --source=<sha> --worktree --no-overlay -- .`` writes the
        # working-tree files tracked at <sha> and removes files absent from <sha>
        # (``--no-overlay``).  HEAD and all branch pointers are untouched.
        try:
            self._git(
                "restore",
                f"--source={commit_sha}",
                "--worktree",
                "--no-overlay",
                "--",
                ".",
            )
        except subprocess.CalledProcessError as exc:
            raise GitCommandError(
                argv=[
                    "git",
                    "restore",
                    f"--source={commit_sha}",
                    "--worktree",
                    "--no-overlay",
                    "--",
                    ".",
                ],
                returncode=exc.returncode,
                stderr=(exc.stderr or "").strip(),
            ) from exc

        # Step 4 — Restore the index to HEAD so the caller's commit sees the
        # materialized files as uncommitted working-tree changes rather than
        # staged changes.  ``reset_index()`` runs ``git reset HEAD -- .``.
        # A failure here is a hard error — do not proceed with a corrupted index.
        try:
            self.reset_index()
        except subprocess.CalledProcessError as exc:
            raise GitCommandError(
                argv=["git", "reset", "HEAD", "--", "."],
                returncode=exc.returncode,
                stderr=(exc.stderr or "").strip(),
            ) from exc

        return MaterializeResult(status="materialized", commit_sha=commit_sha)

    def git_gc_auto(self) -> None:
        """Run ``git gc --auto`` — fire-and-forget housekeeping (Requirement 35).

        ``git gc --auto`` only packs/prunes when the repo has crossed git's own
        auto-threshold (loose-object count, etc.), so it is cheap on most runs
        and only does real work when the repo has grown enough to warrant it.

        Logs a structured INFO line with the ``.git/`` directory size before and
        after so operators can observe per-run overhead (Requirement 35 AC 3).
        Never raises — a gc failure must never affect the run outcome (Requirement
        35 AC 2).
        """

        def _git_dir_bytes() -> int:
            """Sum the raw file sizes under ``.git/`` (the only thing gc touches)."""
            git_dir = self._root / ".git"
            if not git_dir.is_dir():
                return 0
            try:
                return sum(p.stat().st_size for p in git_dir.rglob("*") if p.is_file())
            except OSError:
                return 0

        try:
            before = _git_dir_bytes()
            self._git("gc", "--auto", "--quiet")
            after = _git_dir_bytes()
            logger.info(
                "git_gc_auto run=%s/%s git_dir_before_bytes=%d git_dir_after_bytes=%d git_dir_delta_bytes=%d",
                self._sandbox.user_seg,
                self._sandbox.run_seg,
                before,
                after,
                after - before,
            )
        except Exception:  # noqa: BLE001 — gc is best-effort, must never raise
            logger.debug("git_gc_auto: gc failed (non-fatal)", exc_info=True)

    def spawn_point_commit(self) -> str:
        """Capture the working-branch HEAD commit at spawn (the 11-03 merge-base).

        The 3-way merge in 11-03 needs the commit the worker branches diverged FROM.
        Captured via the ``_git`` owner; returns the full SHA (empty string if the
        repo has no commits yet — a fresh repo edge the merge handles).
        """
        try:
            return self._git("rev-parse", "HEAD").strip()
        except subprocess.CalledProcessError:
            return ""  # no commits yet — merge-base is the empty tree

    def remove_worktree(
        self, worktree_ws: "LocalWorkspace", *, delete_branch: bool = True
    ) -> None:
        """Remove a worktree workspace and optionally delete its per-worker branch.

        ``delete_branch=True`` (default): happy-path teardown after a successful merge
        — removes the worktree and deletes the ``fanout/{step}/{i}`` branch so
        ``git worktree list`` is left with ZERO orphans (T-11-02-04).

        ``delete_branch=False``: cancel-path teardown — removes the worktree but
        RETAINS the branch in git history so completed worker work is never permanently
        lost (Requirement 28).  The branch stays invisible in the version picker (which
        lists tags only) but is visible to ``git branch``.

        Best-effort per op so a partially-removed worktree never aborts the run.
        """
        branch = getattr(worktree_ws, "_worktree_branch", None)
        wt_path = getattr(worktree_ws, "_worktree_path", None)
        if wt_path is not None:
            try:
                self._git("worktree", "remove", "--force", str(wt_path))
            except subprocess.CalledProcessError as exc:
                logger.warning("worktree remove failed (%s) — pruning", exc)
                try:
                    self._git("worktree", "prune")
                except subprocess.CalledProcessError:
                    pass
        if branch and delete_branch:
            try:
                self._git("branch", "-D", branch)
            except subprocess.CalledProcessError as exc:
                logger.warning("worktree branch delete failed (%s)", exc)

    # ── Byte and index helpers (task 5.6 / Requirement 4, 6, 10) ────────────
    # Reached by ``getattr`` duck-typing from ``RunSandbox`` — NOT added to the
    # ``Workspace`` Protocol so that three import-linter contracts remain green.

    def read_bytes(self, relpath: str) -> bytes:
        """Read raw bytes from a file in the sandbox.

        Raises ``FileNotFoundError`` if the file does not exist.
        """
        full = self._root / relpath
        if not full.exists():
            raise FileNotFoundError(f"read_bytes: {relpath!r} not found in sandbox")
        return full.read_bytes()

    def list_prefix(self, prefix: str) -> list[str]:
        """List all file relpaths starting with ``prefix`` from the live working tree.

        Uses ``os.walk`` — does not require git.  Best-effort: returns ``[]``
        on any error (non-raising).
        """
        try:
            results: list[str] = []
            for dirpath, _dirnames, filenames in os.walk(self._root):
                for name in filenames:
                    full = Path(dirpath) / name
                    try:
                        rel = full.relative_to(self._root).as_posix()
                    except ValueError:
                        continue
                    if rel.startswith(prefix):
                        results.append(rel)
            return sorted(results)
        except Exception:  # noqa: BLE001 — best-effort, must never raise
            return []

    def staged_entries(self) -> list[str]:
        """Return the list of relpaths currently staged in the index.

        Uses ``git diff --cached --name-only``.
        Best-effort: returns ``[]`` on any error (non-raising).
        """
        try:
            out = self._git("diff", "--cached", "--name-only")
            return [p.strip() for p in out.splitlines() if p.strip()]
        except Exception:  # noqa: BLE001 — best-effort, must never raise
            return []

    def stage_exact(self, paths: list[str]) -> None:
        """Stage exactly the listed paths with ``git add --force -- <paths>``.

        Only the given exact paths are staged — no glob expansion.
        Raises ``subprocess.CalledProcessError`` on failure.
        """
        if not paths:
            return
        self._git("add", "--force", "--", *paths)

    def head_commit(self) -> str:
        """Return the current HEAD commit SHA.

        Returns ``""`` if the repo has no commits yet (unborn HEAD).
        """
        try:
            return self._git("rev-parse", "HEAD").strip()
        except subprocess.CalledProcessError:
            return ""  # unborn HEAD — no commits yet

    def reset_index(self) -> None:
        """Reset the index back to HEAD without touching the working tree.

        Runs ``git reset HEAD -- .``.  If HEAD does not yet exist (new empty repo
        with no commits), uses ``git rm --cached -r .`` to clear the index instead.
        Never removes working-tree files.
        """
        try:
            self._git("reset", "HEAD", "--", ".")
        except subprocess.CalledProcessError:
            # HEAD may not exist on an empty repo — clear the index another way.
            try:
                self._git("rm", "--cached", "-r", ".")
            except subprocess.CalledProcessError:
                pass  # no index entries to remove — already empty

    def git_rm_cached(self, relpath: str) -> None:
        """Remove a file from the index only (not the working tree).

        Runs ``git rm --cached -- <relpath>``.
        Best-effort: no-op if the file is not tracked (non-raising).
        """
        try:
            self._git("rm", "--cached", "--", relpath)
        except subprocess.CalledProcessError:
            pass  # not tracked — treat as no-op

    def tracked_chain_paths(self) -> list[str]:
        """List all tracked paths under ``.chain/`` via ``git ls-files .chain/``.

        Returns ``[]`` if the repo has no commits or on any error (non-raising).
        """
        try:
            out = self._git("ls-files", ".chain/")
            return [p.strip() for p in out.splitlines() if p.strip()]
        except Exception:  # noqa: BLE001 — best-effort, must never raise
            return []

    def atomic_replace_dir(self, src: Path, dst: Path) -> None:
        """Atomically replace ``dst`` with ``src`` on both POSIX and Windows.

        Creates ``dst.parent`` if it does not exist.  Uses ``shutil.move`` rather
        than ``os.replace`` because ``os.replace`` refuses to overwrite a
        non-empty directory on Windows (``OSError: [WinError 5]``).  The sequence:
        1. Rename ``dst`` → ``dst.old`` (best-effort, ignored if absent).
        2. Move ``src`` → ``dst``.
        3. Remove ``dst.old`` (best-effort, ignored if absent).

        This provides the minimum atomicity needed on POSIX (step 2 is an atomic
        rename within the same filesystem mount) and is safe on Windows where a
        true atomic dir-swap is not available to Python.
        """
        dst.parent.mkdir(parents=True, exist_ok=True)
        old = dst.parent / (dst.name + ".old")
        # Remove any leftover sentinel from a previous partial run.
        if old.exists():
            shutil.rmtree(old, ignore_errors=True)
        # Rename current dst aside atomically (may not exist — that is fine).
        if dst.exists():
            dst.rename(old)
        try:
            shutil.move(str(src), str(dst))
        except Exception:
            # Restore the old directory if the move failed.
            if old.exists():
                old.rename(dst)
            raise
        # Clean up the old directory (best-effort).
        if old.exists():
            shutil.rmtree(old, ignore_errors=True)

    def atomic_context_install(self, src: Path) -> None:
        """Atomically install ``src`` directory as ``.context/`` inside this sandbox.

        Delegates to :meth:`atomic_replace_dir` targeting ``self._root / ".context"``.
        """
        self.atomic_replace_dir(src, self._root / ".context")

    def merge_worktree(self, branch: str, base_commit: str) -> dict:
        """3-way merge a per-worker ``branch`` back into the base working branch (11-03).

        Runs ``git merge --no-ff --no-commit <branch>`` via the ``_git`` owner (the
        SINGLE git-subprocess owner — the merge NEVER runs capability-side, Phase-9
        D-10). ``base_commit`` is the captured spawn-point merge-base (advisory — git
        resolves the actual merge-base from history; recorded for provenance). Returns
        a dict ``{"conflicts": [<rel paths>], "snippet": <truncated>}``: an EMPTY
        ``conflicts`` list means the merge applied cleanly; a non-empty list names the
        conflicting paths (parsed from ``git diff --name-only --diff-filter=U``) so the
        caller reports them as first-class conflicts and NEVER silently overwrites the
        base (T-11-03-01). On a conflict the merge is ABORTED (``git merge --abort``) so
        the base working tree is left clean for the on_conflict policy to adjudicate.

        If git REFUSES TO START the merge (dirty index, unborn HEAD, lock held, etc.)
        ``MergeRefusedError`` is raised instead of returning ``conflicts: []``.
        The critical invariant: a ``CalledProcessError`` with no ``--diff-filter=U``
        output NEVER produces ``conflicts: []`` — that would falsely report a clean
        merge when no merge took place.  ``git merge --abort`` is only run AFTER
        confirming that a merge started (MERGE_HEAD exists), never before.
        """
        try:
            # --no-commit so a clean merge leaves the integration staged but uncommitted
            # (the deliverable resolvers read the working tree); --no-ff keeps the merge
            # explicit. A conflict exits non-zero → CalledProcessError below.
            self._git("merge", "--no-ff", "--no-commit", branch)
        except subprocess.CalledProcessError as exc:
            # ── Step 1: classify the error BEFORE taking any action ─────────────────
            # MERGE_HEAD is written by git ONLY when the merge started and found
            # conflicts.  Its absence means git refused to start the merge entirely
            # (e.g. dirty index, unborn HEAD, lock file, unsatisfied pre-merge hook).
            merge_started = (self._root / ".git" / "MERGE_HEAD").exists()

            if not merge_started:
                # git refused to start — there are no conflicts to enumerate and no
                # in-progress merge to abort.  Raise instead of returning conflicts: [].
                raise MergeRefusedError(
                    branch,
                    reason=(exc.stderr or exc.stdout or str(exc)).strip()[:256],
                ) from exc

            # ── Step 2: merge ran and found conflicts — enumerate them ────────────
            # Only reached when MERGE_HEAD exists, i.e. git started the merge and
            # stopped at conflict markers.
            conflicts: list[str] = []
            try:
                out = self._git("diff", "--name-only", "--diff-filter=U")
                conflicts = [p for p in out.splitlines() if p.strip()]
            except subprocess.CalledProcessError:
                conflicts = [branch]  # could not enumerate — report the branch itself

            # ── Step 3: abort the in-progress merge to restore a clean tree ───────
            # Only runs because we confirmed a merge is in progress (MERGE_HEAD).
            try:
                self._git("merge", "--abort")
            except subprocess.CalledProcessError:
                pass  # best-effort restore; the base may already be clean

            return {"conflicts": conflicts, "snippet": ", ".join(conflicts)[:256]}
        return {"conflicts": [], "snippet": ""}

    def detect_persistent_git_state(self) -> dict:
        """Detect leftover git state from a prior crash.

        Inspects the sandbox ``.git/`` directory for well-known persistent-state
        files that remain on disk when a git operation was interrupted: ``MERGE_HEAD``
        (an in-progress merge), ``CHERRY_PICK_HEAD`` (an in-progress cherry-pick),
        ``REVERT_HEAD`` (an in-progress revert), ``BISECT_LOG`` (an active bisect
        session), and ``SQUASH_MSG`` (a squash commit message prepared but not yet
        committed).

        Returns a ``dict`` with three keys:

        - ``"state"``: one of ``"clean"``, ``"merge"``, ``"cherry_pick"``,
          ``"revert"``, ``"bisect"``, or ``"squash"``.
        - ``"file"``: the name of the state file found (e.g. ``"MERGE_HEAD"``), or
          ``None`` when state is ``"clean"``.
        - ``"sha"``: the SHA read from the state file (stripped), or ``None`` when
          not applicable or unreadable.

        The first matching file wins in detection order: ``MERGE_HEAD``,
        ``CHERRY_PICK_HEAD``, ``REVERT_HEAD``, ``BISECT_LOG``, ``SQUASH_MSG``.
        Only the SHA-bearing files (``MERGE_HEAD``, ``CHERRY_PICK_HEAD``,
        ``REVERT_HEAD``) are read for a SHA; the others return ``sha=None``.
        """
        git_dir = self._root / ".git"
        _STATE_FILES: list[tuple[str, str, bool]] = [
            # (filename, state_label, has_sha)
            ("MERGE_HEAD", "merge", True),
            ("CHERRY_PICK_HEAD", "cherry_pick", True),
            ("REVERT_HEAD", "revert", True),
            ("BISECT_LOG", "bisect", False),
            ("SQUASH_MSG", "squash", False),
        ]
        for filename, state_label, has_sha in _STATE_FILES:
            state_file = git_dir / filename
            if state_file.exists():
                sha: str | None = None
                if has_sha:
                    try:
                        sha = state_file.read_text(encoding="utf-8").strip()
                    except OSError:
                        sha = None
                return {"state": state_label, "file": filename, "sha": sha}
        return {"state": "clean", "file": None, "sha": None}

    def reconcile_persistent_git_state(self, state: dict) -> str:
        """Reconcile leftover git state from a prior crash.

        Given the result of :meth:`detect_persistent_git_state`, runs the
        appropriate abort or reset command to restore a clean working tree:

        - ``"merge"`` → ``git merge --abort``  → returns ``"merge_aborted"``
        - ``"cherry_pick"`` → ``git cherry-pick --abort``  → returns
          ``"cherry_pick_aborted"``
        - ``"revert"`` → ``git revert --abort``  → returns ``"revert_aborted"``
        - ``"bisect"`` → ``git bisect reset`` → returns ``"bisect_reset"``
        - other non-clean states → ``git reset HEAD --hard`` (WARNING: discards
          working-tree changes) → returns ``"reset_hard"``
        - ``"clean"`` → nothing to do → returns ``"already_clean"``

        Always best-effort: any exception is caught and ``"reconcile_failed"`` is
        returned so callers never crash during recovery (Requirement 19 AC 3 /
        crash-recovery path must not abort the run start).
        """
        current_state = state.get("state", "clean")
        if current_state == "clean":
            return "already_clean"
        try:
            if current_state == "merge":
                self._git("merge", "--abort")
                return "merge_aborted"
            if current_state == "cherry_pick":
                self._git("cherry-pick", "--abort")
                return "cherry_pick_aborted"
            if current_state == "revert":
                self._git("revert", "--abort")
                return "revert_aborted"
            if current_state == "bisect":
                self._git("bisect", "reset")
                return "bisect_reset"
            # Fallback for "squash" or any unknown persistent state.
            # WARNING: discards all uncommitted working-tree changes.
            self._git("reset", "HEAD", "--hard")
            return "reset_hard"
        except Exception:  # noqa: BLE001 — best-effort; must never raise
            return "reconcile_failed"


@register(
    "runtime_env",
    "local",
    description="Local on-disk sandbox runtime environment (the ECS/container-swap seam).",
)
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
        has_git: bool = True,
        exec: bool = False,
        recorder=None,
    ) -> Workspace:
        """Provision a local-disk ``Workspace`` for one run.

        ``has_git`` marks the workspace as a git checkout — STORED on the
        workspace (CR-06) so the engine's fan-out isolation-scope selection
        (``worktree`` vs ``sub_sandbox``) keys on it; ``clone_repo`` also flips
        it True when a repo lands later. ``exec``
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
            # CR-06: STORE the flag (it was documented "advisory" and discarded,
            # leaving the engine's worktree isolation scope unreachable live).
            has_git=has_git,
        )
        if recorder is not None:
            ws._recorder = recorder
        return ws

    def teardown(self, ws: Workspace) -> None:
        ws.teardown()


# ── Legacy payload relocation and read path (V2 task 6.7) ────────────────────
#
# v1 chaining used nested per-run directories inside `.chain/{run_id}/`.
# v2 uses a flat three-file layout directly in `.chain/`.  These helpers
# relocate v1 payloads to `.chain-legacy/{run_id}/` at sandbox open so that
# `.chain/` contains only the flat v2 payload, and provide the admission-gate
# read path for pre-mint legacy source selection.
#
# Design constraints (Requirement 7):
#   - An untagged legacy terminal run is ELIGIBLE — `git_tag` is conditional.
#   - When a tag is present, validate it against `list_tags()` BEFORE any
#     Git subprocess sees it (prevents injection via a stored tag string).
#   - NEVER synthesize or backfill `refs/ideaflow/runs/{run_id}` for a legacy
#     source — internal refs are v2 only.
#   - Fallback order for `select_legacy_payload`:
#       1. `.chain-legacy/{run_id}/`  (post-relocation path)
#       2. `.chain/{run_id}/`         (pre-relocation fallback)
#     Nothing else — never the flat v2 `.chain/`, another run's directory,
#     the latest tag, an ordinal-derived tag, or `HEAD`.
#   - Atomic relocation: copy bytes → fsync-ish via shutil → remove source.
#     An existing destination is NEVER overwritten silently; skip instead.
#   - `.chain-legacy/` is excluded from Git, deliverables, zips, agent tools,
#     and the listing surface — all derived from the canonical RESERVED_PATHS
#     registry (already contains `.chain-legacy/`).

_LEGACY_PAYLOAD_BASENAMES: frozenset[str] = frozenset(
    {
        "logs.jsonl",
        "summary.md",
    }
)
"""Fixed names that are always included when present in a legacy payload dir.

The third file (the workflow output) has a variable basename derived from the
deliverable name, so the selection logic adds any other regular file found
alongside the two fixed names — capped at one extra file.
"""

_SUMMARY_RUN_ID_RE = re.compile(
    r"^\s*run_id\s*:\s*([0-9a-fA-F-]{32,})\s*$",
    re.MULTILINE,
)
"""Extracts the ``run_id`` field from a ``summary.md`` YAML/text block.

Matches the canonical ``run_id: <uuid>`` line produced by the v1 finalizer.
UUID-shaped strings only (hex + hyphens, ≥ 32 chars) — no free-form strings.
"""

_SUMMARY_GIT_TAG_RE = re.compile(
    r"^\s*(?:git_tag|intended_tag)\s*:\s*(\S+)\s*$",
    re.MULTILINE,
)
"""Extracts ``git_tag`` or ``intended_tag`` from a ``summary.md`` block.

Both field names are tried: v1 used ``git_tag``; v2 ``summary.md`` uses
``intended_tag``.  The value must be non-whitespace.  ``null`` / empty values
are left to the caller to interpret as absent.
"""


@dataclass(frozen=True)
class LegacySelection:
    """The result of :func:`select_legacy_payload` for a single legacy source run.

    Carries all facts the chain-context installer (:func:`install_legacy_chain_context`)
    and the admission gate need without re-reading disk a second time.

    Attributes:
        source_run_id: The run UUID the payload belongs to (validated from
            ``summary.md``; matches the requested ``source_run_id``).
        base_dir: Absolute path to the directory that was found — either
            ``.chain-legacy/{source_run_id}/`` or ``.chain/{source_run_id}/``.
        files: Selected file basenames to copy.  Always a subset of the three
            canonical names; never empty if ``select_legacy_payload`` returned
            non-``None``.
        git_tag: The tag string parsed from ``summary.md``, or ``None`` when
            the summary is absent or carries no tag field.  When non-``None``
            the caller MUST validate it against ``list_tags()`` before passing
            it to any Git command.
        is_legacy: Always ``True``.  Present so dispatch code can discriminate
            ``LegacySelection`` from a v2 ``SourceSelection`` without an
            ``isinstance`` check.
    """

    source_run_id: str
    base_dir: Path
    files: list[str]
    git_tag: str | None = None
    is_legacy: bool = True


def relocate_legacy_payloads(sandbox_root: Path) -> None:
    """Move v1 per-run ``.chain/{run_id}/`` directories to ``.chain-legacy/{run_id}/``.

    Called at sandbox open, before any v2 payload write, so that ``.chain/``
    is left with only the flat three-file v2 payload (or empty).

    Rules:
    - Iterates over **immediate** subdirectories of ``.chain/`` only.
    - A subdirectory whose name is UUID-shaped (hex + hyphens) is a legacy
      per-run payload dir and is relocated.
    - Non-UUID entries (e.g. the flat v2 files ``logs.jsonl``, ``summary.md``,
      or an output file) are left untouched.
    - If the destination ``.chain-legacy/{run_id}/`` already exists the source
      is left as-is (idempotent — a previous partial relocation wins).
    - Relocation is atomic at the OS level when source and destination are on
      the same filesystem (``shutil.copytree`` + ``shutil.rmtree``).  If they
      differ, byte-copy completes before the source is removed.

    Args:
        sandbox_root: The **root** directory of the revision-root sandbox
            (the directory containing ``.chain/`` and ``.chain-legacy/``).

    Raises:
        Nothing — relocation errors are logged at WARNING level and skipped so
        a partial failure cannot block sandbox open for a new run.
    """
    chain_dir = sandbox_root / ".chain"
    if not chain_dir.is_dir():
        return

    legacy_dir = sandbox_root / ".chain-legacy"
    _log = logging.getLogger(__name__)

    # Pattern matches UUID-shaped names: hex digits and hyphens, min 32 chars.
    _uuid_re = re.compile(r"^[0-9a-fA-F-]{32,}$")

    for entry in chain_dir.iterdir():
        if not entry.is_dir():
            continue
        if not _uuid_re.match(entry.name):
            # Not a per-run directory (could be a staging temp dir or similar).
            continue

        dest = legacy_dir / entry.name
        if dest.exists():
            # Destination already present — previous relocation succeeded or
            # partial.  Leave both in place; the source is harmless and the
            # select path handles the fallback.
            _log.debug(
                "relocate_legacy_payloads: destination exists, skipping %s → %s",
                entry,
                dest,
            )
            continue

        try:
            legacy_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(entry, dest)
            shutil.rmtree(entry)
            _log.info(
                "relocate_legacy_payloads: relocated %s → %s",
                entry.name,
                dest,
            )
        except Exception:  # noqa: BLE001
            _log.warning(
                "relocate_legacy_payloads: failed to relocate %s, skipping",
                entry,
                exc_info=True,
            )


def select_legacy_payload(
    sandbox_root: Path,
    source_run_id: str,
) -> LegacySelection | None:
    """Find and validate a legacy v1 chain payload for ``source_run_id``.

    Tries, in order:
    1. ``.chain-legacy/{source_run_id}/``   (post-relocation)
    2. ``.chain/{source_run_id}/``          (pre-relocation fallback)

    Nothing else is consulted — never the flat v2 ``.chain/``, another run's
    directory, the latest tag, an ordinal-derived tag, or ``HEAD``.

    Validation:
    - ``summary.md`` must exist in the directory.
    - The ``run_id:`` field in ``summary.md`` must match ``source_run_id``.
    - Up to one extra file (the workflow output) is selected alongside the two
      fixed names (``logs.jsonl``, ``summary.md``).

    The caller is responsible for tag validation: when the returned
    ``LegacySelection.git_tag`` is non-``None``, it MUST be verified against
    ``list_tags()`` on the source sandbox before any Git command receives it.

    Args:
        sandbox_root: Revision-root sandbox directory.
        source_run_id: UUID of the source run to look up.

    Returns:
        A :class:`LegacySelection` when a valid legacy payload is found, or
        ``None`` when neither candidate directory holds a valid payload.
    """
    _log = logging.getLogger(__name__)

    # Candidate directories in fallback order.
    candidates = [
        sandbox_root / ".chain-legacy" / source_run_id,
        sandbox_root / ".chain" / source_run_id,
    ]

    for base_dir in candidates:
        if not base_dir.is_dir():
            continue

        summary_path = base_dir / "summary.md"
        if not summary_path.is_file():
            _log.debug(
                "select_legacy_payload: no summary.md in %s, skipping",
                base_dir,
            )
            continue

        # Validate run_id field.
        try:
            summary_text = summary_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            _log.debug(
                "select_legacy_payload: cannot read summary.md in %s, skipping",
                base_dir,
            )
            continue

        match = _SUMMARY_RUN_ID_RE.search(summary_text)
        if match is None:
            _log.debug(
                "select_legacy_payload: no run_id field in %s/summary.md, skipping",
                base_dir,
            )
            continue

        found_run_id = match.group(1)
        if found_run_id != source_run_id:
            _log.warning(
                "select_legacy_payload: run_id mismatch in %s/summary.md "
                "(expected %s, found %s), skipping",
                base_dir,
                source_run_id,
                found_run_id,
            )
            continue

        # Extract optional git_tag.
        tag_match = _SUMMARY_GIT_TAG_RE.search(summary_text)
        git_tag: str | None = None
        if tag_match is not None:
            raw_tag = tag_match.group(1).strip()
            if raw_tag and raw_tag.lower() not in ("null", "~", ""):
                git_tag = raw_tag

        # Collect files: fixed names present + up to one extra regular file.
        selected: list[str] = []
        extra: list[str] = []
        for child in sorted(base_dir.iterdir()):
            if not child.is_file():
                continue
            if child.name in _LEGACY_PAYLOAD_BASENAMES:
                selected.append(child.name)
            else:
                extra.append(child.name)

        # Accept exactly one output file beyond the two fixed names; if there
        # are multiple extras the payload is ambiguous — select none to avoid
        # shipping the wrong file.
        if len(extra) == 1:
            selected.append(extra[0])
        elif len(extra) > 1:
            _log.warning(
                "select_legacy_payload: %d extra files in %s — ambiguous output, "
                "omitting extras",
                len(extra),
                base_dir,
            )

        if not selected:
            _log.debug(
                "select_legacy_payload: no files found in %s, skipping",
                base_dir,
            )
            continue

        return LegacySelection(
            source_run_id=source_run_id,
            base_dir=base_dir,
            files=selected,
            git_tag=git_tag,
        )

    return None


def install_legacy_chain_context(
    selection: LegacySelection,
    dest_dir: Path,
) -> None:
    """Byte-copy the selected legacy files from ``selection.base_dir`` into ``dest_dir``.

    Copies exactly the files named in ``selection.files`` and nothing else.
    Creates ``dest_dir`` if it does not exist.

    This is a pure byte copy — no template expansion, no text encoding, no
    format conversion.  Binary output files (e.g. PPTX) survive intact.

    Args:
        selection: The :class:`LegacySelection` returned by
            :func:`select_legacy_payload`.
        dest_dir: Destination directory (typically the ``.context/`` root of
            the receiving sandbox).

    Raises:
        OSError: If a source file cannot be read or the destination cannot be
            written.  The caller is responsible for error handling; this
            function does not swallow IO errors.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    for basename in selection.files:
        src = selection.base_dir / basename
        dst = dest_dir / basename
        shutil.copy2(src, dst)
