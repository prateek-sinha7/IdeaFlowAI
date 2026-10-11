"""
Unit tests for tools/ci/change_scope.py — the F-15 path-filter decision.

ci.yml's `changes` job runs this module as a stdlib script. Its outputs decide
which jobs a pull request skips, so every branch of the decision is asserted
here, including the fail-closed path for a malformed filter value.
"""

from __future__ import annotations

import pytest

from tools.ci import change_scope
from tools.ci.change_scope import AREAS, FILTER_NAMES, resolve_scope
from tools.ci.signal_registry import PATH_FILTER_AREAS


def _pr_filters(**overrides: str) -> dict[str, str]:
    """A pull-request filter set with everything unchanged, plus overrides."""
    filters = {name: "false" for name in FILTER_NAMES}
    filters.update(overrides)
    return filters


class TestResolveScopeFullScope:
    """Non-PR events and workflow changes run everything."""

    @pytest.mark.parametrize(
        "event", ["push", "workflow_dispatch", "workflow_call", "schedule"]
    )
    def test_resolve_scope_returns_full_scope_when_event_is_not_pull_request(
        self, event
    ):
        decision = resolve_scope(event, {})

        assert decision.filtered_areas == ()
        assert decision.security_legs == ("secrets", "iac")
        assert decision.container_components == ("backend", "frontend")
        assert decision.backend and decision.frontend and decision.infra

    def test_resolve_scope_returns_full_scope_when_pr_changes_workflows(self):
        decision = resolve_scope("pull_request", _pr_filters(workflows="true"))

        assert decision.filtered_areas == ()
        assert decision.security_legs == ("secrets", "iac")
        assert decision.container_components == ("backend", "frontend")


class TestResolveScopePullRequest:
    """Pull requests filter exactly the unchanged areas."""

    def test_resolve_scope_filters_all_five_areas_when_pr_is_docs_only(self):
        decision = resolve_scope("pull_request", _pr_filters())

        assert decision.filtered_areas == AREAS
        assert decision.security_legs == ("secrets",)
        assert decision.container_components == ()
        assert not decision.backend and not decision.frontend

    def test_resolve_scope_keeps_backend_and_image_when_pr_is_backend_only(self):
        decision = resolve_scope(
            "pull_request", _pr_filters(backend="true", backend_image="true")
        )

        assert decision.backend is True
        assert decision.backend_image is True
        assert decision.frontend is False
        assert decision.container_components == ("backend",)
        assert decision.filtered_areas == ("frontend", "infra", "frontend_image")

    def test_resolve_scope_keeps_frontend_and_image_when_pr_is_frontend_only(self):
        decision = resolve_scope(
            "pull_request", _pr_filters(backend="true", frontend="true")
        )

        assert decision.frontend is True
        assert decision.frontend_image is True
        assert decision.backend_image is False
        assert decision.container_components == ("frontend",)
        assert decision.filtered_areas == ("infra", "backend_image")

    def test_resolve_scope_scans_both_images_when_docker_inputs_change(self):
        decision = resolve_scope(
            "pull_request", _pr_filters(backend="true", docker="true")
        )

        assert decision.backend_image is True
        assert decision.frontend_image is True
        assert decision.container_components == ("backend", "frontend")
        assert "backend_image" not in decision.filtered_areas
        assert "frontend_image" not in decision.filtered_areas

    def test_resolve_scope_adds_iac_leg_when_infra_changes(self):
        decision = resolve_scope(
            "pull_request", _pr_filters(backend="true", infra="true")
        )

        assert decision.security_legs == ("secrets", "iac")
        assert "infra" not in decision.filtered_areas

    def test_resolve_scope_raises_when_pr_filter_value_missing(self):
        filters = _pr_filters()
        del filters["frontend"]

        with pytest.raises(ValueError, match="frontend"):
            resolve_scope("pull_request", filters)

    @pytest.mark.parametrize("bad", ["", "True", "1", "yes", "false "])
    def test_resolve_scope_raises_when_pr_filter_value_invalid(self, bad):
        with pytest.raises(ValueError, match="must be 'true' or 'false'"):
            resolve_scope("pull_request", _pr_filters(backend=bad))


class TestMain:
    """`main` writes the exact $GITHUB_OUTPUT lines ci.yml maps to outputs."""

    def _set_env(self, monkeypatch, tmp_path, event: str, **filters: str):
        output = tmp_path / "github_output"
        output.write_text("", encoding="utf-8")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("EVENT_NAME", event)
        for name in FILTER_NAMES:
            monkeypatch.setenv(f"F_{name.upper()}", filters.get(name, "false"))
        return output

    def test_main_writes_full_scope_lines_when_event_is_push(
        self, monkeypatch, tmp_path
    ):
        output = self._set_env(monkeypatch, tmp_path, "push")

        assert change_scope.main() == 0
        assert output.read_text(encoding="utf-8").splitlines() == [
            "backend=true",
            "frontend=true",
            "infra=true",
            "docker=true",
            "workflows=true",
            "backend_image=true",
            "frontend_image=true",
            'security_legs=["secrets","iac"]',
            'container_components=["backend","frontend"]',
            "filtered_areas=",
        ]

    def test_main_writes_filtered_lines_when_pr_is_backend_only(
        self, monkeypatch, tmp_path
    ):
        output = self._set_env(
            monkeypatch, tmp_path, "pull_request", backend="true", backend_image="true"
        )

        assert change_scope.main() == 0
        assert output.read_text(encoding="utf-8").splitlines() == [
            "backend=true",
            "frontend=false",
            "infra=false",
            "docker=false",
            "workflows=false",
            "backend_image=true",
            "frontend_image=false",
            'security_legs=["secrets"]',
            'container_components=["backend"]',
            "filtered_areas=frontend,infra,frontend_image",
        ]

    def test_main_fails_and_writes_nothing_when_pr_filter_invalid(
        self, monkeypatch, tmp_path
    ):
        output = self._set_env(monkeypatch, tmp_path, "pull_request", backend="")

        assert change_scope.main() == 1
        assert output.read_text(encoding="utf-8") == ""

    def test_main_fails_when_github_output_unset(self, monkeypatch, tmp_path):
        self._set_env(monkeypatch, tmp_path, "push")
        monkeypatch.delenv("GITHUB_OUTPUT")

        assert change_scope.main() == 1


def test_areas_equal_registry_path_filter_areas_when_compared_as_sets():
    """change_scope cannot import the registry, so the two copies are pinned here."""
    assert set(AREAS) == PATH_FILTER_AREAS
    assert len(AREAS) == len(set(AREAS))
