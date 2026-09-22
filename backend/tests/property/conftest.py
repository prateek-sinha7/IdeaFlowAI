"""Shared fixtures for the property suite.

Property tests use hypothesis to validate invariants over generated inputs.
These tests assert that properties hold across a wide range of random cases
(e.g., "sorting is idempotent", "encoding then decoding returns the original").

Hypothesis is configured in `pyproject.toml` (`[tool.hypothesis]`).
This conftest is a placeholder for any property-specific fixtures.
"""

from __future__ import annotations
