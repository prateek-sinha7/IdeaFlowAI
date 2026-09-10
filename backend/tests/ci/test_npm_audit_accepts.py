"""
Tests for the npm audit accept filter.

The property under test is narrowness. A suppression that removes more than the
advisory it names is worse than no suppression, so most of these cases assert
that an entry SURVIVES.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.ci.npm_audit_accepts import (
    ACCEPTED_ADVISORIES,
    filter_report,
    main,
)

ACCEPTED_A = "GHSA-w3rx-r6r6-pgpr"
ACCEPTED_B = "GHSA-5p2g-fcmc-qvqq"


def _advisory(ghsa: str, severity: str = "high") -> dict:
    """Build a `via` advisory object shaped like npm's."""
    return {
        "source": 1138808,
        "name": "image-size",
        "title": f"advisory {ghsa}",
        "url": f"https://github.com/advisories/{ghsa}",
        "severity": severity,
        "range": "<=2.0.2",
    }


def _report(vulnerabilities: dict) -> dict:
    """Build a minimal npm audit document."""
    return {
        "auditReportVersion": 2,
        "vulnerabilities": vulnerabilities,
        "metadata": {
            "vulnerabilities": {
                "info": 0,
                "low": 0,
                "moderate": 0,
                "high": 99,
                "critical": 0,
                "total": 99,
            },
            "dependencies": {"total": 1},
        },
    }


def _real_world_report() -> dict:
    """The exact shape the failing CI run produced: root cause + propagator."""
    return _report(
        {
            "image-size": {
                "name": "image-size",
                "severity": "high",
                "isDirect": False,
                "via": [_advisory(ACCEPTED_A), _advisory(ACCEPTED_B)],
                "effects": ["pptxgenjs"],
                "range": "*",
            },
            "pptxgenjs": {
                "name": "pptxgenjs",
                "severity": "high",
                "isDirect": True,
                "via": ["image-size"],
                "effects": [],
                "range": "1.1.5-1 || >=1.1.6",
            },
        }
    )


class TestAcceptList:
    """The accept list itself is reviewed content, so assert its shape."""

    def test_every_accept_names_a_ghsa_and_justifies_itself(self):
        assert ACCEPTED_ADVISORIES, "an empty accept list should be deleted"
        for accept in ACCEPTED_ADVISORIES:
            assert accept.ghsa.startswith("GHSA-")
            # Long enough that it cannot be a placeholder like "n/a".
            assert len(accept.justification) > 80

    def test_accepts_are_unique(self):
        ghsas = [accept.ghsa for accept in ACCEPTED_ADVISORIES]
        assert len(ghsas) == len(set(ghsas))


class TestFilterReport:
    """Transitive resolution across the `via` graph."""

    def test_root_cause_and_propagator_both_drop(self):
        filtered, dropped, unused = filter_report(_real_world_report())
        assert filtered["vulnerabilities"] == {}
        assert sorted(dropped) == ["image-size", "pptxgenjs"]
        assert unused == []

    def test_counts_are_rebuilt_not_inherited(self):
        filtered, _, _ = filter_report(_real_world_report())
        counts = filtered["metadata"]["vulnerabilities"]
        assert counts["high"] == 0
        assert counts["total"] == 0

    def test_input_is_not_mutated(self):
        report = _real_world_report()
        before = json.dumps(report, sort_keys=True)
        filter_report(report)
        assert json.dumps(report, sort_keys=True) == before

    def test_unaccepted_advisory_survives(self):
        report = _report(
            {
                "left-pad": {
                    "name": "left-pad",
                    "severity": "critical",
                    "via": [_advisory("GHSA-xxxx-yyyy-zzzz", "critical")],
                }
            }
        )
        filtered, dropped, unused = filter_report(report)
        assert "left-pad" in filtered["vulnerabilities"]
        assert dropped == []
        # Both real accepts matched nothing in this synthetic report.
        assert unused == sorted({ACCEPTED_A, ACCEPTED_B})

    def test_a_new_advisory_on_an_accepted_package_keeps_the_entry(self):
        """The accept must not become a blanket waiver for the package."""
        report = _report(
            {
                "image-size": {
                    "name": "image-size",
                    "severity": "high",
                    "via": [
                        _advisory(ACCEPTED_A),
                        _advisory(ACCEPTED_B),
                        _advisory("GHSA-new0-new0-new0"),
                    ],
                }
            }
        )
        filtered, dropped, _ = filter_report(report)
        assert "image-size" in filtered["vulnerabilities"]
        assert dropped == []

    def test_propagator_survives_when_it_also_has_an_unaccepted_cause(self):
        report = _report(
            {
                "image-size": {
                    "name": "image-size",
                    "severity": "high",
                    "via": [_advisory(ACCEPTED_A), _advisory(ACCEPTED_B)],
                },
                "other-dep": {
                    "name": "other-dep",
                    "severity": "high",
                    "via": [_advisory("GHSA-aaaa-bbbb-cccc")],
                },
                "pptxgenjs": {
                    "name": "pptxgenjs",
                    "severity": "high",
                    "via": ["image-size", "other-dep"],
                },
            }
        )
        filtered, dropped, _ = filter_report(report)
        assert dropped == ["image-size"]
        assert set(filtered["vulnerabilities"]) == {"other-dep", "pptxgenjs"}

    def test_unresolvable_via_reference_is_not_treated_as_accepted(self):
        """An unknown package name in `via` means the cause set is unknown."""
        report = _report(
            {
                "pptxgenjs": {
                    "name": "pptxgenjs",
                    "severity": "high",
                    "via": ["image-size"],
                }
            }
        )
        filtered, dropped, _ = filter_report(report)
        assert "pptxgenjs" in filtered["vulnerabilities"]
        assert dropped == []

    def test_via_cycle_does_not_recurse_forever(self):
        report = _report(
            {
                "a": {"name": "a", "severity": "high", "via": ["b"]},
                "b": {"name": "b", "severity": "high", "via": ["a"]},
            }
        )
        filtered, dropped, _ = filter_report(report)
        assert set(filtered["vulnerabilities"]) == {"a", "b"}
        assert dropped == []

    def test_clean_report_reports_every_accept_as_unused(self):
        filtered, dropped, unused = filter_report(_report({}))
        assert filtered["vulnerabilities"] == {}
        assert dropped == []
        assert unused == sorted({ACCEPTED_A, ACCEPTED_B})


class TestCli:
    """Exit codes, because the shell script relies on them."""

    def _write(self, tmp_path: Path, report: dict) -> Path:
        path = tmp_path / "npm-audit.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        return path

    def test_success_writes_the_gated_report(self, tmp_path: Path):
        raw = self._write(tmp_path, _real_world_report())
        out = tmp_path / "npm-audit-gated.json"
        assert main(["--report", str(raw), "--out", str(out)]) == 0
        assert json.loads(out.read_text(encoding="utf-8"))["vulnerabilities"] == {}

    def test_stale_accept_fails_and_writes_nothing(self, tmp_path: Path):
        raw = self._write(tmp_path, _report({}))
        out = tmp_path / "npm-audit-gated.json"
        assert main(["--report", str(raw), "--out", str(out)]) == 1
        assert not out.exists()

    def test_missing_report_fails(self, tmp_path: Path):
        out = tmp_path / "npm-audit-gated.json"
        assert main(["--report", str(tmp_path / "nope.json"), "--out", str(out)]) == 1

    def test_empty_report_fails(self, tmp_path: Path):
        raw = tmp_path / "npm-audit.json"
        raw.write_text("", encoding="utf-8")
        out = tmp_path / "npm-audit-gated.json"
        assert main(["--report", str(raw), "--out", str(out)]) == 1

    def test_malformed_report_fails(self, tmp_path: Path):
        raw = tmp_path / "npm-audit.json"
        raw.write_text("{not json", encoding="utf-8")
        out = tmp_path / "npm-audit-gated.json"
        assert main(["--report", str(raw), "--out", str(out)]) == 1


class TestAgainstTheRealAuditGate:
    """End-to-end: the filtered report must make the real gate pass."""

    def test_gate_passes_on_the_filtered_real_world_report(self):
        from tools.ci.scanner_parsers import parse_npm_audit_json

        raw = _real_world_report()
        before = parse_npm_audit_json(json.dumps(raw))
        assert before.high_count == 2, "fixture must reproduce the CI failure"

        filtered, _, unused = filter_report(raw)
        assert unused == []
        after = parse_npm_audit_json(json.dumps(filtered))
        assert after.high_count == 0
        assert after.critical_count == 0
        assert after.success

    @pytest.mark.parametrize("severity", ["high", "critical"])
    def test_gate_still_fails_on_anything_unaccepted(self, severity: str):
        from tools.ci.scanner_parsers import parse_npm_audit_json

        report = _report(
            {
                "some-dep": {
                    "name": "some-dep",
                    "severity": severity,
                    "via": [_advisory("GHSA-dddd-eeee-ffff", severity)],
                }
            }
        )
        filtered, _, _ = filter_report(report)
        assert not parse_npm_audit_json(json.dumps(filtered)).success
