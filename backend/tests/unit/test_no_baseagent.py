"""Constitution §II guard: no ``BaseAgent`` *code* usage anywhere in the agent tree.

``BaseAgent`` (single LLM call, stateless, no tools) was the legacy chat/utility
agent base. The deepagents migration replaced it everywhere: pipelines run as
``DeepAgentRunner`` graphs (engine-driven), free-chat runs on
``app.agents.chat_runner.ChatRunner``, and the ``/flowin-handoff`` IDE→PR agents
call ``app.agents.model_factory.build_model().ainvoke`` directly. This guard
asserts that no ``BaseAgent`` reference creeps back into that code.

WIDENED in migration Phase 7b-5: the legacy free-chat stack (``orchestrator.py`` +
the 7 ``BaseAgent`` chat agents) was deleted, so the scan was widened from a handful
of engine modules to the WHOLE agent tree — ``agents/`` + ``app/agents/`` +
``app/api/``.

FINALIZED in migration Phase 7c (plan 002 §5 "Phase 7c", task 7c-3): the four
handoff agents were migrated off ``BaseAgent`` (sibling task 7c-2) and the last
legacy module ``app/agents/base.py`` was **deleted**. The scan therefore has
**zero exemptions** — ``BaseAgent`` must not appear as a code token *anywhere* in
the agent tree (true zero-legacy). ``test_base_module_is_deleted`` pins the
deletion so the file can never be reintroduced.

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


def _python_files() -> list[Path]:
    files: list[Path] = []
    for p in SCANNED_PATHS:
        if p.is_dir():
            files.extend(sorted(p.rglob("*.py")))
        elif p.is_file():
            files.append(p)
    return files


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
        f"(lines {hits}) — the deepagents migration forbids BaseAgent tree-wide. "
        f"Pipelines use DeepAgentRunner; free-chat uses ChatRunner; the handoff "
        f"agents use build_model().ainvoke. There are no exemptions."
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


def test_base_module_is_deleted() -> None:
    """The last legacy module ``app/agents/base.py`` is gone (7c-3 zero-legacy).

    ``base.py`` was the sole definer of ``BaseAgent`` (plus ``AgentConfigurationError``
    / ``estimate_cost_usd`` / ``_COST_PER_1K``). Its only remaining consumer was the
    ``/flowin-handoff`` subsystem, migrated off ``BaseAgent`` in Phase 7c. Deleting
    the module is what makes the no-exemption tree-wide scan above genuinely
    zero-legacy rather than merely exemption-masked.
    """
    assert not (BACKEND / "app" / "agents" / "base.py").exists(), (
        "app/agents/base.py reappeared — it was deleted in Phase 7c (true "
        "zero-BaseAgent). Use app.agents.model_factory.build_model() for LLM "
        "construction and app.agents.types.TokenUsage for token accounting."
    )
