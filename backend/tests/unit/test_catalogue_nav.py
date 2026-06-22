"""
Tests for FIX-002 (KAN-75) — Add Catalogue tab for saved workflow navigation.

Validates:
  - The backend /api/user-workflows endpoint exists and is reachable
  - The UserWorkflowSummary shape includes created_at / updated_at
    (needed for the Catalogue's metadata display)
  - No regression on /api/user-workflows CRUD (the Catalogue's data source)
"""

from __future__ import annotations

import pytest


class TestUserWorkflowsApiForCatalogue:
    """Smoke tests for the backend data source powering the Catalogue tab."""

    def test_user_workflows_api_module_importable(self):
        """The user_workflows API module can be imported without errors."""
        import app.api.user_workflows as m  # noqa: F401
        assert m is not None

    def test_user_workflow_summary_has_timestamps(self):
        """UserWorkflowSummary includes created_at and updated_at for the Catalogue metadata row."""
        from app.api.user_workflows import UserWorkflowResponse
        fields = UserWorkflowResponse.model_fields
        assert "created_at" in fields, "created_at missing — Catalogue last-updated display broken"
        assert "updated_at" in fields, "updated_at missing — Catalogue last-updated display broken"

    def test_user_workflow_summary_has_base_pipeline_type(self):
        """UserWorkflowSummary includes base_pipeline_type for the pipeline badge."""
        from app.api.user_workflows import UserWorkflowResponse
        fields = UserWorkflowResponse.model_fields
        assert "base_pipeline_type" in fields

    def test_user_workflow_summary_has_agent_ids(self):
        """UserWorkflowSummary includes agent_ids for the agent count display."""
        from app.api.user_workflows import UserWorkflowResponse
        fields = UserWorkflowResponse.model_fields
        assert "agent_ids" in fields

    def test_user_workflow_summary_has_name_and_description(self):
        """UserWorkflowSummary has name and description for the Catalogue card text."""
        from app.api.user_workflows import UserWorkflowResponse
        fields = UserWorkflowResponse.model_fields
        assert "name" in fields
        assert "description" in fields

    def test_user_workflows_router_has_get_list_endpoint(self):
        """The /api/user-workflows GET list endpoint is registered."""
        from app.api.user_workflows import router
        routes = [r.path for r in router.routes]  # type: ignore[attr-defined]
        assert any("/user-workflows" in p for p in routes), \
            "GET /api/user-workflows not found — Catalogue data source missing"

    def test_user_workflows_router_has_crud_endpoints(self):
        """The /api/user-workflows PATCH and DELETE endpoints are registered (Catalogue actions)."""
        from app.api.user_workflows import router
        methods_by_path: dict[str, set] = {}
        for route in router.routes:  # type: ignore[attr-defined]
            if hasattr(route, "methods"):
                methods_by_path[route.path] = methods_by_path.get(route.path, set()) | route.methods

        all_methods = set()
        for ms in methods_by_path.values():
            all_methods |= ms

        assert "PATCH" in all_methods, "PATCH (rename) missing from user-workflows router"
        assert "DELETE" in all_methods, "DELETE missing from user-workflows router"
        assert "POST" in all_methods, "POST (create/duplicate) missing from user-workflows router"
