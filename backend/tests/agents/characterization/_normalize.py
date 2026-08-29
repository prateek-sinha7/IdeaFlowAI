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

ORDERING NOTE (why the snapshot is an order-canonical MULTISET, not a raw sequence):
The engine's prototype/app build loop interleaves ``tool_result`` / ``task_progress`` /
retry ``tool_call`` events from the per-task sub-agent loop in an order that is NOT stable
run-to-run (an async-interleaving artifact — the final deliverable is byte-stable, but the
intermediate tool/progress events swap adjacent positions). A raw positional snapshot would
therefore be FLAKY (it failed across two clean runs of the unchanged engine). So the
event-snapshot is compared as an **order-canonical multiset**: ``_canonical_order()`` sorts
the normalized events by their canonical JSON, pinning the event *vocabulary*, per-type
*required keys*, the full *multiset of events*, and the *final result* — robust to legitimate
interleaving and 0C text drift, yet still failing on a dropped event, a new undocumented
type, or a lost required key. Strict emission ORDER is covered separately by
``assert_seq_contiguous()`` (when the engine stamps ``seq``) and the existing positional
sequence assertions in ``test_phase3_cutover_verify.py`` / the 01-01 suite.

Public surface:
    VOLATILE_SENTINEL            — the named replacement VALUE for volatile-but-required keys.
    _normalize(events)           — return a normalized copy of the event list (D-06).
    _canonical_order(events)     — stable order-canonical sort of normalized events (multiset).
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
    "_canonical_order",
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
        # ── context_message DE-BLINDED (07-06 / PARITY-09 / INV-3) ───────────────
        # context_message was previously stripped here because it "embeds the
        # unaliased run text + prior-agent summaries". For the SCRIPTED characterization
        # fixtures, the user brief is held constant and the OD blocks are deterministic
        # once run_id/timestamps are already stripped — so the context_message is
        # parity-stable and is now PINNED by the golden snapshots, closing the structural
        # blind spot that let the CR-01/02/03 regressions pass silently. A dedicated,
        # normalizer-independent context_message parity assertion also pins the OD block
        # structure/bytes (test_context_providers.test_context_message_parity_*).
        "context_sources",
        # ── Per-run durable-log stamps (05-04 seq sink) ──────────────────────
        # The engine now stamps a monotonic per-run ``seq`` + a uuid ``event_id``
        # on every event at the single execute() emit boundary (PERSIST-03). Both
        # are run-specific and NOT in _REQUIRED_DATA_KEYS, so they are STRIPPED
        # from the canonical-JSON multiset — otherwise every event would carry a
        # unique event_id and a position-dependent seq, perturbing the multiset
        # and breaking 0A semantic-event parity. Emission ORDER (the seq DELTAS==1
        # contract) is still enforced separately by assert_seq_contiguous(), which
        # reads ``seq`` from the RAW (un-normalized) events — so stripping here
        # does not weaken the contiguity check.
        "seq",
        "event_id",
        # ── Additive-but-parity-neutral pipeline_complete keys (ISS-021 / 18-01) ─
        # The engine now emits a DECLARED deliverable shape hint on every
        # pipeline_complete: ``deliverable_mimetype`` (the resolved/declared
        # mimetype) + ``deliverable_filename`` (the declared output name). Both are
        # metadata-only additions (the deliverable BYTES are unchanged) and NOT in
        # _REQUIRED_DATA_KEYS, so they are STRIPPED here — mirroring the
        # model_id/estimated_cost_usd precedent — keeping the 5 characterization
        # event goldens byte-identical (INV-3).
        "deliverable_mimetype",
        "deliverable_filename",
        # ── Additive-but-parity-neutral review_gate_ready keys (REDO-GATE F1b /
        #    SC-001 KAN-101) ───────────────────────────────────────────────────
        # The engine now stamps generic discriminators on every ``review_gate_ready``:
        #   * ``redoable``             — True from the inline call site, False from the
        #     declared path (the FE renders the Redo button iff set).
        #   * ``update_specs_eligible`` / ``artifact_kind`` — the SC-001 name-free
        #     update-specs discriminator, True only from the inline analyze/spec call
        #     site (derived structurally from _artifact_kind_for, never an agent-id
        #     literal); the FE drives the "Update the Specs" affordance off the flag.
        # All three are metadata-only and NOT in _REQUIRED_DATA_KEYS, so they are
        # STRIPPED here — mirroring the deliverable_mimetype/deliverable_filename
        # precedent — keeping the 5 characterization event goldens byte-identical
        # (INV-3).
        "redoable",
        "update_specs_eligible",
        "artifact_kind",
        # ── Additive-but-parity-neutral review_gate_ready keys (ISS-052 / FIX-220) ──
        # The engine also stamps the per-FIRING discriminator on every
        # ``review_gate_ready``: ``revision_cycle`` (which spec-revision cycle this gate
        # belongs to, 0 = none) + ``revision_in_flight`` (is the gate INSIDE that pass).
        # Without them the analyze gate opened inside a revision pass and the one
        # re-opened after it returns are identical on the wire — same gate_key, same
        # output bytes. Metadata-only and NOT in _REQUIRED_DATA_KEYS, so they are
        # STRIPPED here, mirroring the redoable / update_specs_eligible precedent, to
        # keep the characterization event goldens byte-identical (INV-3).
        "revision_cycle",
        "revision_in_flight",
        # ── Additive-but-parity-neutral prompt-cache keys (ISS-032 / FIX-036) ────
        # The runner now surfaces the Bedrock prompt-cache split
        # (input_token_details.cache_read/cache_creation) → the engine threads it
        # onto agent_complete (``cache_read_tokens``/``cache_write_tokens``) and the
        # run totals onto pipeline_complete (``total_cache_read_tokens``/
        # ``total_cache_write_tokens``). Under the SCRIPTED characterization model
        # there is no input_token_details, so every key is 0 — but they are
        # additive metadata NOT in _REQUIRED_DATA_KEYS, so they are STRIPPED here
        # (mirroring the deliverable_mimetype/redoable precedent) to keep the 5
        # characterization event goldens byte-identical (INV-3).
        "cache_read_tokens",
        "cache_write_tokens",
        "total_cache_read_tokens",
        "total_cache_write_tokens",
        # ── Additive-but-parity-neutral image_count key (image-input Wave 1 / edw) ──
        # The engine stamps ``image_count`` on ``agent_input`` ONLY when image blocks
        # ride the dispatch (>0). No workflow opts in this wave, so it is NEVER emitted
        # — this strip is belt-and-suspenders (metadata-only, NOT in _REQUIRED_DATA_KEYS)
        # so the 5 characterization event goldens stay byte-identical (INV-3).
        "image_count",
        # ── Additive-but-parity-neutral chat-lane volatile subkeys (POR D-01, Phase 29+) ──
        # The run-chat lane (chat_message/chat_reply/stream_attached) lands in
        # Phase 29+ and carries two run-specific/client-generated subkeys:
        #   * ``message_id``           — the FE-generated idempotency key on a
        #     ``chat_message`` turn (client-random → never parity-stable).
        #   * ``replayed_through_seq`` — the run-specific replay cursor on the
        #     ``stream_attached`` SSE handshake (depends on how far the run got).
        # No golden emits any chat event (the scripted harness has no chat lane),
        # so this strip is belt-and-suspenders — mirroring the image_count
        # precedent above: metadata-only, NOT in _REQUIRED_DATA_KEYS, so it keeps
        # the 5 characterization event goldens byte-identical (INV-3). The
        # ``stream_attached.live`` boolean is deterministic (not run-specific) and
        # the ``chat_reply`` card discriminators are stable, so neither is stripped.
        "message_id",
        "replayed_through_seq",
        # ── Additive-but-parity-neutral pipeline_start key (KAN-120 / ISS-068) ───
        # The engine stamps ``resume_offset`` on ``pipeline_start`` — how many leading
        # agents a resumed run skips — so the FE can mark them "done" immediately
        # instead of waiting for the durable SSE replay. It is 0 on every non-resumed
        # run, and the characterization harness never resumes, so it is 0 in all 5
        # goldens; but a key whose VALUE is 0 is still a NEW KEY, and the snapshot
        # compares whole canonical-JSON dicts — which is why all 5 event goldens went
        # red when it landed. ``_REQUIRED_DATA_KEYS`` has no ``pipeline_start`` entry
        # at all, so this is metadata-only and stripping it cannot weaken the
        # required-keys assertion; resume-offset behaviour is pinned directly by
        # ``test_restart_resume.py``, so no oracle power is lost. Stripping (rather
        # than regenerating) keeps all 5 golden files byte-untouched — maximum INV-3
        # conservation — mirroring the deliverable_mimetype / redoable / cache_* /
        # image_count precedents above.
        "resume_offset",
        # ── Additive-but-parity-neutral pipeline_complete key (ISS-034) ──────────
        # The engine also prices the run as-if-UNCACHED (``estimated_cost_full_usd``
        # — the same token base with the cache tiers switched off) so Analytics can
        # report the SIGNED effect of prompt caching. It is a run-specific cost
        # rollup exactly like its ``estimated_cost_usd`` sibling six lines above, and
        # is NOT in _REQUIRED_DATA_KEYS, so it is STRIPPED here. Stripping (rather
        # than regenerating) keeps all 5 event goldens byte-untouched — mirroring the
        # deliverable_mimetype / redoable / cache_* / resume_offset precedents.
        "estimated_cost_full_usd",
        # ── Additive-but-parity-neutral pipeline_start key (ISS-276) ─────────────
        # The engine now stamps the run's real ``created_at`` on ``pipeline_start``
        # so a durable REST replay of that frame is distinguishable from a live one
        # (the FE reducer previously fell back to "now" and dated a day-old run to
        # page-load time). It is a per-run wall-clock stamp — the most volatile kind
        # of value there is — and ``_REQUIRED_DATA_KEYS`` has no ``pipeline_start``
        # entry at all, so it is metadata-only and STRIPPED here, exactly like its
        # ``resume_offset`` sibling above, keeping all 5 event goldens byte-untouched
        # (INV-3).
        "created_at",
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


def _canonical_order(events: list[dict]) -> list[dict]:
    """Return the normalized events in a stable, order-canonical order (a multiset).

    The engine's build loop interleaves ``tool_result`` / ``task_progress`` / retry
    ``tool_call`` events nondeterministically across runs (see the module ORDERING
    NOTE), so a raw positional snapshot is flaky. Sorting by each event's canonical
    JSON yields a deterministic order that pins the event *multiset* (types +
    required keys + values + final result) while tolerating legitimate interleaving.
    Input must already be ``_normalize()``-d so volatile values do not perturb the sort.
    """
    return sorted(
        events,
        key=lambda e: json.dumps(e, sort_keys=True, ensure_ascii=False),
    )


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
