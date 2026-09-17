"""Load ``alembic/versions/0038_cognito_only_users.py`` by path.

``alembic/versions/`` is not a package (filenames start with a digit and are
not valid module identifiers), so a normal import is not available -- same
constraint ``test_cutover_verifier_checks.py::_load_verifier`` documents for
``backend/scripts/verify_cognito_cutover.py``. Loading by spec lets
``_preflight`` be called directly, without going through a real
``alembic upgrade`` (used by ``test_migration_0038_preflight.py`` for its
full-migration tests, but not practical for the "unique constraint bypassed"
scenario, since SQLite refuses to drop an index tied to a live constraint).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_migration_0038() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "0038_cognito_only_users.py"
    )
    spec = importlib.util.spec_from_file_location("_migration_0038", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
