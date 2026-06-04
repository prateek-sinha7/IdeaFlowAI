"""Constitution §II guard: no ``BaseAgent`` *code* usage across the agent tree.

``BaseAgent`` (single LLM call, stateless, no tools) was the legacy chat/utility
agent base. The deepagents migration replaced it everywhere on the pipeline and
free-chat paths: pipelines run as ``DeepAgentRunner`` graphs (engine-driven) and
free-chat runs on ``app.agents.chat_runner.ChatRunner``. This guard asserts that no
NEW ``BaseAgent`` reference creeps back into that code.

WIDENED in migration Phase 7b-5 (plan 002 §5 "Phase 7", task "7b task 12"): the
legacy free-chat stack (``orchestrator.py`` + the 7 ``BaseAgent`` chat agents) was
deleted, so the scan is widened from a handful of engine modules to the WHOLE agent
tree — ``agents/`` + ``app/agents/`` + ``app/api/``. It now forbids ``BaseAgent`` as a
code token everywhere in that tree.

Two narrowly-scoped, documented EXEMPTIONS remain, both for the **live**
``/flowin-handoff`` IDE-to-PR feature (a separate subsystem the chat/pipeline
migration never touched — wired into ``app.main`` via ``app.api.handoff`` /
``app.api.websocket_handoff``):
  * ``app/agents/base.py`` — still DEFINES ``BaseAgent`` (its only remaining consumer
    is the handoff subsystem; ``TokenUsage`` was relocated to ``app/agents/types.py``);
  * ``app/agents/handoff/`` — ``CodingAgent`` / ``TestAgent`` / ``ComplianceAgent`` /
    ``classify_task`` subclass / instantiate ``BaseAgent`` at runtime.
Deleting ``base.py`` is therefore out of scope for the chat migration (it would break
the handoff feature); if/when handoff is migrated off ``BaseAgent``, drop the
exemptions and ``base.py``.

Detection uses Python ``tokenize`` so ``BaseAgent`` mentions inside COMMENTS and
DOCSTRINGS/strings do NOT trip the guard (only a real ``NAME`` token does) — matching
the migration's grep-zero gate, which permits comment/docstring references.
"""

from __future__ import annotations

import io
import tokenize
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent.parent

# Whole agent tree (widened 7b-5). Each entry is scanned recursively for *.py.
SCANNED_PATHS = [
    BACKEND / "agents",
    BACKEND / "app" / "agents",
    BACKEND / "app" / "api",
]

# Live ``/flowin-handoff`` subsystem — the only legitimate remaining BaseAgent users.
# Paths here (file or directory) are skipped. Documented in the module docstring.
_EXEMPT = [
    BACKEND / "app" / "agents" / "base.py",
    BACKEND / "app" / "agents" / "handoff",
]


def _is_exempt(path: Path) -> bool:
    for ex in _EXEMPT:
        if path == ex:
            return True
        if ex.is_dir() and ex in path.parents:
            return True
    return False


def _python_files() -> list[Path]:
    files: list[Path] = []
    for p in SCANNED_PATHS:
        if p.is_dir():
            files.extend(sorted(p.rglob("*.py")))
        elif p.is_file():
            files.append(p)
    return [f for f in files if not _is_exempt(f)]


def _baseagent_code_tokens(text: str) -> list[int]:
    """Return the line numbers where ``BaseAgent`` appears as a NAME token.

    COMMENT and STRING (incl. docstring) tokens are ignored, so a ``BaseAgent``
    reference inside a comment or docstring does NOT count — only real code does.
    """
    hits: list[int] = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        for tok in tokens:
            if tok.type == tokenize.NAME and tok.string == "BaseAgent":
                hits.append(tok.start[0])
    except (tokenize.TokenError, IndentationError):
        # Fallback: a tokenizer failure shouldn't silently pass the guard — fall
        # back to a substring check so a malformed file still fails loudly.
        if "BaseAgent" in text:
            hits.append(-1)
    return hits


@pytest.mark.parametrize("py_file", _python_files(), ids=lambda p: str(p.relative_to(BACKEND)))
def test_no_baseagent_reference(py_file: Path) -> None:
    """No scanned agent-tree module may reference ``BaseAgent`` as a code token."""
    text = py_file.read_text(encoding="utf-8")
    hits = _baseagent_code_tokens(text)
    assert not hits, (
        f"{py_file.relative_to(BACKEND)} references BaseAgent as a code token "
        f"(lines {hits}) — the deepagents migration forbids BaseAgent on the "
        f"pipeline/free-chat paths. Pipelines use DeepAgentRunner; free-chat uses "
        f"ChatRunner. (The live /flowin-handoff subsystem is the only exemption.)"
    )


def test_scanned_paths_exist() -> None:
    """Sanity: the scanned roots exist (catches accidental path typos)."""
    assert (BACKEND / "agents" / "execution_engine" / "engine.py").exists()
    assert (BACKEND / "app" / "agents" / "chat_runner.py").exists()
    assert (BACKEND / "app" / "api" / "websocket.py").exists()


def test_legacy_chat_stack_is_deleted() -> None:
    """The legacy free-chat stack files are gone (7b-5 true zero-legacy)."""
    for gone in (
        "orchestrator.py", "deep_agent.py", "discovery.py", "requirements.py",
        "user_stories.py", "ppt.py", "prototype.py", "ui_design.py", "preview.py",
    ):
        assert not (BACKEND / "app" / "agents" / gone).exists(), gone


def test_exemptions_are_genuinely_live() -> None:
    """The BaseAgent exemptions are the live handoff subsystem, not dead code.

    Guards against the exemption list silently masking a reintroduced legacy chat
    agent: each exempt path must still exist AND the handoff agents must still import
    BaseAgent (i.e. the exemption is load-bearing for a live feature, not stale).
    """
    base = BACKEND / "app" / "agents" / "base.py"
    handoff = BACKEND / "app" / "agents" / "handoff"
    assert base.exists() and "class BaseAgent" in base.read_text(encoding="utf-8")
    assert handoff.is_dir()
    # At least one live handoff agent imports BaseAgent (the reason base.py survives).
    importers = [
        p for p in handoff.rglob("*.py")
        if "from app.agents.base import BaseAgent" in p.read_text(encoding="utf-8")
    ]
    assert importers, "no handoff agent imports BaseAgent — exemption may be stale"
