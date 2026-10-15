"""ISS-683 (QA-KB-022): the single_file readback must not replace a later, read-only step's reply.

After the build writes prototype.html, a reviewer that only reads keeps its own findings in
results, the typed artifact, ``.agents/NN-*.md`` and ``agent_complete.output_length``. The
writer (a short confirmation, file just changed) still gets the file.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

# Keep first: sets RUNS_ROOT + in-memory checkpointer before app.core.config loads.
from tests.agents._scripted_model import _RUNS_ROOT  # noqa: F401

BIG_HTML = "<!doctype html><html><body>" + "<p>screen</p>" * 200 + "</body></html>"
CONFIRM = "Built prototype.html."
FINDINGS = "Validation: 3 screens checked, no issues found."


class _Runner:
    system_prompt = ""

    def __init__(self, text, write=None, sandbox=None):
        self.text, self.write, self.sandbox = text, write, sandbox

    async def astream_events(self, message):
        if self.write:
            self.sandbox.write("prototype.html", self.write)
        yield {"type": "chunk", "chunk": self.text}
        yield {"type": "usage", "input_tokens": 3, "output_tokens": 2}


async def _drive_two_steps():
    import agents.execution_engine.engine as engine_mod
    import agents.factory as factory_mod
    from agents.capabilities.model_catalog import ModelCatalog
    from agents.execution_engine.context import ExecutionContext
    from agents.execution_engine.engine import ExecutionEngine
    from agents.loader import load_agent_spec
    from agents.model_policy import ModelResolver
    from app.agents.sandbox import RunSandbox, agent_output_relpath
    from app.core.config import settings as _settings

    _settings.RUNS_ROOT = _RUNS_ROOT
    run_id = "readback-scope"
    engine = ExecutionEngine()
    typed: list[tuple] = []

    async def _noop(*a, **k):
        return "artifact-id"

    async def _record(*a, **k):
        typed.append((a, k))
        return "artifact-id"

    engine._store.store = _noop  # type: ignore[assignment]
    engine._dual_write_artifact = _record  # type: ignore[assignment]

    writer, reviewer = (
        load_agent_spec("prototype-build"),
        load_agent_spec("prototype-validate"),
    )
    specs = [writer, reviewer]
    ectx = ExecutionContext(run_id=run_id, owner_id="anon")
    ectx.disk_principal = "anon"
    ectx.deliverable = SimpleNamespace(strategy="single_file", name="prototype.html")
    ectx.model_resolver = ModelResolver(
        session_model_id="claude-haiku-4-5-20251001",
        haiku_default=_settings.BEDROCK_INFERENCE_PROFILE_ID,
        catalog=ModelCatalog(),
        _region_override="",
    )
    sandbox = RunSandbox("anon", run_id, runs_root=_RUNS_ROOT)
    results: list[dict] = []
    events: list[dict] = []
    orig_factory, orig_engine = (
        factory_mod.create_runner,
        getattr(engine_mod, "create_runner", None),
    )
    try:
        for i, (spec, runner) in enumerate(
            [
                (writer, _Runner(CONFIRM, BIG_HTML, sandbox)),
                (reviewer, _Runner(FINDINGS)),
            ]
        ):
            factory_mod.create_runner = engine_mod.create_runner = (
                lambda *a, _r=runner, **k: _r
            )
            async for ev in engine._run_agent(
                spec,
                i,
                specs,
                "Build it.",
                sandbox,
                run_id,
                "prototype",
                engine._default_planning_context("Build it."),
                None,
                None,
                "claude-haiku-4-5-20251001",
                results,
                None,
                ectx,
            ):
                events.append(ev if isinstance(ev, dict) else {"raw": str(ev)})
    finally:
        factory_mod.create_runner = orig_factory
        if orig_engine is not None:
            engine_mod.create_runner = orig_engine
    transcript = sandbox.read(agent_output_relpath(index=1, agent_id=reviewer.id)) or ""
    return results, typed, events, transcript


@pytest.mark.issue("ISS-683")
@pytest.mark.asyncio
async def test_read_only_reviewer_after_build_keeps_its_own_output():
    """ISS-683 — the build step keeps the file; a reviewer that only reads keeps its text."""
    results, typed, events, transcript = await _drive_two_steps()
    assert (
        results[0]["output"] == BIG_HTML
    )  # writer: file stands in for the confirmation
    assert results[1]["output"] == FINDINGS
    assert "<!doctype" not in transcript.lower() and FINDINGS in transcript
    reviewer_typed = [
        t for t in typed if t[1].get("producer_agent") == "prototype-validate"
    ]
    assert reviewer_typed and not any(
        "<!doctype" in repr(t).lower() for t in reviewer_typed
    )
    lengths = [
        e["data"]["output_length"] for e in events if e.get("type") == "agent_complete"
    ]
    assert lengths[-1] == len(FINDINGS)
