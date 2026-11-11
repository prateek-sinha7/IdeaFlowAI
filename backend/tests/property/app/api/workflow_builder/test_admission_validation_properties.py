"""Property tests for message content and ``canvas_state`` validation.

# Feature: ai-workflow-builder, Property 18: Message and canvas validation

For any string, the server accepts it as message content if and only if it is not
whitespace-only and has at most 12,000 code points. For any JSON value, the server
accepts it as ``canvas_state`` if and only if it is an object with a ``steps`` list
of objects, within the depth and string limits, and at most 524,288 bytes as
compact UTF-8 JSON.

**Validates: Requirements 4.7, 21.11, 21.12, 47.1, 47.11**

Systems under test:

* message content: ``SendMessageRequest`` (check 5 of design 3.1.2);
* ``canvas_state``: ``validate_canvas_state`` (check 11 and design 3.2.3). It
  answers 422 ``canvas_state_invalid`` for a structure failure and 413
  ``canvas_state_too_large`` for a size failure, structure first.

The limits are written out here (12,000, 32, 200,000, 524,288) instead of read
from settings, so the test fails if a default drifts from the spec. The oracles are
independent of the production helpers: a recursive depth and longest-string walk
for the structure, ``json.dumps`` with the compact separators for the size (the
definition in G-23), and a UTF-32 byte count for code points.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from app.api.workflow_builder.admission import validate_canvas_state
from app.api.workflow_builder.schemas import SendMessageRequest

_MAX_CODE_POINTS = 12_000
_MAX_DEPTH = 32
_MAX_STRING = 200_000
_MAX_BYTES = 524_288

_INVALID = (422, "canvas_state_invalid")
_TOO_LARGE = (413, "canvas_state_too_large")

# --- Message content ---------------------------------------------------------------

_WHITESPACE = (" ", "\t", "\n", "\r", "\u00a0", "\u2003", "\u3000")
# Characters whose code-point count differs from their UTF-16 or grapheme count.
_CONTENT_CHARS = ("a", "Z", "7", "é", "\u0301", "\u200b", "😀", "漢", *_WHITESPACE)
_LENGTHS = (0, 1, 2, 11_999, 12_000, 12_001, 12_002)


@st.composite
def _contents(draw: st.DrawFn) -> str:
    """Short mixed strings, plus long runs that straddle the 12,000 limit."""
    if draw(st.booleans()):
        return draw(
            st.text(alphabet=st.sampled_from(_CONTENT_CHARS), max_size=40),
        )
    filler = draw(st.sampled_from(_CONTENT_CHARS))
    length = draw(st.sampled_from(_LENGTHS) | st.integers(min_value=0, max_value=30))
    tail = draw(st.sampled_from(("", "x")))
    body = max(0, length - len(tail))
    return filler * body + tail


def _code_points(text: str) -> int:
    return len(text.encode("utf-32-le")) // 4


def _content_is_acceptable(text: str) -> bool:
    has_visible_char = any(not ch.isspace() for ch in text)
    return has_visible_char and _code_points(text) <= _MAX_CODE_POINTS


def _message_payload(content: str) -> dict[str, Any]:
    return {
        "content": content,
        "model_id": "model-under-test",
        "effort": None,
        "canvas_state": {"steps": []},
        "client_message_id": "abcdefgh12345678",
    }


# Feature: ai-workflow-builder, Property 18: Message and canvas validation
@settings(max_examples=200, deadline=None)
@given(content=_contents())
def test_send_message_request_accepts_content_when_visible_and_within_limit(
    content: str,
) -> None:
    accepted = True
    try:
        parsed = SendMessageRequest.model_validate(_message_payload(content))
    except ValidationError:
        accepted = False

    assert accepted == _content_is_acceptable(content)
    if accepted:
        # Accepted content is stored as sent, never trimmed.
        assert parsed.content == content


# --- canvas_state ------------------------------------------------------------------

_json_scalars = (
    st.none()
    | st.booleans()
    | st.integers(min_value=-(2**53), max_value=2**53)
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text(max_size=20)
)
_json_values = st.recursive(
    _json_scalars,
    lambda children: (
        st.lists(children, max_size=4)
        | st.dictionaries(st.text(max_size=8), children, max_size=4)
    ),
    max_leaves=12,
)
_small_objects = st.dictionaries(st.text(max_size=8), _json_values, max_size=3)

_PAD_CHARS = ("a", "é", "€", "😀")  # 1, 2, 3 and 4 bytes in UTF-8
_STRING_LENGTHS = (_MAX_STRING - 1, _MAX_STRING, _MAX_STRING + 1, _MAX_STRING + 2)


def _outcome(canvas: object) -> tuple[int, str] | None:
    """Run check 11 and return ``(status, code)`` of the refusal, or ``None``."""
    try:
        validate_canvas_state(canvas)
    except HTTPException as exc:
        detail = exc.detail
        assert isinstance(detail, dict)
        return exc.status_code, str(detail["code"])
    return None


def _container_depth(value: object) -> int:
    """Nesting depth: 1 for a flat container, 0 for a scalar."""
    if isinstance(value, dict):
        return 1 + max((_container_depth(v) for v in value.values()), default=0)
    if isinstance(value, list):
        return 1 + max((_container_depth(v) for v in value), default=0)
    return 0


def _longest_string(value: object) -> int:
    """Longest string anywhere, keys included."""
    if isinstance(value, str):
        return len(value)
    if isinstance(value, dict):
        return max(
            (max(len(k), _longest_string(v)) for k, v in value.items()), default=0
        )
    if isinstance(value, list):
        return max((_longest_string(v) for v in value), default=0)
    return 0


def _compact_size(value: object) -> int:
    return len(
        json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )


def _expected_outcome(canvas: object) -> tuple[int, str] | None:
    steps = canvas.get("steps") if isinstance(canvas, dict) else None
    well_formed = isinstance(steps, list) and all(isinstance(s, dict) for s in steps)
    if (
        not well_formed
        or _container_depth(canvas) > _MAX_DEPTH
        or _longest_string(canvas) > _MAX_STRING
    ):
        return _INVALID
    if _compact_size(canvas) > _MAX_BYTES:
        return _TOO_LARGE
    return None


def _nest(depth: int, kind: str) -> object:
    """A chain of ``depth`` containers around one leaf."""
    value: object = "leaf"
    for level in range(depth):
        wrap_in_list = kind == "list" or (kind == "mixed" and level % 2 == 0)
        value = [value] if wrap_in_list else {"n": value}
    return value


def _pad_steps(char: str, total_chars: int) -> list[dict[str, Any]]:
    """Steps holding ``total_chars`` characters, none longer than the string limit."""
    steps: list[dict[str, Any]] = []
    left = total_chars
    while left > 0:
        piece = min(left, _MAX_STRING)
        steps.append({"pad": char * piece})
        left -= piece
    return steps


@st.composite
def _canvases(draw: st.DrawFn) -> object:
    """JSON values: arbitrary ones, near-valid canvases and each kind of violation."""
    arm = draw(
        st.sampled_from(
            ("any", "shape", "valid", "deep", "string", "key", "size", "bad_steps")
        )
    )
    if arm == "any":
        return draw(_json_values)
    steps: list[Any] = draw(st.lists(_small_objects, max_size=3))
    canvas: dict[str, Any] = {"steps": steps}
    if draw(st.booleans()):
        canvas["note"] = draw(_json_values)
    if arm == "shape":
        # Wrong top-level shape: no steps, or steps that is not a list.
        broken = draw(st.sampled_from(("no_steps", "steps_value", "not_object")))
        if broken == "no_steps":
            return {"other": steps}
        if broken == "steps_value":
            return {"steps": draw(_json_scalars | _small_objects)}
        return draw(_json_values.filter(lambda v: not isinstance(v, dict)))
    if arm == "bad_steps":
        bad = draw(_json_scalars | st.lists(_json_scalars, max_size=2))
        steps.insert(draw(st.integers(0, len(steps))), bad)
    elif arm == "deep":
        kind = draw(st.sampled_from(("list", "dict", "mixed")))
        # Top object, steps list and a step are 3 levels, so 29 more reach 32.
        level = draw(st.sampled_from((0, 1, 27, 28, 29, 30, 31)) | st.integers(0, 40))
        steps.append({"nest": _nest(level, kind)})
    elif arm == "string":
        length = draw(st.sampled_from(_STRING_LENGTHS))
        steps.append({"text": "a" * length})
    elif arm == "key":
        length = draw(st.sampled_from(_STRING_LENGTHS))
        steps.append({"k" * length: 1})
    elif arm == "size":
        char = draw(st.sampled_from(_PAD_CHARS))
        near_limit = _MAX_BYTES // len(char.encode("utf-8"))
        chars = draw(
            st.integers(min_value=near_limit - 8, max_value=near_limit + 8)
            | st.integers(min_value=0, max_value=2 * near_limit)
        )
        steps.extend(_pad_steps(char, chars))
    return canvas


# Feature: ai-workflow-builder, Property 18: Message and canvas validation
@settings(max_examples=200, deadline=None)
@given(canvas=_canvases())
def test_validate_canvas_state_matches_oracle_when_value_is_any_json(
    canvas: object,
) -> None:
    assert _outcome(canvas) == _expected_outcome(canvas)


# Feature: ai-workflow-builder, Property 18: Message and canvas validation
@settings(max_examples=100, deadline=None)
@given(
    kind=st.sampled_from(("list", "dict", "mixed")),
    delta=st.integers(min_value=-2, max_value=2),
    siblings=st.lists(_small_objects, max_size=3),
)
def test_validate_canvas_state_switches_at_the_depth_limit_when_nesting_is_exact(
    kind: str, delta: int, siblings: list[dict[str, Any]]
) -> None:
    """The deepest container sits at exactly ``32 + delta`` levels."""
    # Top object, steps list and the step object are 3 levels; the chain adds the rest.
    chain = _MAX_DEPTH + delta - 3
    canvas = {"steps": [*siblings, {"nest": _nest(chain, kind)}]}

    assert _container_depth(canvas) == _MAX_DEPTH + delta
    assert _outcome(canvas) == (None if delta <= 0 else _INVALID)


# Feature: ai-workflow-builder, Property 18: Message and canvas validation
@settings(max_examples=100, deadline=None)
@given(
    char=st.sampled_from(_PAD_CHARS),
    delta=st.integers(min_value=-2, max_value=2),
)
def test_validate_canvas_state_switches_at_the_byte_limit_when_size_is_exact(
    char: str, delta: int
) -> None:
    """A canvas of exactly ``limit + delta`` compact UTF-8 bytes, any character width."""
    target = _MAX_BYTES + delta
    # Leave room for the filler step added below, then fill to the exact byte.
    steps = _pad_steps(char, (target - 64) // len(char.encode("utf-8")))
    canvas: dict[str, Any] = {"steps": [*steps, {"f": ""}]}
    canvas["steps"][-1]["f"] = "a" * (target - _compact_size(canvas))

    assert _compact_size(canvas) == target
    assert _longest_string(canvas) <= _MAX_STRING
    assert _outcome(canvas) == (None if delta <= 0 else _TOO_LARGE)


# Feature: ai-workflow-builder, Property 18: Message and canvas validation
@settings(max_examples=100, deadline=None)
@given(
    steps=st.lists(_small_objects, max_size=3),
    junk=st.sampled_from(("\ud800", "\udfff")),
    where=st.sampled_from(("value", "key")),
)
def test_validate_canvas_state_refuses_as_invalid_when_text_is_not_utf8_encodable(
    steps: list[dict[str, Any]], junk: str, where: str
) -> None:
    """A lone surrogate has no UTF-8 size, so the canvas is unreadable (422)."""
    step = {"a": junk} if where == "value" else {junk: 1}
    canvas = {"steps": [*steps, step]}

    assert _outcome(canvas) == _INVALID
