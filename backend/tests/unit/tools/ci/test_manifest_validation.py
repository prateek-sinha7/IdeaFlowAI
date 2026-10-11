"""
Unit tests for tools/ci/manifest_validation.py — the trusted PR finalizer's rules.

The finalizer runs this file from the default branch against the evaluator's
manifest. Every refusal it ported from the old shell heredoc is asserted, plus
the F-15 rules: path filtering only on pull_request, never for a
NEVER_FILTERABLE signal, never overlapping a verdict, and every required signal
accounted for exactly once.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tools.ci.aggregate_truth import compute_aggregate_required_signals
from tools.ci.manifest_validation import NEVER_FILTERABLE, main, validate_manifest
from tools.ci.signal_registry import SIGNAL_REGISTRY

SHA = "b" * 40
REQUIRED = sorted(compute_aggregate_required_signals())


def _manifest(**overrides: Any) -> dict[str, Any]:
    """A strict, fully green push manifest, plus overrides."""
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "producer": "ci-evidence",
        "evaluation_sha": SHA,
        "outcome": "success",
        "strict_outcome": "success",
        "event": "push",
        "filtered_areas": [],
        "required_signals": REQUIRED,
        "signal_states": {name: "success" for name in REQUIRED},
        "policy_filtered": [],
        "advisory_signals": [],
        "advisory_downgraded": {},
    }
    manifest.update(overrides)
    return manifest


def _filtered_pr_manifest(filtered: list[str]) -> dict[str, Any]:
    """A pull-request manifest with `filtered` moved out of signal_states."""
    return _manifest(
        event="pull_request",
        filtered_areas=["backend"],
        signal_states={n: "success" for n in REQUIRED if n not in filtered},
        policy_filtered=sorted(filtered),
    )


BACKEND_IDS = sorted(s.id for s in SIGNAL_REGISTRY.get_signals_by_area("backend"))


class TestAccepts:
    def test_validate_manifest_accepts_when_strict_and_complete(self):
        assert validate_manifest(_manifest(), SHA) == []

    def test_validate_manifest_accepts_when_pr_policy_filtered_is_complete(self):
        assert validate_manifest(_filtered_pr_manifest(BACKEND_IDS), SHA) == []

    def test_validate_manifest_accepts_when_manifest_predates_filter_fields(self):
        """A manifest written before F-15 (no event / policy_filtered) still passes."""
        manifest = _manifest()
        for field in ("event", "filtered_areas", "policy_filtered"):
            del manifest[field]
        assert validate_manifest(manifest, SHA) == []


class TestRejectsFiltering:
    @pytest.mark.parametrize("event", ["push", "workflow_dispatch", None])
    def test_validate_manifest_rejects_when_filtered_off_pull_request(self, event):
        manifest = _filtered_pr_manifest(BACKEND_IDS)
        manifest["event"] = event

        problems = validate_manifest(manifest, SHA)

        assert any("only valid on pull_request" in p for p in problems)

    @pytest.mark.parametrize("signal_id", sorted(NEVER_FILTERABLE))
    def test_validate_manifest_rejects_when_never_filterable_id_filtered(
        self, signal_id
    ):
        problems = validate_manifest(_filtered_pr_manifest([signal_id]), SHA)

        assert any(f"{signal_id} can never be policy-filtered" in p for p in problems)

    def test_validate_manifest_rejects_when_id_in_both_maps(self):
        manifest = _filtered_pr_manifest(BACKEND_IDS)
        manifest["signal_states"]["backend-offline"] = "success"

        problems = validate_manifest(manifest, SHA)

        assert any("in both signal_states and policy_filtered" in p for p in problems)

    def test_validate_manifest_rejects_when_required_id_in_neither_map(self):
        manifest = _manifest()
        del manifest["signal_states"]["frontend-build"]

        problems = validate_manifest(manifest, SHA)

        assert any("frontend-build is in neither" in p for p in problems)

    def test_validate_manifest_rejects_when_required_signals_absent(self):
        manifest = _manifest()
        del manifest["required_signals"]

        assert "manifest lists no required_signals" in validate_manifest(manifest, SHA)


class TestRejectsPortedChecks:
    """Every refusal the old ci-validate-evidence.sh heredoc made."""

    def test_validate_manifest_rejects_when_signal_not_success(self):
        manifest = _manifest()
        manifest["signal_states"]["backend-offline"] = "skipped"

        assert "signal backend-offline is skipped" in validate_manifest(manifest, SHA)

    def test_validate_manifest_rejects_when_advisory_downgraded(self):
        manifest = _manifest(advisory_downgraded={"frontend-e2e": "failure"})

        problems = validate_manifest(manifest, SHA)

        assert any("downgraded to advisory" in p for p in problems)

    def test_validate_manifest_rejects_when_strict_outcome_failed(self):
        problems = validate_manifest(_manifest(strict_outcome="failure"), SHA)

        assert any("strict outcome" in p for p in problems)

    def test_validate_manifest_rejects_when_sha_is_stale(self):
        problems = validate_manifest(_manifest(evaluation_sha="c" * 40), SHA)

        assert any("stale evidence" in p for p in problems)

    def test_validate_manifest_rejects_when_outcome_failed(self):
        problems = validate_manifest(_manifest(outcome="failure"), SHA)

        assert any("cannot be finalized as green" in p for p in problems)

    @pytest.mark.parametrize(
        ("field", "value", "fragment"),
        [
            ("schema_version", 2, "unsupported schema_version"),
            ("producer", "someone-else", "unexpected producer"),
        ],
    )
    def test_validate_manifest_rejects_when_header_field_wrong(
        self, field, value, fragment
    ):
        problems = validate_manifest(_manifest(**{field: value}), SHA)

        assert any(fragment in p for p in problems)

    @pytest.mark.parametrize(
        "field", ["schema_version", "producer", "evaluation_sha", "outcome"]
    )
    def test_validate_manifest_rejects_when_required_field_missing(self, field):
        manifest = _manifest()
        del manifest[field]

        assert f"missing required field '{field}'" in validate_manifest(manifest, SHA)

    def test_validate_manifest_rejects_when_not_an_object(self):
        assert validate_manifest([], SHA) == ["manifest is not a JSON object"]  # type: ignore[arg-type]


def test_never_filterable_equals_registry_members_without_area_when_compared():
    """The stdlib copy must match the registry's None-area aggregate members."""
    aggregate = SIGNAL_REGISTRY["ci-required"].aggregate_members or []
    unfilterable = {
        name for name in aggregate if SIGNAL_REGISTRY[name].path_filter_area is None
    }
    assert NEVER_FILTERABLE == unfilterable


class TestMain:
    def _write(self, tmp_path: Path, manifest: Any) -> Path:
        path = tmp_path / "ci-evidence-manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path

    def test_main_returns_zero_when_manifest_accepted(self, tmp_path, capsys):
        path = self._write(tmp_path, _filtered_pr_manifest(BACKEND_IDS))

        assert main([str(path), SHA]) == 0
        assert "Evaluator evidence accepted" in capsys.readouterr().out

    def test_main_returns_one_and_prints_errors_when_manifest_rejected(
        self, tmp_path, capsys
    ):
        path = self._write(tmp_path, _manifest(outcome="failure"))

        assert main([str(path), SHA]) == 1
        assert "::error::" in capsys.readouterr().out

    def test_main_returns_one_when_manifest_unreadable(self, tmp_path):
        path = tmp_path / "broken.json"
        path.write_text("{not json", encoding="utf-8")

        assert main([str(path), SHA]) == 1
        assert main([str(tmp_path / "absent.json"), SHA]) == 1

    def test_main_returns_two_when_arguments_wrong(self):
        assert main([]) == 2
