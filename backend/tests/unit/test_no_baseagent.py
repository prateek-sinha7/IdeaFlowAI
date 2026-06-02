"""T021a — Constitution §II guard: no new BaseAgent usage in engine code.

BaseAgent (single LLM call, stateless, no tools) is deprecated. The Universal
Execution_Engine and all new Phase 2+ modules MUST use DeepAgent only.

This test asserts that the new engine/agent modules introduced in Phase 1–2
contain zero `BaseAgent` references. It runs at every phase boundary to catch
accidental reintroduction during Phases 2–8.

Note: the legacy app/agents/orchestrator_v2.py, od_runner.py, od_ppt_runner.py
are EXEMPT until they are physically deleted (T021, gated behind T025). Once
deleted, this guard can be widened to all of backend/app/agents/.
"""

from __future__ import annotations

from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent.parent

# New Phase 1–2 modules that MUST be BaseAgent-free
GUARDED_PATHS = [
    BACKEND / "agents" / "execution_engine",
    BACKEND / "agents" / "planner",
    BACKEND / "agents" / "artifact_store",
    BACKEND / "agents" / "workflow_memory",
    BACKEND / "app" / "agents" / "types.py",
]


def _python_files() -> list[Path]:
    files: list[Path] = []
    for p in GUARDED_PATHS:
        if p.is_dir():
            files.extend(p.rglob("*.py"))
        elif p.is_file():
            files.append(p)
    return files


@pytest.mark.parametrize("py_file", _python_files(), ids=lambda p: str(p.name))
def test_no_baseagent_reference(py_file: Path) -> None:
    """No guarded engine module may reference BaseAgent."""
    text = py_file.read_text(encoding="utf-8")
    assert "BaseAgent" not in text, (
        f"{py_file} references BaseAgent — constitution §II forbids BaseAgent in "
        f"new/migrated pipeline code. Use DeepAgent(tools=[], max_iterations=1) "
        f"for utility single-call agents."
    )


def test_guarded_paths_exist() -> None:
    """Sanity: the guarded engine paths exist (catches accidental path typos)."""
    assert (BACKEND / "agents" / "execution_engine" / "engine.py").exists()
    assert (BACKEND / "agents" / "planner" / "tools.py").exists()
