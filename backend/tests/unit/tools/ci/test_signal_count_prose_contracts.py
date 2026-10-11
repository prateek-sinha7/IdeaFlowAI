"""
F-20: prose must not restate the mandatory-signal count.

The registry is the only authority for how many signals are mandatory and
``ci_gate aggregate`` prints the derived number into the ``ci-evidence`` log.
Any literal count in a comment or document goes stale the next time a signal is
added, so the files below must name no such number.

The scan is deliberately pattern-based rather than a list of known stale
numbers: it catches a NEW literal, whatever its value.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[5]

#: Prose that describes the mandatory set and so must not state its size.
SCANNED_GLOBS = (
    ".github/workflows/*.yml",
    ".github/CI_STATUS.md",
    ".github/ROLLBACK_PROCEDURE.md",
    "README.md",
    "backend/tools/ci/signal_registry.py",
    "backend/tools/ci/AGGREGATE_TRUTH_IMPLEMENTATION.md",
)

_STALE_COUNT_PATTERNS = (
    re.compile(
        r"\b(?:all|other|remaining)\s+\d+\s+(?:mandatory\s+|CI\s+)*(?:signals?|blocking)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b\d+\s+(?:mandatory\s+)+signals?\b", re.IGNORECASE),
    re.compile(
        r"\bmandatory\s+(?:CI\s+)?signals?\s*(?:[:=(]|total\b)\s*\d+", re.IGNORECASE
    ),
)


def _normalise(text: str) -> str:
    """Drop comment markers and collapse whitespace so wrapped prose matches."""
    without_markers = re.sub(r"^\s*(?:#|//)+", " ", text, flags=re.MULTILINE)
    return re.sub(r"\s+", " ", without_markers)


def _stale_count_phrases(text: str) -> list[str]:
    """Every phrase in ``text`` that restates a mandatory-signal count."""
    flat = _normalise(text)
    return [
        m.group(0) for pattern in _STALE_COUNT_PATTERNS for m in pattern.finditer(flat)
    ]


def _scanned_files() -> list[Path]:
    found: list[Path] = []
    for pattern in SCANNED_GLOBS:
        found.extend(sorted(REPO_ROOT.glob(pattern)))
    return found


def test_prose_has_no_mandatory_count_literal_when_registry_is_the_authority() -> None:
    """No scanned file states how many signals are mandatory."""
    files = _scanned_files()
    assert files, "the prose scan matched no files"
    offenders = {
        str(path.relative_to(REPO_ROOT)): phrases
        for path in files
        if (phrases := _stale_count_phrases(path.read_text(encoding="utf-8")))
    }
    assert not offenders, (
        "signal counts are derived from the registry (ci_gate aggregate prints "
        f"them); remove the literal from: {offenders}"
    )


@pytest.mark.parametrize(
    "text",
    [
        "which succeeds only if all 32 signals",
        "while keeping the other 31 blocking",
        "succeeds only when all 33 mandatory signals succeeded",
        "NOT one of the 33 mandatory signals",
        "# wrapped: all\n# 33 mandatory\n# signals succeeded",
        "**Total: mandatory signals: 28**",
    ],
)
def test_count_pattern_flags_known_stale_phrases_when_text_matches(text: str) -> None:
    """Self-test: the stale phrasings the audit found are detected."""
    assert _stale_count_phrases(text)


@pytest.mark.parametrize(
    "text",
    [
        "Owns 8 signals",
        "succeeds only if every mandatory signal succeeded",
        "mandatory signals: {count}",
        "mandatory signals: {len(required)}",
    ],
)
def test_count_pattern_accepts_prose_when_no_literal_count_is_stated(text: str) -> None:
    """Self-test: per-job counts and derived counts are not flagged."""
    assert not _stale_count_phrases(text)
