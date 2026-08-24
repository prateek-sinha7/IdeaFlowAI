"""
Unit tests for test count enforcement and skip linting.

Validates:
- Test count collection and comparison against baselines
- Skip/disable detection and remediation record validation

Requirements: 32.3, 32.4, 32.5, 2.7
"""

import pytest
from pathlib import Path
from datetime import datetime, timedelta
from test_count_enforcement import TestCountValidator, SkipEnforcementLinter


@pytest.fixture
def temp_repo_root(tmp_path):
    """Create a temporary repo structure."""
    repo = tmp_path / "repo"
    repo.mkdir()

    # Create .planning directory
    planning_dir = repo / ".planning"
    planning_dir.mkdir()

    # Create baseline file
    baseline_content = """baselines:
  pytest: 100
  vitest: 50
  playwright_mocked: 25
  playwright_live: 5
"""
    (planning_dir / "test-baselines.yml").write_text(baseline_content)

    # Create remediation record
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    record_content = f"""# Remediation Record

## Disabled Tests

| Case ID | Suite | Directive | Owner | Reason | Expiry |
|---------|-------|-----------|-------|--------|--------|
| test_known_skip | pytest | skip | @alice | ISS-123 | {tomorrow} |
| test_fixme_frontend | vitest | fixme | @bob | ISS-124 | {tomorrow} |
"""
    (planning_dir / "REMEDIATION-RECORD.md").write_text(record_content)

    # Create backend tests directory
    backend_dir = repo / "backend" / "tests"
    backend_dir.mkdir(parents=True)

    # Create frontend tests directory
    frontend_dir = repo / "frontend" / "src"
    frontend_dir.mkdir(parents=True)

    return repo


def test_validator_loads_baselines(temp_repo_root):
    """Test that validator loads baseline counts correctly."""
    validator = TestCountValidator(repo_root=temp_repo_root)

    assert validator.baselines["pytest"] == 100
    assert validator.baselines["vitest"] == 50
    assert validator.baselines["playwright_mocked"] == 25
    assert validator.baselines["playwright_live"] == 5


def test_validator_missing_baseline_file(tmp_path):
    """Test validator with missing baseline file."""
    with pytest.raises(FileNotFoundError):
        TestCountValidator(repo_root=tmp_path)


def test_validator_invalid_baseline_file(tmp_path):
    """Test validator with invalid baseline file format."""
    repo = tmp_path / "repo"
    repo.mkdir()
    planning_dir = repo / ".planning"
    planning_dir.mkdir()

    # Create invalid baseline file (missing 'baselines' key)
    (planning_dir / "test-baselines.yml").write_text("invalid: content\n")

    with pytest.raises(ValueError, match="Invalid baseline file format"):
        TestCountValidator(repo_root=repo)


def test_skip_linter_loads_recorded_skips(temp_repo_root):
    """Test that linter loads recorded skip entries."""
    linter = SkipEnforcementLinter(repo_root=temp_repo_root)

    assert "test_known_skip" in linter.recorded_skips
    assert "test_fixme_frontend" in linter.recorded_skips


def test_skip_linter_missing_record(tmp_path):
    """Test linter with missing remediation record."""
    repo = tmp_path / "repo"
    repo.mkdir()
    planning_dir = repo / ".planning"
    planning_dir.mkdir()

    linter = SkipEnforcementLinter(repo_root=repo)

    # Should have empty recorded_skips
    assert len(linter.recorded_skips) == 0


def test_skip_linter_finds_unrecorded_pytest_skip(temp_repo_root):
    """Test that linter detects unrecorded pytest.skip() calls."""
    # Create a test file with an unrecorded skip
    test_file = temp_repo_root / "backend" / "tests" / "test_example.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)

    test_content = '''
def test_recorded_skip():
    pytest.skip("Known skip")

def test_unrecorded_skip():
    pytest.skip("Unknown skip")
'''
    test_file.write_text(test_content)

    linter = SkipEnforcementLinter(repo_root=temp_repo_root)
    findings = linter.lint_backend_tests()

    # Should find at least one finding for unrecorded skip
    unrecorded = [f for f in findings if "unrecorded_skip" in f["case_id"].lower()]
    assert len(unrecorded) > 0
    assert any(f["directive"] == "pytest.skip()" for f in unrecorded)


def test_skip_linter_finds_unrecorded_pytest_mark_skip(temp_repo_root):
    """Test that linter detects unrecorded @pytest.mark.skip."""
    test_file = temp_repo_root / "backend" / "tests" / "test_marked.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)

    test_content = '''
@pytest.mark.skip
def test_unrecorded_marked_skip():
    pass
'''
    test_file.write_text(test_content)

    linter = SkipEnforcementLinter(repo_root=temp_repo_root)
    findings = linter.lint_backend_tests()

    # Should find the marked skip
    marked_skips = [f for f in findings if "@pytest.mark.skip" in f["directive"]]
    assert len(marked_skips) > 0


def test_skip_linter_finds_unrecorded_vitest_skip(temp_repo_root):
    """Test that linter detects unrecorded test.skip() in vitest."""
    test_file = temp_repo_root / "frontend" / "src" / "test_example.test.ts"
    test_file.parent.mkdir(parents=True, exist_ok=True)

    test_content = '''
test.skip("unrecorded test skip", () => {
  expect(true).toBe(true);
});
'''
    test_file.write_text(test_content)

    linter = SkipEnforcementLinter(repo_root=temp_repo_root)
    findings = linter.lint_frontend_tests()

    # Should find the skip
    skips = [f for f in findings if "unrecorded test skip" in f["case_id"]]
    assert len(skips) > 0
    assert any(f["directive"] == "test.skip()" for f in skips)


def test_skip_linter_finds_unrecorded_vitest_fixme(temp_repo_root):
    """Test that linter detects unrecorded test.fixme() in vitest."""
    test_file = temp_repo_root / "frontend" / "src" / "test_example.test.ts"
    test_file.parent.mkdir(parents=True, exist_ok=True)

    test_content = '''
test.fixme("unrecorded test fixme", () => {
  expect(true).toBe(true);
});
'''
    test_file.write_text(test_content)

    linter = SkipEnforcementLinter(repo_root=temp_repo_root)
    findings = linter.lint_frontend_tests()

    # Should find the fixme
    fixmes = [f for f in findings if "unrecorded test fixme" in f["case_id"]]
    assert len(fixmes) > 0
    assert any(f["directive"] == "test.fixme()" for f in fixmes)


def test_skip_linter_ignores_recorded_skips(temp_repo_root):
    """Test that linter ignores recorded skips."""
    # Create a test file with a recorded skip
    test_file = temp_repo_root / "backend" / "tests" / "test_recorded.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)

    test_content = '''
def test_known_skip():
    pytest.skip("This is recorded")
'''
    test_file.write_text(test_content)

    linter = SkipEnforcementLinter(repo_root=temp_repo_root)
    findings = linter.lint_backend_tests()

    # Should NOT find the recorded skip
    known_skips = [f for f in findings if "test_known_skip" in f["case_id"]]
    assert len(known_skips) == 0


def test_skip_linter_has_findings(temp_repo_root):
    """Test has_findings() method."""
    # Create an unrecorded skip
    test_file = temp_repo_root / "backend" / "tests" / "test_new.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("def test_new():\n    pytest.skip('new')\n")

    linter = SkipEnforcementLinter(repo_root=temp_repo_root)
    assert not linter.has_findings()  # No linting done yet

    linter.lint_backend_tests()
    assert linter.has_findings()  # Now we should have findings


def test_skip_linter_format_findings(temp_repo_root):
    """Test format_findings() output."""
    linter = SkipEnforcementLinter(repo_root=temp_repo_root)

    # Empty findings
    output = linter.format_findings()
    assert "No unrecorded test skips found" in output

    # Add a finding manually
    linter.findings.append({
        "file": "backend/tests/test_example.py",
        "line": 42,
        "directive": "pytest.skip()",
        "case_id": "test_example",
    })

    output = linter.format_findings()
    assert "Unrecorded test skips/disables found" in output
    assert "test_example.py:42" in output
    assert "pytest.skip()" in output


def test_validator_format_failure_message(temp_repo_root):
    """Test failure message formatting."""
    validator = TestCountValidator(repo_root=temp_repo_root)

    results = {
        "pytest": {"baseline": 100, "collected": 99, "match": False},
        "vitest": {"baseline": 50, "collected": 50, "match": True},
        "playwright_mocked": {"baseline": 25, "collected": 30, "match": False},
    }

    msg = validator.format_failure_message(results)

    assert "Test count validation failed" in msg
    assert "pytest: baseline=100, collected=99" in msg
    assert "playwright_mocked: baseline=25, collected=30" in msg
    # vitest should not be in the failure message since it matches
    assert "vitest" not in msg or "baseline=50, collected=50" not in msg


def test_linter_multiple_findings(temp_repo_root):
    """Test linter with multiple unrecorded skips."""
    test_file = temp_repo_root / "backend" / "tests" / "test_multi.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)

    test_content = '''
def test_skip1():
    pytest.skip("skip1")

@pytest.mark.skip
def test_skip2():
    pass

def test_skip3():
    pytest.skip("skip3")
'''
    test_file.write_text(test_content)

    linter = SkipEnforcementLinter(repo_root=temp_repo_root)
    findings = linter.lint_backend_tests()

    # Should have multiple findings
    assert len(findings) >= 2
