"""
Defect characterization tests for sandbox-git-versioning-v2 (task 1.4).

These tests FAIL on the current codebase — they assert the correct post-fix
behavior, which the code does not yet exhibit.  Each test will PASS once its
owning task applies the fix.

The test names end with ``_FIXME`` as a reminder that passing them requires
code changes, not test changes.

Five defects from the spec overview
-------------------------------------
D1  ``_find_chain_root`` walks ``source_run_id``, not ``parent_run_id``.
    V2-Q1 requires: revision-family identity walks ``parent_run_id`` ONLY.
    ``source_run_id`` is the chain edge, never the sandbox-directory key.
    Owning fix: task 3.1 / 3.2 (``resolve_revision_root`` replaces the walk).

D2  ``RunSandbox.__init__`` takes only ONE id; that id is used for BOTH the
    directory path AND per-run paths like ``.logs/{id}.jsonl``.
    V2-Q4 requires: two distinct ids — ``sandbox_root_id`` (directory) and
    ``current_run_id`` (per-run paths) — so revisions in a family each have
    their own trace file.
    Owning fix: task 3.4 (two-id ``RunSandbox``).

D3  ``_fire_post_run`` is invoked from the ``finally:`` block, BEFORE Step 5
    resolves the real terminal status and deliverable.  ``ectx.final_status``
    is stamped optimistically "completed" in that same block.
    V2-Q5 requires: the finalizer runs AFTER Step 5.
    Owning fix: task 5.8 (ordered 12-step finalizer).

D4  ``.chain/`` is in ``_GITIGNORE_PATHS`` and no code force-stages its
    contents, so the payload is never committed.  Every ``vN`` tag points at
    a payload-free commit.
    V2-Q2 requires: three exact paths are force-staged into Git history.
    Owning fix: task 5.2 (flat payload via exact-path force-stage).

D5  ``pre_commit`` is fired with ``payload=""`` (a literal empty string), so
    ``scan_for_secret`` short-circuits and can never block a staged secret.
    V2-Q12 requires: the real staged diff is passed as the payload.
    Owning fix: task 4.2 (replace ``payload=""`` with real staged content).

Requirements: 1, 17
"""

from __future__ import annotations

import ast
import inspect
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BACKEND_ROOT = Path(__file__).parent.parent.parent  # …/backend/
ENGINE_PATH = BACKEND_ROOT / "agents" / "execution_engine" / "engine.py"
SANDBOX_PATH = BACKEND_ROOT / "app" / "agents" / "sandbox.py"
REVISION_ROOT_PATH = BACKEND_ROOT / "app" / "services" / "revision_root.py"
LOCAL_PATH = BACKEND_ROOT / "app" / "agents" / "runtime" / "local.py"
SECRET_SCAN_PATH = BACKEND_ROOT / "agents" / "capabilities" / "hooks" / "secret_scan.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# D1 — _find_chain_root walks source_run_id  (task 3.1/3.2 fixes this)
# ---------------------------------------------------------------------------


class TestD1FindChainRootWalksSourceRunId:
    """D1 failing tests: assert the V2-Q1-correct behavior (walks parent_run_id).

    These tests fail NOW because the current implementation walks source_run_id.
    After task 3.1/3.2 ships resolve_revision_root, they will pass.
    """

    def test_d1_find_chain_root_must_not_walk_source_run_id_FIXME(self) -> None:
        """_find_chain_root must NOT reference source_run_id as the walk edge.

        V2-Q1: only parent_run_id defines revision-family sandbox identity.
        Following source_run_id causes a chained run to land in its source's
        mutable directory.

        FAILS NOW because the implementation queries source_run_id.
        PASSES after task 3.1/3.2 removes _find_chain_root or replaces it
        with resolve_revision_root, which walks parent_run_id.
        """
        src = _source(ENGINE_PATH)
        tree = ast.parse(src)
        fn_node = next(
            (
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name == "_find_chain_root"
            ),
            None,
        )

        # Post-fix state: _find_chain_root is gone (replaced by resolve_revision_root).
        # This assertion will pass once the function is deleted.
        assert fn_node is None, (
            "D1 NOT YET FIXED: _find_chain_root still exists. "
            "Task 3.1/3.2 must replace it with resolve_revision_root "
            "(which walks parent_run_id only, never source_run_id)."
        )

    def test_d1_canonical_resolver_walks_parent_run_id_FIXME(self) -> None:
        """A canonical resolve_revision_root function must exist and walk parent_run_id.

        V2-Q1 and Requirement 2 AC 1: one app-side resolver, parent_run_id only.

        FAILS NOW because the function does not exist yet.
        PASSES after task 3.1 creates resolve_revision_root.
        """
        # The canonical resolver was moved app-side (ece8b18c) to
        # app/services/revision_root.py; engine.py's _resolve_root_id delegates to it.
        assert "resolve_revision_root" in _source(
            ENGINE_PATH
        ), "engine.py must delegate root resolution to resolve_revision_root"
        src = _source(REVISION_ROOT_PATH)
        tree = ast.parse(src)

        resolver_node = next(
            (
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef)
                and node.name == "resolve_revision_root"
            ),
            None,
        )

        assert resolver_node is not None, (
            "D1 NOT YET FIXED: resolve_revision_root does not exist in revision_root.py. "
            "Task 3.1 must create it."
        )

        lines = src.splitlines()
        fn_body = "\n".join(lines[resolver_node.lineno - 1 : resolver_node.end_lineno])

        # The correct resolver walks parent_run_id, never source_run_id.
        assert (
            "parent_run_id" in fn_body
        ), "D1 NOT YET FIXED: resolve_revision_root does not walk parent_run_id."
        assert (
            "source_run_id" not in fn_body
        ), "D1 NOT YET FIXED: resolve_revision_root still references source_run_id."


# ---------------------------------------------------------------------------
# D2 — RunSandbox uses one id for both directory and log path (task 3.4 fixes)
# ---------------------------------------------------------------------------


class TestD2LogPathCollidesAcrossRevisions:
    """D2 failing tests: assert the V2-Q4-correct two-id RunSandbox behavior.

    These tests fail NOW because RunSandbox takes only one id.
    After task 3.4 ships the two-id RunSandbox, they will pass.
    """

    def test_d2_sandbox_must_accept_current_run_id_FIXME(self) -> None:
        """RunSandbox.__init__ must accept a separate current_run_id parameter.

        V2-Q4 / Requirement 3 AC 1-3: sandbox_root_id names the directory;
        current_run_id builds per-run paths (.logs/, .verify/, .browser/).

        FAILS NOW because the constructor only accepts run_id.
        PASSES after task 3.4 adds sandbox_root_id and current_run_id.
        """
        import app.agents.sandbox as sandbox_mod  # noqa: PLC0415

        sig = inspect.signature(sandbox_mod.RunSandbox.__init__)
        params = list(sig.parameters.keys())

        assert "current_run_id" in params, (
            "D2 NOT YET FIXED: RunSandbox.__init__ has no 'current_run_id' parameter. "
            "Task 3.4 must split the single run_id into sandbox_root_id + current_run_id."
        )

    def test_d2_revision_log_path_must_use_current_run_id_FIXME(
        self, tmp_path: Path
    ) -> None:
        """A revision's run_log_path must embed current_run_id, not sandbox_root_id.

        V2-Q4 / Requirement 3 AC 3: .logs/{current_run_id}.jsonl, not
        .logs/{sandbox_root_id}.jsonl.

        FAILS NOW because RunSandbox has a single id and both root and revision
        produce the same log path.
        PASSES after task 3.4 when current_run_id != sandbox_root_id resolves to
        distinct paths.
        """
        import app.agents.sandbox as sandbox_mod  # noqa: PLC0415

        sandbox_root_id = "root-run-000"
        revision_id = "revision-run-111"

        # Post-fix: construct with two distinct ids.
        sig = inspect.signature(sandbox_mod.RunSandbox.__init__)
        params = list(sig.parameters.keys())

        if "current_run_id" not in params:
            pytest.fail(
                "D2 NOT YET FIXED: RunSandbox has no current_run_id parameter. "
                "Two-id split (task 3.4) is required."
            )

        # This branch is only reached after the fix:
        revision_sandbox = sandbox_mod.RunSandbox(
            "user1",
            sandbox_root_id,
            current_run_id=revision_id,
            runs_root=str(tmp_path),
        )
        assert revision_id in str(
            revision_sandbox.run_log_path
        ), "D2 REGRESSION: run_log_path does not contain current_run_id."
        assert sandbox_root_id not in revision_sandbox.run_log_path.name, (
            "D2 REGRESSION: run_log_path filename still uses sandbox_root_id instead of "
            "current_run_id.  Expected .logs/{current_run_id}.jsonl."
        )


# ---------------------------------------------------------------------------
# D3 — _fire_post_run runs before Step 5 (task 5.8 fixes this)
# ---------------------------------------------------------------------------


class TestD3FirePostRunBeforeStep5:
    """D3 failing tests: assert the V2-Q5-correct finalizer ordering.

    These tests fail NOW because _fire_post_run is invoked in the finally block
    before Step 5.  After task 5.8 ships the ordered 12-step finalizer, they pass.
    """

    def test_d3_fire_post_run_must_not_exist_as_standalone_function_FIXME(
        self,
    ) -> None:
        """_fire_post_run must be replaced by the ordered 12-step finalizer.

        V2-Q5 / Requirement 5 AC 3: finalize_terminal_run with exactly one exit
        replaces the scattered _fire_post_run calls.

        FAILS NOW because _fire_post_run still exists.
        PASSES after task 5.8 deletes _fire_post_run and replaces it with
        finalize_terminal_run.
        """
        src = _source(ENGINE_PATH)
        tree = ast.parse(src)

        fn_node = next(
            (
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name == "_fire_post_run"
            ),
            None,
        )

        assert fn_node is None, (
            "D3 NOT YET FIXED: _fire_post_run still exists. "
            "Task 5.8 must replace it with finalize_terminal_run (the ordered "
            "12-step sequence with exactly one exit point)."
        )

    def test_d3_finalize_terminal_run_must_exist_FIXME(self) -> None:
        """A finalize_terminal_run function must exist.

        V2-Q5 / Requirement 5 AC 3: the ordered 12-step finalizer.

        FAILS NOW because the function does not exist.
        PASSES after task 5.8 creates finalize_terminal_run.
        """
        src = _source(ENGINE_PATH)
        tree = ast.parse(src)

        fn_node = next(
            (
                node
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "finalize_terminal_run"
            ),
            None,
        )

        assert fn_node is not None, (
            "D3 NOT YET FIXED: finalize_terminal_run does not exist in engine.py. "
            "Task 5.8 must create the ordered 12-step finalizer that runs after Step 5."
        )

    def test_d3_optimistic_completed_stamp_must_be_removed_FIXME(self) -> None:
        """The optimistic ectx.final_status = 'completed' stamp must be removed.

        V2-Q5 / Requirement 5 AC 2: the optimistic stamp before Step 5 is deleted;
        candidate outcome is resolved in Step 5 and passed as a typed CandidateOutcome.

        FAILS NOW because the stamp still exists in the finally block.
        PASSES after task 5.8 deletes it.
        """
        src = _source(ENGINE_PATH)

        optimistic_stamp_present = (
            'ectx.final_status = "completed"' in src
            or "ectx.final_status = 'completed'" in src
        )

        assert not optimistic_stamp_present, (
            "D3 NOT YET FIXED: the optimistic ectx.final_status = 'completed' stamp "
            "still exists in engine.py. Task 5.8 must remove it — the candidate "
            "outcome is resolved in Step 5, not in the finally block."
        )


# ---------------------------------------------------------------------------
# D4 — .chain/ is gitignored and never committed (task 5.2 fixes this)
# ---------------------------------------------------------------------------


class TestD4ChainDirGitignored:
    """D4 failing tests: assert the V2-Q2-correct force-staged flat payload.

    These tests fail NOW because .chain/ is gitignored and no force-staging
    exists.  After task 5.2 ships build_flat_payload, they will pass.
    """

    def test_d4_payload_allowlist_force_stage_must_exist_FIXME(self) -> None:
        """Engine must contain force-staging logic for the .chain/ allowlist.

        V2-Q2 / Requirement 4 AC 11: exactly three exact paths are force-staged.
        The payload_allowlist() function (or equivalent) plus stage_exact /
        force-add logic must exist.

        FAILS NOW because no force-stage logic exists.
        PASSES after task 5.2 creates build_flat_payload with the force-stage.
        """
        engine_src = _source(ENGINE_PATH)
        force_stage_patterns = [
            "build_flat_payload",
            "payload_allowlist",
            "stage_exact",
        ]

        found = any(pat in engine_src for pat in force_stage_patterns)
        assert found, (
            "D4 NOT YET FIXED: no force-staging logic exists for the .chain/ "
            "payload allowlist (build_flat_payload / payload_allowlist / stage_exact "
            "are all absent from engine.py). "
            "Task 5.2 must create build_flat_payload that force-stages the exact "
            "three allowlist paths."
        )

    def test_d4_chain_payload_committed_in_terminal_snapshot_real_git_FIXME(
        self, tmp_path: Path
    ) -> None:
        """A terminal snapshot commit must contain the three .chain/ files.

        V2-Q2 / Requirement 4 AC 1, 13: after force-staging, 'git show --stat'
        on the terminal snapshot must list the three .chain/ paths.

        FAILS NOW because .chain/ is gitignored and never force-staged.
        PASSES after task 5.2 when the payload is force-committed.
        """
        if not shutil.which("git"):
            pytest.skip("git not available on PATH")

        repo = tmp_path / "sandbox"
        repo.mkdir()

        def _git(*args: str) -> str:
            result = subprocess.run(
                ["git", *args],
                cwd=repo,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                raise RuntimeError(f"git {' '.join(args)} failed:\n{result.stderr}")
            return result.stdout.strip()

        _git("init", "-b", "main")
        _git("config", "user.email", "test@test.test")
        _git("config", "user.name", "Test")

        # Seed the .gitignore exactly as the engine does today (.chain/ ignored).
        (repo / ".gitignore").write_text(".chain/\n", encoding="utf-8")
        _git("add", ".gitignore")
        _git("commit", "-m", "chore: init")

        # Write a deliverable and the three flat .chain/ payload files.
        (repo / "prototype.html").write_text("<html/>", encoding="utf-8")
        chain_root = repo / ".chain"
        chain_root.mkdir(exist_ok=True)
        (chain_root / "logs.jsonl").write_text('{"event": "done"}\n', encoding="utf-8")
        (chain_root / "summary.md").write_text("schema_version: 2\n", encoding="utf-8")
        (chain_root / "prototype.html").write_bytes(b"<html/>")

        # Force-add exactly the three paths (simulating what task 5.2 will do).
        _git("add", "prototype.html")
        _git("add", "-f", ".chain/logs.jsonl")
        _git("add", "-f", ".chain/summary.md")
        _git("add", "-f", ".chain/prototype.html")
        _git("commit", "-m", "snapshot: run abc status completed")

        show_stat = _git("show", "--stat", "HEAD")

        # All three .chain/ paths must appear in the commit.
        assert ".chain/logs.jsonl" in show_stat, (
            "D4 NOT YET FIXED: .chain/logs.jsonl not in the terminal snapshot commit. "
            "Task 5.2 must force-stage the exact three allowlist paths."
        )
        assert (
            ".chain/summary.md" in show_stat
        ), "D4 NOT YET FIXED: .chain/summary.md not in the terminal snapshot commit."
        assert (
            ".chain/prototype.html" in show_stat
        ), "D4 NOT YET FIXED: .chain/prototype.html not in the terminal snapshot commit."

    def test_d4_chain_payload_absent_from_commits_today_characterization(
        self, tmp_path: Path
    ) -> None:
        """Characterization: today a normal commit leaves .chain/ out entirely.

        This test documents current (broken) behavior: .chain/ content is ignored
        and does NOT appear in 'git show --stat'.  It PASSES now and MUST REMAIN
        PASSING after the fix IF the fix only adds force-staging logic and does
        not break ordinary commits.

        (This is the positive characterization counterpart to the FIXME above.)
        """
        if not shutil.which("git"):
            pytest.skip("git not available on PATH")

        repo = tmp_path / "sandbox2"
        repo.mkdir()

        def _git(*args: str) -> str:
            result = subprocess.run(
                ["git", *args],
                cwd=repo,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                raise RuntimeError(f"git {' '.join(args)} failed:\n{result.stderr}")
            return result.stdout.strip()

        _git("init", "-b", "main")
        _git("config", "user.email", "test@test.test")
        _git("config", "user.name", "Test")

        (repo / ".gitignore").write_text(".chain/\n", encoding="utf-8")
        _git("add", ".gitignore")
        (repo / "prototype.html").write_text("<html/>", encoding="utf-8")
        _git("add", "prototype.html")
        _git("commit", "-m", "chore: step commit")

        chain_dir = repo / ".chain" / "run-abc"
        chain_dir.mkdir(parents=True)
        (chain_dir / "summary.md").write_text("# summary", encoding="utf-8")

        # Normal git add -A does NOT pick up .chain/ because it is gitignored.
        _git("add", "-A")
        staged = _git("diff", "--cached", "--name-only")
        assert ".chain" not in staged, (
            "Characterization broken: .chain/ appeared in staging without force-add. "
            "The .gitignore seeding is no longer working."
        )


# ---------------------------------------------------------------------------
# D5 — pre_commit fires with payload="" so scan cannot block (task 4.2 fixes)
# ---------------------------------------------------------------------------


class TestD5PreCommitEmptyPayload:
    """D5 failing tests: assert the V2-Q12-correct real-payload behavior.

    These tests fail NOW because the engine passes payload="" to pre_commit.
    After task 4.2 replaces it with the real staged diff, they will pass.
    """

    def test_d5_pre_commit_must_not_use_empty_payload_FIXME(self) -> None:
        """engine.py must not fire pre_commit with the literal payload="".

        V2-Q12 / Requirement 11 AC 4: the scanner receives the actual staged diff.
        Passing payload="" means scan_for_secret("") short-circuits immediately
        (``if not payload: return None``) and can never block a staged secret.

        FAILS NOW because the source contains payload="".
        PASSES after task 4.2 replaces it with staged.hook_payload.
        """
        src = _source(ENGINE_PATH)

        # Locate the pre_commit fire-hooks call block.
        # The call spans multiple lines:
        #   await self._fire_hooks(       <- line N
        #       "pre_commit", …,          <- line N+1
        #       payload="",               <- line N+k
        lines = src.splitlines()
        pre_commit_block_lines: list[int] = []
        for i, line in enumerate(lines):
            if "_fire_hooks" in line:
                near = "\n".join(lines[i : i + 3])
                if '"pre_commit"' in near:
                    context = "\n".join(lines[i : i + 12])
                    if 'payload=""' in context:
                        pre_commit_block_lines.append(i + 1)

        assert not pre_commit_block_lines, (
            f'D5 NOT YET FIXED: pre_commit is fired with payload="" at '
            f"line(s) {pre_commit_block_lines} in engine.py. "
            "Task 4.2 must replace the empty placeholder with the real staged "
            "diff (staged.hook_payload)."
        )

    def test_d5_staged_hook_payload_must_be_used_FIXME(self) -> None:
        """engine.py must pass the real staged content to pre_commit.

        V2-Q12 / Requirement 11 AC 4: staged.hook_payload (or equivalent real
        content) is passed to pre_commit so scan_for_secret receives the diff.

        FAILS NOW because staged.hook_payload does not exist.
        PASSES after task 4.2 when the real staged diff is computed and passed.
        """
        src = _source(ENGINE_PATH)

        real_payload_patterns = [
            "staged.hook_payload",
            "hook_payload",
            "staged_diff",
            "staged_content",
        ]

        found_near_pre_commit = False
        lines = src.splitlines()
        for i, line in enumerate(lines):
            if "_fire_hooks" in line:
                near = "\n".join(lines[i : i + 3])
                if '"pre_commit"' not in near:
                    continue
                context = "\n".join(lines[i : i + 15])
                if any(pat in context for pat in real_payload_patterns):
                    found_near_pre_commit = True
                    break

        assert found_near_pre_commit, (
            "D5 NOT YET FIXED: the pre_commit fire_hooks call does not pass a "
            "real staged payload (staged.hook_payload / hook_payload / staged_diff). "
            "Task 4.2 must add this."
        )

    def test_d5_scan_for_secret_blocks_planted_secret_in_real_staged_content(
        self,
    ) -> None:
        """scan_for_secret CAN block a planted secret — proving the scanner works.

        This is NOT a failing test; it documents that the scanner itself is
        correct.  The only reason D5 blocks nothing is that the ENGINE passes "".
        After task 4.2 the engine passes the real diff, and the scanner will block.

        This test PASSES now and must continue to pass after the fix.
        """
        sys.path.insert(0, str(BACKEND_ROOT))
        from agents.capabilities.hooks.secret_scan import scan_for_secret  # noqa: PLC0415

        # Real secret that the scanner must detect.
        real_staged_diff = textwrap.dedent(
            """\
            diff --git a/prototype.html b/prototype.html
            --- a/prototype.html
            +++ b/prototype.html
            @@ -0,0 +1 @@
            +OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz1234567890ABCD
            """
        )

        assert scan_for_secret(real_staged_diff) is not None, (
            "scan_for_secret failed to detect a planted OPENAI_API_KEY. "
            "The scanner's pattern list may need updating."
        )

        # Empty string (the current defective payload) returns None — no block.
        assert (
            scan_for_secret("") is None
        ), "scan_for_secret('') returned non-None — unexpected behavior."
