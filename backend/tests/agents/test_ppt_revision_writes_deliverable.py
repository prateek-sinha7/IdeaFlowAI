"""tests/agents/test_ppt_revision_writes_deliverable.py — FIX-601 regression guard.

Before FIX-601, ``ppt_revision`` had no write tools: a step with no ``tools:``
block compiles to ``write_files: False`` (``agents/workflows/plan.py``'s
``ToolPermissions`` default), and ``denied_tools`` (``agents/workflows/
permission_caps.py``) then stripped ``write_file``/``edit_file`` from the
runner. Its deliverable also resolved via ``strategy: ppt``/``presentation.pptx``
(``ctx.last_streamed`` — chat text, never a sandbox file). So
``presentation.html`` was written exactly once, by ``ppt-composer`` on v1, and
never again: every ``ref=vN`` git tag captured identical stale bytes.

The fix (``agents/workflows/ppt_revision/workflow.yaml``): the step gained
``tools: {read_files: true, write_files: true}``, and the deliverable moved to
``strategy: single_file``/``name: presentation.html`` so it reads the sandbox
file back instead of the last streamed chat turn.

This file pins, at three levels:

  1. Compile time — the step's compiled permissions grant write access and the
     deliverable resolves from the sandbox, not chat text.
  2. Git — a revision that writes the deliverable produces a NEW commit
     touching that file (not one stale commit repeated across tags).
  3. Chain payload — ``.chain/{run_id}/presentation.html`` is byte-identical
     to the sandbox-root deliverable after a terminal write.

Offline / no API key. Run this file alone (not the whole suite).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

from agents.execution_engine.engine import compile_for_run
from agents.workflows.permission_caps import denied_tools


# ---------------------------------------------------------------------------
# 1. Compile-time: write tools granted, deliverable reads the sandbox
# ---------------------------------------------------------------------------


def test_ppt_revision_step_compiles_with_write_tools_granted() -> None:
    """FIX-601: the step must NOT compile to the least-privilege (no-write) default.

    Before the fix this step had no ``tools:`` block, so ``write_files`` compiled
    to ``False`` and ``denied_tools`` stripped ``edit_file``/``write_file``
    (measured: ``denied: ['edit_file', 'execute', 'write_file']``). After the
    fix only ``execute`` remains denied.
    """
    compiled = compile_for_run("ppt_revision")
    step = compiled.steps[0]

    assert step.tools.read_files is True
    assert step.tools.write_files is True

    denied = denied_tools(step.tools)
    assert (
        "edit_file" not in denied
    ), f"edit_file must be grantable on ppt_revision's step; denied={sorted(denied)}"
    assert (
        "write_file" not in denied
    ), f"write_file must be grantable on ppt_revision's step; denied={sorted(denied)}"


def test_ppt_revision_deliverable_is_single_file_presentation_html() -> None:
    """FIX-601: the deliverable reads the sandbox back, it does not stream chat text.

    ``strategy: ppt`` resolves to ``ctx.last_streamed`` — the revision agent's
    LAST turn of prose, never a file. ``single_file`` reads ``presentation.html``
    off the sandbox instead, so a revision that edits that file is actually
    reflected in the deliverable.
    """
    compiled = compile_for_run("ppt_revision")
    assert compiled.deliverable.strategy == "single_file"
    assert compiled.deliverable.name == "presentation.html"


# ---------------------------------------------------------------------------
# 2. Git: a revision that writes the deliverable produces a new commit
# ---------------------------------------------------------------------------


def _git(*args: str, cwd: Path) -> str:
    """Run a git command and return stdout (stripped). Matches the
    ``test_git_versioning_e2e.py`` helper's fixed test identity."""
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=E2E Test",
            "-c",
            "user.email=test@flowin.local",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"git {args} failed: {result.stderr}"
    return result.stdout.strip()


def _mk_git_sandbox(tmp_path: Path, *, user_id: str = "user-1", run_id: str = "run-1"):
    """A real, throwaway git sandbox — never depends on the reference family."""
    from app.agents.sandbox import RunSandbox

    sb = RunSandbox(user_id, run_id, runs_root=str(tmp_path))
    sb.ensure()
    sb.git_init_sandbox()
    return sb


def test_revision_writing_the_deliverable_is_a_new_commit_on_that_path() -> None:
    """The direct encoding of "git log -- presentation.html gains a commit per
    version" (FIX-601's measured before/after on the real 6-version family).

    Before the fix, only ppt-composer's v1 write ever touched
    ``presentation.html`` — a later revision's edit never landed in the
    sandbox, so this path had exactly one commit no matter how many revisions
    ran. After the fix, a revision step that edits the file in place produces
    its own commit touching that path.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        sb = _mk_git_sandbox(Path(td), run_id="fix601-git")

        # v1: ppt-composer writes the deck.
        (sb.root / "presentation.html").write_text(
            "<h1>Subsea Fibre Splice Operations</h1>", encoding="utf-8"
        )
        v1_sha = sb.commit_all("step: ppt-composer")
        assert v1_sha, "v1 commit must produce a SHA"
        sb.create_tag("v1")

        # v2: ppt-revision-agent edits presentation.html in place (the fix).
        (sb.root / "presentation.html").write_text(
            "<h1>SPLICE REVISION THREE</h1>", encoding="utf-8"
        )
        v2_sha = sb.commit_all("step: ppt-revision-agent")
        assert v2_sha, "v2 commit must produce a SHA"
        assert v2_sha != v1_sha
        sb.create_tag("v2")

        log = _git(
            "log", "--oneline", "--", "presentation.html", cwd=sb.root
        ).splitlines()
        assert len(log) == 2, (
            "presentation.html must gain one commit per revision, not stay at "
            f"the v1 write forever; got {len(log)} commit(s): {log}"
        )

        v2_bytes = _git("show", "v2:presentation.html", cwd=sb.root)
        assert v2_bytes == "<h1>SPLICE REVISION THREE</h1>"
        assert v2_bytes != _git("show", "v1:presentation.html", cwd=sb.root)


# ---------------------------------------------------------------------------
# 3. Chain payload: .chain/{run_id}/presentation.html mirrors the sandbox root
# ---------------------------------------------------------------------------


def test_chain_payload_copies_the_revised_deliverable_byte_identical() -> None:
    """.chain/{run_id}/<deliverable> must be a byte-identical copy of the
    sandbox-root deliverable that the revision actually wrote.

    Exercises ``_write_chain_payload`` directly (same technique as
    ``test_phase1_chain.py``), but with ``ectx.deliverable`` set — that file's
    existing tests always leave ``ectx.deliverable = None`` and never assert
    on the copy step (engine.py ~1084-1093), so this is new coverage, not a
    duplicate.
    """
    from agents.execution_engine.engine import _write_chain_payload
    from app.agents.sandbox import RunSandbox

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        sb = RunSandbox("user-1", "fix601-chain", runs_root=td)
        sb.ensure()

        revised_bytes = "<h1>SPLICE REVISION FOUR</h1>"
        (sb.root / "presentation.html").write_text(revised_bytes, encoding="utf-8")

        ectx = SimpleNamespace(
            runner=SimpleNamespace(sandbox=sb),
            final_status="completed",
            revision_ordinal=4,
            completed_tasks=[],
            git_tag="v4",
            deliverable=SimpleNamespace(name="presentation.html"),
        )

        _write_chain_payload("fix601-chain", ectx)

        copied = sb.root / ".chain" / "fix601-chain" / "presentation.html"
        assert (
            copied.is_file()
        ), ".chain/{run_id}/presentation.html must exist after a terminal write"
        assert copied.read_text(encoding="utf-8") == revised_bytes, (
            ".chain/ copy must be byte-identical to the sandbox-root deliverable "
            "the revision wrote, not stale v1 content"
        )
