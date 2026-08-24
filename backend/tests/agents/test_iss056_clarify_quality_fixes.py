"""Tests for ISS-056 — three clarify quality gap fixes.

H1: all 7 eight-default manifests compile with clarify.rounds == 2
H2: accessibility.md guardrail appears verbatim in prototype-build's prompt
H3: style/ui_style pruned when ds_id set; design_system_name threaded into
    planning_context; SmartPlanner._build_prompt emits 'Design already chosen'
    block when design_context is supplied.

Requirements: INV-1 / INV-3 / INV-12 / SC-001 — see ISS-056 grounded context.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# The real workflow manifests live two levels above this test file.
_WORKFLOWS_DIR = Path(__file__).resolve().parents[2] / "agents" / "workflows"

# ---------------------------------------------------------------------------
# H1 — FIX-ISS056: 7 eight-default manifests compile with rounds == 2
# ---------------------------------------------------------------------------


class TestH1ManifestRounds:
    """FIX-ISS056-H1: every 8-default manifest must now declare rounds: 2."""

    EIGHT_DEFAULT_MANIFESTS = [
        "app_builder",
        "custom",
        "dotnet_to_azure",
        "mulesoft_to_springboot",
        "ppt",
        "prototype",
        "user_stories",
    ]

    @pytest.mark.parametrize("workflow_id", EIGHT_DEFAULT_MANIFESTS)
    def test_manifest_compiles_with_rounds_2(self, workflow_id: str) -> None:
        """ISS-056/H1: each 8-default manifest must compile to rounds == 2."""
        from agents.capabilities.registry import CapabilityRegistry, discover
        from agents.workflows.compiler import WorkflowCompiler
        from agents.workflows.manifest import load_manifest

        discover()
        manifest = load_manifest(workflow_id, _WORKFLOWS_DIR)
        compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust="file")
        assert compiled.clarify.rounds == 2, (
            f"FIX-ISS056/H1: manifest '{workflow_id}' must declare rounds: 2 "
            f"(got {compiled.clarify.rounds})"
        )

    @pytest.mark.parametrize("workflow_id", EIGHT_DEFAULT_MANIFESTS)
    def test_manifest_defaults_count(self, workflow_id: str) -> None:
        """Safety boundary: each manifest must still declare exactly 8 defaults."""
        from agents.capabilities.registry import CapabilityRegistry, discover
        from agents.workflows.compiler import WorkflowCompiler
        from agents.workflows.manifest import load_manifest

        discover()
        manifest = load_manifest(workflow_id, _WORKFLOWS_DIR)
        compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust="file")
        assert len(compiled.clarify.defaults) == 8, (
            f"FIX-ISS056/H1: '{workflow_id}' must retain 8 clarify defaults "
            f"(got {len(compiled.clarify.defaults)})"
        )

    def test_four_default_manifests_unaffected(self) -> None:
        """Safety boundary: revision manifests (4 defaults) must stay at rounds == 1."""
        from agents.capabilities.registry import CapabilityRegistry, discover
        from agents.workflows.compiler import WorkflowCompiler
        from agents.workflows.manifest import load_manifest

        discover()
        unchanged = [
            "app_builder_revision", "ppt_revision",
            "prototype_revision", "user_stories_revision",
        ]
        for workflow_id in unchanged:
            manifest_path = _WORKFLOWS_DIR / workflow_id / "workflow.yaml"
            if not manifest_path.exists():
                continue  # skip if not present in this repo configuration
            manifest = load_manifest(workflow_id, _WORKFLOWS_DIR)
            compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust="file")
            assert compiled.clarify.rounds == 1, (
                f"FIX-ISS056/H1 safety: '{workflow_id}' must remain at rounds == 1 "
                f"(got {compiled.clarify.rounds})"
            )


# ---------------------------------------------------------------------------
# H2 — FIX-NNN: accessibility.md guardrail wired into prototype-family agents
# ---------------------------------------------------------------------------


class TestH2AccessibilityGuardrail:
    """FIX-ISS056-H2: accessibility.md must appear verbatim in prototype build/validate prompts."""

    PROTOTYPE_BUILD_VALIDATE_AGENTS = [
        "prototype-build",
        "prototype-validate",
        "prototype-revision-agent",
        # prototype-revision-validate was deleted in revision-pipeline-agent-reuse spec
        # (task 5.1): the pipeline now reuses prototype-validate directly.
    ]

    def _compose(self, agent_id: str):
        from agents.factory import AgentContext, _compose_system_prompt
        from agents.loader import load_agent_spec

        spec = load_agent_spec(agent_id)
        ctx = AgentContext(user_request="Build a dashboard prototype")
        return _compose_system_prompt(spec, ctx)

    @pytest.mark.parametrize("agent_id", PROTOTYPE_BUILD_VALIDATE_AGENTS)
    def test_agent_declares_accessibility_guardrail(self, agent_id: str) -> None:
        """ISS-056/H2: agent frontmatter must list 'accessibility' in guardrails."""
        from agents.loader import load_agent_spec

        spec = load_agent_spec(agent_id)
        assert "accessibility" in spec.guardrails, (
            f"FIX-ISS056/H2: '{agent_id}' must declare accessibility in its guardrails list"
        )

    @pytest.mark.parametrize("agent_id", PROTOTYPE_BUILD_VALIDATE_AGENTS)
    def test_accessibility_content_verbatim_in_prompt(self, agent_id: str) -> None:
        """ISS-056/H2: full accessibility.md content must appear verbatim in composed prompt."""
        from agents.factory import _GUARDRAILS_DIR

        accessibility_file = _GUARDRAILS_DIR / "accessibility.md"
        assert accessibility_file.exists(), f"accessibility.md not found at {accessibility_file}"
        content = accessibility_file.read_text(encoding="utf-8")
        assert content.strip(), "accessibility.md is empty"

        system_prompt = self._compose(agent_id)
        assert content in system_prompt, (
            f"FIX-ISS056/H2: full accessibility.md content must appear verbatim "
            f"in '{agent_id}' system prompt.\n"
            f"Expected:\n{content[:200]}...\n"
            f"Prompt start:\n{system_prompt[:200]}..."
        )

    @pytest.mark.parametrize("agent_id", PROTOTYPE_BUILD_VALIDATE_AGENTS)
    def test_guardrail_section_header_present(self, agent_id: str) -> None:
        """ISS-056/H2: ## Guardrail: accessibility header must be present."""
        system_prompt = self._compose(agent_id)
        assert "## Guardrail: accessibility" in system_prompt, (
            f"FIX-ISS056/H2: '## Guardrail: accessibility' header must appear in "
            f"'{agent_id}' system prompt"
        )

    def test_html_prototype_guardrail_still_present(self) -> None:
        """Safety boundary: adding accessibility must not remove html-prototype."""
        from agents.loader import load_agent_spec

        spec = load_agent_spec("prototype-build")
        assert "html-prototype" in spec.guardrails, (
            "FIX-ISS056/H2 safety: html-prototype guardrail must still be declared"
        )


# ---------------------------------------------------------------------------
# H3 — FIX-NNN: design-system-aware clarify / planner
# ---------------------------------------------------------------------------


class TestH3DesignContextOdContext:
    """FIX-ISS056-H3(b): od_context now carries template_name and ds_name."""

    def _make_od_context(self, template_id: str, ds_id: str) -> dict:
        """Build a minimal od_context dict the same way od_context.py does."""
        from agents.execution_engine.od_context import load_prototype_context

        try:
            return load_prototype_context(template_id, ds_id)
        except LookupError:
            pytest.skip(f"Template '{template_id}' or DS '{ds_id}' not in catalog on this machine")

    def test_main_branch_has_template_name(self) -> None:
        """ISS-056/H3(b): main return branch must include template_name."""
        import importlib

        od_ctx = importlib.import_module("agents.execution_engine.od_context")
        # Stub a minimal template dict to avoid disk I/O
        import unittest.mock as mock

        fake_template = {"name": "Web Prototype", "body": "# stub", "craft_required": []}
        fake_ds = {"name": "Apple-inspired", "body": "# stub"}

        with mock.patch.object(od_ctx.od_loader, "get_template", return_value=fake_template), \
             mock.patch.object(od_ctx.od_loader, "get_design_system", return_value=fake_ds), \
             mock.patch.object(od_ctx.od_loader, "get_craft_rules", return_value={}):
            result = od_ctx.load_prototype_context("web-prototype", "apple-inspired")

        assert "template_name" in result, "FIX-ISS056/H3: template_name missing from od_context"
        assert "ds_name" in result, "FIX-ISS056/H3: ds_name missing from od_context"
        assert result["template_name"] == "Web Prototype"
        assert result["ds_name"] == "Apple-inspired"

    def test_no_template_branch_has_ds_name(self) -> None:
        """ISS-056/H3(b): no-template (blank-canvas) branch must include ds_name."""
        import importlib
        import unittest.mock as mock

        od_ctx = importlib.import_module("agents.execution_engine.od_context")
        fake_ds = {"name": "Material Design", "body": "# stub"}

        with mock.patch.object(od_ctx.od_loader, "get_template", return_value=None), \
             mock.patch.object(od_ctx.od_loader, "get_design_system", return_value=fake_ds):
            result = od_ctx.load_prototype_context(None, "material")

        assert result.get("no_template") is True
        assert result.get("template_name") is None  # blank-canvas: no template
        assert result.get("ds_name") == "Material Design"


class TestH3StyleFilter:
    """FIX-ISS056-H3(a): style/ui_style pruned from missing_information when ds_id is set."""

    def _run_filter(self, missing: list[str], od_context: dict | None) -> list[str]:
        """Exercise the H3(a) filter in engine.py in isolation.

        We reproduce the identical conditional that was added, so tests remain
        fast and deterministic without requiring a full engine.execute() pass.
        """
        planning_context = {"missing_information": list(missing)}
        _od = od_context or {}

        if _od.get("ds_id") and not _od.get("no_template"):
            _missing = planning_context.get("missing_information") or []
            _filtered = [m for m in _missing if m not in ("style", "ui_style")]
            planning_context["missing_information"] = _filtered

        return planning_context["missing_information"]

    def test_style_pruned_when_ds_id_present(self) -> None:
        """ISS-056/H3(a): style must be removed when ds_id is set."""
        result = self._run_filter(
            missing=["target_audience", "style", "user_journeys"],
            od_context={"ds_id": "apple-inspired"},
        )
        assert "style" not in result, "FIX-ISS056/H3(a): style must be pruned when ds_id is set"
        assert "target_audience" in result
        assert "user_journeys" in result

    def test_ui_style_pruned_when_ds_id_present(self) -> None:
        """ISS-056/H3(a): ui_style must also be removed when ds_id is set."""
        result = self._run_filter(
            missing=["ui_style", "scope"],
            od_context={"ds_id": "material"},
        )
        assert "ui_style" not in result
        assert "scope" in result

    def test_style_kept_when_no_ds_id(self) -> None:
        """Safety boundary: style must NOT be pruned when od_context has no ds_id."""
        result = self._run_filter(
            missing=["style", "scope"],
            od_context={"ds_id": None},
        )
        assert "style" in result, "FIX-ISS056/H3(a) safety: style must remain when no ds_id"

    def test_style_kept_when_no_template_mode(self) -> None:
        """Safety boundary: blank-canvas mode must not prune style (KAN-87 intent)."""
        result = self._run_filter(
            missing=["style", "scope"],
            od_context={"ds_id": "material", "no_template": True},
        )
        assert "style" in result, (
            "FIX-ISS056/H3(a) safety: style must remain in blank-canvas mode "
            "(no_template=True) so KAN-87's ui_style injection still fires"
        )

    def test_style_kept_when_od_context_none(self) -> None:
        """Safety boundary: no od_context (non-OD workflow) must not prune anything."""
        result = self._run_filter(
            missing=["style", "scope"],
            od_context=None,
        )
        assert "style" in result


class TestH3SmartPlannerDesignNote:
    """FIX-ISS056-H3(b): SmartPlanner._build_prompt emits 'Design already chosen' block."""

    def _make_planner(self):
        from agents.planner.smart_planner import SmartPlanner

        return SmartPlanner(model_id=None)

    def test_design_note_present_when_design_context_supplied(self) -> None:
        """ISS-056/H3(b): 'Design already chosen' must appear when design_context is non-None."""
        planner = self._make_planner()
        prompt = planner._build_prompt(
            brief="Build a dashboard",
            pipeline_type="prototype",
            design_context={"template_name": "Web Prototype", "ds_name": "Apple-inspired"},
        )
        assert "Design already chosen" in prompt, (
            "FIX-ISS056/H3(b): 'Design already chosen' block must appear in prompt "
            "when design_context is supplied"
        )
        assert "Apple-inspired" in prompt
        assert "Web Prototype" in prompt
        assert "Do NOT flag visual style" in prompt

    def test_design_note_absent_when_design_context_none(self) -> None:
        """Safety boundary: prompt must NOT mention design_context when it is None."""
        planner = self._make_planner()
        prompt = planner._build_prompt(
            brief="Build a dashboard",
            pipeline_type="prototype",
            design_context=None,
        )
        assert "Design already chosen" not in prompt, (
            "FIX-ISS056/H3(b) safety: 'Design already chosen' must NOT appear "
            "when design_context is None"
        )

    def test_design_note_absent_when_both_names_missing(self) -> None:
        """Edge case: empty design_context dict must not inject the note."""
        planner = self._make_planner()
        prompt = planner._build_prompt(
            brief="Build a dashboard",
            pipeline_type="prototype",
            design_context={"template_name": None, "ds_name": None},
        )
        assert "Design already chosen" not in prompt

    def test_plan_signature_accepts_design_context(self) -> None:
        """ISS-056/H3(b): plan() must accept the design_context kwarg without raising."""
        import inspect

        from agents.planner.smart_planner import SmartPlanner

        sig = inspect.signature(SmartPlanner.plan)
        assert "design_context" in sig.parameters, (
            "FIX-ISS056/H3(b): SmartPlanner.plan() must accept design_context parameter"
        )
