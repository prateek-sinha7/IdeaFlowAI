"""ISS-974 (sibling of ISS-665 / QA-KB-053) - figma-export renders the live
prototype.html for any member id, because the route takes no ref."""

import inspect

import pytest

from app.api.run_figma_export import figma_export


@pytest.mark.issue("ISS-974")
def test_figma_export_accepts_a_ref():
    assert "ref" in inspect.signature(figma_export).parameters
