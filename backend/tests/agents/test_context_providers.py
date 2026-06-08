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

from agents.capabilities.context_providers.opendesign import OpenDesignProvider
from agents.capabilities.context_providers.previous_run import PreviousRunProvider


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
    """assert_owns stub — raises PermissionError for a cross-owner parent."""

    def __init__(self, *, cross_owner=False) -> None:
        self._cross_owner = cross_owner
        self.assert_called = False

    async def assert_owns(self, parent_run_id):
        self.assert_called = True
        if self._cross_owner:
            raise PermissionError(
                f"owner may not seed from parent run {parent_run_id!r}"
            )
        return None


class _Ctx:
    def __init__(self, runner, *, od_context=None, scoped_store=None,
                 parent_run_id=None) -> None:
        self.runner = runner
        self.od_context = od_context
        self.scoped_store = scoped_store
        self.parent_run_id = parent_run_id


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


@pytest.mark.asyncio
async def test_opendesign_block_name_keys_and_content():
    runner = _FakeRunner(
        od_context=_OD,
        injection_parts=["=== TEMPLATE SEED ===\nseed\n=== END TEMPLATE SEED ==="],
        example="<html>example</html>",
    )
    ctx = _Ctx(runner, od_context=_OD)
    blocks = await OpenDesignProvider().load(ctx)

    assert blocks["ACTIVE DESIGN SYSTEM: midnight"] == "DS TOKENS"
    assert blocks["ACTIVE TEMPLATE (SKILL.md): web-prototype"] == "TEMPLATE BODY"
    assert blocks["TEMPLATE EXAMPLE (example.html): web-prototype"].startswith(
        "<html>example"
    )
    # The get_template_injection_parts block is present.
    assert any("TEMPLATE SEED" in v for v in blocks.values())


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
    ctx = _Ctx(runner, scoped_store=store, parent_run_id="parent-1")

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
    ctx = _Ctx(runner, scoped_store=store, parent_run_id="parent-evil")

    with pytest.raises(PermissionError):
        await PreviousRunProvider().load(ctx)

    # assert_owns was called BEFORE any seed — nothing was written.
    assert store.assert_called is True
    assert sandbox.written == {}


@pytest.mark.asyncio
async def test_previous_run_noop_without_parent():
    sandbox = _FakeSandbox()
    runner = _FakeRunner(sandbox=sandbox)
    ctx = _Ctx(runner, scoped_store=_FakeScopedStore(), parent_run_id=None)
    out = await PreviousRunProvider().load(ctx)
    assert out == {}
    assert sandbox.written == {}
