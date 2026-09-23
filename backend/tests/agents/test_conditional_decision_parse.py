"""The conditional gate's decision parser — prose-then-JSON recovery.

A decision agent's ``route_decision`` artifact is its WHOLE streamed reply. A
tool-using step reasons in prose and only then commits to its answer, so a strict
``json.loads`` of the whole string fails and the gate reads "no decision": the
route is skipped and the run silently takes ``default_next`` as though the agent
never spoke.

Observed live (run 5475825c): a Coverage Check correctly answered
``{"decision": "incomplete"}`` after ~4KB of analysis naming seven real gaps. The
gate could not parse it, the ``incomplete -> Synthesizer`` loop-back never fired,
and the run carried on building from a synthesis its own checker had rejected.

The recovery is deliberately ONE-SIDED — see
``test_conditional_branch_route_t25.py::test_unparseable_decision_ends_the_run_instead_of_falling_through``,
which pins the opposite shape (``{...}`` followed by chatter) as a
must-fail-closed case. Prose-then-JSON is a model that finished deciding;
JSON-then-prose is one that did not.
"""

from agents.capabilities.gates.conditional import _trailing_json_object


def test_bare_json_object_parses():
    assert _trailing_json_object('{"decision": "complete"}') == {"decision": "complete"}


def test_prose_then_json_is_recovered():
    """The live failure shape: analysis, then the committed decision."""
    reply = (
        "Let me check the synthesis against the reading plan.\n\n"
        "**Key deficiencies:** Location field labels unclear; Form Sets dropdown "
        "list missing; State selection not detailed.\n\n"
        '{"decision": "incomplete", "reason": "dropdown values not enumerated"}'
    )
    assert _trailing_json_object(reply) == {
        "decision": "incomplete",
        "reason": "dropdown values not enumerated",
    }


def test_json_then_prose_still_fails_closed():
    """The deliberately-rejected shape stays rejected (t25's fixture verbatim)."""
    assert _trailing_json_object(
        '{"decision": "english"}Hello! How can I help you today?'
    ) is None


def test_fenced_json_is_recovered():
    reply = 'Here is my verdict:\n\n```json\n{"decision": "gaps"}\n```'
    assert _trailing_json_object(reply) == {"decision": "gaps"}


def test_brace_inside_a_string_does_not_truncate_the_scan():
    reply = 'Analysis.\n{"decision": "ok", "note": "a } brace, and a \\" quote"}'
    assert _trailing_json_object(reply) == {
        "decision": "ok",
        "note": 'a } brace, and a " quote',
    }


def test_nested_object_is_recovered_whole():
    reply = 'Done.\n{"decision": "x", "detail": {"missing": ["a", "b"]}}'
    assert _trailing_json_object(reply) == {
        "decision": "x",
        "detail": {"missing": ["a", "b"]},
    }


def test_no_json_returns_none():
    assert _trailing_json_object("I could not determine a decision.") is None


def test_malformed_trailing_object_returns_none():
    assert _trailing_json_object("Analysis.\n{decision: incomplete}") is None


def test_non_object_json_returns_none():
    """A trailing ARRAY is not a decision payload — the caller wants a mapping."""
    assert _trailing_json_object('Analysis.\n["incomplete"]') is None


def test_non_string_input_returns_none():
    assert _trailing_json_object(None) is None  # type: ignore[arg-type]
