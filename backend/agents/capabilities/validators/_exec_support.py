"""agents/capabilities/validators/_exec_support.py — shared exec-handle helpers (EXEC-02).

The three code validators (``code_compile`` / ``code_test`` / ``code_lint``) all
reach exec the SAME way — through the runner/workspace handle, never importing
``app.*``, never spawning directly. This module factors the three shared helpers so
each validator copies the reach by import (not by re-typing it):

  * ``workspace_of(runner)`` — the ``repo_diff._workspace`` reach: prefer
    ``runner.workspace`` (the live KernelServices handle, 10-03 §15 seam), else a
    bare ``Workspace`` passed AS the runner (the offline harness shape). A workspace
    qualifies iff it exposes a callable ``exec_command``.
  * ``exec_granted(ws)`` — ``ws is not None and ws.policy.allows("exec")`` (the
    single grant check; degrades to ``False`` if the policy is absent/odd).
  * ``target_py_files(target)`` — a stdlib glob over the run root reached from the
    target (``runner.workspace`` root / ``target.path``) for ``*.py`` files (relative
    POSIX paths the argv passes). Never hardcodes a path.

Pure stdlib; imports only ``typing`` + ``pathlib``. Kernel-pure (no ``app.*`` /
``agents.execution_engine`` import) so the import-linter stays 4 kept / 0 broken.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def workspace_of(runner: Any) -> Any:
    """Reach the ``Workspace`` via the runner handle (mirrors ``repo_diff._workspace``).

    Prefers a runner exposing ``.workspace`` (the live KernelServices handle); falls
    back to a bare ``Workspace`` passed AS the runner (the offline harness shape).
    A candidate qualifies iff it exposes a callable ``exec_command``.
    """
    if runner is None:
        return None
    ws = getattr(runner, "workspace", None)
    if ws is not None and callable(getattr(ws, "exec_command", None)):
        return ws
    if callable(getattr(runner, "exec_command", None)):
        return runner
    return None


def exec_granted(ws: Any) -> bool:
    """``True`` iff the workspace exists and its policy allows ``exec``.

    WR-03 — this is a RUN-scoped check, NOT per-step: it reads the shared,
    run-global workspace policy, so once any step's security+approval grant
    provisions the exec workspace (the engine host seam binds it for the whole
    run), every step's exec validators see ``exec_granted`` True. Per-step
    re-authorization is intentionally not enforced here — D-03's SPEC-locked
    first-exec memory means one approval opens exec for the whole run and
    subsequent exec steps don't re-prompt. The compiler's engineer-trust ceiling
    bounds this (a user/db manifest can never provision the exec workspace).
    """
    if ws is None:
        return False
    policy = getattr(ws, "policy", None)
    allows = getattr(policy, "allows", None)
    if not callable(allows):
        return False
    try:
        return bool(allows("exec"))
    except Exception:  # noqa: BLE001 — an odd policy degrades to "not granted"
        return False


def _run_root(target: Any) -> Path | None:
    """Resolve the run root the validators glob over (stdlib only, no hardcode).

    Prefers the workspace's own root (``ws._root`` — the traversal-proof per-run
    dir), then ``target.path`` (a directory or a file whose parent is the root).
    """
    ws = workspace_of(getattr(target, "runner", None))
    root = getattr(ws, "_root", None)
    if root is not None:
        p = Path(root)
        if p.is_dir():
            return p
    path = getattr(target, "path", None)
    if path is not None:
        p = Path(path)
        if p.is_dir():
            return p
        if p.is_file():
            return p.parent
    return None


def target_py_files(target: Any) -> list[str]:
    """Glob the run root for ``*.py`` files → relative POSIX paths (stdlib only).

    Skips the ``.git`` dir and any ``__pycache__``. Returns paths RELATIVE to the
    run root so the argv runs ``cwd``-anchored in the workspace.
    """
    root = _run_root(target)
    if root is None:
        return []
    files: list[str] = []
    for path in sorted(root.rglob("*.py")):
        parts = path.relative_to(root).parts
        if ".git" in parts or "__pycache__" in parts:
            continue
        files.append(path.relative_to(root).as_posix())
    return files
