"""Offline unit tests for ClarifyEngine._parse_llm_json_array (KAN-82 / FIX-024).

The tolerant LLM-JSON parser is the PRIMARY, blocking proof of Part B. Haiku 4.5
returns slightly-malformed JSON every round; this parser must extract + repair the
five common malformation classes and return None on genuine garbage (so the gate
falls back to the static library and never crashes — INV-3).

Pure offline: no model, no network. json.loads-only (no eval/exec) — T-v1f-01.
"""

from __future__ import annotations

from agents.execution_engine.clarify_engine import _parse_llm_json_array


def test_clean_json_array_unchanged():
    raw = '[{"question_text": "What layout?", "answer_type": "single_choice"}]'
    result = _parse_llm_json_array(raw)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["question_text"] == "What layout?"


def test_markdown_fenced_array_stripped():
    raw = (
        "```json\n"
        '[{"question_text": "Which audience?", "answer_type": "single_choice"}]\n'
        "```"
    )
    result = _parse_llm_json_array(raw)
    assert isinstance(result, list)
    assert result[0]["question_text"] == "Which audience?"


def test_bare_fenced_array_stripped():
    raw = (
        "```\n"
        '[{"question_text": "Which style?", "answer_type": "single_choice"}]\n'
        "```"
    )
    result = _parse_llm_json_array(raw)
    assert isinstance(result, list)
    assert result[0]["question_text"] == "Which style?"


def test_trailing_comma_repaired():
    raw = (
        '[\n'
        '  {"question_text": "Q1", "answer_type": "short_text",},\n'
        '  {"question_text": "Q2", "answer_type": "short_text"},\n'
        ']'
    )
    result = _parse_llm_json_array(raw)
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[1]["question_text"] == "Q2"


def test_missing_comma_between_objects_repaired():
    raw = (
        '[\n'
        '  {"question_text": "Q1", "answer_type": "short_text"}\n'
        '  {"question_text": "Q2", "answer_type": "short_text"}\n'
        ']'
    )
    result = _parse_llm_json_array(raw)
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["question_text"] == "Q1"
    assert result[1]["question_text"] == "Q2"


def test_smart_quotes_normalized():
    # Curly/smart quotes around keys and values.
    raw = "[{“question_text”: “What scope?”, “answer_type”: “short_text”}]"
    result = _parse_llm_json_array(raw)
    assert isinstance(result, list)
    assert result[0]["question_text"] == "What scope?"


def test_truncated_array_returns_complete_objects():
    # Opener + two complete objects, then cut off mid-third object (no closing ]).
    raw = (
        '[\n'
        '  {"question_text": "Q1", "answer_type": "short_text"},\n'
        '  {"question_text": "Q2", "answer_type": "short_text"},\n'
        '  {"question_text": "Q3", "answer_ty'
    )
    result = _parse_llm_json_array(raw)
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["question_text"] == "Q1"
    assert result[1]["question_text"] == "Q2"


def test_prose_wrapped_array_extracted():
    raw = (
        "Sure! Here are the clarification questions:\n"
        '[{"question_text": "Which pages?", "answer_type": "multi_select"}]\n'
        "Let me know if you need more."
    )
    result = _parse_llm_json_array(raw)
    assert isinstance(result, list)
    assert result[0]["question_text"] == "Which pages?"


def test_genuine_garbage_returns_none():
    assert _parse_llm_json_array("I cannot help with that request.") is None
    assert _parse_llm_json_array("") is None
    assert _parse_llm_json_array("   ") is None


def test_non_string_returns_none():
    assert _parse_llm_json_array(None) is None  # type: ignore[arg-type]


def test_empty_array_returns_none():
    # A syntactically valid but empty array yields no questions -> None (fallback).
    assert _parse_llm_json_array("[]") is None
