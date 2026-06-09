"""Tests for the single canonical severity mapping (VALID-03 / D-04 / 08-01 Task 4).

``agents/capabilities/validators/severity.py::map_severity`` is THE single source
mapping the internal P0–P3 severities to the UI-facing CRITICAL/HIGH/MEDIUM/LOW
labels (VALID-03 single-source rule). The 08-02 validation gate imports it (so it
must be import-clean, with NO ``@register``/``discover()`` side-effect, BEFORE
08-04's validators run); 08-04's validators import — never recreate — it.
"""

from __future__ import annotations

import sys

import pytest

from agents.capabilities.validators.severity import map_severity


@pytest.mark.parametrize(
    "internal,label",
    [
        ("P0", "CRITICAL"),
        ("P1", "HIGH"),
        ("P2", "MEDIUM"),
        ("P3", "LOW"),
    ],
)
def test_map_severity_p0_p3(internal: str, label: str) -> None:
    assert map_severity(internal) == label


def test_unknown_severity_is_deterministic() -> None:
    # One deterministic behavior for an unknown internal severity (no second
    # mapping anywhere). An unknown input raises ValueError naming the bad value.
    with pytest.raises(ValueError) as exc:
        map_severity("P9")
    assert "P9" in str(exc.value)


def test_import_has_no_registry_side_effect() -> None:
    # Importing severity must NOT trigger discovery / impl binding — the 08-02 gate
    # imports it before 08-04 runs. Assert the registry has not been discovered
    # merely by importing this module (a fresh interpreter would have _DISCOVERED
    # False until something calls discover(); we assert importing severity alone
    # does not import the impl modules).
    # severity.py imports ONLY stdlib — it does not import the registry at all.
    import agents.capabilities.validators.severity as sev_mod

    src = sev_mod.__file__
    assert src is not None
    # The module must not have pulled the registry decorator into its namespace.
    assert not hasattr(sev_mod, "register")
    # And importing it must not have loaded any capability impl strategy module
    # as a side effect of THIS module (it imports stdlib only).
    assert "agents.capabilities.registry" not in _imports_of(sev_mod)


def _imports_of(mod) -> set[str]:
    """Best-effort: the module-level names that are themselves imported modules."""
    names = set()
    for name in dir(mod):
        obj = getattr(mod, name, None)
        modname = getattr(obj, "__name__", None)
        if isinstance(obj, type(sys)) and modname:
            names.add(modname)
    return names
