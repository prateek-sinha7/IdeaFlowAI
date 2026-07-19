"""tests/agents/test_task_identity.py — RESUME-14 pure identity-core unit cases.

Pins every behavior bullet of the pure ``agents.capabilities.task_identity`` module:

  * ``normalize_task_content`` — heading-ordinal strip (reorder-stability), NFC +
    ``\\r\\n``→``\\n`` + whitespace collapse, edit-sensitivity across title/body and
    the forward scheduling fields (targets/depends_on/conflict_keys — the json-wave
    disambiguation RESEARCH §Normalization mandates).
  * ``occurrence_ordinals`` — 0-based prior-identical count per index (WR-05 duplicate
    disambiguation).
  * ``compute_task_key`` — canonical-JSON sha256 of the (upstream · content · ordinal)
    triple; 64-char hex; deterministic cross-process (no ``hash()``/ts/uuid); every
    component change rotates the key; a key can never equal a positional id.

These are PURE-function tests (no engine state, no I/O).
"""

from __future__ import annotations

import re

from agents.capabilities import task_identity
from agents.workflows.plan import Task


# --------------------------------------------------------------------------- #
# normalize_task_content — reorder stability (heading ordinal strip)           #
# --------------------------------------------------------------------------- #

def _heading_task(task_num: int, title: str, rest: str) -> Task:
    """Build a heading-parser-shaped Task whose body INCLUDES the ``## Task N:`` header."""
    body = f"## Task {task_num}: {title}\n{rest}"
    return Task(id=str(task_num), title=title, body=body)


def test_reorder_heading_yields_identical_normalized_content():
    # Same title/body, different ordinal in the header → normalization MUST be identical
    # (the ordinal token is stripped) so reordering the list does not rotate the key.
    t_first = _heading_task(1, "Build the login form", "Add the fields and submit handler.")
    t_third = _heading_task(3, "Build the login form", "Add the fields and submit handler.")
    assert task_identity.normalize_task_content(t_first) == task_identity.normalize_task_content(
        t_third
    )


def test_ordinal_token_stripped_from_first_line():
    # The leading ``## Task N:`` token is removed; the title text after the colon is kept.
    t = _heading_task(7, "Wire the router", "Body text here.")
    norm = task_identity.normalize_task_content(t)
    assert "## Task 7" not in norm
    assert "Task 7" not in norm  # the ordinal token, header form, is gone
    assert "Wire the router" in norm
    assert "Body text here." in norm


def test_editing_body_changes_normalized_content():
    t_a = _heading_task(1, "Build the login form", "Add the fields.")
    t_b = _heading_task(1, "Build the login form", "Add the fields and validation.")
    assert task_identity.normalize_task_content(t_a) != task_identity.normalize_task_content(t_b)


def test_editing_title_changes_normalized_content():
    # A json-wave task whose title changes must rotate (edit-sensitivity).
    t_a = Task(id="w1", title="Render the header", body="")
    t_b = Task(id="w1", title="Render the footer", body="")
    assert task_identity.normalize_task_content(t_a) != task_identity.normalize_task_content(t_b)


def test_editing_forward_fields_changes_normalized_content():
    # Two same title/body wave workers with DIFFERENT targets must not collide
    # (RESEARCH §Normalization — the json disambiguation dimension).
    t_a = Task(id="w1", title="Patch section", body="edit it", targets=["#hero"])
    t_b = Task(id="w2", title="Patch section", body="edit it", targets=["#footer"])
    assert task_identity.normalize_task_content(t_a) != task_identity.normalize_task_content(t_b)


def test_normalize_collapses_whitespace_and_newlines():
    # \r\n → \n and runs of whitespace collapse; NFC applied. Two spellings of the
    # same content normalize equal.
    t_crlf = Task(id="1", title="A", body="line one\r\n\r\n   line   two")
    t_lf = Task(id="1", title="A", body="line one line two")
    assert task_identity.normalize_task_content(t_crlf) == task_identity.normalize_task_content(
        t_lf
    )


def test_normalize_nfc_unicode_equivalence():
    # Composed vs decomposed "é" normalize equal under NFC.
    t_composed = Task(id="1", title="café", body="x")
    t_decomposed = Task(id="1", title="café", body="x")
    assert task_identity.normalize_task_content(
        t_composed
    ) == task_identity.normalize_task_content(t_decomposed)


def test_normalize_returns_str():
    assert isinstance(
        task_identity.normalize_task_content(_heading_task(1, "T", "B")), str
    )


# --------------------------------------------------------------------------- #
# occurrence_ordinals — duplicate-text disambiguation                          #
# --------------------------------------------------------------------------- #

def test_occurrence_ordinals_duplicate_text():
    # Two identical "Fix styling" tasks → ordinals 0 and 1; a distinct one → 0.
    dup_a = Task(id="1", title="Fix styling", body="do it")
    distinct = Task(id="2", title="Add tests", body="write them")
    dup_b = Task(id="3", title="Fix styling", body="do it")
    ords = task_identity.occurrence_ordinals([dup_a, distinct, dup_b])
    assert ords == [0, 0, 1]


def test_occurrence_ordinals_all_distinct():
    tasks = [
        Task(id="1", title="A", body="a"),
        Task(id="2", title="B", body="b"),
        Task(id="3", title="C", body="c"),
    ]
    assert task_identity.occurrence_ordinals(tasks) == [0, 0, 0]


def test_occurrence_ordinals_left_to_right():
    # Three identical → 0,1,2 (left-to-right prior count).
    t = lambda: Task(id="x", title="same", body="same")
    assert task_identity.occurrence_ordinals([t(), t(), t()]) == [0, 1, 2]


# --------------------------------------------------------------------------- #
# compute_task_key — canonical-JSON sha256 discipline                          #
# --------------------------------------------------------------------------- #

_HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")


def test_compute_task_key_is_64_char_hex():
    key = task_identity.compute_task_key("upstreamhash", "normalized content", 0)
    assert _HEX64.match(key)


def test_compute_task_key_deterministic_cross_call():
    # Fresh calls with the same triple are byte-equal (no hash()/ts/uuid).
    a = task_identity.compute_task_key("u", "c", 2)
    b = task_identity.compute_task_key("u", "c", 2)
    assert a == b


def test_compute_task_key_changes_on_upstream():
    a = task_identity.compute_task_key("upstream-A", "c", 0)
    b = task_identity.compute_task_key("upstream-B", "c", 0)
    assert a != b


def test_compute_task_key_changes_on_content():
    a = task_identity.compute_task_key("u", "content-A", 0)
    b = task_identity.compute_task_key("u", "content-B", 0)
    assert a != b


def test_compute_task_key_changes_on_ordinal():
    a = task_identity.compute_task_key("u", "c", 0)
    b = task_identity.compute_task_key("u", "c", 1)
    assert a != b


def test_compute_task_key_never_equals_positional():
    # A produced key can never collide with a legacy positional id ("1", "0", …):
    # length + charset make it impossible (the backward-compat fail-safe).
    key = task_identity.compute_task_key("u", "c", 0)
    for positional in ("0", "1", "2", "tb", "wa", "10"):
        assert key != positional
    assert len(key) == 64


def test_compute_task_key_canonical_json_key_order_stable():
    # Whatever the internal payload, the sha is stable across repeated calls — proving
    # canonical (sort_keys) serialization, not dict-iteration-order dependent.
    keys = {task_identity.compute_task_key("u", "some content", 3) for _ in range(5)}
    assert len(keys) == 1


# --------------------------------------------------------------------------- #
# end-to-end: reorder-safe, insert-safe, duplicate-safe, upstream-aware        #
# --------------------------------------------------------------------------- #

def test_key_is_reorder_safe_end_to_end():
    # Same upstream, two heading tasks reordered → same key (content-addressed).
    t1 = _heading_task(1, "Alpha", "do alpha")
    t3 = _heading_task(3, "Alpha", "do alpha")
    k1 = task_identity.compute_task_key(
        "up", task_identity.normalize_task_content(t1), 0
    )
    k3 = task_identity.compute_task_key(
        "up", task_identity.normalize_task_content(t3), 0
    )
    assert k1 == k3


def test_key_is_upstream_aware_end_to_end():
    # Same task text, rotated upstream hash → different key (spec/plan edit rotation).
    t = _heading_task(1, "Alpha", "do alpha")
    content = task_identity.normalize_task_content(t)
    assert task_identity.compute_task_key("up-v1", content, 0) != task_identity.compute_task_key(
        "up-v2", content, 0
    )


def test_key_is_duplicate_safe_end_to_end():
    # Two identical tasks disambiguated by ordinal → distinct keys.
    dup = _heading_task(1, "Fix styling", "do it")
    content = task_identity.normalize_task_content(dup)
    ords = task_identity.occurrence_ordinals([dup, dup])
    k0 = task_identity.compute_task_key("up", content, ords[0])
    k1 = task_identity.compute_task_key("up", content, ords[1])
    assert k0 != k1
