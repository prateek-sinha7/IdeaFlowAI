"""
Tests for the single Trivy/Grype exceptions list (tools/ci/scan_accepts.py).

The property under test is narrowness. An exception that removes more than the
exact finding it names is worse than no exception, so most cases assert that a
finding SURVIVES, and that anything expired, stale or unreadable FAILS.

Carries forward the coverage of the retired test_npm_audit_accepts.py (stale
accept fails, a new advisory on an accepted package stays red, the input is not
mutated, the gate still fails on anything unaccepted) for the list that
replaced it.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from tools.ci.scan_accepts import (
    ACCEPTED_FINDINGS,
    KNOWN_SCOPES,
    AcceptedFinding,
    apply_accepts,
    filter_grype_report,
    filter_trivy_report,
    gated_path,
    main,
    normalise_package,
    validate_accepts,
)
from tools.ci.scanner_parsers import parse_grype_json, parse_trivy_json

#: A date safely before every expiry in the real list.
BEFORE_EXPIRY = date(2026, 10, 1)

ZLIB = AcceptedFinding(
    ids=frozenset({"CVE-2023-45853"}),
    package="zlib1g",
    scopes=frozenset({"backend-image"}),
    expires="2026-12-31",
    owner="platform-engineering",
    justification="MiniZip is not built into zlib1g; test fixture justification text.",
)
ECDSA = AcceptedFinding(
    ids=frozenset({"CVE-2024-23342", "GHSA-wj6h-64fc-37mp"}),
    package="ecdsa",
    scopes=frozenset({"backend-image"}),
    expires="2026-12-31",
    owner="platform-engineering",
    justification="Only RS256 is used; the EC signing path is unreachable in this app.",
)


def _trivy(*vulns: tuple[str, str, str]) -> dict:
    """Trivy JSON with one result holding (id, package, severity) findings."""
    return {
        "SchemaVersion": 2,
        "Results": [
            {
                "Target": "image",
                "Class": "os-pkg",
                "Vulnerabilities": [
                    {
                        "VulnerabilityID": vuln_id,
                        "PkgName": package,
                        "InstalledVersion": "1.0",
                        "Severity": severity,
                    }
                    for vuln_id, package, severity in vulns
                ],
            }
        ],
    }


def _grype(*matches: tuple[str, list[str], str, str]) -> dict:
    """Grype JSON with (id, related ids, package, severity) matches."""
    return {
        "matches": [
            {
                "vulnerability": {"id": vuln_id, "severity": severity},
                "relatedVulnerabilities": [{"id": rid} for rid in related],
                "artifact": {"name": package, "version": "1.0"},
            }
            for vuln_id, related, package, severity in matches
        ]
    }


def _write(path: Path, payload: dict) -> Path:
    """Write a JSON report and return its path."""
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class TestValidateAccepts:
    """The real list is reviewed content, so its shape is asserted."""

    def test_validate_accepts_returns_no_problems_when_given_the_real_list(self):
        assert validate_accepts() == []

    def test_validate_accepts_reports_problem_when_scope_is_unknown(self):
        bad = AcceptedFinding(
            ids=frozenset({"CVE-1"}),
            package="pkg",
            scopes=frozenset({"somewhere-else"}),
            expires="2026-12-31",
            owner="x",
            justification="long enough justification to pass the length check here",
        )
        assert any("scopes" in problem for problem in validate_accepts([bad]))

    def test_validate_accepts_reports_problem_when_expiry_is_not_a_date(self):
        bad = AcceptedFinding(
            ids=frozenset({"CVE-1"}),
            package="pkg",
            scopes=frozenset({"backend-image"}),
            expires="soon",
            owner="x",
            justification="long enough justification to pass the length check here",
        )
        assert any("ISO date" in problem for problem in validate_accepts([bad]))

    def test_validate_accepts_reports_problem_when_id_is_listed_twice(self):
        assert any("listed twice" in p for p in validate_accepts([ZLIB, ZLIB]))

    def test_real_list_scopes_are_known_and_expiry_within_a_quarter(self):
        for accept in ACCEPTED_FINDINGS:
            assert accept.scopes <= KNOWN_SCOPES
            assert date.fromisoformat(accept.expires) <= date(2026, 12, 31)

    def test_real_list_does_not_accept_setuptools_when_a_fix_exists(self):
        """setuptools CVE-2025-47273 has a fix, so it is fixed, not accepted."""
        packages = {normalise_package(accept.package) for accept in ACCEPTED_FINDINGS}
        assert "setuptools" not in packages


class TestFilterTrivyReport:
    """Exact (id, package) matching on Trivy reports."""

    def test_filter_trivy_report_removes_finding_when_id_and_package_match(self):
        gated, matched = filter_trivy_report(
            _trivy(("CVE-2023-45853", "zlib1g", "CRITICAL")), [ZLIB]
        )
        assert gated["Results"][0]["Vulnerabilities"] == []
        assert [accept for accept, _ in matched] == [ZLIB]

    def test_filter_trivy_report_keeps_finding_when_id_is_on_another_package(self):
        gated, matched = filter_trivy_report(
            _trivy(("CVE-2023-45853", "libminizip1", "CRITICAL")), [ZLIB]
        )
        assert len(gated["Results"][0]["Vulnerabilities"]) == 1
        assert matched == []

    def test_filter_trivy_report_keeps_finding_when_new_advisory_hits_accepted_package(
        self,
    ):
        gated, _ = filter_trivy_report(
            _trivy(
                ("CVE-2023-45853", "zlib1g", "CRITICAL"),
                ("CVE-2099-0001", "zlib1g", "HIGH"),
            ),
            [ZLIB],
        )
        remaining = gated["Results"][0]["Vulnerabilities"]
        assert [v["VulnerabilityID"] for v in remaining] == ["CVE-2099-0001"]

    def test_filter_trivy_report_leaves_input_unmutated_when_filtering(self):
        report = _trivy(("CVE-2023-45853", "zlib1g", "CRITICAL"))
        before = json.dumps(report, sort_keys=True)
        filter_trivy_report(report, [ZLIB])
        assert json.dumps(report, sort_keys=True) == before

    def test_filter_trivy_report_gated_output_still_fails_gate_when_unaccepted_remains(
        self,
    ):
        gated, _ = filter_trivy_report(
            _trivy(
                ("CVE-2023-45853", "zlib1g", "CRITICAL"),
                ("CVE-2099-0001", "openssl", "HIGH"),
            ),
            [ZLIB],
        )
        assert parse_trivy_json(json.dumps(gated)).success is False

    def test_filter_trivy_report_gated_output_passes_gate_when_all_findings_accepted(
        self,
    ):
        gated, _ = filter_trivy_report(
            _trivy(("CVE-2023-45853", "zlib1g", "CRITICAL")), [ZLIB]
        )
        assert parse_trivy_json(json.dumps(gated)).success is True


class TestFilterGrypeReport:
    """Grype reports GHSA ids with CVE aliases; both must match one entry."""

    def test_filter_grype_report_removes_match_when_alias_matches(self):
        gated, matched = filter_grype_report(
            _grype(("GHSA-wj6h-64fc-37mp", ["CVE-2024-23342"], "ecdsa", "High")),
            [ECDSA],
        )
        assert gated["matches"] == []
        assert len(matched) == 1

    def test_filter_grype_report_removes_match_when_only_related_id_is_listed(self):
        only_cve = AcceptedFinding(
            ids=frozenset({"CVE-2024-23342"}),
            package="ecdsa",
            scopes=frozenset({"backend-image"}),
            expires="2026-12-31",
            owner="x",
            justification="long enough justification to pass the length check here",
        )
        gated, _ = filter_grype_report(
            _grype(("GHSA-wj6h-64fc-37mp", ["CVE-2024-23342"], "ecdsa", "High")),
            [only_cve],
        )
        assert gated["matches"] == []

    def test_filter_grype_report_keeps_match_when_package_differs(self):
        gated, _ = filter_grype_report(
            _grype(("CVE-2024-23342", [], "python-jose", "High")), [ECDSA]
        )
        assert len(gated["matches"]) == 1
        assert parse_grype_json(json.dumps(gated)).success is False


class TestApplyAccepts:
    """Expiry, staleness and unreadable reports all fail closed."""

    def test_apply_accepts_succeeds_and_writes_gated_reports_when_every_entry_matches(
        self, tmp_path: Path
    ):
        trivy = _write(
            tmp_path / "trivy.json", _trivy(("CVE-2023-45853", "zlib1g", "CRITICAL"))
        )
        grype = _write(
            tmp_path / "grype.json",
            _grype(("GHSA-wj6h-64fc-37mp", ["CVE-2024-23342"], "ecdsa", "High")),
        )
        errors, evidence = apply_accepts(
            "backend-image",
            [("trivy", trivy), ("grype", grype)],
            BEFORE_EXPIRY,
            [ZLIB, ECDSA],
        )
        assert errors == []
        assert gated_path(trivy).exists() and gated_path(grype).exists()
        assert evidence["reports"]["trivy"]["accepted"][0]["ids"] == ["CVE-2023-45853"]

    def test_apply_accepts_does_not_flag_stale_when_only_one_engine_reports_it(
        self, tmp_path: Path
    ):
        """Staleness is judged per scope across engines, not per engine."""
        trivy = _write(
            tmp_path / "trivy.json", _trivy(("CVE-2023-45853", "zlib1g", "CRITICAL"))
        )
        grype = _write(tmp_path / "grype.json", _grype())
        errors, _ = apply_accepts(
            "backend-image", [("trivy", trivy), ("grype", grype)], BEFORE_EXPIRY, [ZLIB]
        )
        assert errors == []

    def test_apply_accepts_reports_error_when_entry_matches_nothing(
        self, tmp_path: Path
    ):
        trivy = _write(tmp_path / "trivy.json", _trivy())
        errors, _ = apply_accepts(
            "backend-image", [("trivy", trivy)], BEFORE_EXPIRY, [ZLIB]
        )
        assert any("matched nothing" in error for error in errors)

    def test_apply_accepts_reports_error_and_stops_accepting_when_entry_expired(
        self, tmp_path: Path
    ):
        trivy = _write(
            tmp_path / "trivy.json", _trivy(("CVE-2023-45853", "zlib1g", "CRITICAL"))
        )
        errors, _ = apply_accepts(
            "backend-image", [("trivy", trivy)], date(2027, 1, 1), [ZLIB]
        )
        assert any("expired" in error for error in errors)
        gated = json.loads(gated_path(trivy).read_text(encoding="utf-8"))
        assert len(gated["Results"][0]["Vulnerabilities"]) == 1

    def test_apply_accepts_accepts_entry_when_evaluated_on_expiry_day(
        self, tmp_path: Path
    ):
        trivy = _write(
            tmp_path / "trivy.json", _trivy(("CVE-2023-45853", "zlib1g", "CRITICAL"))
        )
        errors, _ = apply_accepts(
            "backend-image", [("trivy", trivy)], date(2026, 12, 31), [ZLIB]
        )
        assert errors == []

    def test_apply_accepts_ignores_entries_when_scope_is_not_declared(
        self, tmp_path: Path
    ):
        trivy = _write(
            tmp_path / "trivy.json", _trivy(("CVE-2023-45853", "zlib1g", "CRITICAL"))
        )
        errors, _ = apply_accepts(
            "frontend-image", [("trivy", trivy)], BEFORE_EXPIRY, [ZLIB]
        )
        assert errors == []
        gated = json.loads(gated_path(trivy).read_text(encoding="utf-8"))
        assert len(gated["Results"][0]["Vulnerabilities"]) == 1

    def test_apply_accepts_reports_error_without_stale_noise_when_report_missing(
        self, tmp_path: Path
    ):
        errors, _ = apply_accepts(
            "backend-image",
            [("trivy", tmp_path / "absent.json")],
            BEFORE_EXPIRY,
            [ZLIB],
        )
        assert any("report not found" in error for error in errors)
        assert not any("matched nothing" in error for error in errors)

    @pytest.mark.parametrize("content", ["", "{not json", "[]"])
    def test_apply_accepts_reports_error_when_report_unusable(
        self, tmp_path: Path, content: str
    ):
        raw = tmp_path / "trivy.json"
        raw.write_text(content, encoding="utf-8")
        errors, _ = apply_accepts(
            "backend-image", [("trivy", raw)], BEFORE_EXPIRY, [ZLIB]
        )
        assert errors
        assert not gated_path(raw).exists()


class TestMain:
    """CLI exit codes, which are what ci-image-scan.sh reads."""

    def test_main_returns_one_when_no_report_is_given(self, tmp_path: Path):
        assert (
            main(["--scope", "backend-image", "--out", str(tmp_path / "e.json")]) == 1
        )

    def test_main_returns_one_when_real_entry_is_stale_for_scope(self, tmp_path: Path):
        trivy = _write(tmp_path / "trivy.json", _trivy())
        code = main(
            [
                "--scope",
                "frontend-image",
                "--trivy",
                str(trivy),
                "--out",
                str(tmp_path / "e.json"),
            ],
            today=BEFORE_EXPIRY,
        )
        assert code == 1

    def test_main_returns_zero_when_real_list_matches_frontend_lockfile(
        self, tmp_path: Path
    ):
        trivy = _write(
            tmp_path / "trivy.json",
            _trivy(
                ("CVE-2025-71330", "image-size", "HIGH"),
                ("GHSA-5p2g-fcmc-qvqq", "image-size", "HIGH"),
            ),
        )
        evidence = tmp_path / "e.json"
        code = main(
            [
                "--scope",
                "frontend-lockfile",
                "--trivy",
                str(trivy),
                "--out",
                str(evidence),
            ],
            today=BEFORE_EXPIRY,
        )
        assert code == 0
        assert json.loads(evidence.read_text(encoding="utf-8"))["errors"] == []
        gated = json.loads(gated_path(trivy).read_text(encoding="utf-8"))
        assert parse_trivy_json(json.dumps(gated)).success is True
