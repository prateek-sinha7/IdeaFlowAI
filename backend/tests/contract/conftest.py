"""Shared fixtures for the contract suite.

Contract tests validate API schemas, consumer contracts, and public API shapes.
These tests are fast (ms), require no real infrastructure, and focus on
stability and compatibility.

No dedicated fixtures needed beyond what unit/e2e provide. Tests in this suite
can use:
- `client` fixture (from tests/unit/api/**/routers/conftest.py) for schema validation
- `http_client` fixture (from tests/e2e/conftest.py) for full-stack contract checks
- Standard pytest fixtures (tmp_path, monkeypatch, etc.)

This conftest is a placeholder for suite-specific fixtures that may be added later
(e.g., a fixture that returns an OpenAPI snapshot for comparison).
"""

from __future__ import annotations
