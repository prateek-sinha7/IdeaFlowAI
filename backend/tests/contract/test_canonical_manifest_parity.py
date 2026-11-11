"""Contract: ``canonical.py`` agrees with the shared canonical-form cases file.

``frontend/src/lib/canonicalManifest.cases.json`` is read by both this module
and ``frontend/src/lib/canonicalManifest.test.ts``. Each case holds a
``manifest`` and the ``expected`` canonical dict, ``expected_json`` string and
``expected_hash`` the Python implementation produces. If either implementation
changes behaviour alone, one of the two suites fails (design 3.10.8, G-34).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from app.agents.workflow_builder.canonical import (
    canonical_hash,
    canonical_json,
    canonicalize,
)

_CASES_PATH = (
    Path(__file__).resolve().parents[3]
    / "frontend"
    / "src"
    / "lib"
    / "canonicalManifest.cases.json"
)


def _load_cases() -> list[dict[str, Any]]:
    """Read the shared cases file; a missing file fails collection loudly."""
    with _CASES_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)["cases"]


_CASES = _load_cases()


class TestSharedCasesFile:
    """The cases file itself is well formed."""

    def test_cases_file_has_unique_named_cases_when_loaded(self) -> None:
        names = [case["name"] for case in _CASES]

        assert names
        assert len(names) == len(set(names))

    @pytest.mark.parametrize("case", _CASES, ids=lambda case: case["name"])
    def test_case_is_self_consistent_when_checked_without_the_implementation(
        self, case: dict[str, Any]
    ) -> None:
        assert json.loads(case["expected_json"]) == case["expected"]
        digest = hashlib.sha256(case["expected_json"].encode("utf-8")).hexdigest()
        assert case["expected_hash"] == digest


class TestCanonicalParity:
    """The Python implementation reproduces every shared case."""

    @pytest.mark.parametrize("case", _CASES, ids=lambda case: case["name"])
    def test_canonicalize_returns_expected_when_given_case_manifest(
        self, case: dict[str, Any]
    ) -> None:
        assert canonicalize(case["manifest"]) == case["expected"]

    @pytest.mark.parametrize("case", _CASES, ids=lambda case: case["name"])
    def test_canonical_json_returns_expected_when_given_case_manifest(
        self, case: dict[str, Any]
    ) -> None:
        assert canonical_json(case["manifest"]) == case["expected_json"]

    @pytest.mark.parametrize("case", _CASES, ids=lambda case: case["name"])
    def test_canonical_hash_returns_expected_when_given_case_manifest(
        self, case: dict[str, Any]
    ) -> None:
        assert canonical_hash(case["manifest"]) == case["expected_hash"]
