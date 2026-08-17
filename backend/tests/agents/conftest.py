"""conftest.py for agents test suite.

Provides shared fixtures and helpers for testing the folder-per-agent
architecture (loader, factory, registry, orchestrator).
"""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Hermetic checkpointer — these tests must not need a database
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def in_process_checkpointer(monkeypatch):
    """Pin the LangGraph checkpointer to InMemorySaver for the whole agent suite.

    `get_checkpointer()` chooses purely on the `DATABASE_URL` *scheme*
    (`app/agents/checkpointer.py`), and there is no fallback for "Postgres is
    configured but unreachable" — only a Windows event-loop one. Nothing pinned
    `DATABASE_URL` in the test tree, so these tests silently bound to whatever
    the developer's `backend/.env` pointed at.

    That made the suite non-hermetic in the worst way: with Postgres down, every
    characterization run burned a 30-second `psycopg_pool.PoolTimeout`, errored,
    and reported `pipeline_failed` — a whole-suite red that says nothing about
    the code. One file took 482s instead of 2.6s. The goldens were therefore
    only ever verified on machines that happened to have a database running.

    These tests assert event streams and deliverable bytes; not one of them
    asserts anything about persistence, so an in-memory saver is the correct
    dependency, not a compromise. The suite that *does* need durability —
    `test_phase8_resume.py` — starts its own docker Postgres, skips when docker
    is absent, and does all its Postgres work in **subprocesses** that receive
    `DATABASE_URL` through an explicit child env. Patching the in-process
    `settings` singleton here leaves that untouched.
    """
    from app.agents import checkpointer as checkpointer_module
    from app.core.config import settings

    monkeypatch.setattr(settings, "DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    # The factory caches a process-wide singleton; clear it so this test builds
    # its own, and restore afterwards so ordering cannot leak a saver between tests.
    monkeypatch.setattr(checkpointer_module, "_checkpointer", None)
    monkeypatch.setattr(checkpointer_module, "_pool", None)
    yield


# ---------------------------------------------------------------------------
# Helpers for building AGENT.md content in tests
# ---------------------------------------------------------------------------


def make_agent_md(
    *,
    id: str = "test-agent",
    name: str = "Test Agent",
    role: str = "Testing",
    pipeline_type: str = "user_stories",
    order: int = 1,
    max_tokens: int = 4000,
    tools: list[str] | None = None,
    guardrails: list[str] | None = None,
    context_from: list[str] | None = None,
    icon: str = "🤖",
    estimated_duration: float = 3.0,
    prompt_body: str = "You are a test agent.",
    extra_fields: dict | None = None,
) -> str:
    """Build a valid AGENT.md string for use in tests."""
    lines = ["---"]
    lines.append(f"id: {id}")
    lines.append(f"name: {name}")
    lines.append(f"role: {role}")
    lines.append(f"pipeline_type: {pipeline_type}")
    lines.append(f"order: {order}")
    lines.append(f"max_tokens: {max_tokens}")

    if tools is not None:
        if tools:
            lines.append("tools:")
            for t in tools:
                lines.append(f"  - {t}")
        else:
            lines.append("tools: []")

    if guardrails is not None:
        if guardrails:
            lines.append("guardrails:")
            for g in guardrails:
                lines.append(f"  - {g}")
        else:
            lines.append("guardrails: []")

    if context_from is not None:
        if context_from:
            lines.append("context_from:")
            for c in context_from:
                lines.append(f"  - {c}")
        else:
            lines.append("context_from: []")

    lines.append(f'icon: "{icon}"')
    lines.append(f"estimated_duration: {estimated_duration}")

    if extra_fields:
        for k, v in extra_fields.items():
            lines.append(f"{k}: {v!r}")

    lines.append("---")
    lines.append("")
    lines.append(prompt_body)

    return "\n".join(lines)


@pytest.fixture
def tmp_agent_dir(tmp_path: Path):
    """Fixture that provides a temporary agents/prompts directory.

    Patches agents.loader._PROMPTS_DIR to point to the temp directory
    so tests don't touch the real filesystem.
    """
    import agents.loader as loader_module

    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()

    original_prompts_dir = loader_module._PROMPTS_DIR
    original_cache = dict(loader_module._SPEC_CACHE)

    loader_module._PROMPTS_DIR = prompts_dir
    loader_module._SPEC_CACHE.clear()

    yield prompts_dir

    # Restore
    loader_module._PROMPTS_DIR = original_prompts_dir
    loader_module._SPEC_CACHE.clear()
    loader_module._SPEC_CACHE.update(original_cache)


def create_agent_file(prompts_dir: Path, agent_id: str, content: str) -> Path:
    """Create an AGENT.md file in the given prompts directory."""
    agent_dir = prompts_dir / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    agent_file = agent_dir / "AGENT.md"
    agent_file.write_text(content, encoding="utf-8")
    return agent_file


# ---------------------------------------------------------------------------
# Local git repo fixture (Phase 09 — RUNTIME-01 / repo workflows).
#
# Seeds a tiny REAL git repository on local disk (NO network clone) so the
# LocalSandboxRuntime's clone/branch/diff path can be exercised fully offline.
# Placed in the suite conftest so the repo workflow plans 09-03/09-04 reuse it.
# ---------------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> None:
    """Run a git subprocess in ``cwd``, raising on failure. Identity is forced via
    flags so the fixture works on a machine with no global git user configured."""
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Flowin Test",
            "-c",
            "user.email=test@flowin.local",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "init.defaultBranch=main",
            *args,
        ],
        cwd=str(cwd),
        check=True,
        capture_output=True,
    )


@pytest.fixture
def local_git_fixture(tmp_path: Path) -> Path:
    """Seed a tiny local git repo and return its path (no network).

    The repo carries a few source files committed on ``main`` so a downstream
    ``LocalSandboxRuntime`` can ``git clone`` it into a per-run dir, branch off it,
    read/write/search its files, and produce a ``git_diff``.
    """
    repo = tmp_path / "origin_repo"
    repo.mkdir()
    _git(repo, "init")

    (repo / "README.md").write_text(
        "# Sample Repo\n\nA brownfield fixture for the local runtime.\n",
        encoding="utf-8",
    )
    src = repo / "src"
    src.mkdir()
    (src / "app.py").write_text(
        textwrap.dedent(
            '''\
            """Sample module."""


            def greet(name: str) -> str:
                return f"hello {name}"
            '''
        ),
        encoding="utf-8",
    )
    (src / "util.py").write_text(
        textwrap.dedent(
            '''\
            """Utility helpers."""


            def add(a: int, b: int) -> int:
                return a + b
            '''
        ),
        encoding="utf-8",
    )

    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "initial commit")
    # Normalize the default branch name so callers can clone+diff against "main".
    _git(repo, "branch", "-M", "main")
    return repo
