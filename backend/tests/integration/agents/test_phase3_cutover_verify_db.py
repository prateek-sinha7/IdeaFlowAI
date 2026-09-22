"""Phase-3 cutover forward guard — the engine-driving (DB-touching) half.

Split out of ``tests/unit/agents/test_phase3_cutover_verify.py``. That file's
``TestCheckpointResume`` exercises the in-process ``InMemorySaver`` directly and is
zero-I/O, so it STAYS in the unit suite. ``TestNewEngineEventVocabulary`` below drives
the real ``ExecutionEngine.execute()`` through the shared ``_drive`` harness, which
opens a ``SessionLocal()`` to persist run events — the unit-isolation guard in
``tests/unit/conftest.py`` rejects that by design.

``_DOCUMENTED_EVENT_TYPES`` / ``_REQUIRED_DATA_KEYS`` are deliberately NOT copied here.
They remain in the unit module as the SINGLE SOURCE OF TRUTH for the outbound event
contract and are imported by ``tests/agents/characterization/_normalize.py`` (which
re-exports them to the six contract characterization suites) and by
``test_phase5_revision_validation_db.py``. Importing them across the suite boundary —
rather than duplicating — is the existing precedent in this repo and is what keeps the
contract un-forkable (T-02-01).

Offline (scripted model, no Bedrock) — but NOT zero-I/O.
"""

from __future__ import annotations

import pytest

from tests.agents._scripted_model import _drive

# The documented outbound contract — imported, never copied (see module docstring).
from tests.unit.agents.test_phase3_cutover_verify import (
    _DOCUMENTED_EVENT_TYPES,
    _REQUIRED_DATA_KEYS,
)


class TestNewEngineEventVocabulary:
    """Forward guard: the NEW engine emits ONLY documented event types with the
    documented payload key-shapes, for a scripted text run and a prototype build."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("pipeline_type", ["user_stories", "prototype"])
    async def test_event_vocabulary_conforms_to_contract(
        self, pipeline_type: str
    ) -> None:
        events = await _drive(pipeline_type, "new")
        assert events, f"{pipeline_type}: NEW engine produced no events"

        seen_types = {e.get("type") for e in events}
        # Every emitted type is in the documented vocabulary (no surprise types).
        unknown = seen_types - _DOCUMENTED_EVENT_TYPES
        assert not unknown, (
            f"{pipeline_type}: NEW engine emitted UNDOCUMENTED event type(s) the "
            f"frontend does not handle: {sorted(unknown)}"
        )

        # Each load-bearing event carries (at least) its documented data keys.
        for ev in events:
            t = ev.get("type")
            required = _REQUIRED_DATA_KEYS.get(t)
            if required is None:
                continue
            data = ev.get("data", {})
            missing = required - set(data.keys())
            assert not missing, (
                f"{pipeline_type}: event '{t}' is MISSING required data keys "
                f"{sorted(missing)} (UI depends on them); got {sorted(data.keys())}"
            )

    @pytest.mark.asyncio
    async def test_text_pipeline_core_sequence(self) -> None:
        """A text pipeline must bracket each agent with start/input/…/complete and
        bookend the run with pipeline_start … pipeline_complete."""
        events = await _drive("user_stories", "new")
        types = [e.get("type") for e in events]
        assert types[0] == "workflow_validated"
        assert "pipeline_start" in types
        assert types[-1] == "pipeline_complete"
        # Every agent_start is eventually followed by an agent_complete (or error).
        assert types.count("agent_start") == types.count(
            "agent_complete"
        ), f"each agent_start must pair with an agent_complete; got {types}"

    @pytest.mark.asyncio
    async def test_prototype_build_emits_task_progress_from_tool_args(self) -> None:
        """The prototype build derives task_progress from report_task_complete args.

        Confirms the Phase-3 mechanism: the build agent's report_task_complete
        tool call (task_number/task_title/summary) yields a task_progress event
        whose completed_tasks item carries number/title/summary — the SAME payload
        shape the pre-cutover engine produced from PrototypeArtifactStore.
        """
        events = await _drive("prototype", "new")
        tps = [e for e in events if e.get("type") == "task_progress"]
        assert tps, "prototype build must emit at least one task_progress event"
        for tp in tps:
            data = tp.get("data", {})
            ctasks = data.get("completed_tasks") or []
            assert ctasks, "task_progress must carry a non-empty completed_tasks list"
            item = ctasks[0]
            assert (
                set(item.keys()) == {"number", "title", "summary"}
            ), f"completed_tasks item must be {{number,title,summary}}; got {sorted(item.keys())}"
            assert (
                item["number"] == 1 and item["title"] == "Build shell"
            ), f"task_progress payload must reflect the report_task_complete args; got {item}"
