"""tests/agents/test_revision_gating.py — DECLARED revision-intent gating (07-10).

WR-04 / WR-06 (cluster D): revision behavior is driven by the DECLARED
per-deliverable revision-intent flag (``compiled.deliverable.revises_existing``,
sourced from ``deliverable.revises_existing`` in the manifest), NOT by the
provider-name proxy ``"previous_run" in compiled.context_providers`` and NOT by a
workflow-name branch (INV-1).

This locks three properties:

1. WR-04 — ONLY ``prototype_revision`` is classified as an in-place revision. The
   FOUR other workflows that declare the ``previous_run`` context provider
   (``ppt_revision`` / ``user_stories_revision`` / ``app_builder_revision`` /
   ``od_ppt_revision``) are NOT in-place revisions (they regenerate the whole
   artifact), even though they declare ``previous_run`` — the proxy
   misclassification is closed.

2. WR-06 — the ``previous_run`` provider seed + ``assert_owns`` fire ONLY when
   the run DECLARES revision-intent (``ctx.is_revision_workflow``), NOT on a stray
   ``parent_run_id`` alone. A forward build carrying a parent_run_id triggers NO
   cross-run seed and runs NO assert_owns.

3. L16 — when revision-intent IS declared and a parent_run_id is present, the
   provider runs ``assert_owns`` BEFORE any seed and a cross-owner
   ``PermissionError`` PROPAGATES (never swallowed). (The store-layer denial is
   covered exhaustively in ``test_parent_run_ownership.py``; here we assert the
   gate ordering at the provider seam.)

Offline / no API key.
"""

from __future__ import annotations

import pytest

from agents.capabilities.context_providers.previous_run import PreviousRunProvider
from agents.execution_engine.engine import compile_for_run

# The five workflows that DECLARE the ``previous_run`` context provider.
_PREVIOUS_RUN_WORKFLOWS = (
    "prototype_revision",
    "ppt_revision",
    "user_stories_revision",
    "app_builder_revision",
    "od_ppt_revision",
)


# ════════════════════════════════════════════════════════════════════════════
# WR-04 — classification by the DECLARED flag, not the provider-name proxy
# ════════════════════════════════════════════════════════════════════════════


def test_all_five_declare_the_previous_run_provider() -> None:
    """Sanity: all five workflows DO declare ``previous_run`` (the proxy's input)."""
    for wf in _PREVIOUS_RUN_WORKFLOWS:
        compiled = compile_for_run(wf)
        assert "previous_run" in (compiled.context_providers or []), (
            f"{wf} is expected to declare the previous_run context provider"
        )


def test_only_prototype_revision_is_an_in_place_revision() -> None:
    """WR-04: ONLY prototype_revision declares ``revises_existing`` (in-place edit).

    The other four previous_run-declaring workflows regenerate the whole artifact
    and MUST NOT be classified as in-place revisions — closing the proxy
    misclassification that was masked only by the secondary
    ``prototype.html.is_file()`` guard.
    """
    compiled = compile_for_run("prototype_revision")
    assert compiled.deliverable.revises_existing is True, (
        "prototype_revision must declare deliverable.revises_existing: true"
    )

    for wf in _PREVIOUS_RUN_WORKFLOWS:
        if wf == "prototype_revision":
            continue
        compiled = compile_for_run(wf)
        assert compiled.deliverable.revises_existing is False, (
            f"{wf} declares previous_run but is NOT an in-place revision — it must "
            f"have deliverable.revises_existing == False (WR-04 misclassification "
            f"closed)"
        )


def test_revision_intent_is_independent_of_provider_presence() -> None:
    """The classification keys off the DECLARED flag, never provider presence.

    All five declare previous_run; only one is an in-place revision — so the
    classification cannot be a function of ``"previous_run" in context_providers``.
    """
    classified = {
        wf: compile_for_run(wf).deliverable.revises_existing
        for wf in _PREVIOUS_RUN_WORKFLOWS
    }
    assert sum(classified.values()) == 1, (
        f"exactly one previous_run workflow must be an in-place revision; got "
        f"{classified}"
    )
    assert classified["prototype_revision"] is True


# ════════════════════════════════════════════════════════════════════════════
# WR-06 — the seed + assert_owns gate on DECLARED revision-intent
# ════════════════════════════════════════════════════════════════════════════


class _Ctx:
    """Minimal ctx the provider reads off (dynamic-attr surface only)."""

    def __init__(self, *, is_revision_workflow, parent_run_id, scoped_store=None, runner=None):
        self.is_revision_workflow = is_revision_workflow
        self.parent_run_id = parent_run_id
        self.scoped_store = scoped_store
        self.runner = runner


class _RecordingStore:
    """Records whether assert_owns was called; can raise to model a cross-owner."""

    def __init__(self, *, raises: bool = False):
        self.called = False
        self._raises = raises

    async def assert_owns(self, parent_run_id):
        self.called = True
        if self._raises:
            raise PermissionError(f"cross-owner: {parent_run_id}")


class _RecordingRunner:
    """Records parent-file reads + sandbox writes (the seed side effects)."""

    def __init__(self):
        self.reads: list[str] = []
        self.writes: list[tuple[str, str]] = []
        self.sandbox = self

    def read_parent_file(self, parent_run_id, name):
        self.reads.append(name)
        return f"content-of-{name}"

    def write(self, name, content):
        self.writes.append((name, content))


@pytest.mark.asyncio
async def test_forward_build_with_stray_parent_run_id_does_not_seed() -> None:
    """WR-06: a forward build (no declared revision-intent) NEVER seeds.

    Even with a stray ``parent_run_id`` AND a scoped_store present, the provider
    must short-circuit: no assert_owns, no parent reads, no sandbox writes.
    """
    store = _RecordingStore()
    runner = _RecordingRunner()
    ctx = _Ctx(
        is_revision_workflow=False,       # forward build — NOT a declared revision
        parent_run_id="parent-123",       # stray parent id on the payload
        scoped_store=store,
        runner=runner,
    )

    result = await PreviousRunProvider().load(ctx)

    assert result == {}
    assert store.called is False, "assert_owns must NOT run on a forward build (WR-06)"
    assert runner.reads == [], "no parent files may be read on a forward build (WR-06)"
    assert runner.writes == [], "no sandbox seed may occur on a forward build (WR-06)"


@pytest.mark.asyncio
async def test_declared_revision_with_parent_seeds_after_assert_owns() -> None:
    """A DECLARED revision with a parent runs assert_owns, THEN seeds."""
    store = _RecordingStore()
    runner = _RecordingRunner()
    ctx = _Ctx(
        is_revision_workflow=True,        # declared in-place revision
        parent_run_id="parent-123",
        scoped_store=store,
        runner=runner,
    )

    await PreviousRunProvider().load(ctx)

    assert store.called is True, "assert_owns must run on a declared revision"
    assert runner.reads == ["spec.md", "design.md", "tasks.md"]
    # Every readable file is seeded into the sandbox.
    assert [w[0] for w in runner.writes] == ["spec.md", "design.md", "tasks.md"]


@pytest.mark.asyncio
async def test_declared_revision_without_parent_does_not_seed() -> None:
    """A declared revision with no recorded parent seeds nothing (degrades)."""
    store = _RecordingStore()
    runner = _RecordingRunner()
    ctx = _Ctx(
        is_revision_workflow=True,
        parent_run_id=None,               # no recorded parent
        scoped_store=store,
        runner=runner,
    )

    result = await PreviousRunProvider().load(ctx)

    assert result == {}
    assert store.called is False
    assert runner.reads == []
    assert runner.writes == []


@pytest.mark.asyncio
async def test_cross_owner_permission_error_propagates_before_any_seed() -> None:
    """L16: a cross-owner PermissionError PROPAGATES; NO seed occurs.

    assert_owns runs BEFORE any parent read/seed and its PermissionError is never
    swallowed — the cross-owner parent is never silently seeded.
    """
    store = _RecordingStore(raises=True)
    runner = _RecordingRunner()
    ctx = _Ctx(
        is_revision_workflow=True,
        parent_run_id="someone-elses-run",
        scoped_store=store,
        runner=runner,
    )

    with pytest.raises(PermissionError):
        await PreviousRunProvider().load(ctx)

    assert store.called is True
    assert runner.reads == [], "assert_owns must gate BEFORE any parent read (L16)"
    assert runner.writes == [], "no cross-owner seed may occur (L16)"
