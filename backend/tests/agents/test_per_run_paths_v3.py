"""tests/agents/test_per_run_paths_v3.py

Behavioral tests for sandbox-git-versioning-v2, Requirement 37.

Two revisions through the real writers leave distinct `.logs/{run}.jsonl`,
`.verify/{run}/`, `.browser/{run}/` paths.

Coverage (Requirement 37 AC 1–3):
──────────────────────────────────
When a pipeline is executed, the engine writes run events to `.logs/{run_id}.jsonl`,
and tools (like playwright/pptx) write to `.verify/{run_id}/` and `.browser/{run_id}/`.
Two revisions in the same family sandbox each write to distinct per-run paths, so
their traces and evidence never collide.

fix attempt 1: the previous version of this file drove `drive_engine_pipeline` for
the `.logs/` tests but never read back the REAL `RunSandbox`/on-disk file the engine
produced — it recomputed the expected filename inline from two independently
generated UUIDs, which is trivially always distinct regardless of what the code
under test actually did (it would still pass if `run_log_path` regressed to key off
`sandbox_root_id`). It also never fed the harness a family the engine could
resolve: `drive_engine_pipeline` calls the real `ExecutionEngine.execute()`, whose
`_resolve_root_id` looks up `parent_run_id` via a REAL DB query
(`app.services.revision_root.resolve_revision_root`) — with no `WorkflowRun` row for the
revision's run id, resolution fails closed and DEGRADES the revision to its OWN
run id as the sandbox root, so root and revision silently land in two SEPARATE
physical directories instead of sharing one family sandbox (verified by direct
experimentation against a scratch sqlite DB before writing this fix). The tests
below now seed the `WorkflowRun` family chain into the app's real (hermetic,
per-process sqlite) DB before driving the revision — exactly what the API's mint
step does in production — so `_resolve_root_id` actually resolves, the revision's
sandbox genuinely shares the root's physical directory, and the assertions read the
real `RunSandbox.run_log_path` plus `Path.exists()` on the files the engine wrote.

`.verify/{run_id}/` is closed the same way, driving the real writer functions
(`pptx_tools._save_attempt` / `_write_report`) rather than only reading the
`verify_dir` property — those functions are pure `Path.write_text` (no LibreOffice/
browser dependency), so they are cheap and deterministic while still exercising the
production code path a regression would actually break.

fix attempt 2: `.browser/{run_id}/` is now ALSO writer-driven
(`test_revision_browser_dir_writer_driven`), correcting fix-attempt-1's
justification for skipping it. That justification claimed both real `.browser/`
writers "require a live Playwright browser session this harness doesn't stand
up ... degrades to unavailable without Chromium" — the prior verify FAIL
disproved this empirically: Chromium launches in this environment, and driving
the real (non-mocked) `playwright_navigate` + `playwright_take_screenshot`
tools against a `file://` URL (permitted by the default `BROWSER_URL_POLICY =
"file,localhost"`) writes a real screenshot to `.browser/{run_id}/`, no extra
infrastructure needed — the same "bind sandbox, call the real tool, assert the
file exists" shape used for `.verify/` above. The new test still degrades to a
documented `pytest.skip` (never a silent pass) if the tool itself reports
"browser unavailable" — e.g. on a machine with no Chromium install — rather
than asserting a false positive; that is a genuine environment-portability
guard, not the (disproven) blanket claim fix-attempt-1 made.
`test_revision_uses_correct_browser_dir_path` is unchanged and kept as the
fast, no-Chromium-dependency property check.

All tests use a scripted model (zero cost, deterministic).
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Path setup — make ``backend/`` importable
# ---------------------------------------------------------------------------

import sys

_BACKEND_ROOT = Path(__file__).parent.parent.parent  # …/backend/
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _turn(text: str):
    """Create a simple scripted turn with the given text.

    Mimics the helper from test_agent_input_system_prompt_v3.py.
    """
    from tests.agents._scripted_model import _ScriptedTurn

    return [_ScriptedTurn(texts=[text], usage=(5, 3))]


def _seed_family_rows(
    *, db_user_id: str, root_id: str, revision_ids: list[str]
) -> None:
    """Insert a ``User`` + ``WorkflowRun`` family chain via ``SessionLocal``.

    ``_resolve_root_id`` (``engine.py``) walks ``parent_run_id`` via a DB
    query (``app.services.revision_root.resolve_revision_root``) to find the shared sandbox
    root for a revision. In production this row exists because the API mints it
    at launch time, before calling ``engine.execute()``. This harness calls
    ``execute()`` directly, so without seeding this row the revision's root
    resolution fails closed and degrades to the revision's OWN run id — the
    revision would get its own physical sandbox directory rather than sharing
    the root's, defeating the point of this test. Every ``revision_ids`` entry
    is seeded as a direct child of ``root_id`` (matches how the tests below
    call ``drive_engine_pipeline(parent_run_id=root_id, ...)`` for each one).
    Callers MUST hold the ``isolated_db`` fixture active first — see its
    docstring for why writing through the ambient ``SessionLocal`` without it
    would risk the real database.
    """
    from app.models.database import SessionLocal
    from app.models.user import User
    from app.models.workflow import WorkflowRun

    db = SessionLocal()
    try:
        # users.cognito_sub is NOT NULL since the Cognito-only auth migration (b2a621f8).
        db.add(
            User(
                id=db_user_id,
                email=f"{db_user_id}@test.local",
                cognito_sub=f"sub-{db_user_id}",
            )
        )
        db.add(
            WorkflowRun(
                id=root_id,
                user_id=db_user_id,
                title="v7 fixture root",
                type="user_stories",
                status="completed",
                input="seed",
                owner_id=db_user_id,
                parent_run_id=None,
            )
        )
        for rev_id in revision_ids:
            db.add(
                WorkflowRun(
                    id=rev_id,
                    user_id=db_user_id,
                    title="v7 fixture revision",
                    type="user_stories",
                    status="running",
                    input="seed",
                    owner_id=db_user_id,
                    parent_run_id=root_id,
                )
            )
        db.commit()
    finally:
        db.close()


@pytest.fixture
def isolated_db():
    """Bind ``app.models.database.SessionLocal`` to a private in-memory sqlite
    engine for the test's duration.

    fix attempt 1: `tests/conftest.py` documents pinning `os.environ["DATABASE_URL"]`
    to a hermetic per-process sqlite file specifically so no test touches a real
    database. Empirically (confirmed by replaying `tests/conftest.py`'s exact
    top-level code and inspecting the result) that pin does NOT reach
    `app.core.config.settings.DATABASE_URL` here: `Settings` uses a legacy
    pydantic v1-style `class Config: env_file=...` block, which in this repo's
    pydantic-settings version resolves `backend/.env`'s live
    ``postgresql://…/flowin_local_pdf`` URL even with the correct value already
    sitting in `os.environ`. `_resolve_root_id` (`engine.py`) — and every other
    internal writer, all via the same `from app.models.database import
    SessionLocal` deferred-import convention — would otherwise open a REAL
    session against that forbidden database the moment a `WorkflowRun` row is
    seeded/read. Patching the module attribute directly (the same technique
    `test_revision_ordinal_v3.py` uses for the finalizer path) sidesteps
    `settings.DATABASE_URL` entirely, so nothing this file does can reach
    `flowin_local_pdf`. This is a pre-existing conftest/config gap outside this
    row's file ownership — flagged in the journal, not fixed here.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import app.models.database as db_module

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    db_module.Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
    )

    with patch.object(db_module, "SessionLocal", session_factory):
        yield


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPerRunPathsDistinct:
    """Verify that two revisions write to distinct per-run paths.

    Requirement 37 AC 1–3: `.logs/{run_id}.jsonl`, `.verify/{run_id}/`,
    and `.browser/{run_id}/` each use run_id as the key, so multiple
    revisions in one shared sandbox stay separated.
    """

    @pytest.mark.asyncio
    async def test_two_revisions_write_distinct_log_paths(self, isolated_db) -> None:
        """Two revisions produce separate `.logs/{run_id}.jsonl` files.

        Requirement 37 AC 1: the log writer (RunLog) writes to
        .logs/{run_id}.jsonl, not a shared flat filename. Drives the REAL
        engine for both runs, seeds the DB family link so the revision
        actually shares the root's physical sandbox (see module docstring),
        then reads back the REAL `RunSandbox.run_log_path` for each and
        asserts the on-disk files the engine itself wrote. ``isolated_db``
        keeps every DB access this triggers off the real database (see its
        docstring).
        """
        from app.agents.sandbox import RunSandbox
        from tests.agents.live_harness import drive_engine_pipeline, _RUNS_ROOT
        from tests.agents._scripted_model import ScriptedFakeChatModel

        db_user_id = f"v7-{uuid.uuid4().hex[:8]}"
        root_run_id = str(uuid.uuid4())
        rev_run_id = str(uuid.uuid4())

        # ── Drive the root run ──
        root_result = await drive_engine_pipeline(
            "user_stories",
            model=ScriptedFakeChatModel(_turn("root output")),
            brief="test brief",
            user_id=db_user_id,
            run_id=root_run_id,
            fake_planner=True,
        )
        assert root_result.completed, f"Root run failed: {root_result.error}"

        # ── Seed the family link BEFORE driving the revision (mirrors the
        #    API's mint-time insert) so _resolve_root_id can find it. ──
        _seed_family_rows(
            db_user_id=db_user_id, root_id=root_run_id, revision_ids=[rev_run_id]
        )

        # ── Drive a revision (with parent_run_id pointing to root) ──
        rev_result = await drive_engine_pipeline(
            "user_stories",
            model=ScriptedFakeChatModel(_turn("revision output")),
            brief="test revision brief",
            user_id=db_user_id,
            parent_run_id=root_run_id,
            run_id=rev_run_id,
            fake_planner=True,
        )
        assert rev_result.completed, f"Revision run failed: {rev_result.error}"

        # ── Read back the REAL sandbox the engine used — not a recomputed path. ──
        root_sb = RunSandbox(db_user_id, root_run_id, runs_root=str(_RUNS_ROOT))
        rev_sb = RunSandbox(
            db_user_id,
            root_run_id,
            current_run_id=rev_run_id,
            runs_root=str(_RUNS_ROOT),
        )

        assert root_sb.root == rev_sb.root, (
            "the revision must share the root's physical sandbox directory "
            "(family-root resolution failed — check the WorkflowRun seed)"
        )
        assert (
            root_sb.run_log_path.parent == rev_sb.run_log_path.parent
        ), "both runs must use .logs under the shared sandbox root"
        assert (
            root_sb.run_log_path != rev_sb.run_log_path
        ), "root and revision must use different log file paths"
        assert root_sb.run_log_path.exists(), (
            f"the engine must have written the root's real log file at "
            f"{root_sb.run_log_path}"
        )
        assert rev_sb.run_log_path.exists(), (
            f"the engine must have written the revision's real log file at "
            f"{rev_sb.run_log_path}"
        )

    @pytest.mark.asyncio
    async def test_revision_uses_correct_verify_dir_path(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """A revision's `.verify/{run_id}/` path uses run_id, not sandbox_root_id.

        Requirement 37 AC 2: the verify_dir property returns
        .verify/{run_id}/, not a flat .verify/ directory — and the REAL writer
        (`pptx_tools._save_attempt` / `_write_report`, the functions the ppt
        pipeline calls to leave build evidence) actually lands two revisions'
        files at those two distinct directories on disk. These two functions
        are pure `Path.write_text` (no LibreOffice/browser dependency), so
        they are safe to drive directly here without the network/binary
        dependency a full pptx build would need.
        """
        from app.agents.sandbox import RunSandbox
        from app.agents.tools import pptx_tools

        # Monkeypatch RUNS_ROOT for consistent paths.
        monkeypatch.setenv("RUNS_ROOT", str(tmp_path))

        root_id = "root-abc"
        rev_id = "revision-def"
        user_id = "user1"

        # Create sandbox instances for both the root and revision.
        root_sb = RunSandbox(user_id, root_id, runs_root=str(tmp_path))
        rev_sb = RunSandbox(
            user_id, root_id, current_run_id=rev_id, runs_root=str(tmp_path)
        )

        # Both share the same physical root directory.
        assert (
            root_sb.root == rev_sb.root
        ), "Root and revision should share the same physical sandbox directory"

        # But each has its own verify_dir.
        assert root_sb.verify_dir == root_sb.root / ".verify" / root_id
        assert rev_sb.verify_dir == rev_sb.root / ".verify" / rev_id
        assert (
            root_sb.verify_dir != rev_sb.verify_dir
        ), "verify_dir must use run_id to separate revisions"

        # ── Drive the REAL writer for each sandbox in turn (bind_sandbox is
        #    exactly what the factory does at runner-composition time). ──
        _orig_sandbox = pptx_tools._SANDBOX
        try:
            pptx_tools.bind_sandbox(root_sb)
            pptx_tools._save_attempt("root attempt source")
            pptx_tools._write_report("PASS", "root report body")

            pptx_tools.bind_sandbox(rev_sb)
            pptx_tools._save_attempt("revision attempt source")
            pptx_tools._write_report("PASS", "revision report body")
        finally:
            pptx_tools._SANDBOX = _orig_sandbox

        root_attempt = root_sb.verify_dir / "attempt-01.js"
        rev_attempt = rev_sb.verify_dir / "attempt-01.js"
        assert (
            root_attempt.exists() and root_attempt.read_text() == "root attempt source"
        )
        assert (
            rev_attempt.exists()
            and rev_attempt.read_text() == "revision attempt source"
        )
        assert (
            root_attempt != rev_attempt
        ), "each revision's attempt file must be its own"

        root_report = root_sb.verify_dir / "report.txt"
        rev_report = rev_sb.verify_dir / "report.txt"
        assert root_report.exists() and "root report body" in root_report.read_text()
        assert rev_report.exists() and "revision report body" in rev_report.read_text()
        assert (
            "revision report body" not in root_report.read_text()
        ), "the revision's report must not land in the root's verify dir"

    @pytest.mark.asyncio
    async def test_revision_uses_correct_browser_dir_path(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """A revision's `.browser/{run_id}/` path uses run_id, not sandbox_root_id.

        Requirement 37 AC 3: the browser_dir property returns
        .browser/{run_id}/, not a flat .browser/ directory.

        Property-level only, kept as a fast, no-Chromium-dependency check.
        `test_revision_browser_dir_writer_driven` below covers the same path
        with the real `playwright_navigate`/`playwright_take_screenshot`
        writers (fix attempt 2 — fix attempt 1 wrongly claimed a live browser
        session was unavailable in this harness; it is not, see that test's
        docstring).
        """
        from app.agents.sandbox import RunSandbox

        # Monkeypatch RUNS_ROOT for consistent paths.
        monkeypatch.setenv("RUNS_ROOT", str(tmp_path))

        root_id = "root-ghi"
        rev_id = "revision-jkl"
        user_id = "user2"

        # Create sandbox instances for both the root and revision.
        root_sb = RunSandbox(user_id, root_id, runs_root=str(tmp_path))
        rev_sb = RunSandbox(
            user_id, root_id, current_run_id=rev_id, runs_root=str(tmp_path)
        )

        # Both share the same physical root directory.
        assert (
            root_sb.root == rev_sb.root
        ), "Root and revision should share the same physical sandbox directory"

        # But each has its own browser_dir.
        assert root_sb.browser_dir == root_sb.root / ".browser" / root_id
        assert rev_sb.browser_dir == rev_sb.root / ".browser" / rev_id
        assert (
            root_sb.browser_dir != rev_sb.browser_dir
        ), "browser_dir must use run_id to separate revisions"

    @pytest.mark.asyncio
    async def test_revision_browser_dir_writer_driven(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Two sandboxes sharing one root write distinct real files under `.browser/`.

        Requirement 37 AC 3 — closing fix attempt 1's gap. Fix attempt 1 left
        `.browser/` property-only, justified by the claim that both real
        `.browser/` writers "require a live Playwright browser session this
        harness doesn't stand up ... degrades to unavailable without
        Chromium". The verify FAIL disproved that empirically: Chromium
        launches here, and driving the real (non-mocked) `playwright_navigate`
        + `playwright_take_screenshot` tools against a `file://` URL
        (permitted by the default `BROWSER_URL_POLICY = "file,localhost"`,
        `app/core/config.py`) writes a real screenshot to `.browser/{run_id}/`
        with no extra infrastructure — the same "bind sandbox, call the real
        tool, assert the file exists" shape `test_revision_uses_correct_
        verify_dir_path` above already uses for `.verify/`.

        Still degrades to a documented `pytest.skip` (never a silent pass) if
        the tool itself reports "browser unavailable" — a genuine
        environment-portability guard for a machine with no Chromium install,
        not a blanket excuse to skip the writer path outright.
        """
        from app.agents.sandbox import RunSandbox
        from app.agents.tools import playwright as playwright_tools

        monkeypatch.setenv("RUNS_ROOT", str(tmp_path))

        root_id = "root-mno"
        rev_id = "revision-pqr"
        user_id = "user3"

        root_sb = RunSandbox(user_id, root_id, runs_root=str(tmp_path))
        rev_sb = RunSandbox(
            user_id, root_id, current_run_id=rev_id, runs_root=str(tmp_path)
        )
        assert (
            root_sb.root == rev_sb.root
        ), "root and revision should share the same physical sandbox directory"

        root_sb.ensure()
        (root_sb.root / "root.html").write_text("<html><body>root page</body></html>")
        (root_sb.root / "rev.html").write_text(
            "<html><body>revision page</body></html>"
        )

        # The binding lives in context variables since spec 018 / FR-010 (per-worker
        # BrowserContext isolation), not a module-level ``_SANDBOX``; restore both.
        _orig_sandbox = playwright_tools._SANDBOX_VAR.get()
        _orig_agent_key = playwright_tools._AGENT_KEY_VAR.get()
        try:
            # ── Root: navigate + screenshot through the REAL tools. ──
            playwright_tools.bind_sandbox(root_sb, agent_id="root-agent")
            nav_root = playwright_tools.playwright_navigate.invoke({"url": "root.html"})
            if "browser unavailable" in nav_root.lower():
                pytest.skip(f"Chromium unavailable in this environment: {nav_root}")
            assert nav_root.lower().startswith("opened"), nav_root
            playwright_tools.playwright_take_screenshot.invoke({"filename": "shot.png"})

            # ── Revision: same real tools, distinct sandbox binding. ──
            playwright_tools.bind_sandbox(rev_sb, agent_id="rev-agent")
            nav_rev = playwright_tools.playwright_navigate.invoke({"url": "rev.html"})
            assert nav_rev.lower().startswith("opened"), nav_rev
            playwright_tools.playwright_take_screenshot.invoke({"filename": "shot.png"})
        finally:
            playwright_tools.playwright_close.invoke({})
            playwright_tools._SANDBOX_VAR.set(_orig_sandbox)
            playwright_tools._AGENT_KEY_VAR.set(_orig_agent_key)

        root_shot = root_sb.browser_dir / "shot.png"
        rev_shot = rev_sb.browser_dir / "shot.png"
        assert root_shot != rev_shot, "each revision's screenshot must be its own path"
        assert (
            root_shot.exists() and root_shot.stat().st_size > 0
        ), f"the real playwright_take_screenshot writer must have written {root_shot}"
        assert (
            rev_shot.exists() and rev_shot.stat().st_size > 0
        ), f"the real playwright_take_screenshot writer must have written {rev_shot}"

    @pytest.mark.asyncio
    async def test_three_runs_produce_three_distinct_log_paths(
        self, isolated_db
    ) -> None:
        """Root + two revisions each write to distinct `.logs/{run_id}.jsonl` files.

        Requirement 37 AC 1: multiple revisions in one family produce three
        distinct, non-overlapping log files — the root plus two depth-one
        revisions, all in the same physical sandbox directory. Drives the
        REAL engine for all three, seeds the DB family link for both
        revisions up front (see module docstring), then reads back the REAL
        `RunSandbox.run_log_path` for each and asserts the on-disk files the
        engine itself wrote. ``isolated_db`` keeps every DB access this
        triggers off the real database (see its docstring).
        """
        from app.agents.sandbox import RunSandbox
        from tests.agents.live_harness import drive_engine_pipeline, _RUNS_ROOT
        from tests.agents._scripted_model import ScriptedFakeChatModel

        db_user_id = f"v7-{uuid.uuid4().hex[:8]}"
        root_run_id = str(uuid.uuid4())
        rev1_run_id = str(uuid.uuid4())
        rev2_run_id = str(uuid.uuid4())

        # ── Drive the root run ──
        root_result = await drive_engine_pipeline(
            "user_stories",
            model=ScriptedFakeChatModel(_turn("root brief")),
            brief="root brief",
            user_id=db_user_id,
            run_id=root_run_id,
            fake_planner=True,
        )
        assert root_result.completed, f"Root run failed: {root_result.error}"

        # ── Seed both revisions as direct children of root BEFORE driving
        #    them, so _resolve_root_id can find the family for each. ──
        _seed_family_rows(
            db_user_id=db_user_id,
            root_id=root_run_id,
            revision_ids=[rev1_run_id, rev2_run_id],
        )

        # ── Drive first revision ──
        rev1_result = await drive_engine_pipeline(
            "user_stories",
            model=ScriptedFakeChatModel(_turn("revision 1 brief")),
            brief="revision 1 brief",
            user_id=db_user_id,
            parent_run_id=root_run_id,
            run_id=rev1_run_id,
            fake_planner=True,
        )
        assert rev1_result.completed, f"Revision 1 failed: {rev1_result.error}"

        # ── Drive second revision ──
        rev2_result = await drive_engine_pipeline(
            "user_stories",
            model=ScriptedFakeChatModel(_turn("revision 2 brief")),
            brief="revision 2 brief",
            user_id=db_user_id,
            parent_run_id=root_run_id,
            run_id=rev2_run_id,
            fake_planner=True,
        )
        assert rev2_result.completed, f"Revision 2 failed: {rev2_result.error}"

        # ── Read back the REAL sandboxes the engine used. ──
        root_sb = RunSandbox(db_user_id, root_run_id, runs_root=str(_RUNS_ROOT))
        rev1_sb = RunSandbox(
            db_user_id,
            root_run_id,
            current_run_id=rev1_run_id,
            runs_root=str(_RUNS_ROOT),
        )
        rev2_sb = RunSandbox(
            db_user_id,
            root_run_id,
            current_run_id=rev2_run_id,
            runs_root=str(_RUNS_ROOT),
        )

        assert (
            root_sb.root == rev1_sb.root == rev2_sb.root
        ), "all three runs must share one physical sandbox directory"

        root_log, rev1_log, rev2_log = (
            root_sb.run_log_path,
            rev1_sb.run_log_path,
            rev2_sb.run_log_path,
        )

        assert (
            root_log.parent
            == rev1_log.parent
            == rev2_log.parent
            == root_sb.root / ".logs"
        ), "all three runs must use the same .logs directory under the shared sandbox root"

        log_paths = {root_log, rev1_log, rev2_log}
        assert (
            len(log_paths) == 3
        ), f"three runs must produce 3 distinct log paths, got {log_paths}"

        for path in (root_log, rev1_log, rev2_log):
            assert (
                path.exists()
            ), f"the engine must have written the real log file at {path}"
