"""003 characterization baseline — deliverable byte-snapshot helpers (SAFE-01).

This package holds the **deliverable byte-snapshots** (golden files) that lock the
current per-pipeline deliverable output BYTE-FOR-BYTE *before* any engine refactor
touches ``engine.py`` / ``factory.py`` (INV-3 / plan §24 — characterization tests
first). It is the byte-identity half of SAFE-01; the semantic event-stream snapshot
half lands in plan 01-02 (``_normalize.py`` + ``*.events.json``).

Golden files live under ``golden/<pipeline>.<ext>``. They are generated DELIBERATELY
by running the characterization tests once with ``SNAPSHOT_UPDATE=1`` set, then
committed so the default (no-env) run is a real byte-for-byte assertion against the
committed bytes (D-07). A regenerate must be an intentional, reviewed act — never an
accident — so the default run NEVER writes goldens.

Public helpers:
    GOLDEN_DIR                 — Path to the committed golden directory.
    SNAPSHOT_UPDATE            — True iff the SNAPSHOT_UPDATE env var is set (regenerate).
    golden_path(name)          — Path for a named golden file.
    read_golden_bytes(name)    — bytes | None (None when the golden does not exist).
    write_golden_bytes(name,d) — write bytes to golden/<name> (used only under SNAPSHOT_UPDATE).
"""

from __future__ import annotations

import os
from pathlib import Path

# The committed golden directory (deliverable byte-snapshots).
GOLDEN_DIR: Path = Path(__file__).parent / "golden"

# Regenerate-goldens flag (D-07). Setting SNAPSHOT_UPDATE=1 makes the tests WRITE
# the golden files (after the non-empty guard) instead of asserting against them.
# Unset (the CI / default path) → the tests assert byte-for-byte.
SNAPSHOT_UPDATE: bool = bool(os.environ.get("SNAPSHOT_UPDATE"))


def golden_path(name: str) -> Path:
    """Return the Path to the named golden file (does not require it to exist)."""
    return GOLDEN_DIR / name


def read_golden_bytes(name: str) -> bytes | None:
    """Return the bytes of golden/<name>, or None when the file does not exist."""
    p = golden_path(name)
    if not p.is_file():
        return None
    return p.read_bytes()


def write_golden_bytes(name: str, data: bytes) -> None:
    """Write ``data`` to golden/<name>, creating the golden directory if needed.

    Used ONLY under SNAPSHOT_UPDATE (deliberate regeneration). Never called on the
    default assertion path.
    """
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    golden_path(name).write_bytes(data)


def extract_final_output(events: list[dict]) -> str:
    """Pull the deterministic deliverable off the ``pipeline_complete`` event.

    Per PATTERNS S4, the byte-stable deliverable is captured in the engine's
    ``pipeline_complete`` event ``final_output`` (a documented, required key —
    see ``_REQUIRED_DATA_KEYS["pipeline_complete"]``). ``_drive`` runs against a
    FRESH temp ``RUNS_ROOT`` per call, so reading the event stream is more stable
    than reading the on-disk sandbox. Raises if the run never completed.
    """
    completes = [e for e in events if e.get("type") == "pipeline_complete"]
    assert completes, "run produced no pipeline_complete event (drove nothing / errored)"
    final_output = (completes[-1].get("data") or {}).get("final_output")
    assert isinstance(final_output, str), (
        f"pipeline_complete.final_output must be a str; got {type(final_output)!r}"
    )
    return final_output


def assert_deliverable_snapshot(name: str, deliverable: bytes) -> None:
    """Lock ``deliverable`` against the committed golden ``name`` BYTE-FOR-BYTE.

    Anti-false-green contract (T-01-01 / T-01-02):
      * ALWAYS assert the captured deliverable is NON-EMPTY first — a no-op /
        empty drive cannot pass vacuously, on BOTH the update and assert paths.
      * Under SNAPSHOT_UPDATE: write the golden (deliberate regeneration).
      * Otherwise: assert the golden exists, is non-empty, and equals the
        captured bytes exactly.
    """
    assert len(deliverable) > 0, (
        f"{name}: captured deliverable is EMPTY — a zero-byte snapshot would pass "
        f"vacuously and give false confidence before the refactor (SAFE-01)."
    )

    if SNAPSHOT_UPDATE:
        write_golden_bytes(name, deliverable)
        return

    golden = read_golden_bytes(name)
    assert golden is not None, (
        f"{name}: golden file missing — run the suite once with SNAPSHOT_UPDATE=1 "
        f"and COMMIT golden/{name} so the default run is a real byte assertion (D-07)."
    )
    assert len(golden) > 0, f"{name}: committed golden is zero-byte (must be non-empty)."
    assert deliverable == golden, (
        f"{name}: deliverable bytes diverged from the committed golden "
        f"(len now={len(deliverable)}, golden={len(golden)}). This is the SAFE-01 "
        f"byte-identity tripwire: if the change is intentional (e.g. the sanctioned "
        f"[0C] byte change), regenerate with SNAPSHOT_UPDATE=1 and review the diff."
    )
