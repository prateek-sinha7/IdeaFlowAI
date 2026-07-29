"""Fixtures specific to the prototype/revision eval phase.

Phase-local (not suite-wide, unlike evals/hybrid/conftest.py's runs_root/
_hermetic_db) because they're tied to THIS phase's fixtures/ folder — a
future workflow/<domain>/<variant>/ phase defines its own FIXTURES_DIR here,
not a shared one.
"""

from __future__ import annotations

from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"
