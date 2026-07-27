"""Phase-0 harness gate (T-004 / R-05): prove the eval-suite plumbing works
BEFORE any real test is built on it.

Validates, in one file:
  1. package refs — the offline scripted-model harness, the workflow
     compiler, and the revision post-step capability all import;
  2. the harness actually drives — one scripted model turn streams text and
     usage metadata end-to-end;
  3. sandbox plumbing — the ``runs_root`` fixture lets a real ``RunSandbox``
     write/read a file locally;
  4. marker selection — this module is collected under ``-m eval``.

Zero LLM tokens; no network.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.eval


def test_harness_imports() -> None:
    """All load-bearing suite dependencies import (R-05a)."""
    from agents.capabilities.post_steps.revision_validation import (
        RevisionValidationPostStep,
    )
    from agents.execution_engine.engine import compile_for_run  # noqa: F401
    from tests.agents._scripted_model import (  # noqa: F401
        ScriptedFakeChatModel,
        _ScriptedTurn,
    )

    assert RevisionValidationPostStep.name == "revision_validation"


def test_compile_prototype_revision_resolves() -> None:
    """The target workflow compiles (shape assertions are L2's job, not here)."""
    from agents.execution_engine.engine import compile_for_run

    compiled = compile_for_run("prototype_revision")
    assert compiled is not None


def test_scripted_model_turn_streams() -> None:
    """One scripted turn drives: text chunks + usage arrive (R-05b)."""
    from tests.agents._scripted_model import ScriptedFakeChatModel, _ScriptedTurn

    model = ScriptedFakeChatModel(
        [_ScriptedTurn(texts=["hello ", "world"], usage=(10, 5))]
    )
    chunks = list(model.stream("hi"))
    text = "".join(c.content for c in chunks if isinstance(c.content, str))
    assert text == "hello world"


def test_runs_root_sandbox_roundtrip(runs_root) -> None:
    """The runs_root fixture makes a real RunSandbox usable locally (R-05c)."""
    from app.agents.sandbox import RunSandbox

    sandbox = RunSandbox("eval-user", "eval-run")
    sandbox.ensure()
    assert str(sandbox.root).startswith(str(runs_root))
    sandbox.path_for("prototype.html").write_text("<!doctype html>", encoding="utf-8")
    assert sandbox.path_for("prototype.html").read_text(encoding="utf-8") == "<!doctype html>"
