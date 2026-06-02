"""T031 — Unit tests for agents/planner/tools.py (Phase 3 US1).

Tests:
  - analyze_request extracts stated_goal from brief
  - infer_constraints returns the correct schema shape
  - assess_readiness returns PROCEED by default (LLM overrides in real use)
  - build_execution_plan returns sequential strategy by default
  - store_planning_context parses valid JSON and returns gate verdict
  - store_planning_context handles invalid JSON gracefully (defaults to PROCEED)
  - retrieve_planning_context returns a placeholder in Phase 2/3 in-memory mode
  - timeout defaults to PROCEED (via engine._default_planning_context)
"""

from __future__ import annotations

import json

import pytest

from agents.planner.tools import (
    analyze_request,
    infer_constraints,
    assess_readiness,
    build_execution_plan,
    store_planning_context,
    retrieve_planning_context,
    PLANNING_TOOLS,
)
from agents.execution_engine.engine import ExecutionEngine


# ---------------------------------------------------------------------------
# analyze_request
# ---------------------------------------------------------------------------


def test_analyze_request_extracts_stated_goal():
    result = json.loads(analyze_request.invoke({"brief": "Build a login feature for a SaaS app"}))
    assert "stated_goal" in result
    assert "Build a login feature" in result["stated_goal"]


def test_analyze_request_returns_required_keys():
    result = json.loads(analyze_request.invoke({"brief": "test brief"}))
    for key in ("stated_goal", "explicit_constraints", "pipeline_type_hint",
                "user_personas", "deliverable_type"):
        assert key in result, f"Missing key: {key}"


def test_analyze_request_empty_brief():
    result = json.loads(analyze_request.invoke({"brief": ""}))
    assert result["stated_goal"] == ""


# ---------------------------------------------------------------------------
# infer_constraints
# ---------------------------------------------------------------------------


def test_infer_constraints_returns_required_keys():
    result = json.loads(infer_constraints.invoke({
        "brief": "Build a fintech dashboard",
        "stated_goal": "Build a fintech dashboard",
    }))
    for key in ("implicit_constraints", "inferred_personas", "inferred_nfrs",
                "inferred_tech_stack", "inferred_compliance", "missing_information"):
        assert key in result, f"Missing key: {key}"


def test_infer_constraints_returns_lists():
    result = json.loads(infer_constraints.invoke({
        "brief": "Build a healthcare app",
        "stated_goal": "Build a healthcare app",
    }))
    assert isinstance(result["implicit_constraints"], list)
    assert isinstance(result["inferred_personas"], list)
    assert isinstance(result["missing_information"], list)


# ---------------------------------------------------------------------------
# assess_readiness
# ---------------------------------------------------------------------------


def test_assess_readiness_defaults_to_proceed():
    result = json.loads(assess_readiness.invoke({
        "explicit_constraints": "[]",
        "implicit_constraints": "[]",
        "missing_information": "[]",
    }))
    assert result["gate_verdict"] == "PROCEED"
    assert "readiness_score" in result
    assert isinstance(result["readiness_score"], float)


def test_assess_readiness_returns_required_keys():
    result = json.loads(assess_readiness.invoke({
        "explicit_constraints": '["React frontend"]',
        "implicit_constraints": '["WCAG 2.1 compliance"]',
        "missing_information": '[]',
    }))
    for key in ("gate_verdict", "readiness_score", "blocking_gaps", "clarification_topics"):
        assert key in result, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# build_execution_plan
# ---------------------------------------------------------------------------


def test_build_execution_plan_defaults_to_sequential():
    result = json.loads(build_execution_plan.invoke({
        "stated_goal": "Build user stories",
        "gate_verdict": "PROCEED",
        "pipeline_type_hint": "user_stories",
    }))
    assert result["execution_strategy"] == "sequential"


def test_build_execution_plan_uses_pipeline_type_hint():
    result = json.loads(build_execution_plan.invoke({
        "stated_goal": "Build a prototype",
        "gate_verdict": "PROCEED",
        "pipeline_type_hint": "prototype",
    }))
    assert result["recommended_pipeline_type"] == "prototype"


# ---------------------------------------------------------------------------
# store_planning_context
# ---------------------------------------------------------------------------


def test_store_planning_context_parses_valid_json():
    ctx = {
        "inferred_intent": "Build a login feature",
        "execution_gate": "PROCEED",
        "explicit_constraints": [],
        "implicit_constraints": [],
        "missing_information": [],
        "execution_strategy": "sequential",
        "inferred_personas": [],
        "inferred_nfrs": [],
        "quality_targets": [],
    }
    result = store_planning_context.invoke({"planning_context_json": json.dumps(ctx)})
    assert "PROCEED" in result
    assert "stored" in result.lower()


def test_store_planning_context_clarify_required():
    ctx = {"execution_gate": "CLARIFY_REQUIRED", "inferred_intent": "unclear brief"}
    result = store_planning_context.invoke({"planning_context_json": json.dumps(ctx)})
    assert "CLARIFY_REQUIRED" in result


def test_store_planning_context_invalid_json_defaults_to_proceed():
    result = store_planning_context.invoke({"planning_context_json": "not valid json {"})
    assert "PROCEED" in result
    assert "parse warning" in result.lower() or "stored" in result.lower()


# ---------------------------------------------------------------------------
# retrieve_planning_context
# ---------------------------------------------------------------------------


def test_retrieve_planning_context_returns_placeholder():
    result = json.loads(retrieve_planning_context.invoke({"pipeline_run_id": "run-abc"}))
    # Phase 2/3 in-memory: returns an error/placeholder, not a real context
    assert "pipeline_run_id" in result or "error" in result


# ---------------------------------------------------------------------------
# PLANNING_TOOLS registry
# ---------------------------------------------------------------------------


def test_planning_tools_registry_has_all_tools():
    tool_names = {t.name for t in PLANNING_TOOLS}
    expected = {
        "analyze_request", "infer_constraints", "assess_readiness",
        "build_execution_plan", "store_planning_context", "retrieve_planning_context",
    }
    assert expected == tool_names


# ---------------------------------------------------------------------------
# Timeout defaults to PROCEED (engine._default_planning_context)
# ---------------------------------------------------------------------------


def test_timeout_defaults_to_proceed():
    engine = ExecutionEngine()
    ctx = engine._default_planning_context("some brief", timed_out=True)
    assert ctx["execution_gate"] == "PROCEED"
    assert ctx["planner_timed_out"] is True
    assert ctx["inferred_intent"] == "some brief"


def test_default_planning_context_has_all_required_fields():
    engine = ExecutionEngine()
    ctx = engine._default_planning_context("test")
    for field in ("inferred_intent", "explicit_constraints", "implicit_constraints",
                  "missing_information", "execution_strategy", "execution_gate",
                  "inferred_personas", "inferred_nfrs", "quality_targets"):
        assert field in ctx, f"Missing field: {field}"
