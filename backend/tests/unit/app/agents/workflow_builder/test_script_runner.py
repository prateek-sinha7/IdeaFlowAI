"""Unit tests for ``app.agents.workflow_builder.script_runner``.

Covers the runner's result handling: status mapping, the tool result header, the
output cap, refusal texts, the ``--compiler`` intercept, start failures, stops
and the ``run_skill_script`` tool. No real subprocess starts: every call goes
through :func:`run_command` with a ``FakeProcessFactory``, a ``FakeGate`` and a
``FakeTurnPort``, and the sandbox lives under ``tmp_path``.

Requirements: 35.12 (refusals carry the reason), 36.1 (``--compiler`` exit code),
36.9 (merged output, result header), 49.2.
"""

from __future__ import annotations

import asyncio
import dataclasses
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import ToolMessage

from app.agents.workflow_builder.events import CheckResultEvent
from app.agents.workflow_builder.ports import GateIssue, GateResult
from app.agents.workflow_builder.sandbox import BuilderSandbox, SandboxPathError
from app.agents.workflow_builder.script_policy import BUILDER_SKILL_ID, PathSlotKind
from app.agents.workflow_builder.script_runner import (
    Refusal,
    Roots,
    ScriptContext,
    ScriptResult,
    build_script_tool,
    map_path,
    run_command,
)
from app.agents.workflow_builder.stages import DryRunStarted
from tests.fakes.builder_gate import FakeGate, accepted_result, rejected_result
from tests.fakes.builder_turn import FakeTurnPort
from tests.fakes.process_factory import FakeProcessFactory, ProcessScript

_SCRIPTS = f"/skills/{BUILDER_SKILL_ID}/scripts"
_MANIFEST = "/workflows/a.workflow.json"
VALIDATE = f"python {_SCRIPTS}/validate_manifest.py {_MANIFEST}"
CATALOG = f"python {_SCRIPTS}/catalog_lookup.py overview --trust user"
SELFTEST = f"python {_SCRIPTS}/selftest.py"
CALL_ID = "call-1"

VALID_LINE = "VALID: 0 error(s), 0 warning(s)\n"
INVALID_LINE = "INVALID: 2 error(s), 1 warning(s)\n"


@dataclass
class Harness:
    """One runner context with its fakes and what the runner reported."""

    sandbox: BuilderSandbox
    skill_root: Path
    gate: FakeGate
    turn: FakeTurnPort
    factory: FakeProcessFactory
    finished: list[tuple[str, ScriptResult]] = field(
        default_factory=lambda: list[tuple[str, ScriptResult]]()
    )
    metrics: list[tuple[str, float, int | None, bool]] = field(
        default_factory=lambda: list[tuple[str, float, int | None, bool]]()
    )

    def ctx(self, **overrides: Any) -> ScriptContext:
        """Return a context over the fakes, with ``overrides`` applied."""
        base = ScriptContext(
            sandbox=self.sandbox,
            skill_root=self.skill_root,
            gate=self.gate,
            turn=self.turn,
            semaphore=asyncio.Semaphore(2),
            spawn=self.factory,
            call_id=CALL_ID,
            timeout_seconds=5.0,
            on_finished=lambda call_id, result: self.finished.append((call_id, result)),
            on_metric=lambda *args: self.metrics.append(args),
        )
        return dataclasses.replace(base, **overrides)

    def checks(self) -> list[tuple[str, str, int, int]]:
        """Return the published ``check_result`` events as plain tuples."""
        return [
            (e.source, e.verdict, e.errors, e.warnings)
            for e in self.turn.events
            if isinstance(e, CheckResultEvent)
        ]

    @property
    def temp_dir(self) -> Path:
        """The call's temp folder, which must not exist after the call."""
        return self.sandbox.path / ".tmp" / CALL_ID


def _harness(
    tmp_path: Path,
    *scripts: ProcessScript,
    gate: FakeGate | None = None,
) -> Harness:
    sandbox = BuilderSandbox("user-1", "session-1", root=tmp_path / "builder")
    sandbox.ensure()
    skill_root = tmp_path / "skill"
    (skill_root / "scripts").mkdir(parents=True)
    return Harness(
        sandbox=sandbox,
        skill_root=skill_root,
        gate=gate if gate is not None else FakeGate(),
        turn=FakeTurnPort(),
        factory=FakeProcessFactory(*scripts),
    )


def _text(text: str, *, exit_code: int = 0) -> ProcessScript:
    return ProcessScript.with_text(text, exit_code=exit_code)


# --- status mapping --------------------------------------------------------------


@pytest.mark.parametrize(
    ("command", "exit_code", "status"),
    [
        (VALIDATE, 0, "ok"),
        (VALIDATE, 1, "ok"),
        (VALIDATE, 2, "error"),
        (VALIDATE, 127, "error"),
        (CATALOG, 0, "ok"),
        (CATALOG, 1, "error"),
        (CATALOG, 2, "error"),
        (SELFTEST, 0, "ok"),
        (SELFTEST, 1, "error"),
    ],
)
async def test_run_command_maps_the_exit_code_to_a_status_when_the_script_ends(
    tmp_path: Path, command: str, exit_code: int, status: str
) -> None:
    h = _harness(tmp_path, _text("output\n", exit_code=exit_code))

    result = await run_command(command, h.ctx())

    assert result.status == status
    assert result.exit_code == exit_code
    assert f"exit code: {exit_code}\n" in result.text


async def test_run_command_returns_timed_out_and_kills_the_process_when_the_script_hangs(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path, ProcessScript(chunks=(b"partial\n",), hang=True))

    result = await run_command(CATALOG, h.ctx(timeout_seconds=0.05))

    process = h.factory.processes[0]
    assert result.status == "timed_out"
    assert result.exit_code is None
    assert process.kill_count >= 1
    assert process.wait_count >= 1
    assert result.text.startswith(f"$ {CATALOG}\nexit code: none\npartial\n")
    assert result.text.endswith("[timed out after 0.05 s; the script was stopped]")
    assert not h.temp_dir.exists()


async def test_run_command_returns_error_without_spawning_when_the_turn_is_stopping(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path)
    h.turn.stop("cancelled")

    result = await run_command(CATALOG, h.ctx())

    assert result.status == "error"
    assert result.summary == "stopped with the turn"
    assert result.exit_code is None
    assert h.factory.starts == []


async def test_run_command_returns_timed_out_when_the_turn_cap_stopped_the_call(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path)
    h.turn.stop("time")

    result = await run_command(CATALOG, h.ctx(stopped_by_turn_cap=lambda: True))

    assert result.status == "timed_out"
    assert result.summary == "stopped with the turn"
    assert result.text.endswith("The script did not finish because the turn stopped.")


async def test_run_command_kills_the_process_and_reraises_when_the_call_is_cancelled(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path, ProcessScript(hang=True))
    task = asyncio.create_task(run_command(CATALOG, h.ctx(timeout_seconds=30.0)))
    for _ in range(200):
        if h.factory.processes:
            break
        await asyncio.sleep(0.001)
    assert h.factory.processes

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    process = h.factory.processes[0]
    assert process.kill_count == 1
    assert process.wait_count >= 1
    assert not h.temp_dir.exists()
    assert [(cid, r.status) for cid, r in h.finished] == [(CALL_ID, "error")]


# --- tool result header and output -----------------------------------------------


async def test_run_command_starts_the_result_with_command_and_exit_code_when_script_prints(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path, _text("hello\n"))

    result = await run_command(CATALOG, h.ctx())

    assert result.text == f"$ {CATALOG}\nexit code: 0\nhello\n"
    assert result.script == "catalog_lookup.py"
    assert result.summary == "catalog_lookup.py overview exited with code 0."


async def test_run_command_merges_output_in_arrival_order_when_script_prints_in_pieces(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path, ProcessScript(chunks=(b"out 1\n", b"err 2\n", b"out 3\n")))

    result = await run_command(CATALOG, h.ctx())

    assert result.text.endswith("exit code: 0\nout 1\nerr 2\nout 3\n")


async def test_run_command_decodes_invalid_utf8_as_replacement_when_script_prints_bytes(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path, ProcessScript(chunks=(b"ok \xff\xfe end",)))

    result = await run_command(CATALOG, h.ctx())

    assert result.text.endswith("ok \ufffd\ufffd end")


async def test_run_command_clips_the_echoed_command_when_it_is_very_long(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path)
    long_command = f"python {_SCRIPTS}/catalog_lookup.py search " + "word " * 1000

    result = await run_command(long_command, h.ctx())

    first_line = result.text.split("\n", 1)[0]
    assert first_line.endswith("...")
    assert len(first_line) == len("$ ") + 2000 + len("...")


async def test_run_command_keeps_the_result_within_the_cap_and_marks_the_cut_when_output_is_huge(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path, _text("x" * 5000))

    result = await run_command(CATALOG, h.ctx(output_cap_chars=300))

    assert len(result.text) <= 300
    assert result.text.startswith(f"$ {CATALOG}\nexit code: 0\n")
    assert "characters cut" in result.text


async def test_run_command_keeps_the_verdict_line_when_output_is_cut(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path, _text("A" * 100_000 + "\n" + INVALID_LINE, exit_code=1))

    result = await run_command(VALIDATE, h.ctx(output_cap_chars=80_000))

    assert len(result.text) <= 80_000
    assert "characters cut" in result.text
    assert result.text.endswith(INVALID_LINE)
    assert result.verdict == "invalid"
    assert (result.errors, result.warnings) == (2, 1)


async def test_run_command_keeps_the_last_line_when_output_fits_the_head_but_not_the_cap(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path, _text("A" * 5000 + "\n" + INVALID_LINE, exit_code=1))

    result = await run_command(VALIDATE, h.ctx(output_cap_chars=1000))

    assert len(result.text) <= 1000
    assert "characters cut" in result.text
    assert result.text.endswith(INVALID_LINE)


async def test_run_command_removes_the_call_temp_folder_when_the_script_ends(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path, _text("done\n"))

    await run_command(CATALOG, h.ctx())

    assert not h.temp_dir.exists()


async def test_run_command_starts_the_interpreter_in_the_sandbox_when_the_command_is_allowed(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path)

    await run_command(CATALOG, h.ctx())

    start = h.factory.starts[0]
    script = h.skill_root.resolve() / "scripts" / "catalog_lookup.py"
    assert start.argv == (
        sys.executable, "-B", "-s", "-X", "utf8", str(script),
        "overview", "--trust", "user",
    )  # fmt: skip
    assert start.cwd == h.sandbox.path
    assert start.env["TMP"] == str(h.temp_dir)


# --- validator verdict -----------------------------------------------------------


async def test_run_command_publishes_the_validator_verdict_when_validator_prints_a_verdict(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path, _text("noise\n" + INVALID_LINE, exit_code=1))

    result = await run_command(VALIDATE, h.ctx())

    assert h.checks() == [("skill_validator", "invalid", 2, 1)]
    assert (result.verdict, result.errors, result.warnings) == ("invalid", 2, 1)


async def test_run_command_publishes_an_unknown_verdict_when_validator_prints_no_verdict_line(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path, _text("Traceback: boom\n", exit_code=2))

    result = await run_command(VALIDATE, h.ctx())

    assert h.checks() == [("skill_validator", "unknown", 0, 0)]
    assert result.verdict == "unknown"


async def test_run_command_reads_the_json_report_when_json_was_requested(
    tmp_path: Path,
) -> None:
    report = '{\n  "valid": false,\n  "counts": {"errors": 3, "warnings": 4}\n}\n'
    h = _harness(tmp_path, _text(report, exit_code=1))

    await run_command(f"{VALIDATE} --json", h.ctx())

    assert h.checks() == [("skill_validator", "invalid", 3, 4)]


async def test_run_command_publishes_no_check_when_the_script_is_not_the_validator(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path, _text(VALID_LINE))

    result = await run_command(CATALOG, h.ctx())

    assert h.checks() == []
    assert result.verdict is None


# --- refusals --------------------------------------------------------------------

_CATALOG_REFUSED = "always reads the skill's own catalog and schema"
_CI_CATALOG = "The catalog is refreshed in CI. Use catalog_lookup.py to read it."


@pytest.mark.parametrize(
    ("call", "expected"),
    [
        ("catalog_lookup.py overview --catalog x.md", _CATALOG_REFUSED),
        ("catalog_lookup.py overview --schema=x.json", _CATALOG_REFUSED),
        (f"validate_manifest.py {_MANIFEST} --catalog x.md", _CATALOG_REFUSED),
        (f"validate_manifest.py {_MANIFEST} --schema x.json", _CATALOG_REFUSED),
        ("selftest.py --compiler out", "CI runs the compiler self-test"),
        ("selftest.py --catalog x.md", _CATALOG_REFUSED),
        ("refresh_catalog.py --check --source x", _CI_CATALOG),
        ("refresh_catalog.py --check --api x", _CI_CATALOG),
        ("refresh_catalog.py --check --render", _CI_CATALOG),
        ("refresh_catalog.py --check --token t", _CI_CATALOG),
        ("refresh_catalog.py --check --out-json x", _CI_CATALOG),
        ("refresh_catalog.py --check --out-md x", _CI_CATALOG),
        ("refresh_catalog.py --check --schema x", _CI_CATALOG),
        ("refresh_catalog.py --check --no-schema", _CI_CATALOG),
        ("refresh_catalog.py", _CI_CATALOG),
        ("schema_sync.py", "The schema never changes at run time. Use --check."),
        ("schema_sync.py --check --catalog x", "The schema never changes at run time."),
        ("schema_sync.py --check --schema x", "The schema never changes at run time."),
        (f"export_manifest.py {_MANIFEST}", "exactly one output option"),
        (
            f"export_manifest.py {_MANIFEST} --yaml /exports/a.yaml --run-payload /exports/b",
            "exactly one output option",
        ),
        (
            f"export_manifest.py {_MANIFEST} --yaml /workflows/a.yaml",
            "Write exports under /exports/. The canvas saves and runs the workflow.",
        ),
        (
            f"export_manifest.py {_MANIFEST} --yaml /exports/../workflows/a.yaml",
            "Write exports under /exports/.",
        ),
        (
            f"validate_manifest.py /skills/{BUILDER_SKILL_ID}/SKILL.md",
            "skill's own files cannot be used as input",
        ),
        ("validate_manifest.py ../../etc/passwd", "outside the allowed folder"),
        ("validate_manifest.py --bogus x", "Option '--bogus' is not allowed"),
        ("catalog_lookup.py", "needs a subcommand"),
        ("catalog_lookup.py nonsense", "Unknown subcommand 'nonsense'"),
        ("catalog_lookup.py agent", "takes exactly 1 argument(s)"),
    ],
)
async def test_run_command_returns_the_policy_reason_when_the_call_is_refused(
    tmp_path: Path, call: str, expected: str
) -> None:
    h = _harness(tmp_path)

    result = await run_command(f"python {_SCRIPTS}/{call}", h.ctx())

    assert result.status == "refused"
    assert result.script == "refused"
    assert result.exit_code is None
    assert expected in result.text
    assert h.factory.starts == []


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("", "The command is empty."),
        ("python -c 'print(1)'", "Interpreter options"),
        ("python -m http.server", "Interpreter options"),
        (f"{CATALOG} && echo hi", "Shell syntax (&&) is not supported."),
        (f"{CATALOG} | cat", "Shell syntax (|) is not supported."),
        (f"{CATALOG} > out.txt", "Shell syntax (>) is not supported."),
        (f"{CATALOG}; ls", "Shell syntax (;) is not supported."),
        (f"{CATALOG} $(id)", "Shell syntax ($() is not supported."),
        (f"{CATALOG}\nls", "A newline ends the command."),
        ("ls -la", "Start the command with python"),
        ("python /etc/passwd", "Only these scripts can run:"),
        (f"python {_SCRIPTS}/evil.py", "Only these scripts can run:"),
        (f"python {_SCRIPTS}/../scripts/../../x.py", "Only these scripts can run:"),
    ],
)
async def test_run_command_refuses_without_spawning_when_the_command_is_not_a_skill_script(
    tmp_path: Path, command: str, expected: str
) -> None:
    h = _harness(tmp_path)

    result = await run_command(command, h.ctx())

    assert result.status == "refused"
    assert expected in result.text
    assert h.factory.starts == []


async def test_run_command_notifies_the_callback_and_metric_once_when_the_call_is_refused(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path)

    await run_command("python -c 'x'", h.ctx())

    assert [(cid, r.status) for cid, r in h.finished] == [(CALL_ID, "refused")]
    assert len(h.metrics) == 1
    name, seconds, exit_code, refused = h.metrics[0]
    assert (name, exit_code, refused) == ("refused", None, True)
    assert seconds >= 0


async def test_run_command_allows_a_help_call_when_required_options_are_missing(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path, _text("usage: refresh_catalog.py\n"))

    result = await run_command(f"python {_SCRIPTS}/refresh_catalog.py --help", h.ctx())

    assert result.status == "ok"
    assert h.factory.starts[0].argv[-1] == "--help"


async def test_run_command_notifies_the_metric_with_the_exit_code_when_a_script_ends(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path, _text("x\n", exit_code=1))

    await run_command(CATALOG, h.ctx())

    name, seconds, exit_code, refused = h.metrics[0]
    assert (name, exit_code, refused) == ("catalog_lookup.py", 1, False)
    assert seconds >= 0


# --- the --compiler intercept ----------------------------------------------------


async def test_run_command_runs_the_validator_without_compiler_when_compiler_is_given(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path, _text(VALID_LINE))

    await run_command(f"{VALIDATE} --compiler outdir --trust user", h.ctx())

    argv = h.factory.starts[0].argv
    manifest = h.sandbox.path / "workflows" / "a.workflow.json"
    assert "--compiler" not in argv
    assert "outdir" not in argv
    assert argv[-3:] == (str(manifest), "--trust", "user")


async def test_run_command_appends_the_dry_run_and_exits_zero_when_both_checks_pass(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path, _text(VALID_LINE), gate=FakeGate(dry_run=accepted_result()))

    result = await run_command(f"{VALIDATE} --compiler outdir", h.ctx())

    assert result.exit_code == 0
    assert result.status == "ok"
    assert result.text.startswith(f"$ {VALIDATE} --compiler outdir\nexit code: 0\n")
    assert result.text.endswith(
        VALID_LINE
        + "\n--- platform check (dry run, trust user) ---\n"
        + "PASS: the platform accepts this manifest."
    )
    assert h.checks() == [
        ("skill_validator", "valid", 0, 0),
        ("platform_dry_run", "valid", 0, 0),
    ]
    assert any(isinstance(s, DryRunStarted) for s in h.turn.signals)
    call = h.gate.dry_run_calls[0]
    assert call.manifest_path == h.sandbox.path / "workflows" / "a.workflow.json"
    assert call.requested_trust == "user"


async def test_run_command_signals_the_dry_run_once_when_compiler_is_given(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path, _text(VALID_LINE))

    await run_command(f"{VALIDATE} --compiler outdir", h.ctx())

    assert [type(s) for s in h.turn.signals] == [DryRunStarted]
    assert len(h.gate.dry_run_calls) == 1


async def test_run_command_exits_one_and_lists_issues_when_the_dry_run_rejects(
    tmp_path: Path,
) -> None:
    rejected = rejected_result(
        "model not allowed", rule="step_model", path="steps[0].model"
    )
    h = _harness(tmp_path, _text(VALID_LINE), gate=FakeGate(dry_run=rejected))

    result = await run_command(f"{VALIDATE} --compiler outdir", h.ctx())

    assert result.exit_code == 1
    assert result.status == "ok"
    assert "exit code: 1\n" in result.text
    assert result.text.endswith(
        "FAIL: 1 issue(s)\n1. [step_model] steps[0].model: model not allowed"
    )
    assert h.checks() == [
        ("skill_validator", "valid", 0, 0),
        ("platform_dry_run", "invalid", 1, 0),
    ]


async def test_run_command_lists_twenty_issues_and_counts_the_rest_when_the_dry_run_has_many(
    tmp_path: Path,
) -> None:
    issues = tuple(GateIssue("save_check", "", f"problem {n}") for n in range(25))
    gate = FakeGate(dry_run=GateResult(False, None, issues))
    h = _harness(tmp_path, _text(VALID_LINE), gate=gate)

    result = await run_command(f"{VALIDATE} --compiler outdir", h.ctx())

    assert "FAIL: 25 issue(s)" in result.text
    assert "20. [save_check]: problem 19" in result.text
    assert "21. " not in result.text
    assert result.text.endswith("... and 5 more issue(s)")


async def test_run_command_exits_one_and_still_runs_the_dry_run_when_the_validator_reports_invalid(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path, _text(INVALID_LINE, exit_code=1))

    result = await run_command(f"{VALIDATE} --compiler outdir", h.ctx())

    assert result.exit_code == 1
    assert result.status == "ok"
    assert len(h.gate.dry_run_calls) == 1
    assert h.checks() == [
        ("skill_validator", "invalid", 2, 1),
        ("platform_dry_run", "valid", 0, 0),
    ]


async def test_run_command_skips_the_dry_run_when_the_validator_crashes(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path, _text("Traceback\n", exit_code=2))

    result = await run_command(f"{VALIDATE} --compiler outdir", h.ctx())

    assert result.status == "error"
    assert result.exit_code == 2
    assert h.gate.dry_run_calls == []


async def test_run_command_passes_db_trust_to_the_gate_when_trust_db_is_requested(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path, _text(VALID_LINE))

    result = await run_command(f"{VALIDATE} --compiler outdir --trust db", h.ctx())

    assert h.gate.dry_run_calls[0].requested_trust == "db"
    assert "(dry run, trust db)" in result.text


@pytest.mark.parametrize("trust", ["file", "builtin"])
async def test_run_command_answers_unknown_without_the_gate_when_trust_is_not_composer(
    tmp_path: Path, trust: str
) -> None:
    h = _harness(tmp_path, _text(VALID_LINE))

    result = await run_command(f"{VALIDATE} --compiler outdir --trust {trust}", h.ctx())

    assert h.gate.dry_run_calls == []
    assert result.text.endswith(
        f"--- platform check (dry run, trust {trust}) ---\n"
        "Only user or db trust applies to Composer workflows."
    )
    assert result.exit_code == 1
    assert h.checks() == [
        ("skill_validator", "valid", 0, 0),
        ("platform_dry_run", "unknown", 0, 0),
    ]


async def test_run_command_ends_with_a_generic_message_when_the_gate_raises(
    tmp_path: Path,
) -> None:
    gate = FakeGate(dry_run=RuntimeError("db password=hunter2"))
    h = _harness(tmp_path, _text(VALID_LINE), gate=gate)

    result = await run_command(f"{VALIDATE} --compiler outdir", h.ctx())

    assert result.exit_code == 1
    assert "The platform check could not run." in result.text
    assert "hunter2" not in result.text
    assert h.checks()[-1] == ("platform_dry_run", "unknown", 0, 0)


async def test_run_command_does_not_intercept_when_compiler_is_given_with_help(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path, _text("usage: validate_manifest.py\n"))

    result = await run_command(
        f"python {_SCRIPTS}/validate_manifest.py --compiler outdir --help", h.ctx()
    )

    assert result.status == "ok"
    assert h.gate.dry_run_calls == []
    assert h.checks() == []
    assert "platform check" not in result.text


async def test_run_command_does_not_call_the_gate_when_compiler_is_not_given(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path, _text(VALID_LINE))

    await run_command(VALIDATE, h.ctx())

    assert h.gate.dry_run_calls == []
    assert h.turn.signals == []


# --- runner failures -------------------------------------------------------------


@pytest.mark.parametrize(
    "error",
    [
        FileNotFoundError(2, "No such file", "/srv/secret/python"),
        PermissionError(13, "Permission denied", "/srv/secret/python"),
        OSError("spawn failed in /srv/secret"),
    ],
)
async def test_run_command_returns_a_generic_error_when_the_process_cannot_start(
    tmp_path: Path, error: OSError
) -> None:
    h = _harness(tmp_path, ProcessScript(start_error=error))

    result = await run_command(CATALOG, h.ctx())

    assert result.status == "error"
    assert result.exit_code is None
    assert result.summary == "The script could not be started."
    assert result.text == (
        f"$ {CATALOG}\nexit code: none\nThe script could not be started."
    )
    assert "secret" not in result.text
    assert not h.temp_dir.exists()
    assert [(cid, r.status) for cid, r in h.finished] == [(CALL_ID, "error")]


async def test_run_command_returns_a_generic_error_when_the_temp_folder_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = _harness(tmp_path)

    def refuse(_call_id: str) -> Path:
        raise SandboxPathError("call folder resolved outside .tmp")

    monkeypatch.setattr(h.sandbox, "call_temp_dir", refuse)

    result = await run_command(CATALOG, h.ctx())

    assert result.status == "error"
    assert result.text.endswith("The script could not be started.")
    assert "resolved outside" not in result.text
    assert h.factory.starts == []


async def test_run_command_publishes_no_check_when_the_validator_cannot_start(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path, ProcessScript(start_error=FileNotFoundError()))

    await run_command(f"{VALIDATE} --compiler outdir", h.ctx())

    assert h.checks() == []
    assert h.gate.dry_run_calls == []


# --- the run_skill_script tool ---------------------------------------------------


async def test_build_script_tool_exposes_only_the_command_when_the_schema_is_read(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path)

    tool = build_script_tool(h.ctx())

    assert tool.name == "run_skill_script"
    schema = tool.tool_call_schema
    properties = schema if isinstance(schema, dict) else schema.model_json_schema()
    assert set(properties["properties"]) == {"command"}


async def test_build_script_tool_returns_the_result_text_and_names_the_temp_folder_when_invoked(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path, _text("hello\n"))
    tool = build_script_tool(h.ctx(call_id=""))

    message = await tool.ainvoke(
        {
            "name": "run_skill_script",
            "args": {"command": CATALOG},
            "id": "call-7",
            "type": "tool_call",
        }
    )

    assert isinstance(message, ToolMessage)
    assert message.content == f"$ {CATALOG}\nexit code: 0\nhello\n"
    assert message.tool_call_id == "call-7"
    assert h.factory.starts[0].env["TMP"] == str(h.sandbox.path / ".tmp" / "call-7")
    assert [cid for cid, _ in h.finished] == ["call-7"]


async def test_build_script_tool_returns_the_refusal_text_when_the_command_is_refused(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path)
    tool = build_script_tool(h.ctx())

    message = await tool.ainvoke(
        {
            "name": "run_skill_script",
            "args": {"command": "python -c 'x'"},
            "id": "call-8",
            "type": "tool_call",
        }
    )

    assert isinstance(message, ToolMessage)
    assert "Interpreter options" in str(message.content)
    assert h.factory.starts == []


# --- map_path: skill folder spellings (Req 34.6) ---------------------------------------

_REPO_SKILL = f"app/agents/workflow_builder/skills/{BUILDER_SKILL_ID}"


def _roots(tmp_path: Path) -> Roots:
    sandbox = tmp_path / "sandbox"
    skill = tmp_path / "skill"
    (skill / "scripts").mkdir(parents=True)
    (skill / "scripts" / "catalog_lookup.py").write_text("", encoding="utf-8")
    sandbox.mkdir()
    return Roots(sandbox=sandbox, skill=skill)


@pytest.mark.parametrize(
    "prefix",
    [
        f"/skills/{BUILDER_SKILL_ID}",
        "<skill>",
        _REPO_SKILL,
        f"./{_REPO_SKILL}",
        f"backend/{_REPO_SKILL}",
        f"./backend/{_REPO_SKILL}",
        f"backend\\{_REPO_SKILL}".replace("/", "\\"),
    ],
)
def test_map_path_resolves_to_skill_scripts_when_prefix_names_the_skill_folder(
    tmp_path: Path, prefix: str
) -> None:
    roots = _roots(tmp_path)

    result = map_path(f"{prefix}/scripts/catalog_lookup.py", PathSlotKind.SCRIPT, roots)

    assert result == (roots.skill / "scripts" / "catalog_lookup.py").resolve()


@pytest.mark.parametrize(
    "prefix",
    [
        f".kiro/skills/{BUILDER_SKILL_ID}",
        f"../.kiro/skills/{BUILDER_SKILL_ID}",
    ],
)
def test_map_path_refuses_script_when_prefix_is_the_old_kiro_folder(
    tmp_path: Path, prefix: str
) -> None:
    roots = _roots(tmp_path)

    result = map_path(f"{prefix}/scripts/catalog_lookup.py", PathSlotKind.SCRIPT, roots)

    assert isinstance(result, Refusal)
    assert f"/skills/{BUILDER_SKILL_ID}/scripts/catalog_lookup.py" in result.reason
