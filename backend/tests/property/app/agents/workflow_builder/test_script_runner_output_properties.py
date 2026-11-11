"""Property tests for the script runner's output handling.

Covers design Property 3 (task 12.7, Req 36.1, 36.5, 36.7, 36.9, 36.11, 47.14):

* the tool result stays within the output cap, equals the uncut output when the
  capture kept all of it, and otherwise holds the head, a cut note and the tail;
* the validator verdict (last line, or the ``--json`` report) survives the cut;
* a ``--compiler`` call exits 0 if and only if the validator and the dry run both
  passed.

Every call goes through :func:`run_command` with a :class:`FakeProcessFactory`
and a :class:`FakeGate`, so no subprocess starts. The sizes (60,000 head, 15,000
tail, 80,000 cap) and the cut-note format are restated here and are not read
from the module under test. Each example makes its own temp directory.
"""

from __future__ import annotations

import asyncio
import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from app.agents.workflow_builder.events import CheckResultEvent
from app.agents.workflow_builder.ports import GateIssue, GateResult
from app.agents.workflow_builder.sandbox import BuilderSandbox
from app.agents.workflow_builder.script_policy import BUILDER_SKILL_ID
from app.agents.workflow_builder.script_runner import (
    ScriptContext,
    ScriptResult,
    run_command,
)
from tests.fakes.builder_gate import FakeGate, accepted_result
from tests.fakes.builder_turn import FakeTurnPort
from tests.fakes.process_factory import FakeProcessFactory, ProcessScript

# Restated from Req 36.5, 36.7 and 47.14.
_HEAD = 60_000
_TAIL = 15_000
_CAP = 80_000
_SCRIPTS = f"/skills/{BUILDER_SKILL_ID}/scripts"
_CATALOG = f"python {_SCRIPTS}/catalog_lookup.py overview"
_VALIDATE = f"python {_SCRIPTS}/validate_manifest.py /workflows/a.workflow.json"

_CUT_NOTE = re.compile(r"\n\[\.\.\. (\d+) characters cut \.\.\.\]\n")

# Output text never holds '[' (so it cannot imitate the cut note), NUL or
# surrogates, and no line of it starts with VALID or INVALID unless a test adds it.
_ALPHABET = st.characters(blacklist_categories=("Cs",), blacklist_characters="[\x00VI")
_PIECE = st.text(alphabet=_ALPHABET, min_size=1, max_size=30)
_SMALL = st.text(alphabet=_ALPHABET, max_size=300)
# Big outputs are built by repetition, so hypothesis draws little data for them.
_BIG = st.lists(
    st.tuples(_PIECE, st.integers(min_value=1, max_value=1_500)),
    min_size=1,
    max_size=8,
).map(lambda parts: "".join(piece * count for piece, count in parts))
_OUTPUTS = st.one_of(_SMALL, _BIG)
_CHUNK_SIZES = st.lists(
    st.integers(min_value=1, max_value=70_000), min_size=1, max_size=6
)


@dataclass(frozen=True)
class _Call:
    """What one :func:`_call` produced."""

    result: ScriptResult
    turn: FakeTurnPort
    gate: FakeGate

    def checks(self) -> list[tuple[str, str, int, int]]:
        """Return the published ``check_result`` events as plain tuples."""
        return [
            (e.source, e.verdict, e.errors, e.warnings)
            for e in self.turn.events
            if isinstance(e, CheckResultEvent)
        ]


def _chunks(text: str, sizes: list[int]) -> tuple[bytes, ...]:
    """Split ``text`` (as UTF-8) into pieces of the given sizes, cycling them.

    A piece boundary can fall inside a multi-byte character.
    """
    data = text.encode("utf-8")
    pieces: list[bytes] = []
    start = 0
    index = 0
    while start < len(data):
        size = sizes[index % len(sizes)]
        pieces.append(data[start : start + size])
        start += size
        index += 1
    return tuple(pieces)


def _call(
    command: str,
    script: ProcessScript,
    *,
    gate: FakeGate | None = None,
    cap: int | None = None,
) -> _Call:
    """Run ``command`` against a fake process in a fresh temp directory."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        sandbox = BuilderSandbox("out-user", "out-session", root=root / "builder")
        sandbox.ensure()
        skill_root = root / "skill"
        (skill_root / "scripts").mkdir(parents=True)
        used_gate = gate if gate is not None else FakeGate()
        turn = FakeTurnPort()
        ctx = ScriptContext(
            sandbox=sandbox,
            skill_root=skill_root,
            gate=used_gate,
            turn=turn,
            semaphore=asyncio.Semaphore(1),
            spawn=FakeProcessFactory(script),
            call_id="call-1",
            timeout_seconds=30.0,
            output_cap_chars=cap,
        )
        result = asyncio.run(run_command(command, ctx))
    return _Call(result, turn, used_gate)


def _header(command: str, exit_code: int) -> str:
    """Return the result header of Req 36.9."""
    return f"$ {command}\nexit code: {exit_code}\n"


def _assert_output_shape(
    text: str, header: str, output: str, cap: int, *, tail_expected: bool
) -> None:
    """Check the header, the cap and the head/note/tail layout of one result."""
    assert text.startswith(header)
    assert len(text) <= cap
    body = text[len(header) :]
    note = _CUT_NOTE.search(body)
    if note is None:
        assert body == output
        return
    head_part = body[: note.start()]
    tail_part = body[note.end() :]
    assert output.startswith(head_part)
    assert output.endswith(tail_part)
    assert int(note.group(1)) == len(output) - len(head_part) - len(tail_part)
    assert len(output) > len(head_part) + len(tail_part)
    if tail_expected:
        assert tail_part


# Feature: ai-workflow-builder, Property 3: The output cap keeps the verdict, and the exit code reflects both checks
@settings(max_examples=100, deadline=None)
@given(output=_OUTPUTS, sizes=_CHUNK_SIZES)
def test_run_command_keeps_head_and_tail_within_the_default_cap_when_output_is_any_size(
    output: str, sizes: list[int]
) -> None:
    script = ProcessScript(chunks=_chunks(output, sizes))

    text = _call(_CATALOG, script).result.text

    header = _header(_CATALOG, 0)
    assert len(text) <= _CAP
    _assert_output_shape(text, header, output, _CAP, tail_expected=True)
    if len(output) <= _HEAD + _TAIL:
        assert text == header + output
    else:
        body = text[len(header) :]
        note = _CUT_NOTE.search(body)
        assert note is not None
        assert note.start() == _HEAD
        assert len(body) - note.end() == _TAIL


# Feature: ai-workflow-builder, Property 3: The output cap keeps the verdict, and the exit code reflects both checks
@settings(max_examples=100, deadline=None)
@given(
    output=_OUTPUTS,
    sizes=_CHUNK_SIZES,
    cap=st.integers(min_value=400, max_value=100_000),
)
def test_run_command_never_exceeds_the_cap_when_the_cap_is_any_size(
    output: str, sizes: list[int], cap: int
) -> None:
    script = ProcessScript(chunks=_chunks(output, sizes))

    text = _call(_CATALOG, script, cap=cap).result.text

    header = _header(_CATALOG, 0)
    # The tail is empty only when the whole output sits in the 60,000 head.
    _assert_output_shape(text, header, output, cap, tail_expected=len(output) > _HEAD)
    if len(output) <= _HEAD + _TAIL and len(header) + len(output) <= cap:
        assert text == header + output


# Feature: ai-workflow-builder, Property 3: The output cap keeps the verdict, and the exit code reflects both checks
@settings(max_examples=100, deadline=None)
@given(
    cap=st.integers(min_value=400, max_value=3_000),
    delta=st.integers(min_value=-3, max_value=3),
    piece=_PIECE,
)
def test_run_command_returns_output_uncut_exactly_when_it_fits_the_cap(
    cap: int, delta: int, piece: str
) -> None:
    header = _header(_CATALOG, 0)
    length = cap - len(header) + delta
    output = (piece * (length // len(piece) + 1))[:length]

    text = _call(
        _CATALOG, ProcessScript(chunks=(output.encode(),)), cap=cap
    ).result.text

    assert len(text) <= cap
    if delta <= 0:
        assert text == header + output
    else:
        assert _CUT_NOTE.search(text) is not None


def _verdict_line(valid: bool, errors: int, warnings: int) -> str:
    """Render the validator's last line the way ``validate_manifest.py`` does."""
    word = "VALID" if valid else "INVALID"
    return f"{word}: {errors} error(s), {warnings} warning(s)"


_COUNT = st.integers(min_value=0, max_value=99_999)
# Noise lines: plain text, or a decoy verdict line that an earlier-line match
# would pick up by mistake. Each line is repeated so the output can pass the cap.
_NOISE_LINE = st.one_of(
    _PIECE,
    st.builds(_verdict_line, st.booleans(), _COUNT, _COUNT),
)
_NOISE = st.lists(
    st.tuples(_NOISE_LINE, st.integers(min_value=1, max_value=2_500)),
    max_size=6,
).map(lambda rows: "".join((line + "\n") * count for line, count in rows))


# Feature: ai-workflow-builder, Property 3: The output cap keeps the verdict, and the exit code reflects both checks
@settings(max_examples=100, deadline=None)
@given(
    noise=_NOISE,
    valid=st.booleans(),
    errors=_COUNT,
    warnings=_COUNT,
    sizes=_CHUNK_SIZES,
)
def test_run_command_parses_the_verdict_line_when_the_output_was_cut(
    noise: str, valid: bool, errors: int, warnings: int, sizes: list[int]
) -> None:
    last_line = _verdict_line(valid, errors, warnings)
    output = noise + last_line + "\n"
    script = ProcessScript(exit_code=0 if valid else 1, chunks=_chunks(output, sizes))

    call = _call(_VALIDATE, script)

    expected = ("valid" if valid else "invalid", errors, warnings)
    assert (call.result.verdict, call.result.errors, call.result.warnings) == expected
    assert call.checks() == [("skill_validator", *expected)]
    assert call.result.status == "ok"
    assert len(call.result.text) <= _CAP
    assert call.result.text.endswith(last_line + "\n")


_FINDING = st.builds(
    lambda level, message: {"level": level, "message": message},
    st.sampled_from(("error", "warning", "info")),
    _PIECE,
)
_FINDINGS = st.lists(_FINDING, max_size=40).flatmap(
    lambda rows: st.integers(min_value=1, max_value=120).map(lambda n: rows * n)
)


# Feature: ai-workflow-builder, Property 3: The output cap keeps the verdict, and the exit code reflects both checks
@settings(max_examples=100, deadline=None)
@given(
    findings=_FINDINGS,
    valid=st.booleans(),
    errors=_COUNT,
    warnings=_COUNT,
    sizes=_CHUNK_SIZES,
)
def test_run_command_parses_the_json_report_when_the_output_was_cut(
    findings: list[dict[str, str]],
    valid: bool,
    errors: int,
    warnings: int,
    sizes: list[int],
) -> None:
    report = {
        "trust": "user",
        "cap": "user",
        "valid": valid,
        "counts": {"errors": errors, "warnings": warnings, "info": 0},
        "steps": [],
        "findings": findings,
    }
    output = json.dumps(report, indent=2) + "\n"
    script = ProcessScript(exit_code=0 if valid else 1, chunks=_chunks(output, sizes))

    call = _call(f"{_VALIDATE} --json", script)

    expected = ("valid" if valid else "invalid", errors, warnings)
    assert (call.result.verdict, call.result.errors, call.result.warnings) == expected
    assert call.checks() == [("skill_validator", *expected)]
    assert len(call.result.text) <= _CAP


def _dry_run_result(kind: str, issues: int, trust: str) -> GateResult | Exception:
    """Build the scripted dry-run verdict for ``kind``."""
    if kind == "accepted":
        return accepted_result("db" if trust == "db" else "user")
    if kind == "rejected":
        found = tuple(
            GateIssue("save_check", f"steps[{i}]", f"problem {i}")
            for i in range(issues)
        )
        return GateResult(False, None, found)
    return RuntimeError("the gate failed")


# Feature: ai-workflow-builder, Property 3: The output cap keeps the verdict, and the exit code reflects both checks
@settings(max_examples=100, deadline=None)
@given(
    validator_exit=st.one_of(st.sampled_from((0, 1, 2, 127)), st.integers(0, 255)),
    validator_says_valid=st.booleans(),
    dry_kind=st.sampled_from(("accepted", "rejected", "raises")),
    issues=st.integers(min_value=1, max_value=30),
    trust=st.sampled_from(("user", "db")),
)
def test_run_command_exits_zero_exactly_when_validator_and_dry_run_pass_when_compiler_is_given(
    validator_exit: int,
    validator_says_valid: bool,
    dry_kind: str,
    issues: int,
    trust: str,
) -> None:
    line = _verdict_line(validator_says_valid, 0 if validator_says_valid else 1, 0)
    script = ProcessScript.with_text(line + "\n", exit_code=validator_exit)
    gate = FakeGate(dry_run=_dry_run_result(dry_kind, issues, trust))

    call = _call(f"{_VALIDATE} --compiler out --trust {trust}", script, gate=gate)

    dry_ran = validator_exit in (0, 1)
    both_passed = validator_exit == 0 and dry_kind == "accepted"
    assert (call.result.exit_code == 0) is both_passed
    assert len(call.gate.dry_run_calls) == (1 if dry_ran else 0)
    assert call.result.text.startswith(
        _header(
            f"{_VALIDATE} --compiler out --trust {trust}", call.result.exit_code or 0
        )
    )
    assert ("PASS: the platform accepts this manifest." in call.result.text) is (
        dry_ran and dry_kind == "accepted"
    )
    # A validator exit of 0 or 1 is `ok` whatever the dry run says; other codes are errors.
    assert call.result.status == ("ok" if call.result.exit_code in (0, 1) else "error")
    if not dry_ran:
        assert call.result.exit_code == validator_exit
