"""Unit tests for the module-level path resolution in ``app.services.pptx_export``.

The pptxgenjs install location is resolved at module-import time using the
priority documented at the top of ``pptx_export.py``:

  1. ``PPTX_NODE_MODULES_DIR`` env var — explicit override, wins everywhere.
  2. ``/opt/pptx/node_modules`` — production Docker path, used when it exists.
  3. ``<repo>/frontend/node_modules`` — local dev fallback.

These tests verify all three branches without invoking ``generate_pptx_from_code``
(which would require Node + a real pptxgenjs install — out of scope for unit
tests). Because the resolution runs at MODULE IMPORT TIME, each test must
mutate the environment, then ``importlib.reload`` the module, then read the
resulting ``NODE_MODULES_PPTXGENJS`` / ``NODE_MODULES_DIR`` constants.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def pptx_export_module():
    """Yield the freshly-imported ``pptx_export`` module.

    Always restores the module to its pre-test state on teardown so a test
    that leaves a sandbox path in ``NODE_MODULES_DIR`` cannot leak into
    other tests (or into the test harness's own resolution if it ever
    imports ``pptx_export`` itself).
    """
    import app.services.pptx_export as pptx_export

    # Stash originals.
    original_env = os.environ.get("PPTX_NODE_MODULES_DIR")

    yield pptx_export

    # Restore env var and reload module to ground-truth state.
    if original_env is None:
        os.environ.pop("PPTX_NODE_MODULES_DIR", None)
    else:
        os.environ["PPTX_NODE_MODULES_DIR"] = original_env

    importlib.reload(pptx_export)


def _reload_with(monkeypatch, env_value: str | None, prod_exists: bool):
    """Reload ``pptx_export`` under controlled env + filesystem conditions.

    Sets ``PPTX_NODE_MODULES_DIR`` (or unsets it), patches ``Path.exists``
    so the ``/opt/pptx/node_modules`` probe returns ``prod_exists``, and
    returns the reloaded module.

    The ``Path.exists`` patch is targeted: only the ``/opt/pptx/node_modules``
    probe is intercepted, other ``.exists()`` calls (e.g. during the
    ``importlib`` machinery) delegate to the original implementation. That
    way a misconfigured patch doesn't break import.
    """
    if env_value is None:
        monkeypatch.delenv("PPTX_NODE_MODULES_DIR", raising=False)
    else:
        monkeypatch.setenv("PPTX_NODE_MODULES_DIR", env_value)

    original_exists = Path.exists
    prod_path = Path("/opt/pptx/node_modules")

    def _exists(self):
        if self == prod_path:
            return prod_exists
        return original_exists(self)

    import app.services.pptx_export as pptx_export
    with patch.object(Path, "exists", _exists):
        importlib.reload(pptx_export)
    return pptx_export


class TestEnvVarOverride:
    """``PPTX_NODE_MODULES_DIR`` env var wins over both default branches."""

    def test_env_var_set_wins_over_prod(self, monkeypatch, pptx_export_module):
        """When ``PPTX_NODE_MODULES_DIR`` is set, it must take priority even
        if ``/opt/pptx/node_modules`` also exists.
        """
        pptx_export = _reload_with(
            monkeypatch,
            env_value="/custom/path/node_modules",
            prod_exists=True,  # Even with prod present, env var wins.
        )

        assert pptx_export.NODE_MODULES_DIR == Path("/custom/path/node_modules"), (
            f"PPTX_NODE_MODULES_DIR should win — got "
            f"NODE_MODULES_DIR={pptx_export.NODE_MODULES_DIR}"
        )
        assert pptx_export.NODE_MODULES_PPTXGENJS == Path(
            "/custom/path/node_modules/pptxgenjs"
        )

    def test_env_var_set_wins_when_prod_absent(self, monkeypatch, pptx_export_module):
        """When ``PPTX_NODE_MODULES_DIR`` is set AND ``/opt/pptx/node_modules``
        does NOT exist, the env var still wins (does NOT fall through to
        the dev path).
        """
        pptx_export = _reload_with(
            monkeypatch,
            env_value="/another/custom/path",
            prod_exists=False,
        )

        assert pptx_export.NODE_MODULES_DIR == Path("/another/custom/path")
        assert pptx_export.NODE_MODULES_PPTXGENJS == Path(
            "/another/custom/path/pptxgenjs"
        )


class TestProdFallback:
    """``/opt/pptx/node_modules`` is the second-priority fallback (Docker prod)."""

    def test_prod_path_used_when_exists_and_no_env_var(
        self, monkeypatch, pptx_export_module
    ):
        """With ``PPTX_NODE_MODULES_DIR`` unset and ``/opt/pptx/node_modules``
        present (production Docker), the resolver picks the prod path.
        """
        pptx_export = _reload_with(monkeypatch, env_value=None, prod_exists=True)

        assert pptx_export.NODE_MODULES_DIR == Path("/opt/pptx/node_modules")
        assert pptx_export.NODE_MODULES_PPTXGENJS == Path(
            "/opt/pptx/node_modules/pptxgenjs"
        )


class TestDevFallback:
    """When neither env var nor prod path is set, the dev fallback wins."""

    def test_dev_path_used_when_no_env_var_and_no_prod_path(
        self, monkeypatch, pptx_export_module
    ):
        """With no env var and no ``/opt/pptx/node_modules`` (local dev),
        the resolver falls back to ``<repo>/frontend/node_modules``.
        """
        pptx_export = _reload_with(monkeypatch, env_value=None, prod_exists=False)

        # The dev path is computed relative to pptx_export.py's __file__:
        # ``backend/app/services/pptx_export.py`` ->
        # ``backend/app/services/.. /.. /.. /frontend/node_modules``
        # == ``<repo>/frontend/node_modules``.
        # ``__file__`` is typed as ``str | None``; for any real (non-namespace)
        # module loaded from disk it is always a str — narrow the type here so
        # pyright stops complaining about passing None into ``Path``.
        module_file = pptx_export.__file__
        assert module_file is not None, (
            "pptx_export.__file__ is None — the module is not loaded from disk, "
            "the test environment is misconfigured"
        )
        expected_dev = (
            Path(module_file).parent.parent.parent.parent
            / "frontend"
            / "node_modules"
        )
        assert pptx_export.NODE_MODULES_DIR == expected_dev, (
            f"Expected dev fallback {expected_dev}, "
            f"got {pptx_export.NODE_MODULES_DIR}"
        )
        assert pptx_export.NODE_MODULES_PPTXGENJS == expected_dev / "pptxgenjs"
