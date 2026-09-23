"""tests/agents/test_version_family_v5.py — v1..v5 as genuinely different
versions, re-read after all five exist, and non-interference while a
revision is in flight (GAPS §2 FR-038 / FR-040 / FR-056 / FR-058).

Starting pattern: ``test_revision_ordinal_v3.py``'s
``TestSequentialTagsAcrossRealFinalization`` — it drives the REAL engine
(``ExecutionEngine.execute()`` via ``tests.agents._scripted_model._drive``,
offline/scripted, one real on-disk git sandbox) over 3 completed revisions
and asserts ``v1``/``v2``/``v3``. This file extends that pattern in two
directions that test never covered:

Part A — five DISTINCT versions (not "3 identical stub outputs"), re-read
after all five exist, through the product's ref-scoped reader
(``RunSandbox.read_bytes_at_ref`` / ``list_files_at_ref`` — ``git show
<ref>:<path>`` / ``git ls-tree -r <ref> --name-only``, never ``git show
--name-only`` — S3's documented false-negative trap: that form diffs
against the parent and omits a file whose bytes did not change).

Part B — the concurrency case: hold the 4th run genuinely mid-flight
(suspended inside ``ExecutionEngine.execute()``'s own async generator,
between two ``async for`` pulls on the SAME generator — a real coroutine
suspension, not a thread/event hack) and prove browsing v1/v2 during that
window mutates nothing (HEAD, commit count, ``git status --porcelain``,
tag set all identical before/after the browse), then let v4 finish and
become v4 (not v1, not v5), then drive v5 to confirm the sequence
continues after the interleaving.

Harness note: ``custom``'s 9 agents are all text-only (``tools: []``); the
``streamed_text`` deliverable (``.chain/output.md``) is literally the LAST
agent's (``task-list-planner``, ``order: 9``) streamed output
(``engine.py``: ``ectx.last_streamed = results[-1]["output"]``). The shared
``_scripts_for`` registry (``tests/agents/_scripted_model.py``) returns
FIXED text per agent id regardless of run — fine for T1 (which only needed
3 non-empty, non-colliding tags), but Part A/B need each run's deliverable
to carry a distinct, checkable marker. Done by monkeypatching
``_scripted_model._scripts_for`` for the duration of each driven run so
only ``task-list-planner``'s script changes (a ``VERSION-N`` marker); every
other agent's script is untouched (its content never reaches the
deliverable).

Pausing v4 mid-flight reuses ``_scripted_model._prepare_engine_run`` — a
small extraction out of ``_drive`` added by this task (see the diff in
``_scripted_model.py``): it returns the raw, unconsumed ``execute()`` async
generator instead of draining it, so a caller can pull events until a
boundary, do other (synchronous) work, then resume pulling from the exact
same generator. ``_drive`` itself is now a one-line wrapper around it —
behavior-preserving (verified: ``test_revision_ordinal_v3.py`` unchanged at
6 passed after the refactor).
"""
from __future__ import annotations

import asyncio
import shutil
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

BACKEND_ROOT = Path(__file__).parent.parent.parent  # …/backend/
sys.path.insert(0, str(BACKEND_ROOT))

import tests.agents._scripted_model as scripted_model_mod  # noqa: E402
from tests.agents._scripted_model import (  # noqa: E402
    _prepare_engine_run,
    _drive,
    _ScriptedTurn,
)
from tests.agents._scripted_model import _scripts_for as _orig_scripts_for  # noqa: E402
from tests.agents.test_finalizer_v2 import _run_git  # noqa: E402
from tests.agents.test_revision_ordinal_v3 import _seed_run  # noqa: E402

_OWNER = "harness-user"  # matches _scripted_model._drive's hardcoded owner_id / RunSandbox key


def _scripts_for_with_marker(marker: str):
    """Wrap ``_scripted_model._scripts_for`` so ``task-list-planner`` (the
    LAST agent of ``custom``, whose streamed output IS the deliverable)
    emits a version-identifiable body. Every other agent's script is the
    unmodified original — its content never reaches ``.chain/output.md``.
    """

    def _wrapped(agent_id: str) -> list[_ScriptedTurn]:
        if agent_id == "task-list-planner":
            return [
                _ScriptedTurn(
                    texts=[f"# Deliverable\n\nVersion marker: {marker}\n"],
                    usage=(5, 3),
                )
            ]
        return _orig_scripts_for(agent_id)

    return _wrapped


def _seed_chain(real_db, run_ids: list[str]) -> None:
    from app.models.user import User  # noqa: PLC0415

    if real_db.query(User).filter(User.id == _OWNER).first() is None:
        real_db.add(User(id=_OWNER, email=f"{_OWNER}@test.local"))
        real_db.commit()
    parent: str | None = None
    # GAPS T6: distinct created_offset per row — the family-wide counting
    # rule (BFS down from root, sorted by (created_at, id)) falls back to
    # the ``id`` tiebreak on a tie, and these ids are random UUIDs, so every
    # row sharing one timestamp made ordinal order depend on UUID luck
    # instead of chain order. Invisible under the old ancestor-CHAIN rule
    # (which never reads created_at at all) — newly reached, not newly
    # caused, by this fix (S3 journal precedent).
    for offset, rid in enumerate(run_ids):
        _seed_run(real_db, run_id=rid, parent_run_id=parent, user_id=_OWNER,
                  created_offset=offset * 10)
        parent = rid


def _drive_version(run_id: str, parent_run_id: str | None, marker: str) -> dict:
    """Drive one run to completion with a version-marked deliverable and
    assert it published ``completed`` (the tag assertions below are moot
    otherwise — same guard T1 uses)."""
    drive_kwargs: dict = {"pipeline_run_id": run_id}
    if parent_run_id:
        drive_kwargs["parent_run_id"] = parent_run_id
    with patch.object(scripted_model_mod, "_scripts_for", _scripts_for_with_marker(marker)):
        events = asyncio.run(_drive("custom", **drive_kwargs))
    completes = [e for e in events if e.get("type") == "pipeline_complete"]
    assert len(completes) == 1, (
        f"run {run_id}: expected exactly 1 pipeline_complete, got {completes}"
    )
    published = completes[0]["data"].get("published_status", "completed")
    assert published == "completed", (
        f"run {run_id} did not complete cleanly (published_status={published!r}) — "
        "the tag/content assertions below would be moot"
    )
    return completes[0]


async def _drive_v4_paused(rev3_id: str, rev2_id: str, sandbox, *, pause_after_completions: int = 3):
    """Drive v4 via the raw ``execute()`` generator (``_prepare_engine_run``),
    pausing right after the Nth ``agent_complete`` — genuinely mid-flight,
    well before ``pipeline_complete``/finalization/tagging. Captures a
    before/after git snapshot of the browse performed DURING the pause, then
    resumes the SAME generator to completion.

    Returns ``(events, snapshot)``. Caller is responsible for having the
    ``_scripts_for`` marker patch active for the whole call (it wraps
    ``asyncio.run(...)`` at the call site — agent scripts are looked up
    lazily, per-step, as the generator is pulled on BOTH sides of the pause).
    """
    agen, restore = _prepare_engine_run("custom", pipeline_run_id=rev3_id, parent_run_id=rev2_id)
    events: list[dict] = []
    snapshot: dict = {}
    try:
        completions = 0
        paused = False
        async for ev in agen:
            events.append(ev)
            if ev.get("type") == "agent_complete":
                completions += 1
                if completions == pause_after_completions:
                    paused = True
                    break
        assert paused, "v4 finished before reaching the pause boundary — nothing was in flight"

        # ---- genuinely in-flight here: v4 has not finalized/tagged yet ----
        repo = sandbox.root
        head_before = _run_git("rev-parse", "HEAD", cwd=repo)
        status_before = _run_git("status", "--porcelain", cwd=repo)
        tags_before = sorted(sandbox.list_tags())
        commits_before = len(_run_git("log", "--oneline", cwd=repo).splitlines())

        v1_files = sandbox.list_files_at_ref("v1")
        v1_content = sandbox.read_bytes_at_ref("v1", ".chain/output.md").decode("utf-8")
        v2_files = sandbox.list_files_at_ref("v2")
        v2_content = sandbox.read_bytes_at_ref("v2", ".chain/output.md").decode("utf-8")

        head_after = _run_git("rev-parse", "HEAD", cwd=repo)
        status_after = _run_git("status", "--porcelain", cwd=repo)
        tags_after = sorted(sandbox.list_tags())
        commits_after = len(_run_git("log", "--oneline", cwd=repo).splitlines())

        snapshot = dict(
            v1_files=v1_files, v1_content=v1_content,
            v2_files=v2_files, v2_content=v2_content,
            head_before=head_before, head_after=head_after,
            status_before=status_before, status_after=status_after,
            tags_before=tags_before, tags_after=tags_after,
            commits_before=commits_before, commits_after=commits_after,
        )

        # ---- resume the SAME suspended generator to completion ----
        async for ev in agen:
            events.append(ev)
    finally:
        restore()
    return events, snapshot


# ---------------------------------------------------------------------------
# Part A — five genuinely distinct versions, re-read after all five exist.
# ---------------------------------------------------------------------------

class TestFiveDistinctVersionFamily:
    def test_five_versions_distinct_content_tags_and_reread(self) -> None:
        if not shutil.which("git"):
            pytest.skip("git not available")

        from app.agents.sandbox import RunSandbox  # noqa: PLC0415
        from app.models.database import SessionLocal as _RealSessionLocal  # noqa: PLC0415

        run_ids = [str(uuid.uuid4()) for _ in range(5)]
        root_id = run_ids[0]

        real_db = _RealSessionLocal()
        try:
            _seed_chain(real_db, run_ids)
        finally:
            real_db.close()

        parent: str | None = None
        for i, rid in enumerate(run_ids, start=1):
            _drive_version(rid, parent, f"VERSION-{i}")
            parent = rid

        sandbox = RunSandbox(_OWNER, root_id)
        tags = sorted(sandbox.list_tags())
        assert tags == ["v1", "v2", "v3", "v4", "v5"], (
            f"expected exactly v1..v5, no gaps/reuse — got {tags}"
        )

        version_tags = ["v1", "v2", "v3", "v4", "v5"]

        # Membership via ls-tree, content via `git show <ref>:<path>` — never
        # `git show --name-only` (S3's false-negative: diffs against parent,
        # silently omits a file whose bytes didn't change between revisions).
        for i, tag in enumerate(version_tags, start=1):
            files = sandbox.list_files_at_ref(tag)
            assert ".chain/output.md" in files, (
                f"tag {tag}: deliverable missing from the commit tree ({files})"
            )
            content = sandbox.read_bytes_at_ref(tag, ".chain/output.md").decode("utf-8")
            assert f"VERSION-{i}" in content, (
                f"tag {tag}: expected its own VERSION-{i} marker, got {content!r}"
            )
            for other in range(1, 6):
                if other != i:
                    assert f"VERSION-{other}" not in content, (
                        f"tag {tag}: leaked VERSION-{other}'s content ({content!r})"
                    )

        # Re-read every version AGAIN now that all five exist — a later tag
        # must never clobber an earlier one's content.
        for i, tag in enumerate(version_tags, start=1):
            content = sandbox.read_bytes_at_ref(tag, ".chain/output.md").decode("utf-8")
            assert f"VERSION-{i}" in content, (
                f"tag {tag}: content changed on re-read after all 5 versions exist ({content!r})"
            )


# ---------------------------------------------------------------------------
# Part B — v4 held genuinely mid-flight: browsing v1/v2 must not affect it.
# ---------------------------------------------------------------------------

class TestConcurrentBrowseDuringInFlightRevision:
    def test_browsing_v1_v2_while_v4_in_flight_does_not_affect_it(self) -> None:
        if not shutil.which("git"):
            pytest.skip("git not available")

        from app.agents.sandbox import RunSandbox  # noqa: PLC0415
        from app.models.database import SessionLocal as _RealSessionLocal  # noqa: PLC0415

        root_id, rev1_id, rev2_id, rev3_id, rev4_id = (str(uuid.uuid4()) for _ in range(5))
        run_ids = [root_id, rev1_id, rev2_id, rev3_id, rev4_id]

        real_db = _RealSessionLocal()
        try:
            _seed_chain(real_db, run_ids)
        finally:
            real_db.close()

        # v1, v2, v3 complete synchronously, sequentially — the baseline the
        # owner's request assumes ("with v1, v2, v3 already complete").
        _drive_version(root_id, None, "VERSION-1")
        _drive_version(rev1_id, root_id, "VERSION-2")
        _drive_version(rev2_id, rev1_id, "VERSION-3")

        sandbox = RunSandbox(_OWNER, root_id)
        assert sorted(sandbox.list_tags()) == ["v1", "v2", "v3"]

        # Baseline v1/v2 content/listing BEFORE v4 ever starts — compared
        # against what the mid-flight browse sees below, to prove it "still
        # reflects that version, not the live tree" of the in-progress v4.
        v1_files_baseline = sandbox.list_files_at_ref("v1")
        v1_content_baseline = sandbox.read_bytes_at_ref("v1", ".chain/output.md").decode("utf-8")
        v2_files_baseline = sandbox.list_files_at_ref("v2")
        v2_content_baseline = sandbox.read_bytes_at_ref("v2", ".chain/output.md").decode("utf-8")

        # ---- v4 (rev3_id): start, hold mid-flight, browse, resume, finish ----
        with patch.object(scripted_model_mod, "_scripts_for", _scripts_for_with_marker("VERSION-4")):
            events, snap = asyncio.run(_drive_v4_paused(rev3_id, rev2_id, sandbox))

        # The browse performed WHILE v4 was in flight returned v1/v2's own,
        # unchanged content/listing — not the live (in-progress) tree.
        assert snap["v1_files"] == v1_files_baseline
        assert snap["v1_content"] == v1_content_baseline
        assert "VERSION-1" in snap["v1_content"]
        assert snap["v2_files"] == v2_files_baseline
        assert snap["v2_content"] == v2_content_baseline
        assert "VERSION-2" in snap["v2_content"]

        # The browse itself changed nothing.
        assert snap["head_after"] == snap["head_before"], "browsing moved HEAD"
        assert snap["status_after"] == snap["status_before"], "browsing dirtied the working tree"
        assert snap["tags_after"] == snap["tags_before"], "browsing changed the tag set"
        assert snap["commits_after"] == snap["commits_before"], "browsing added a commit"

        # v4 finished cleanly after being resumed.
        completes = [e for e in events if e.get("type") == "pipeline_complete"]
        assert len(completes) == 1, f"expected exactly 1 pipeline_complete for v4, got {completes}"
        published = completes[0]["data"].get("published_status", "completed")
        assert published == "completed", f"v4 did not complete cleanly (published_status={published!r})"

        # v4 becomes v4 — not v1, not v5 — with its own content in its own tag.
        assert sorted(sandbox.list_tags()) == ["v1", "v2", "v3", "v4"]
        v4_content = sandbox.read_bytes_at_ref("v4", ".chain/output.md").decode("utf-8")
        assert "VERSION-4" in v4_content

        # v1/v2 are still intact and still readable after v4 finalizes.
        assert sandbox.read_bytes_at_ref("v1", ".chain/output.md").decode("utf-8") == v1_content_baseline
        assert sandbox.read_bytes_at_ref("v2", ".chain/output.md").decode("utf-8") == v2_content_baseline

        # A fifth run confirms the sequence continues to v5 after the interleaving.
        _drive_version(rev4_id, rev3_id, "VERSION-5")
        assert sorted(sandbox.list_tags()) == ["v1", "v2", "v3", "v4", "v5"]
        v5_content = sandbox.read_bytes_at_ref("v5", ".chain/output.md").decode("utf-8")
        assert "VERSION-5" in v5_content
