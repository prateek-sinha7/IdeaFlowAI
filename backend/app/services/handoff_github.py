"""GitHub helpers for /flowin-handoff: parse URLs, clone, push, open PRs.

Subprocess invocations of ``git`` are wrapped in the same rlimit /
timeout / env-scrubbing pattern as :mod:`app.services.pptx_export`. PR
creation uses the GitHub REST API (no ``gh`` CLI required) so the only
external binary the handoff pipeline needs is ``git`` itself.

The PAT is injected as ``https://x-access-token:<PAT>@github.com/...``
for clone and push. We never log the credentialed URL — only the
canonical ``https://github.com/owner/repo`` form. The PAT is also not
persisted on disk: ``git`` reads it from the argv form and forwards it
to the HTTPS auth layer; the workspace ``.git/config`` ends up with the
credentialed URL as ``remote.origin.url``, so we wipe it at cleanup
time as defence in depth.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import shutil

# resource module is Unix-only
if sys.platform != "win32":
    import resource
else:
    resource = None  # type: ignore[assignment]
import subprocess  # nosec B404 — controlled invocation of `git`, scrubbed env, rlimits
import time
from dataclasses import dataclass
from typing import Iterable, Optional

import httpx

logger = logging.getLogger("app.services.handoff_github")


# --- Sandbox limits (mirror pptx_export.py) ------------------------------

_RLIMIT_CPU_SECONDS = 30
_RLIMIT_AS_BYTES = 1024 * 1024 * 1024  # 1 GiB virtual memory cap per child
_RLIMIT_FSIZE_BYTES = 256 * 1024 * 1024  # 256 MiB max file size
_RLIMIT_NOFILE = 256
_RLIMIT_NPROC = 256

_GIT_WALL_TIMEOUT_S = 90


def _apply_child_rlimits() -> None:
    """preexec_fn: tighten resource limits on the cloned ``git`` child.
    No-op on Windows where the resource module is unavailable.
    """
    if resource is None:
        return
    for limit, value in [
        (resource.RLIMIT_CPU, _RLIMIT_CPU_SECONDS),
        (resource.RLIMIT_AS, _RLIMIT_AS_BYTES),
        (resource.RLIMIT_FSIZE, _RLIMIT_FSIZE_BYTES),
        (resource.RLIMIT_NOFILE, _RLIMIT_NOFILE),
        (resource.RLIMIT_NPROC, _RLIMIT_NPROC),
    ]:
        try:
            resource.setrlimit(limit, (value, value))
        except (ValueError, resource.error, OSError) as exc:
            logger.debug("setrlimit(%s, %s) failed in child: %s", limit, value, exc)


def _build_git_env(workspace: str) -> dict[str, str]:
    """Scrubbed env for the git child. Inherits as little as possible."""
    return {
        "HOME": workspace,
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        # Refuse to prompt for credentials — if PAT auth fails we want the
        # subprocess to exit non-zero immediately, not wait for stdin.
        "GIT_TERMINAL_PROMPT": "0",
        # Ignore any global / system git config that might exist in the
        # container (highly unlikely in our image, defence in depth).
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        # Committer / author identity for any commit we make on the user's
        # behalf. The PR will additionally credit the user via co-author
        # metadata in the body.
        "GIT_AUTHOR_NAME": "Flowin Handoff",
        "GIT_AUTHOR_EMAIL": "handoff@flowin.local",
        "GIT_COMMITTER_NAME": "Flowin Handoff",
        "GIT_COMMITTER_EMAIL": "handoff@flowin.local",
    }


# --- URL parsing ---------------------------------------------------------


_GITHUB_HTTPS_RE = re.compile(
    r"^https?://(?:[^@/]+@)?(?P<host>github\.com)/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"
)
_GITHUB_SSH_RE = re.compile(
    r"^git@(?P<host>github\.com):(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$"
)


@dataclass(frozen=True)
class RepoTarget:
    owner: str
    repo: str
    host: str = "github.com"

    @property
    def https_url(self) -> str:
        return f"https://{self.host}/{self.owner}/{self.repo}.git"

    @property
    def api_base(self) -> str:
        # GitHub Enterprise would be ``https://<host>/api/v3``; for
        # public github.com we hit ``api.github.com`` directly.
        if self.host == "github.com":
            return "https://api.github.com"
        return f"https://{self.host}/api/v3"


def parse_github_url(url: str) -> RepoTarget:
    """Parse an ``https://`` or ``git@`` GitHub URL.

    Strips ``.git`` suffix and any embedded credentials. Raises
    ``ValueError`` on anything we don't recognise — the handoff API
    rejects malformed URLs early rather than letting a bad URL flow
    into a subprocess.
    """
    url = url.strip()
    if not url:
        raise ValueError("repo_url is empty")
    match = _GITHUB_HTTPS_RE.match(url) or _GITHUB_SSH_RE.match(url)
    if match is None:
        raise ValueError(f"unsupported repo URL form: {url!r}")
    return RepoTarget(
        owner=match.group("owner"),
        repo=match.group("repo"),
        host=match.group("host"),
    )


def _credentialed_clone_url(target: RepoTarget, pat: str) -> str:
    """Build the PAT-embedded clone URL. Never logged."""
    return f"https://x-access-token:{pat}@{target.host}/{target.owner}/{target.repo}.git"


def _redact(text: str, secrets: Iterable[str]) -> str:
    """Replace any matching secret with ``***`` in the given text."""
    out = text
    for s in secrets:
        if s:
            out = out.replace(s, "***")
    return out


# --- git subprocess wrapper ---------------------------------------------


@dataclass
class GitResult:
    returncode: int
    stdout: str
    stderr: str


def _run_git(
    args: list[str],
    cwd: str,
    secrets: Iterable[str] = (),
    timeout: int = _GIT_WALL_TIMEOUT_S,
) -> GitResult:
    """Run ``git <args>`` inside the sandbox. Returns the result.

    ``secrets`` are values (typically the PAT and the credentialed URL)
    that get redacted from stdout/stderr before we log or surface them.
    Stderr is captured but we don't raise on non-zero — the caller decides
    whether to treat the failure as fatal.
    """
    env = _build_git_env(workspace=cwd)
    started = time.monotonic()
    try:
        proc = subprocess.run(  # nosec B603 — `args` is constructed from controlled enum branches
            ["git", *args],
            cwd=cwd,
            env=env,
            preexec_fn=_apply_child_rlimits,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - started
        return GitResult(
            returncode=124,
            stdout="",
            stderr=_redact(
                f"git {args[0] if args else ''} timed out after {elapsed:.1f}s (limit {timeout}s)",
                secrets,
            ),
        )
    return GitResult(
        returncode=proc.returncode,
        stdout=_redact(proc.stdout, secrets),
        stderr=_redact(proc.stderr, secrets),
    )


# --- Public operations --------------------------------------------------


def clone(
    target: RepoTarget,
    pat: str,
    dest_dir: str,
    branch: Optional[str] = None,
) -> GitResult:
    """``git clone`` into ``dest_dir``. ``dest_dir`` must already exist."""
    credentialed = _credentialed_clone_url(target, pat)
    args = ["clone", "--depth", "50"]
    if branch:
        args.extend(["--branch", branch])
    args.extend([credentialed, "workspace"])
    return _run_git(args, cwd=dest_dir, secrets=(pat, credentialed))


def checkout_new_branch(workspace: str, branch_name: str) -> GitResult:
    return _run_git(["checkout", "-b", branch_name], cwd=workspace)


def stage_all(workspace: str) -> GitResult:
    return _run_git(["add", "--all"], cwd=workspace)


def commit(workspace: str, message: str) -> GitResult:
    return _run_git(["commit", "-m", message], cwd=workspace)


def push(
    target: RepoTarget,
    pat: str,
    workspace: str,
    branch_name: str,
) -> GitResult:
    """Push ``branch_name`` to ``origin`` using the PAT-embedded URL."""
    credentialed = _credentialed_clone_url(target, pat)
    return _run_git(
        ["push", credentialed, f"{branch_name}:{branch_name}"],
        cwd=workspace,
        secrets=(pat, credentialed),
    )


def wipe_credentialed_remote(workspace: str) -> None:
    """Best-effort: scrub the PAT-embedded URL from .git/config after push.

    We never *commit* the .git/config — it lives only in the ephemeral
    workspace which we delete in the pipeline's ``finally`` block — but
    if a later cleanup pass logs ``.git/config`` for any reason we'd
    rather it not contain the PAT.
    """
    cfg_path = os.path.join(workspace, ".git", "config")
    try:
        with open(cfg_path, "r", encoding="utf-8", errors="replace") as fh:
            data = fh.read()
        scrubbed = re.sub(r"https://x-access-token:[^@]+@", "https://", data)
        with open(cfg_path, "w", encoding="utf-8") as fh:
            fh.write(scrubbed)
    except OSError:
        pass


def cleanup_workspace(workspace_root: str) -> None:
    """Recursively delete the per-handoff workspace. Idempotent."""
    if not workspace_root:
        return
    shutil.rmtree(workspace_root, ignore_errors=True)


# --- GitHub REST API ----------------------------------------------------


async def get_repo_metadata(target: RepoTarget, pat: str) -> dict[str, str]:
    """Fetch the repo's default_branch (and any other small metadata).

    Returns ``{"default_branch": "..."}``. Raises ``RuntimeError`` on
    non-2xx responses; the caller surfaces this as a pipeline failure.
    """
    url = f"{target.api_base}/repos/{target.owner}/{target.repo}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            url,
            headers={
                "Authorization": f"Bearer {pat}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "Flowin-Handoff/1.0",
            },
        )
    if resp.status_code >= 400:
        raise RuntimeError(
            f"GitHub repo metadata fetch failed ({resp.status_code}): "
            f"{resp.text[:200]}"
        )
    body = resp.json()
    return {"default_branch": body.get("default_branch") or "main"}


async def create_pull_request(
    target: RepoTarget,
    pat: str,
    head_branch: str,
    base_branch: str,
    title: str,
    body: str,
    draft: bool = False,
) -> dict[str, object]:
    """Open a PR via the GitHub REST API.

    Returns ``{"url": <html_url>, "number": <int>}``. Raises
    ``RuntimeError`` on non-201 responses.
    """
    url = f"{target.api_base}/repos/{target.owner}/{target.repo}/pulls"
    payload = {
        "title": title[:256],
        "head": head_branch,
        "base": base_branch,
        "body": body[:65536],
        "draft": draft,
        "maintainer_can_modify": True,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {pat}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "Flowin-Handoff/1.0",
            },
            json=payload,
        )
    if resp.status_code >= 400:
        raise RuntimeError(
            f"GitHub PR creation failed ({resp.status_code}): {resp.text[:400]}"
        )
    body_json = resp.json()
    return {"url": body_json["html_url"], "number": body_json["number"]}
