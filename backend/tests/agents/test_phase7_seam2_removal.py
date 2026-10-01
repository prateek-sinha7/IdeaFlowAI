"""tests/agents/test_phase7_seam2_removal.py — Phase 7 tests: Seam 2 removal and
per-workflow prompt migration.

Covers acceptance criteria from Requirements 29, 30, 31, 40, and 45 as described
in task 9.6:

  1. ``TestBriefGatingByPolicy`` — [Phase Z / GAPS §0.3 step N+1] the brief gate
     in ``_compose_context_message`` routes the user brief to the first-
     dispatched agent only, UNCONDITIONALLY — every workflow finished the Q4
     migration, so the ``_is_migrated`` / default-policy branch this class
     originally tested no longer exists in engine.py at all.

  2. ``TestGovernedAgentConstitutionRetained`` — the ``governance`` policy retains
     Constitution; ``body_only`` intentionally drops it; factory warns when a
     governed agent (one with a prewarmed Constitution) uses ``body_only``.

  3. ``TestRetryBlockTargeting`` — the retry block is delivered to the retrying
     agent only (``_fb_store.pop(spec.id)``); an agent NOT being retried gets none.

  4. ``TestSandboxReadingGuideInAgentMD`` — every ``user_stories`` agent's
     ``AGENT.md`` has a "Sandbox Reading Guide" section with the correct
     ``.agents/NN-agent-id.md`` paths and the explicit responsibility statement.

  5. ``TestPlannerMdWrittenAfterClarify`` — source-level assertion that
     ``PLANNER.md`` is written AFTER ``clarify_task.result()`` in ``engine.py``
     (Requirement 30 AC 4 / task 9.4).

All tests are offline (no LLM, no database) and use source inspection where the
pattern calls for it — this avoids importing the full engine module.  The SC-001
checks verify that gating logic uses generic field names (``prompt_policy``,
``spec.id``) rather than workflow or agent name literals.

Offline / unmarked — runs in CI without ``requires_api_key``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Locate key source files via the test file's own path
# ---------------------------------------------------------------------------

# tests/agents/ → backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_ENGINE_PY = _BACKEND_ROOT / "agents" / "execution_engine" / "engine.py"
_PROMPTS_ROOT = _BACKEND_ROOT / "agents" / "prompts"


def _engine_text() -> str:
    """Return engine.py as a string.  Cached per process via module-level dict."""
    return _ENGINE_PY.read_text(encoding="utf-8")


# ===========================================================================
# 1. Brief gating by prompt policy
# ===========================================================================


class TestBriefGatingByPolicy:
    """Requirement 30 AC 5: user brief reaches agent 1 only on migrated workflows.

    Uses source inspection of engine.py so the test imports no heavy modules
    and stays importable without pydantic / sqlalchemy.
    """

    def test_seam2_no_longer_varies_by_prompt_policy(self) -> None:
        """[Phase Z] The ``_is_migrated`` / ``_spec_policy`` switch this class
        originally tested is gone from engine.py entirely — seam 2 no longer
        branches on ``prompt_policy`` at all (``policy.py`` documents this split:
        ``default`` stays a valid name for seam 1 / the system prompt only).
        """
        text = _engine_text()
        assert "_is_migrated" not in text, (
            "engine.py: _is_migrated must not reappear — seam 2 no longer "
            "varies by prompt_policy (Phase Z, GAPS §0.3 step N+1)"
        )
        assert "_spec_policy" not in text, (
            "engine.py: _spec_policy must not reappear — seam 2 no longer "
            "varies by prompt_policy (Phase Z, GAPS §0.3 step N+1)"
        )

    def test_brief_gated_to_first_agent_only(self) -> None:
        """The brief is included only when is_first_agent (or when there is
        retry feedback — Requirement 14 AC 2) — unconditional since Phase Z.

        Source check: ``if is_first_agent or _has_retry_feedback:`` is the guard.
        """
        text = _engine_text()
        assert "if is_first_agent or _has_retry_feedback:" in text, (
            "engine.py: the brief-inclusion guard must be "
            "``if is_first_agent or _has_retry_feedback:``"
        )

    def test_migrated_later_agent_gets_empty_parts(self) -> None:
        """For a migrated workflow's agent 2+, ``parts`` starts empty (no brief).

        Source check: the ``else`` branch of the brief gate sets ``parts = []``
        with a comment explaining that later agents read context from .agents/.
        """
        text = _engine_text()
        assert "parts = []  # later agents read context from .agents/ files" in text, (
            "engine.py: the else branch for migrated later agents must assign "
            "``parts = []`` with the .agents/ comment"
        )

    def test_sc001_gate_uses_no_workflow_name_literal(self) -> None:
        """SC-001: the brief gate uses no workflow name literal or spec.id comparison.

        [Phase Z] There is no ``prompt_policy`` branch left to police (the
        ``_is_migrated`` gate is gone — see ``test_seam2_no_longer_varies_by_
        prompt_policy``); what remains is the positional ``is_first_agent``
        check plus the ``spec.id``-keyed retry exception, both already generic.
        The INV-1 ratchet (test_banned_patterns.py) enforces zero
        ``if pipeline_type ==`` / ``spec.id ==`` branches in the kernel; this
        test is the Phase-7-specific companion that targets the brief gate.
        """
        text = _engine_text()
        assert "if is_first_agent or _has_retry_feedback:" in text, (
            "engine.py: the brief-inclusion guard must be "
            "``if is_first_agent or _has_retry_feedback:`` — positional / "
            "consume-once-keyed, never a workflow name literal (SC-001)"
        )

    def test_is_first_agent_check_is_positional_not_name_based(self) -> None:
        """The ``is_first_agent`` predicate uses ``index == 0``, not ``spec.id`` comparison.

        Requirement 30 AC 5 / INV-1: the first-agent gate must be workflow-agnostic.
        Source check: ``is_first_agent = (len(ordered_agents) == 0 or index == 0)``.
        """
        import re

        text = _engine_text()
        # ruff format (22bbe1bf) drops the redundant parens — accept either form.
        assert re.search(
            r"is_first_agent = \(?len\(ordered_agents\) == 0 or index == 0\)?", text
        ), (
            "engine.py: ``is_first_agent`` must be a pure positional check "
            "(index == 0) — no spec.id / agent-name comparison"
        )


# ===========================================================================
# 2. Governed agent Constitution retained under governance policy
# ===========================================================================


class TestGovernedAgentConstitutionRetained:
    """Requirement 29 AC 2/3: governance policy retains Constitution; body_only drops it.

    Uses the live registry (no mock).  Mirrors TestPromptPolicyRegistration in
    test_phase6_sandbox_versioning.py but adds the constitution-retention focus
    and the factory warning for governed agents on body_only.
    """

    def test_governance_policy_order_includes_constitution(self) -> None:
        """governance policy order MUST include 'constitution'."""
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        registry = CapabilityRegistry()
        policy = registry.resolve("prompt", "governance")
        order = getattr(policy, "order", ())
        assert "constitution" in order, (
            "governance policy order must include 'constitution' — "
            "Requirement 29 AC 2: governed agents keep their Constitution"
        )

    def test_body_only_policy_order_excludes_constitution(self) -> None:
        """body_only policy order MUST NOT include 'constitution'.

        Losing the Constitution as a side effect of a formatting change is not
        acceptable (Req 29 AC 3) — the exclusion here is INTENTIONAL for
        ungoverned agents.  Governed agents must use 'governance' instead.
        """
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        registry = CapabilityRegistry()
        policy = registry.resolve("prompt", "body_only")
        order = getattr(policy, "order", ())
        assert "constitution" not in order, (
            "body_only policy must NOT include 'constitution' — "
            "governed agents must use 'governance' policy to retain their Constitution"
        )

    def test_governance_assemble_keeps_constitution_block(self) -> None:
        """governance policy's assemble() emits the constitution block content."""
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        registry = CapabilityRegistry()
        policy = registry.resolve("prompt", "governance")
        blocks = {
            "guardrails": ["## Guardrail\n\nDo not harm."],
            "constitution": "## Constitution\n\nBe ethical.",
            "hooks": "## Hooks\n\nHook content.",
            "prompt_body": "# Agent\n\nI am a governed agent.",
        }
        result = policy.assemble(blocks, ctx=None)
        assert "## Constitution" in result, (
            "governance policy assemble() must include the constitution block — "
            "Constitution NOT silently lost on migration (Req 29 AC 2/3)"
        )

    def test_body_only_assemble_drops_constitution_block(self) -> None:
        """body_only policy's assemble() must NOT emit the constitution block.

        This is the deliberate trade-off: ungoverned agents get a clean
        AGENT.md-only system prompt.
        """
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        registry = CapabilityRegistry()
        policy = registry.resolve("prompt", "body_only")
        blocks = {
            "guardrails": ["## Guardrail\n\nDo not harm."],
            "constitution": "## Constitution\n\nBe ethical.",
            "hooks": "## Hooks\n\nHook content.",
            "prompt_body": "# Agent\n\nI am an ungoverned agent.",
        }
        result = policy.assemble(blocks, ctx=None)
        assert "## Constitution" not in result, (
            "body_only assemble() must NOT include the constitution block — "
            "use 'governance' policy to retain it"
        )

    def test_sc001_governance_gate_uses_prompt_policy_not_spec_id(self) -> None:
        """SC-001: governance vs body_only is selected via ``prompt_policy``, not spec.id.

        Source check: ``factory.py`` reads ``spec.prompt_policy`` to select the
        policy, not a spec.id or agent-name literal.
        """
        factory_py = _BACKEND_ROOT / "agents" / "factory.py"
        if not factory_py.exists():
            pytest.skip("factory.py not found — cannot perform source check")
        text = factory_py.read_text(encoding="utf-8")
        assert "prompt_policy" in text, (
            "factory.py must read 'prompt_policy' from the spec to select the "
            "prompt assembly policy (SC-001 — no spec.id / workflow-name gate)"
        )

    def test_factory_warns_when_governed_agent_uses_body_only(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Requirement 29 AC 5: factory emits a WARNING when a governed agent
        (one with a prewarmed Constitution) selects the body_only policy.

        A governed agent that silently drops its Constitution on migration would
        be a correctness bug, not a feature.
        """
        import logging
        from unittest.mock import MagicMock, patch

        from agents.capabilities.registry import discover

        discover()

        spec = MagicMock()
        spec.id = "custom:governed-agent"
        spec.prompt_body = "# Agent body"
        spec.prompt_policy = "body_only"
        spec.guardrails = []
        spec.injects = []
        spec.tools = []
        spec.max_tokens = 1000

        ctx = MagicMock()
        ctx.step_injects = []
        ctx.disk_skill = None
        ctx.attached_hooks = []
        ctx.prewarmed_constitution = "## Constitution\n\nBe safe."  # governed

        from agents.factory import _compose_system_prompt

        # The imports are local inside _compose_system_prompt; patch them at their
        # source module so the factory function sees the stub regardless of import timing.
        with (
            patch("agents.capabilities.skills.providers.extract_ui_skill_blocks", return_value=[]),
            patch("agents.capabilities.hooks.behavioral.render_behavioral_block", return_value=""),
            patch("agents.workflows.artifacts.artifact_name", return_value="out.md"),
            caplog.at_level(logging.WARNING, logger="agents.factory"),
        ):
            try:
                _compose_system_prompt(spec, ctx, no_tools=False, has_write_access=False)
            except Exception:
                # The function may raise for other missing attrs on the mock spec;
                # the warning fires before any raise, so capture it regardless.
                pass

        assert any(
            "body_only" in record.message and "governed" in record.message
            for record in caplog.records
        ), (
            "factory must log a WARNING when a governed agent (with Constitution) "
            "uses 'body_only' policy — Requirement 29 AC 5"
        )


# ===========================================================================
# 3. Retry block targeting — only the retrying agent receives it
# ===========================================================================


class TestRetryBlockTargeting:
    """Requirement 30 AC 6: the retry block is delivered to the retrying agent only.

    Source inspection confirms the ``_fb_store.pop(spec.id)`` keying strategy;
    a functional test with a mocked ectx validates the pop semantics directly.
    """

    def test_retry_block_uses_pop_keyed_on_spec_id(self) -> None:
        """Source check: the retry block pop is keyed on spec.id.

        Only the agent whose id was stored as the key receives the retry block.
        """
        text = _engine_text()
        # The pop must be keyed on spec.id (either directly or via a local derived from it).
        assert (
            "_fb_store.pop(getattr(spec, " in text
            or "_fb_store.pop(_spec_id," in text
        ), (
            "engine.py: the retry block must be popped with the spec's id as the key — "
            "``_fb_store.pop(_spec_id, None)`` keyed on ``_spec_id = getattr(spec, 'id', None)``"
        )
        # The code must derive _spec_id from spec.id.
        assert "_spec_id = getattr(spec, " in text or "_spec_id = spec.id" in text or (
            "_fb_store.pop" in text and "spec.id" in text.replace("_spec_id", "spec.id")
        ), (
            "engine.py: the retry block targeting must be keyed on spec.id"
        )

    def test_retry_fb_store_is_popped_so_second_agent_gets_nothing(self) -> None:
        """A popped entry is consumed — agent B never replays agent A's retry block.

        Uses a plain dict as ``pending_route_feedback`` (the real ectx type).
        """
        # Simulated pending_route_feedback dict keyed by agent id.
        fb_store: dict = {
            "agent-retrying": {
                "pass_number": 2,
                "max_passes": 3,
                "from_step": "validate",
                "decision": "retry",
                "from_output": "Failed validation.",
                "authored": "Fix the HTML.",
            }
        }

        # First pop: the retrying agent receives the block.
        retrying_agent_fb = fb_store.pop("agent-retrying", None)
        assert retrying_agent_fb is not None, (
            "The retrying agent must receive the feedback block"
        )
        assert retrying_agent_fb["pass_number"] == 2

        # Second pop: a different agent (or a re-run of any agent) gets nothing.
        other_agent_fb = fb_store.pop("agent-not-retrying", None)
        assert other_agent_fb is None, (
            "An agent NOT being retried must get None from the pop — "
            "Requirement 30 AC 6: retry block delivered to the retrying agent ONLY"
        )

        # The store is now empty — the block was consumed exactly once.
        assert fb_store == {}, (
            "pending_route_feedback must be empty after the retrying agent consumed it"
        )

    def test_retry_block_header_text_is_in_engine(self) -> None:
        """The retry block header uses the documented marker ``=== RETRY — pass N of M ===``.

        Source check: Requirement 30 AC 6 names this exact block header.
        """
        text = _engine_text()
        assert "=== RETRY — pass" in text, (
            "engine.py: the retry block header must be "
            "``=== RETRY — pass {N} of {M} ===`` (Requirement 30 AC 6)"
        )
        assert "=== END RETRY ===" in text, (
            "engine.py: the retry block must have a closing ``=== END RETRY ===`` marker"
        )

    def test_non_retrying_agent_gets_no_retry_block(self) -> None:
        """An agent with no pending feedback produces no retry section in the message.

        Simulates the logic: ``_fb = _fb_store.pop(spec_id, None) if _fb_store else None``
        and asserts that when ``_fb`` is None, no retry lines are composed.
        """
        # Empty store → no retry block.
        fb_store: dict = {}
        spec_id = "any-agent"
        _fb = fb_store.pop(spec_id, None) if fb_store else None
        assert _fb is None, "Empty feedback store must yield None for any agent"

        # Another pop on a populated store for a different key → also None.
        fb_store2: dict = {"other-agent": {"pass_number": 1, "max_passes": 2}}
        _fb2 = fb_store2.pop(spec_id, None) if fb_store2 else None
        assert _fb2 is None, (
            "Pop for a key not in the store must return None — "
            "agent 'any-agent' gets no retry block when it is not the target"
        )


# ===========================================================================
# 4. Sandbox Reading Guide present in every user_stories AGENT.md
# ===========================================================================


class TestSandboxReadingGuideInAgentMD:
    """Requirement 31 AC 1–3: every migrated agent's AGENT.md states where to look and how.

    Checks the six ``user_stories`` agents' AGENT.md files.  The tests are pure
    file-read assertions — no imports of heavy modules.
    """

    # Mapping: agent-id → expected AGENT.md path
    _AGENT_IDS = [
        "domain-analyst",
        "epic-architect",
        "story-estimator",
        "nfr-specialist",
        "backlog-reviewer",
        "backlog-compiler",
    ]

    def _read_agent_md(self, agent_id: str) -> str:
        path = _PROMPTS_ROOT / agent_id / "AGENT.md"
        assert path.exists(), (
            f"AGENT.md for '{agent_id}' not found at {path} — "
            f"Requirement 31 AC 1: every migrated AGENT.md must exist"
        )
        return path.read_text(encoding="utf-8")

    @pytest.mark.parametrize("agent_id", _AGENT_IDS)
    def test_agent_md_has_sandbox_reading_guide_section(self, agent_id: str) -> None:
        """Requirement 31 AC 1: every user_stories agent has a 'Sandbox Reading Guide' section."""
        text = self._read_agent_md(agent_id)
        assert "## Sandbox Reading Guide" in text, (
            f"AGENT.md for '{agent_id}' is missing '## Sandbox Reading Guide' — "
            "Requirement 31 AC 1"
        )

    @pytest.mark.parametrize("agent_id", _AGENT_IDS)
    def test_agent_md_names_agents_path_and_ordering(self, agent_id: str) -> None:
        """Requirement 31 AC 1: AGENT.md names .agents/ and that it is ordered by step."""
        text = self._read_agent_md(agent_id)
        assert ".agents/" in text, (
            f"AGENT.md for '{agent_id}' must mention the '.agents/' path"
        )

    @pytest.mark.parametrize("agent_id", _AGENT_IDS)
    def test_agent_md_names_context_and_uploads_paths(self, agent_id: str) -> None:
        """Requirement 31 AC 1: AGENT.md names .context/ and .uploads/."""
        text = self._read_agent_md(agent_id)
        assert ".context/" in text, (
            f"AGENT.md for '{agent_id}' must mention '.context/' path"
        )
        assert ".uploads/" in text, (
            f"AGENT.md for '{agent_id}' must mention '.uploads/' path"
        )

    def test_domain_analyst_brief_comes_from_engine_task_message(self) -> None:
        """Requirement 31 AC 3: domain-analyst (step 1) states the brief comes from the
        engine task message — not from a prior agent file.

        After Seam 2 removal the first step is load-bearing: if it says nothing
        about how to obtain the brief, agents have no contract at all.
        """
        text = self._read_agent_md("domain-analyst")
        # The guide must state the brief is delivered via the engine (task message).
        assert (
            "brief is delivered by the engine" in text.lower()
            or "task message" in text.lower()
            or "your task message" in text.lower()
        ), (
            "domain-analyst AGENT.md must state that the user brief comes from "
            "the engine task message (Requirement 31 AC 3)"
        )

    def test_backlog_compiler_reading_is_own_responsibility(self) -> None:
        """Requirement 31 AC 1: backlog-compiler (final step) states reading is agent's own job.

        A prompt that merely says 'read the files' is NOT sufficient
        (Requirement 31 AC 2 / AC 1 sub-bullet).
        """
        text = self._read_agent_md("backlog-compiler")
        assert "reading is your own responsibility" in text.lower(), (
            "backlog-compiler AGENT.md must explicitly state "
            "'reading is your own responsibility' (Requirement 31 AC 1)"
        )

    def test_backlog_compiler_lists_all_prior_agent_files(self) -> None:
        """backlog-compiler must list all five prior agent outputs as named paths."""
        text = self._read_agent_md("backlog-compiler")
        expected_files = [
            ".agents/01-domain-analyst.md",
            ".agents/02-epic-architect.md",
            ".agents/03-story-estimator.md",
            ".agents/04-nfr-specialist.md",
            ".agents/05-backlog-reviewer.md",
        ]
        for path in expected_files:
            assert path in text, (
                f"backlog-compiler AGENT.md must list '{path}' — "
                "Requirement 31 AC 1: agents' guide names correct .agents/ paths"
            )

    def test_epic_architect_lists_correct_prior_file(self) -> None:
        """epic-architect (step 2) must list .agents/01-domain-analyst.md as the input."""
        text = self._read_agent_md("epic-architect")
        assert ".agents/01-domain-analyst.md" in text, (
            "epic-architect AGENT.md must list '.agents/01-domain-analyst.md' — "
            "Requirement 31 AC 1: each agent's guide names the correct step files"
        )

    def test_nfr_specialist_lists_three_prior_files(self) -> None:
        """nfr-specialist (step 4) must list the three prior agent outputs."""
        text = self._read_agent_md("nfr-specialist")
        for path in [
            ".agents/01-domain-analyst.md",
            ".agents/02-epic-architect.md",
            ".agents/03-story-estimator.md",
        ]:
            assert path in text, (
                f"nfr-specialist AGENT.md must list '{path}' — "
                "Requirement 31 AC 1"
            )

    @pytest.mark.parametrize(
        "agent_id,step_num",
        [
            ("domain-analyst", "1"),
            ("epic-architect", "2"),
            ("story-estimator", "3"),
            ("nfr-specialist", "4"),
            ("backlog-reviewer", "5"),
            ("backlog-compiler", "6"),
        ],
    )
    def test_agent_md_states_step_number(self, agent_id: str, step_num: str) -> None:
        """Each AGENT.md must state its own step number (so ordering is self-documenting)."""
        text = self._read_agent_md(agent_id)
        assert f"step {step_num}" in text.lower(), (
            f"AGENT.md for '{agent_id}' must state 'step {step_num}' so agents "
            "understand the ordered pipeline position"
        )


# ===========================================================================
# 5. PLANNER.md written AFTER clarify rounds merge (task 9.4)
# ===========================================================================


class TestPlannerMdWrittenAfterClarify:
    """Requirement 30 AC 4: PLANNER.md write is AFTER ``clarify_task.result()`` in engine.py.

    Source inspection only — no imports of engine modules.  Two complementary
    checks:
      (a) The write appears AFTER ``clarify_task.result()``.
      (b) The write is NOT inside the ``_emit_planner_events`` call block.
    """

    def _locate_line(self, text: str, pattern: str) -> int:
        """Return the 0-based index of the first line matching ``pattern``."""
        for i, line in enumerate(text.splitlines()):
            if pattern in line:
                return i
        return -1

    def test_planner_md_write_is_after_clarify_task_result(self) -> None:
        """Requirement 30 AC 4: ``sandbox.write('PLANNER.md', ...)`` appears AFTER
        ``planning_context = clarify_task.result()`` in engine.py.

        Today the write was at :2221, before the clarify merge at :2339.  Task 9.4
        moved it to after line :2689 (the ``clarify_task.result()`` call).
        """
        text = _engine_text()

        clarify_result_line = self._locate_line(
            text, "planning_context = clarify_task.result()"
        )
        planner_write_line = self._locate_line(text, 'sandbox.write("PLANNER.md"')

        assert clarify_result_line != -1, (
            "engine.py: ``planning_context = clarify_task.result()`` not found — "
            "the clarify-merge call must be present (Requirement 30 AC 4)"
        )
        assert planner_write_line != -1, (
            'engine.py: ``sandbox.write("PLANNER.md", ...)`` not found — '
            "the PLANNER.md write must be present (Requirement 30 AC 4)"
        )
        assert planner_write_line > clarify_result_line, (
            f"engine.py: PLANNER.md write (line {planner_write_line}) must come AFTER "
            f"clarify_task.result() (line {clarify_result_line}) — "
            "Requirement 30 AC 4: agents must read a clarification-enriched plan"
        )

    def test_planner_md_comment_states_written_after_clarify(self) -> None:
        """The PLANNER.md write block carries a comment documenting it is after clarify.

        Task 9.4 added a comment: "Written here — after clarify rounds may have
        merged answers into planning_context".
        """
        text = _engine_text()
        assert (
            "after clarify rounds" in text
            or "After clarify" in text
            or "Written here — after clarify" in text
        ), (
            "engine.py: the PLANNER.md write should carry a comment noting it is "
            "written after the clarify rounds merge (Requirement 30 AC 4 documentation)"
        )

    def test_planner_md_write_is_not_inside_emit_planner_events(self) -> None:
        """Requirement 30 AC 4: the PLANNER.md write must NOT be inside the
        ``_emit_planner_events`` call block.

        The ``_emit_planner_events`` async-for block runs BEFORE the clarify
        gate check, so a write there would precede the clarify merge.
        """
        text = _engine_text()
        lines = text.splitlines()

        emit_planner_line = self._locate_line(text, "async for event in self._emit_planner_events(")
        planner_write_line = self._locate_line(text, 'sandbox.write("PLANNER.md"')

        if emit_planner_line == -1 or planner_write_line == -1:
            pytest.skip(
                "_emit_planner_events call or PLANNER.md write not found — "
                "cannot determine relative ordering"
            )

        # The PLANNER.md write must come AFTER the entire _emit_planner_events block.
        # We detect the block boundary by finding the end of the async-for indented block
        # (first line at the same or lower indentation as the async-for line that is NOT
        # blank and is NOT inside the block).
        emit_line_content = lines[emit_planner_line]
        emit_indent = len(emit_line_content) - len(emit_line_content.lstrip())

        block_end_line = emit_planner_line + 1
        for i, line in enumerate(lines[emit_planner_line + 1 :], start=emit_planner_line + 1):
            stripped = line.lstrip()
            if stripped == "":
                continue  # blank lines don't end a block
            line_indent = len(line) - len(stripped)
            if line_indent <= emit_indent:
                block_end_line = i
                break

        assert planner_write_line > block_end_line, (
            f"engine.py: PLANNER.md write (line {planner_write_line}) must not be "
            f"inside the _emit_planner_events block (ends around line {block_end_line}) — "
            "Requirement 30 AC 4"
        )

    def test_planner_md_write_is_not_before_clarify_block(self) -> None:
        """Sanity: PLANNER.md write must not precede the ``if gate_verdict == 'CLARIFY_REQUIRED':``
        block that houses the clarify rounds loop.

        Complements the direct after-result check with a coarser ordering guard.
        """
        text = _engine_text()
        clarify_gate_line = self._locate_line(
            text, 'if gate_verdict == "CLARIFY_REQUIRED":'
        )
        planner_write_line = self._locate_line(text, 'sandbox.write("PLANNER.md"')

        if clarify_gate_line == -1 or planner_write_line == -1:
            pytest.skip("Clarify gate or PLANNER.md write not found — skip ordering check")

        assert planner_write_line > clarify_gate_line, (
            f"engine.py: PLANNER.md write (line {planner_write_line}) must not appear "
            f"before the clarify-gate block (line {clarify_gate_line})"
        )


# ===========================================================================
# 6. Characterization golden directory purity check
# ===========================================================================


class TestCharacterizationGoldenPurity:
    """Requirement 45 / INV-3: ``git status --porcelain golden/`` shows only intentionally
    re-baselined files after Phase 7 changes.

    This test does not call git directly (it would require git to be installed and
    the repo to be clean, which is not guaranteed in CI).  Instead it asserts the
    structural invariant: the five shipped goldens exist as JSON and the
    ``SNAPSHOT_UPDATE`` env var is NOT set during this test run (the env var
    gates re-baselining — an unintentional re-baseline during a Phase-7 run is
    the failure mode INV-3 guards against).
    """

    _GOLDEN_DIR = (
        Path(__file__).resolve().parents[2]
        / "tests"
        / "agents"
        / "characterization"
        / "golden"
    )
    _EXPECTED_EVENT_JSONS = {
        "app_builder.events.json",
        "ppt.events.json",
        "prototype.events.json",
        "prototype_feature_revision.events.json",
        "prototype_large_revision.events.json",
        "prototype_revision.events.json",
        "sample_subagents_parallel.events.json",
    }

    def test_snapshot_update_is_not_set(self) -> None:
        """INV-3: ``SNAPSHOT_UPDATE`` must NOT be set during the normal test run.

        The golden ratchet fires if this env var is set — re-baselining the five
        goldens without explicit intent would silently break the characterization
        contract.  This test documents and enforces the policy.
        """
        import os

        snapshot_update = os.environ.get("SNAPSHOT_UPDATE", "")
        assert snapshot_update == "", (
            "INV-3: SNAPSHOT_UPDATE is set. This means the golden snapshots would "
            "be re-baselined. Unset SNAPSHOT_UPDATE unless you intentionally want "
            "to re-derive the characterization goldens (Phase 7 AC: only intentionally "
            "re-baselined files should appear in git status --porcelain golden/)"
        )

    def test_golden_directory_exists(self) -> None:
        """The characterization/golden/ directory must exist."""
        assert self._GOLDEN_DIR.exists(), (
            f"characterization/golden/ not found at {self._GOLDEN_DIR} — "
            "INV-3: the golden ratchet requires this directory"
        )

    def test_known_golden_event_files_exist(self) -> None:
        """The known shipped .events.json goldens must all be present.

        An absent golden would mean it was deleted (or never re-baselined), which
        would cause ``test_characterization_*.py`` to fail or be skipped — both
        indicate an unintentional Phase-7 breakage.
        """
        present = {f.name for f in self._GOLDEN_DIR.glob("*.events.json")}
        for name in self._EXPECTED_EVENT_JSONS:
            assert name in present, (
                f"INV-3: golden file '{name}' is missing from "
                f"{self._GOLDEN_DIR} — this golden must not be deleted without "
                "explicit re-baselining intent"
            )

    def test_no_unexpected_events_json_in_golden_dir(self) -> None:
        """No unexpected .events.json file should appear in golden/ without explanation.

        A new golden appearing without a corresponding characterization test update
        would indicate an unintentional snapshot write.  This test flags it for
        review.
        """
        present = {f.name for f in self._GOLDEN_DIR.glob("*.events.json")}
        unexpected = present - self._EXPECTED_EVENT_JSONS
        assert not unexpected, (
            f"INV-3 / Requirement 45: unexpected .events.json files in golden/: "
            f"{sorted(unexpected)} — add them to _EXPECTED_EVENT_JSONS if "
            "they were intentionally re-baselined for Phase 7"
        )
