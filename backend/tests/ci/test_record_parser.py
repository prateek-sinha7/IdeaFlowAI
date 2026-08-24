"""Unit tests for the remediation record parser."""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
from record_parser import RemediationRecordParser, RemediationEntry


@pytest.fixture
def temp_record(tmp_path):
    """Create a temporary remediation record file."""
    record_path = tmp_path / "REMEDIATION-RECORD.md"
    return record_path


def test_parser_complete_entry(temp_record):
    """Test parsing a complete entry with all required fields."""
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    content = f"""# Remediation Record

## Disabled Tests

| Case ID | Suite | Directive | Owner | Reason | Expiry |
|---------|-------|-----------|-------|--------|--------|
| test_foo | pytest | skip | @alice | ISS-123 | {tomorrow} |
"""
    temp_record.write_text(content)
    parser = RemediationRecordParser(temp_record)
    parser.parse()

    assert len(parser.disabled_tests) == 1
    entry = parser.disabled_tests[0]
    assert entry.case_id == "test_foo"
    assert entry.owner == "@alice"
    assert entry.reason == "ISS-123"
    assert entry.expiry is not None


def test_parser_missing_owner(temp_record):
    """Test parsing an entry missing an owner."""
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    content = f"""# Remediation Record

## Disabled Tests

| Case ID | Suite | Directive | Owner | Reason | Expiry |
|---------|-------|-----------|-------|--------|--------|
| test_foo | pytest | skip | TBD | ISS-123 | {tomorrow} |
"""
    temp_record.write_text(content)
    parser = RemediationRecordParser(temp_record)
    parser.parse()

    assert len(parser.disabled_tests) == 1
    is_valid, errors = parser.disabled_tests[0].is_valid()
    assert not is_valid
    assert any("owner" in err.lower() for err in errors)


def test_parser_missing_expiry(temp_record):
    """Test parsing an entry missing an expiry date."""
    content = """# Remediation Record

## Disabled Tests

| Case ID | Suite | Directive | Owner | Reason | Expiry |
|---------|-------|-----------|-------|--------|--------|
| test_foo | pytest | skip | @alice | ISS-123 | YYYY-MM-DD |
"""
    temp_record.write_text(content)
    parser = RemediationRecordParser(temp_record)
    parser.parse()

    assert len(parser.disabled_tests) == 1
    is_valid, errors = parser.disabled_tests[0].is_valid()
    assert not is_valid
    assert any("expiry" in err.lower() for err in errors)


def test_parser_past_expiry(temp_record):
    """Test parsing an entry with a past expiry date."""
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    content = f"""# Remediation Record

## Disabled Tests

| Case ID | Suite | Directive | Owner | Reason | Expiry |
|---------|-------|-----------|-------|--------|--------|
| test_foo | pytest | skip | @alice | ISS-123 | {yesterday} |
"""
    temp_record.write_text(content)
    parser = RemediationRecordParser(temp_record)
    parser.parse()

    assert len(parser.disabled_tests) == 1
    is_valid, errors = parser.disabled_tests[0].is_valid()
    assert not is_valid
    assert any("past" in err.lower() for err in errors)


def test_parser_missing_reason(temp_record):
    """Test parsing an entry missing a reason."""
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    content = f"""# Remediation Record

## Disabled Tests

| Case ID | Suite | Directive | Owner | Reason | Expiry |
|---------|-------|-----------|-------|--------|--------|
| test_foo | pytest | skip | @alice |  | {tomorrow} |
"""
    temp_record.write_text(content)
    parser = RemediationRecordParser(temp_record)
    parser.parse()

    assert len(parser.disabled_tests) == 1
    is_valid, errors = parser.disabled_tests[0].is_valid()
    assert not is_valid
    assert any("reason" in err.lower() for err in errors)


def test_parser_multiple_sections(temp_record):
    """Test parsing multiple sections."""
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    content = f"""# Remediation Record

## Disabled Tests

| Case ID | Suite | Directive | Owner | Reason | Expiry |
|---------|-------|-----------|-------|--------|--------|
| test_foo | pytest | skip | @alice | ISS-123 | {tomorrow} |

## Coverage Exclusions

| Pattern | Justification | Owner | Expiry |
|---------|--------------|-------|--------|
| alembic/versions/* | Generated migrations | @bob | {tomorrow} |
"""
    temp_record.write_text(content)
    parser = RemediationRecordParser(temp_record)
    parser.parse()

    assert len(parser.disabled_tests) == 1
    assert len(parser.coverage_exclusions) == 1


def test_parser_validate_completeness_pass(temp_record):
    """Test validation of a complete record."""
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    content = f"""# Remediation Record

## Disabled Tests

| Case ID | Suite | Directive | Owner | Reason | Expiry |
|---------|-------|-----------|-------|--------|--------|
| test_foo | pytest | skip | @alice | ISS-123 | {tomorrow} |
"""
    temp_record.write_text(content)
    parser = RemediationRecordParser(temp_record)
    parser.parse()

    is_valid, errors = parser.validate_completeness()
    assert is_valid
    assert len(errors) == 0


def test_parser_validate_completeness_fail(temp_record):
    """Test validation failure with incomplete entries."""
    content = """# Remediation Record

## Disabled Tests

| Case ID | Suite | Directive | Owner | Reason | Expiry |
|---------|-------|-----------|-------|--------|--------|
| test_foo | pytest | skip | TBD | ISS-123 | YYYY-MM-DD |
"""
    temp_record.write_text(content)
    parser = RemediationRecordParser(temp_record)
    parser.parse()

    is_valid, errors = parser.validate_completeness()
    assert not is_valid
    assert len(errors) > 0


def test_parser_placeholder_rows_skipped(temp_record):
    """Test that placeholder rows are skipped."""
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    content = f"""# Remediation Record

## Disabled Tests

| Case ID | Suite | Directive | Owner | Reason | Expiry |
|---------|-------|-----------|-------|--------|--------|
| (placeholder) | pytest | skip | @alice | ISS-123 | {tomorrow} |
| test_foo | pytest | skip | @alice | ISS-123 | {tomorrow} |
"""
    temp_record.write_text(content)
    parser = RemediationRecordParser(temp_record)
    parser.parse()

    assert len(parser.disabled_tests) == 1
    assert parser.disabled_tests[0].case_id == "test_foo"


def test_parser_missing_file(tmp_path):
    """Test parser with missing record file."""
    record_path = tmp_path / "nonexistent.md"
    parser = RemediationRecordParser(record_path)

    with pytest.raises(FileNotFoundError):
        parser.parse()


def test_parser_get_expired_entries(temp_record):
    """Test retrieving expired entries."""
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    content = f"""# Remediation Record

## Disabled Tests

| Case ID | Suite | Directive | Owner | Reason | Expiry |
|---------|-------|-----------|-------|--------|--------|
| test_foo | pytest | skip | @alice | ISS-123 | {yesterday} |
| test_bar | pytest | skip | @alice | ISS-124 | {tomorrow} |
"""
    temp_record.write_text(content)
    parser = RemediationRecordParser(temp_record)
    parser.parse()

    expired = parser.get_expired_entries()
    assert len(expired) == 1
    assert expired[0].case_id == "test_foo"


def test_parser_get_incomplete_entries(temp_record):
    """Test retrieving incomplete entries."""
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    content = f"""# Remediation Record

## Disabled Tests

| Case ID | Suite | Directive | Owner | Reason | Expiry |
|---------|-------|-----------|-------|--------|--------|
| test_foo | pytest | skip | @alice | ISS-123 | {tomorrow} |
| test_bar | pytest | skip | TBD | ISS-124 | {tomorrow} |
"""
    temp_record.write_text(content)
    parser = RemediationRecordParser(temp_record)
    parser.parse()

    incomplete = parser.get_incomplete_entries()
    assert len(incomplete) == 1
    assert incomplete[0].case_id == "test_bar"
