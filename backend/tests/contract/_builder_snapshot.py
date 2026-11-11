"""Snapshot helper for the AI Workflow Builder contract tests.

The builder contract tests compare live output (the builder slice of the OpenAPI
document, the JSON schema of ``BuilderEvent``) with JSON files committed under
``tests/fixtures/workflow_builder/``. This module reads and, on request, rewrites
those files.

Update path (this docstring is the reference; the fixture folder holds JSON only):

1. A contract test fails with a diff because the contract changed on purpose.
2. Run the one test file with ``BUILDER_CONTRACT_SNAPSHOT_UPDATE=1`` set, for
   example from ``backend/``::

       $env:BUILDER_CONTRACT_SNAPSHOT_UPDATE = "1"
       uv run pytest tests/contract/test_workflow_builder_openapi_contract.py
       Remove-Item Env:BUILDER_CONTRACT_SNAPSHOT_UPDATE

3. The affected test writes the file and is reported as *skipped* with the
   reason, so the run never looks green. Review ``git diff`` on the fixture,
   unset the variable, and run the suite again; it must pass.

The flag is unset by default, must be exactly ``1``, is refused when ``CI`` is
set, and is not ``SNAPSHOT_UPDATE``. That name belongs to the INV-3
characterization goldens, so regenerating one set never touches the other.
"""

from __future__ import annotations

import difflib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

import pytest

__all__ = [
    "FIXTURE_DIR",
    "UPDATE_ENV_VAR",
    "assert_matches_snapshot",
    "render_snapshot",
    "update_requested",
]

#: Environment variable that lets a run rewrite builder contract snapshots.
UPDATE_ENV_VAR: Final = "BUILDER_CONTRACT_SNAPSHOT_UPDATE"

#: Folder that holds the committed builder snapshots (static JSON only).
FIXTURE_DIR: Final = (
    Path(__file__).resolve().parents[1] / "fixtures" / "workflow_builder"
)

_MAX_DIFF_LINES: Final = 80


def render_snapshot(data: Any) -> str:
    """Return the canonical text of a snapshot: sorted keys, 2 spaces, final newline."""
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def update_requested(environ: Mapping[str, str] | None = None) -> bool:
    """Return True only when ``BUILDER_CONTRACT_SNAPSHOT_UPDATE`` is exactly ``1``."""
    env = os.environ if environ is None else environ
    return env.get(UPDATE_ENV_VAR) == "1"


def _update_hint(name: str) -> str:
    return (
        f"If the change is intended, rerun this test file with {UPDATE_ENV_VAR}=1, "
        f"review the git diff of {name}, unset the variable and rerun."
    )


def assert_matches_snapshot(
    name: str,
    actual: Any,
    *,
    environ: Mapping[str, str] | None = None,
    directory: Path = FIXTURE_DIR,
) -> None:
    """Compare ``actual`` with the committed snapshot ``directory / name``.

    Args:
        name: File name of the snapshot, for example ``builder_event_schema.json``.
        actual: JSON-serialisable value produced by the code under test.
        environ: Environment to read the update flag from; defaults to ``os.environ``.
        directory: Snapshot folder; tests of this helper pass a temporary one.

    Raises:
        pytest.fail.Exception: The snapshot is missing or differs and no update was
            requested, or an update was requested while ``CI`` is set.
        pytest.skip.Exception: The snapshot was rewritten (reported, never silent).
    """
    env = os.environ if environ is None else environ
    # Round-trip so tuples, enums and key order cannot make equal data look different.
    normalised = json.loads(render_snapshot(actual))
    expected_text = render_snapshot(normalised)
    path = directory / name

    committed: Any = None
    if path.is_file():
        committed = json.loads(path.read_text(encoding="utf-8"))
        if committed == normalised:
            return

    if update_requested(env):
        if env.get("CI"):
            pytest.fail(
                f"{UPDATE_ENV_VAR}=1 is refused when CI is set; regenerate {name} locally.",
                pytrace=False,
            )
        directory.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(expected_text)
        pytest.skip(
            f"{name} was REWRITTEN because {UPDATE_ENV_VAR}=1. Review the git diff, "
            "unset the variable and rerun; this run does not verify the contract."
        )

    if not path.is_file():
        pytest.fail(
            f"Snapshot {name} is missing at {path}. {_update_hint(name)}",
            pytrace=False,
        )
    diff = list(
        difflib.unified_diff(
            render_snapshot(committed).splitlines(),
            expected_text.splitlines(),
            fromfile=f"committed/{name}",
            tofile=f"current/{name}",
            lineterm="",
        )
    )
    shown = "\n".join(diff[:_MAX_DIFF_LINES])
    more = len(diff) - _MAX_DIFF_LINES
    suffix = f"\n... {more} more diff lines" if more > 0 else ""
    pytest.fail(
        f"Contract snapshot {name} no longer matches.\n{shown}{suffix}\n{_update_hint(name)}",
        pytrace=False,
    )
