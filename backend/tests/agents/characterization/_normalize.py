"""003 characterization baseline — semantic event-stream snapshot helpers (SAFE-02 / SAFE-03).

This module is the **semantic event-snapshot** half of the characterization safety net
(the deliverable byte-snapshot half lives in ``characterization/__init__.py``, plan 01-01).
It pins the engine's outbound WebSocket event vocabulary at semantic parity BEFORE any
engine refactor: the snapshot fixes event *types*, *order*, *required data keys*, and the
*final result*, while normalizing OUT volatile fields (timestamps / durations / token
counts / generated ids / streamed-chunk text) so the snapshot survives the legitimate text
drift Phase 0C introduces, yet FAILS if the migration drops/reorders an event or loses a
required key (INV-3 / D-05 / D-06).

Ground truth for "what to keep" is the EXISTING outbound contract in
``tests/agents/test_phase3_cutover_verify.py`` — ``_DOCUMENTED_EVENT_TYPES`` (the allowed
event vocabulary) and ``_REQUIRED_DATA_KEYS`` (the load-bearing per-type data keys the
frontend reducer reads). Those dicts are IMPORTED here (not copied) so this module can never
silently diverge from the documented contract (T-02-01 mitigation).

Public surface:
    VOLATILE_SENTINEL            — the named replacement VALUE for volatile-but-required keys.
    _normalize(events)           — return a normalized copy of the event list (D-06).
    assert_seq_contiguous(events)— assert per-run ``seq`` (where present) has no gaps (SAFE-03).
    load_events_golden(name)     — read a committed ``golden/<name>`` as parsed JSON (or None).
    write_events_golden(name, d) — write canonical JSON to ``golden/<name>`` (SNAPSHOT_UPDATE only).
    _DOCUMENTED_EVENT_TYPES      — re-exported from the phase3 contract (single source of truth).
    _REQUIRED_DATA_KEYS          — re-exported from the phase3 contract (single source of truth).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from tests.agents.characterization import GOLDEN_DIR, SNAPSHOT_UPDATE

# Single source of truth: the documented outbound WS contract. Imported, NOT copied,
# so _normalize() can never silently diverge from the contract the engine must honour
# (T-02-01). If the engine adds/removes a documented type or required key, it changes
# THERE and flows through here automatically.
from tests.agents.test_phase3_cutover_verify import (  # noqa: E402
    _DOCUMENTED_EVENT_TYPES,
    _REQUIRED_DATA_KEYS,
)

__all__ = [
    "VOLATILE_SENTINEL",
    "_normalize",
    "assert_seq_contiguous",
    "load_events_golden",
    "write_events_golden",
    "_DOCUMENTED_EVENT_TYPES",
    "_REQUIRED_DATA_KEYS",
]

# ---------------------------------------------------------------------------
# The named sentinel — single-sourced. Used as the replacement VALUE for any
# volatile-but-REQUIRED key (e.g. agent_complete.duration / *_tokens are in
# _REQUIRED_DATA_KEYS but their values drift run-to-run). Replacing the value
# (not deleting the key) keeps the key's PRESENCE assertable while tolerating
# value drift (D-06). Never inline this literal at a call site — reference the
# constant so the sentinel is single-sourced.
# ---------------------------------------------------------------------------
VOLATILE_SENTINEL = "<normalized>"

# Volatile-but-REQUIRED data keys: present in _REQUIRED_DATA_KEYS (so their
# PRESENCE is part of the contract) but their VALUES drift every run. We keep
# the key and replace the value with VOLATILE_SENTINEL.
_VOLATILE_REQUIRED_KEYS = frozenset(
    {
        "duration",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "total_input_tokens",
        "total_output_tokens",
    }
)

# Volatile NON-required data keys to STRIP entirely (drop the key): wall-clock
# timestamps, generated run ids, run-specific cost/duration rollups, the
# env-dependent model id, and the run-specific context echo (which embeds the
# unaliased run text + prior-agent summaries). None of these are in
# _REQUIRED_DATA_KEYS, so dropping them does not weaken the required-keys
# assertion in the test modules.
_VOLATILE_STRIP_KEYS = frozenset(
    {
        "timestamp",
        "pipeline_run_id",
        "run_id",
        "total_duration",
        "estimated_cost_usd",
        "model_id",
        "context_message",
        "context_sources",
    }
)

# Streamed-text chunk granularity: the agent_chunk.chunk value is free-form
# streamed model text (the most drift-prone field of all — exactly what 0C may
# rewrite). _REQUIRED_DATA_KEYS["agent_chunk"] == {"agent_id", "chunk"}, so the
# KEY must remain (presence is contractual) but the VALUE is normalized to the
# sentinel. This "drop per-chunk text granularity, keep the structural chunk
# slot" approach preserves event count/order (so the type sequence stays a real
# structural snapshot) instead of coalescing across events (which would erase
# the per-chunk structure entirely). Documented choice (plan Task 1).
_CHUNK_TEXT_KEY = "chunk"


def _normalize_event(event: dict) -> dict:
    """Return a normalized copy of a single event dict (see module docstring)."""
    out = copy.deepcopy(event)
    data = out.get("data")
    if not isinstance(data, dict):
        return out

    # Drop volatile non-required keys outright.
    for k in list(data.keys()):
        if k in _VOLATILE_STRIP_KEYS:
            del data[k]

    # Replace volatile-but-required values with the named sentinel (key stays).
    for k in list(data.keys()):
        if k in _VOLATILE_REQUIRED_KEYS:
            data[k] = VOLATILE_SENTINEL

    # Streamed-chunk text: keep the structural slot, normalize the drifting value.
    if out.get("type") == "agent_chunk" and _CHUNK_TEXT_KEY in data:
        data[_CHUNK_TEXT_KEY] = VOLATILE_SENTINEL

    return out


def _normalize(events: list[dict]) -> list[dict]:
    """Normalize a captured event stream for the semantic snapshot (D-06).

    KEEPS, per event: the ``type``, the original ordering, and every
    ``_REQUIRED_DATA_KEYS[type]`` data key.
    STRIPS/normalizes the volatile fields: wall-clock ``timestamp``s, run-specific
    durations/costs, ``*_tokens`` / token rollups, generated ids
    (``pipeline_run_id`` / ``run_id``), the env-dependent ``model_id``, the
    run-specific context echo, and the streamed ``agent_chunk`` text — volatile-but-
    required values become ``VOLATILE_SENTINEL`` so their presence is still asserted.

    Returns a NEW list of NEW dicts; the input is never mutated.
    """
    return [_normalize_event(e) for e in events]


def assert_seq_contiguous(events: list[dict]) -> None:
    """Assert each event's per-run ``seq`` (where present) is contiguous (SAFE-03).

    The contract is on the DELTAS, never on absolute values: consecutive ``seq``
    values must increase by exactly 1 with no gaps and no duplicates. This is robust
    to run-id / offset changes (a fresh run may start the counter anywhere) yet still
    catches a dropped or duplicated event.

    The current engine does NOT stamp a ``seq`` on its event dicts (events are
    ordered purely by stream position), so in practice this is a vacuous pass today.
    It is wired in NOW so that if the refactor introduces an explicit ``seq`` (a
    plausible WS-ordering hardening), the contiguity invariant is already enforced —
    and it is asserted from the test modules regardless, documenting the SAFE-03
    contract at the call site.
    """
    seqs = [e["data"]["seq"] for e in events
            if isinstance(e.get("data"), dict) and "seq" in e["data"]]
    # Also tolerate a top-level seq, should the engine stamp it there instead.
    if not seqs:
        seqs = [e["seq"] for e in events if "seq" in e]
    if len(seqs) < 2:
        return  # 0 or 1 seq value → trivially contiguous (nothing to gap).
    deltas = [b - a for a, b in zip(seqs, seqs[1:])]
    bad = [(i, d) for i, d in enumerate(deltas) if d != 1]
    assert not bad, (
        "per-run seq is NOT contiguous (delta != 1) — an event was dropped or "
        f"duplicated. seq run={seqs!r}; offending (index, delta) pairs={bad!r}. "
        "SAFE-03 asserts seq DELTAS == 1, never absolute values."
    )


def _events_golden_path(name: str) -> Path:
    return GOLDEN_DIR / name


def load_events_golden(name: str) -> list[dict] | None:
    """Load the committed ``golden/<name>`` event snapshot as parsed JSON.

    Returns ``None`` when the golden does not exist (so the test can raise a clear
    "run with SNAPSHOT_UPDATE=1 and commit" message rather than a bare KeyError).
    """
    p = _events_golden_path(name)
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def write_events_golden(name: str, data: list[dict]) -> None:
    """Write ``data`` to ``golden/<name>`` as canonical JSON (SNAPSHOT_UPDATE only).

    Canonical form: ``indent=2, sort_keys=True, ensure_ascii=False`` plus a trailing
    newline, so diffs are stable and key order is deterministic. Used ONLY on the
    deliberate-regeneration path; never called on the default assertion path.
    """
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    _events_golden_path(name).write_text(text, encoding="utf-8")
