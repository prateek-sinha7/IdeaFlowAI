"""Wave-0 unit tests for the two ``ContextProvider`` capabilities
(07-02 / PARITY-03 + INV-8/L16).

  * ``OpenDesignProvider.load(ctx)`` composes the ``{block-name -> content}`` map
    the engine's L12 od/template/example injection branches build today
    (engine.py:3306-3386) — the EXACT block-name keys + the
    ``get_template_injection_parts`` blocks, in declared order. The heavy
    ``od_loader`` reads ride the boundary ``od_context`` dict + the handle
    (Assumption A6) — the capability imports no ``app.*`` (Pitfall 4).

  * ``PreviousRunProvider.load(ctx)`` seeds the parent run's spec/design/tasks
    into this run's sandbox, ownership-checked via ``ScopedStore.assert_owns``
    BEFORE seeding. A cross-owner parent's ``PermissionError`` PROPAGATES out of
    ``load`` (never swallowed) — the L16 ratchet.

This module also pins the move-don't-copy byte-parity of the three relocated
loaders (``load_prototype_context`` / ``get_template_injection_parts`` /
``get_example_html``) at their NEW home (``agents.execution_engine.od_context``).
"""

from __future__ import annotations

import pytest

from agents.capabilities.context_providers.opendesign import (
    RAW_BLOCK_PREFIX,
    OpenDesignProvider,
)
from agents.capabilities.context_providers.previous_run import PreviousRunProvider


def _raw_part_keys(blocks: dict) -> list[str]:
    """The RAW-sentinel injection-part keys (CR-04), in dict (insertion) order."""
    return [k for k in blocks if k.startswith(f"{RAW_BLOCK_PREFIX}injection-part-")]


def _raw_part_vals(blocks: dict) -> list[str]:
    return [blocks[k] for k in _raw_part_keys(blocks)]


# ===========================================================================
# Fakes — ctx + ctx.runner handle, a scoped store stub, a sandbox stub
# ===========================================================================


class _FakeRunner:
    """ctx.runner handle stub — exposes od_context + the template helpers
    (the seam the opendesign provider reaches the heavy od_loader reads through,
    Assumption A6) and the sandbox + parent-file reader for previous_run."""

    def __init__(self, *, od_context=None, injection_parts=None, example=None,
                 sandbox=None, parent_files=None) -> None:
        self.od_context = od_context
        self._injection_parts = injection_parts or []
        self._example = example
        self.sandbox = sandbox
        self._parent_files = parent_files or {}

    def template_injection_parts(self, template_id):
        return list(self._injection_parts)

    def template_example(self, template_id, max_chars=8000):
        return self._example

    def read_parent_file(self, parent_run_id, name):
        return self._parent_files.get(name)


class _FakeSandbox:
    def __init__(self) -> None:
        self.written: dict[str, str] = {}

    def write(self, name, text):
        self.written[name] = text


class _FakeScopedStore:
    """assert_owns stub — raises PermissionError for a cross-owner parent.

    ``unexpected_error`` (WR-04): raise a NON-PermissionError (a simulated DB
    outage / schema mismatch / transient store bug) so the fail-closed path can
    be exercised — the provider must SKIP the parent seed rather than degrade
    OPEN to seeding on an unconfirmed ownership check.
    """

    def __init__(self, *, cross_owner=False, unexpected_error=False) -> None:
        self._cross_owner = cross_owner
        self._unexpected_error = unexpected_error
        self.assert_called = False

    async def assert_owns(self, parent_run_id):
        self.assert_called = True
        if self._cross_owner:
            raise PermissionError(
                f"owner may not seed from parent run {parent_run_id!r}"
            )
        if self._unexpected_error:
            raise RuntimeError("simulated store outage during ownership lookup")
        return None


class _Ctx:
    def __init__(self, runner, *, od_context=None, scoped_store=None,
                 parent_run_id=None, current_spec_tools=None,
                 build_task_number="", current_spec_injects=None,
                 is_revision_workflow=False, deliverable=None) -> None:
        self.runner = runner
        self.od_context = od_context
        self.scoped_store = scoped_store
        self.parent_run_id = parent_run_id
        # WR-06 (07-10): the previous_run provider gates the seed + assert_owns on
        # the DECLARED revision-intent flag, not raw parent_run_id presence. Default
        # False (a forward build never seeds); the parent-seed tests set it True.
        self.is_revision_workflow = is_revision_workflow
        # CR-06: the existing-artifact seed is parameterized by deliverable.name.
        self.deliverable = deliverable
        # The engine threads the consuming agent's OPAQUE tool set + the build-loop
        # task number onto the ctx before provider.load (D-03; engine.py
        # _compose_context_message). Default current_spec_tools to the BUILDER set so
        # the existing positive example/parts assertions keep exercising the builder
        # path (CR-02); per-test overrides drive the tools:[] planning-agent + the
        # task-2+ suppression cases.
        self.current_spec_tools = (
            {"prototype_emit_only"} if current_spec_tools is None
            else set(current_spec_tools)
        )
        # CR-02 (07-09): the engine threads the DECLARED injects onto the ctx so the
        # provider restores the legacy per-block per-injects gate. Default to the
        # prototype AGENT.md declaration (injects=[template, design_system]) so the
        # existing positive block assertions keep passing; per-test overrides drive
        # the per-block gate cases.
        self.current_spec_injects = (
            {"template", "design_system"} if current_spec_injects is None
            else set(current_spec_injects)
        )
        self.build_task_number = build_task_number


# ===========================================================================
# OpenDesignProvider — block-name map + ordering
# ===========================================================================


_OD = {
    "template_id": "web-prototype",
    "template_body": "TEMPLATE BODY",
    "ds_id": "midnight",
    "ds_body": "DS TOKENS",
    "is_design_system_required": None,
}

# The exact L12 DS-block instruction preamble (git fb55699, spaces after each
# comma). The DS block content is this preamble immediately followed by ds_body.
_DS_PREAMBLE = (
    "Apply these tokens to ALL colors, fonts, and spacing. "
    "Map to :root variables: --bg, --fg, --accent, --surface, --border, --muted.\n"
)


@pytest.mark.asyncio
async def test_opendesign_block_name_keys_and_content():
    runner = _FakeRunner(
        od_context=_OD,
        injection_parts=["=== TEMPLATE SEED ===\nseed\n=== END TEMPLATE SEED ==="],
        example="<html>example</html>",
    )
    ctx = _Ctx(runner, od_context=_OD)
    blocks = await OpenDesignProvider().load(ctx)

    # CR-01: the DS block is the preamble + ds_body (byte-identical to git fb55699),
    # NOT the bare ds_body that the prior assertion locked in.
    assert blocks["ACTIVE DESIGN SYSTEM: midnight"] == _DS_PREAMBLE + "DS TOKENS"
    assert blocks["ACTIVE DESIGN SYSTEM: midnight"].startswith(
        "Apply these tokens to ALL colors, fonts, and spacing."
    )
    assert blocks["ACTIVE DESIGN SYSTEM: midnight"].endswith("DS TOKENS")
    assert blocks["ACTIVE TEMPLATE (SKILL.md): web-prototype"] == "TEMPLATE BODY"
    assert blocks["TEMPLATE EXAMPLE (example.html): web-prototype"].startswith(
        "<html>example"
    )
    # CR-04: the get_template_injection_parts block is present as a RAW (pre-wrapped)
    # block — keyed by the RAW sentinel, content appended verbatim by the engine.
    assert any("TEMPLATE SEED" in v for v in _raw_part_vals(blocks))


@pytest.mark.asyncio
async def test_opendesign_ds_block_has_preamble():
    """CR-01: the ACTIVE DESIGN SYSTEM block content begins with the EXACT full
    instruction preamble line (pin the bytes, not just a fragment)."""
    runner = _FakeRunner(od_context=_OD, injection_parts=[], example=None)
    ctx = _Ctx(runner, od_context=_OD)
    blocks = await OpenDesignProvider().load(ctx)

    ds = blocks["ACTIVE DESIGN SYSTEM: midnight"]
    assert ds.startswith(
        "Apply these tokens to ALL colors, fonts, and spacing. "
        "Map to :root variables: --bg, --fg, --accent, --surface, --border, --muted."
    )
    assert ds == _DS_PREAMBLE + "DS TOKENS"


@pytest.mark.asyncio
async def test_opendesign_example_gated_on_builder_tools():
    """CR-02: example.html injects ONLY for builder tool sets. A tools:[] planning
    agent (prototype-specify / prototype-plan) must NOT receive the full working
    HTML example; a builder (prototype_emit_only) must."""
    # Planning agent — tools:[] — example ABSENT.
    runner = _FakeRunner(
        od_context=_OD,
        injection_parts=["=== TEMPLATE SEED ===\nseed"],
        example="<html>example</html>",
    )
    planner_ctx = _Ctx(runner, od_context=_OD, current_spec_tools=set())
    planner_blocks = await OpenDesignProvider().load(planner_ctx)
    assert "TEMPLATE EXAMPLE (example.html): web-prototype" not in planner_blocks
    assert not any(k.startswith("TEMPLATE EXAMPLE") for k in planner_blocks)
    # A tools:[] planning agent also receives NO injection parts (legacy branch had
    # no else clause for tools:[]).
    assert not _raw_part_keys(planner_blocks)

    # Builder agent — prototype_emit_only — example PRESENT.
    builder_ctx = _Ctx(
        runner, od_context=_OD, current_spec_tools={"prototype_emit_only"}
    )
    builder_blocks = await OpenDesignProvider().load(builder_ctx)
    assert "TEMPLATE EXAMPLE (example.html): web-prototype" in builder_blocks


@pytest.mark.asyncio
async def test_opendesign_per_injects_gate():
    """CR-02 (07-09): the per-block per-injects gate is restored.

    The DS block requires ``"design_system" in injects``; the template body, the
    example, and the injection parts require ``"template" in injects``. An agent that
    declares only ONE of the two injects gets ONLY that block — exactly the legacy L12
    per-block gate (``if "design_system" in injects`` / ``if "template" in injects``).
    """
    runner = _FakeRunner(
        od_context=_OD,
        injection_parts=["=== TEMPLATE SEED ===\nseed\n=== END TEMPLATE SEED ==="],
        example="<html>example</html>",
    )

    # design_system only → DS block present; NO template/example/parts.
    ds_only = await OpenDesignProvider().load(
        _Ctx(runner, od_context=_OD, current_spec_injects={"design_system"})
    )
    assert "ACTIVE DESIGN SYSTEM: midnight" in ds_only
    assert "ACTIVE TEMPLATE (SKILL.md): web-prototype" not in ds_only
    assert "TEMPLATE EXAMPLE (example.html): web-prototype" not in ds_only
    assert not _raw_part_keys(ds_only)

    # template only → template/example/parts present; NO DS block.
    tpl_only = await OpenDesignProvider().load(
        _Ctx(runner, od_context=_OD, current_spec_injects={"template"})
    )
    assert "ACTIVE DESIGN SYSTEM: midnight" not in tpl_only
    assert "ACTIVE TEMPLATE (SKILL.md): web-prototype" in tpl_only
    assert "TEMPLATE EXAMPLE (example.html): web-prototype" in tpl_only
    assert _raw_part_keys(tpl_only)

    # NO injects declared → empty (nothing leaks past the gate).
    none = await OpenDesignProvider().load(
        _Ctx(runner, od_context=_OD, current_spec_injects=set())
    )
    assert none == {}


@pytest.mark.asyncio
async def test_opendesign_example_never_reaches_tools_empty_planning_agent():
    """T-07-09-01: example.html must NOT leak to a tools:[] planning agent EVEN when
    that agent declares the template inject (07-06 CR-02 example gate not re-opened).

    The per-injects gate (07-09) emits the template body + injection parts for a
    planning agent (injects=[template]) — but the example.html block stays behind the
    builder tool-set gate, so a tools:[] agent never receives the full working HTML doc.
    """
    runner = _FakeRunner(
        od_context=_OD,
        injection_parts=["=== TEMPLATE SEED ===\nseed\n=== END TEMPLATE SEED ==="],
        example="<html>example</html>",
    )
    planner = await OpenDesignProvider().load(
        _Ctx(
            runner, od_context=_OD,
            current_spec_tools=set(),  # tools:[]
            current_spec_injects={"template", "design_system"},
        )
    )
    # Template body + parts DO reach the planning agent (per-injects gate)…
    assert "ACTIVE TEMPLATE (SKILL.md): web-prototype" in planner
    assert _raw_part_keys(planner) == []  # tools:[] → no injection parts (legacy)
    # …but the example.html block does NOT (the builder tool-set gate, 07-06 CR-02).
    assert not any(k.startswith("TEMPLATE EXAMPLE") for k in planner)


@pytest.mark.asyncio
async def test_opendesign_build_task_2_plus_suppresses_ds_template_example():
    """CR-03: on build task 2+ for a builder, the DS / template / example blocks are
    ALL absent and only the seed injection part survives. On task 1 all three blocks
    are present (no suppression)."""
    runner = _FakeRunner(
        od_context=_OD,
        injection_parts=[
            "=== TEMPLATE SEED ===\nseed\n=== END TEMPLATE SEED ===",
            "=== LAYOUTS ===\nlayouts",
            "=== CHECKLIST ===\nchecklist",
        ],
        example="<html>example</html>",
    )

    # Task 2 — suppression active.
    t2_ctx = _Ctx(
        runner, od_context=_OD,
        current_spec_tools={"prototype_emit_only"}, build_task_number="2",
    )
    t2 = await OpenDesignProvider().load(t2_ctx)
    assert "ACTIVE DESIGN SYSTEM: midnight" not in t2
    assert "ACTIVE TEMPLATE (SKILL.md): web-prototype" not in t2
    assert "TEMPLATE EXAMPLE (example.html): web-prototype" not in t2
    # Only the seed injection part survives (RAW-keyed).
    part_vals = _raw_part_vals(t2)
    assert part_vals and all("TEMPLATE SEED" in v for v in part_vals)
    assert not any("LAYOUTS" in v or "CHECKLIST" in v for v in part_vals)

    # Task 1 — no suppression; all three blocks present.
    t1_ctx = _Ctx(
        runner, od_context=_OD,
        current_spec_tools={"prototype_emit_only"}, build_task_number="1",
    )
    t1 = await OpenDesignProvider().load(t1_ctx)
    assert "ACTIVE DESIGN SYSTEM: midnight" in t1
    assert "ACTIVE TEMPLATE (SKILL.md): web-prototype" in t1
    assert "TEMPLATE EXAMPLE (example.html): web-prototype" in t1


@pytest.mark.asyncio
async def test_opendesign_declared_order_ds_then_template_then_example():
    runner = _FakeRunner(
        od_context=_OD,
        injection_parts=["=== TEMPLATE SEED ===\nseed"],
        example="<html>example</html>",
    )
    ctx = _Ctx(runner, od_context=_OD)
    blocks = await OpenDesignProvider().load(ctx)
    keys = list(blocks.keys())
    ds_i = keys.index("ACTIVE DESIGN SYSTEM: midnight")
    tpl_i = keys.index("ACTIVE TEMPLATE (SKILL.md): web-prototype")
    ex_i = keys.index("TEMPLATE EXAMPLE (example.html): web-prototype")
    assert ds_i < tpl_i < ex_i


@pytest.mark.asyncio
async def test_context_message_parity_build_task_1_vs_task_2():
    """Dedicated context_message parity assertion (PARITY-09 / INV-3) — INDEPENDENT
    of the characterization event normalizer.

    Pins the EXACT ordered block-key sequence AND the byte content of the composed
    OD block map for a scripted prototype BUILD agent: the full ordered set on task 1
    (DS preamble+body, template body, example[:8000], injection parts in order) and
    the suppressed seed-only set on task 2. This is the non-volatile pin the
    characterization net lacked while context_message was in _VOLATILE_STRIP_KEYS — a
    context-injection regression now hard-fails HERE regardless of the normalizer."""
    example = "<html>example</html>"
    parts = [
        "=== TEMPLATE SEED ===\nseed\n=== END TEMPLATE SEED ===",
        "=== LAYOUTS ===\nlayouts",
        "=== CHECKLIST ===\nchecklist",
    ]
    runner = _FakeRunner(od_context=_OD, injection_parts=parts, example=example)

    # ── Build task 1 — full ordered block set, exact bytes ──────────────────────
    t1_ctx = _Ctx(
        runner, od_context=_OD,
        current_spec_tools={"prototype_emit_only"}, build_task_number="1",
    )
    t1 = await OpenDesignProvider().load(t1_ctx)
    # The non-part blocks keep their named keys; the injection parts are RAW-keyed
    # (CR-04) and appended verbatim by the engine (no `=== TEMPLATE INJECTION PART
    # N ===` outer wrapper). The ordering is DS → template → example → parts.
    assert list(t1.keys()) == [
        "ACTIVE DESIGN SYSTEM: midnight",
        "ACTIVE TEMPLATE (SKILL.md): web-prototype",
        "TEMPLATE EXAMPLE (example.html): web-prototype",
        f"{RAW_BLOCK_PREFIX}injection-part-0",
        f"{RAW_BLOCK_PREFIX}injection-part-1",
        f"{RAW_BLOCK_PREFIX}injection-part-2",
    ]
    assert t1["ACTIVE DESIGN SYSTEM: midnight"] == _DS_PREAMBLE + "DS TOKENS"
    assert t1["ACTIVE TEMPLATE (SKILL.md): web-prototype"] == "TEMPLATE BODY"
    assert t1["TEMPLATE EXAMPLE (example.html): web-prototype"] == example[:8000]
    assert _raw_part_vals(t1) == parts

    # ── Build task 2 — suppressed: seed injection part only ─────────────────────
    t2_ctx = _Ctx(
        runner, od_context=_OD,
        current_spec_tools={"prototype_emit_only"}, build_task_number="2",
    )
    t2 = await OpenDesignProvider().load(t2_ctx)
    assert list(t2.keys()) == [f"{RAW_BLOCK_PREFIX}injection-part-0"]
    assert _raw_part_vals(t2) == [parts[0]]


@pytest.mark.asyncio
async def test_opendesign_empty_when_no_od_context():
    ctx = _Ctx(_FakeRunner(od_context=None), od_context=None)
    assert await OpenDesignProvider().load(ctx) == {}


@pytest.mark.asyncio
async def test_opendesign_imports_no_app():
    import agents.capabilities.context_providers.opendesign as mod
    import inspect

    src = inspect.getsource(mod)
    # No direct app.* / execution_engine import in the capability (Pitfall 4).
    assert "from app." not in src.replace("# ", "")
    assert "import app." not in src
    assert "agents.execution_engine" not in src


# ===========================================================================
# Move-don't-copy byte-parity at the NEW home (execution_engine.od_context)
# ===========================================================================


def test_relocated_loaders_live_in_od_context():
    from agents.execution_engine import od_context as oc

    assert hasattr(oc, "load_prototype_context")
    assert hasattr(oc, "get_template_injection_parts")
    assert hasattr(oc, "get_example_html")
    # The PPT loader STAYS (od_context.py not deleted wholesale).
    assert hasattr(oc, "load_ppt_od_context")
    # Backward-compat re-export name still resolves.
    assert hasattr(oc, "load_prototype_od_context")


def test_old_prototype_context_package_removed():
    # The three loaders were PHYSICALLY MOVED to execution_engine/od_context.py in
    # 07-02 (INV-12 move-don't-copy), and the now-empty ``agents.prototype`` package
    # (context.py + the dead pipeline.py + __init__.py) was DELETED in 07-05. Importing
    # it must fail — the single home for the loaders is od_context.py (asserted above).
    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("agents.prototype.context")
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("agents.prototype")


# ===========================================================================
# PreviousRunProvider — ownership-checked-before-seed; PermissionError propagates
# ===========================================================================


@pytest.mark.asyncio
async def test_previous_run_seeds_same_owner_parent():
    sandbox = _FakeSandbox()
    runner = _FakeRunner(
        sandbox=sandbox,
        parent_files={
            "spec.md": "SPEC", "design.md": "DESIGN", "tasks.md": "TASKS",
        },
    )
    store = _FakeScopedStore(cross_owner=False)
    ctx = _Ctx(
        runner, scoped_store=store, parent_run_id="parent-1",
        is_revision_workflow=True,  # declared revision-intent (WR-06)
    )

    await PreviousRunProvider().load(ctx)

    assert store.assert_called is True
    assert sandbox.written == {
        "spec.md": "SPEC", "design.md": "DESIGN", "tasks.md": "TASKS",
    }


@pytest.mark.asyncio
async def test_previous_run_cross_owner_permission_error_propagates():
    sandbox = _FakeSandbox()
    runner = _FakeRunner(
        sandbox=sandbox,
        parent_files={"spec.md": "SPEC"},
    )
    store = _FakeScopedStore(cross_owner=True)
    ctx = _Ctx(
        runner, scoped_store=store, parent_run_id="parent-evil",
        is_revision_workflow=True,  # declared revision-intent (WR-06)
    )

    with pytest.raises(PermissionError):
        await PreviousRunProvider().load(ctx)

    # assert_owns was called BEFORE any seed — nothing was written.
    assert store.assert_called is True
    assert sandbox.written == {}


@pytest.mark.asyncio
async def test_previous_run_noop_without_parent():
    sandbox = _FakeSandbox()
    runner = _FakeRunner(sandbox=sandbox)
    ctx = _Ctx(
        runner, scoped_store=_FakeScopedStore(), parent_run_id=None,
        is_revision_workflow=True,
    )
    out = await PreviousRunProvider().load(ctx)
    assert out == {}
    assert sandbox.written == {}


@pytest.mark.asyncio
async def test_previous_run_forward_build_with_stray_parent_does_not_seed():
    """WR-06: a forward build (no declared revision-intent) never seeds or asserts.

    Even with a stray parent_run_id AND a scoped_store present, the provider
    short-circuits — closing the latent path where a client-payload change could
    trigger an unintended cross-run seed.
    """
    sandbox = _FakeSandbox()
    runner = _FakeRunner(
        sandbox=sandbox,
        parent_files={"spec.md": "SPEC", "design.md": "DESIGN", "tasks.md": "TASKS"},
    )
    store = _FakeScopedStore(cross_owner=True)  # would raise IF assert_owns ran
    ctx = _Ctx(
        runner, scoped_store=store, parent_run_id="parent-1",
        is_revision_workflow=False,  # forward build — NOT a declared revision
    )

    out = await PreviousRunProvider().load(ctx)

    assert out == {}
    assert store.assert_called is False  # never asserted (no PermissionError raised)
    assert sandbox.written == {}         # nothing seeded


@pytest.mark.asyncio
async def test_previous_run_unexpected_store_error_fails_closed():
    """WR-04: an UNEXPECTED (non-PermissionError) store error during assert_owns
    must FAIL CLOSED — the provider skips the parent-run seed rather than degrade
    OPEN to seeding on an unconfirmed ownership check.

    The cross-run blast radius of degrading open here is data exposure (seeding a
    parent's spec/design/tasks without a confirmed ownership check), so any error
    that is NOT the cross-owner PermissionError (which still propagates, L16) must
    result in NO parent seed. The error is swallowed (a missing/broken parent must
    never break a revision — CTX-05 parity) but the seed does NOT proceed.
    """
    sandbox = _FakeSandbox()
    runner = _FakeRunner(
        sandbox=sandbox,
        parent_files={"spec.md": "SPEC", "design.md": "DESIGN", "tasks.md": "TASKS"},
    )
    store = _FakeScopedStore(unexpected_error=True)
    ctx = _Ctx(
        runner, scoped_store=store, parent_run_id="parent-1",
        is_revision_workflow=True,  # declared revision-intent (WR-06)
    )

    out = await PreviousRunProvider().load(ctx)

    assert out == {}
    assert store.assert_called is True   # the ownership check WAS attempted
    assert sandbox.written == {}         # but FAILED CLOSED — nothing seeded
