"""Step.reply (spec 022 §11): ``last_message`` keeps only a step's final message.

The engine joins every text chunk a step streams into its output: what the review card
shows, the step transcript later steps read, and the typed artifact. Revision 8d4d2d70's
Analyst wrote notes between its tool calls ("Now let me check the revisions folder to
determine the next revision number:…"), so its approval card opened with them instead of
its spec, though its prompt forbade it. A step declaring ``reply: last_message`` keeps the
text after its last tool call or result; every other step is unchanged.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

# Importing the harness sets RUNS_ROOT to a temp dir + forces the InMemory checkpointer
# (no Postgres / no creds) BEFORE app.core.config loads — keep this import first.
from tests.agents._scripted_model import _RUNS_ROOT  # noqa: F401  (import-for-side-effects)

from agents.capabilities.registry import CapabilityRegistry
from agents.workflows.compiler import CompilerError, WorkflowCompiler
from agents.workflows.manifest import WorkflowManifest

SPEC = "Spec: revisions/2/revision-spec.md\n\n## Request\nMake the five site-setup fields required.\n"
NOTES = [
    "Now let me check the revisions folder to determine the next revision number:",
    "Now let me check the highest REQ id in EPIC-02c…",
]


class _NarratingRunner:
    """A runner that writes a note before each tool call, then its spec (split in two
    chunks, as a stream delivers it) — or, with ``final_text=False``, ends on a tool call."""

    system_prompt = ""

    def __init__(self, final_text: bool = True) -> None:
        self.final_text = final_text

    async def astream_events(self, message):
        for i, note in enumerate(NOTES):
            yield {"type": "chunk", "chunk": note}
            yield {
                "type": "tool_call",
                "tool": "grep",
                "args": {"pattern": f"p{i}"},
                "id": f"c{i}",
            }
            yield {
                "type": "tool_result",
                "tool": "grep",
                "result": "hit",
                "id": f"c{i}",
            }
        if self.final_text:
            yield {"type": "chunk", "chunk": SPEC[:20]}
            yield {"type": "chunk", "chunk": SPEC[20:]}
        yield {"type": "usage", "input_tokens": 3, "output_tokens": 2}


async def _drive(reply: str | None, *, final_text: bool = True):
    """Run one agent through ``ExecutionEngine._run_agent`` offline, gated inline.

    Returns ``(output, card, transcript)``: the step's recorded output, the text handed
    to the review card, and the step transcript later steps read."""
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
    run_id = f"reply-{reply}-{final_text}"
    runner = _NarratingRunner(final_text)
    orig_factory, orig_engine = (
        factory_mod.create_runner,
        getattr(engine_mod, "create_runner", None),
    )
    factory_mod.create_runner = engine_mod.create_runner = lambda *a, **k: runner

    engine = ExecutionEngine()

    async def _noop(*a, **k):
        return "artifact-id"

    engine._store.store = _noop  # type: ignore[assignment]
    engine._dual_write_artifact = _noop  # type: ignore[assignment]
    card: list[str] = []

    async def _recording_gate(**kw):
        card.append(kw["output"])
        return
        yield  # pragma: no cover — makes this an async generator

    engine._run_review_gate = _recording_gate  # type: ignore[assignment]

    spec = load_agent_spec("domain-analyst")
    ectx = ExecutionContext(run_id=run_id, owner_id="anon")
    ectx.disk_principal = "anon"
    ectx.model_resolver = ModelResolver(
        session_model_id="claude-haiku-4-5-20251001",
        haiku_default=_settings.BEDROCK_INFERENCE_PROFILE_ID,
        catalog=ModelCatalog(),
        _region_override="",
    )
    ectx.gate_agent_ids = [spec.id]
    if reply is not None:
        ectx.current_step = SimpleNamespace(reply=reply, model=None)
    sandbox = RunSandbox("anon", run_id, runs_root=_RUNS_ROOT)
    results: list[dict] = []
    try:
        async for _ in engine._run_agent(
            spec,
            0,
            [spec],
            "Revise it.",
            sandbox,
            run_id,
            "user_stories",
            engine._default_planning_context("Revise it."),
            None,
            None,
            "claude-haiku-4-5-20251001",
            results,
            None,
            ectx,
        ):
            pass
    finally:
        factory_mod.create_runner = orig_factory
        if orig_engine is not None:
            engine_mod.create_runner = orig_engine
    transcript = sandbox.read(agent_output_relpath(index=0, agent_id=spec.id)) or ""
    return results[-1]["output"], card, transcript


@pytest.mark.asyncio
async def test_last_message_keeps_only_the_final_message_on_the_card_and_in_the_transcript():
    output, card, transcript = await _drive("last_message")
    assert output == SPEC
    assert card == [SPEC]  # the approval card opens with "Spec:"
    assert transcript.startswith(SPEC.rstrip("\n")) or SPEC.strip() in transcript
    assert not any(note in transcript for note in NOTES)


@pytest.mark.asyncio
@pytest.mark.parametrize("reply", ["all", None])
async def test_a_step_without_the_key_keeps_every_word_it_streamed(reply):
    output, card, _ = await _drive(reply)
    assert output == "".join(NOTES) + SPEC  # byte-identical join, as before
    assert card == [output]


@pytest.mark.asyncio
async def test_a_final_message_without_text_keeps_everything():
    output, card, _ = await _drive("last_message", final_text=False)
    assert output == "".join(NOTES)
    assert card == [output]


def _compile_step(**step) -> object:
    manifest = WorkflowManifest(
        id="t-reply",
        steps=[{"agent": "domain-analyst", **step}],
        deliverable={"strategy": "streamed_text"},
        planner="skip",
        clarify={"mode": "auto", "defaults": []},
    )
    return WorkflowCompiler().compile(manifest, CapabilityRegistry()).steps[0]


def test_the_compiler_reads_reply_and_rejects_an_unknown_value():
    assert _compile_step().reply == "all"
    assert _compile_step(reply="last_message").reply == "last_message"
    with pytest.raises(CompilerError, match="reply 'everything'"):
        _compile_step(reply="everything")
