"""Unit tests for ``tools.ci.execution_recorder._Recorder.record_report``.

The recorder feeds ``inventory_cli verify-execution``, which prints each skipped
node's reason. An xfail reaches pytest's report hooks as outcome ``"skipped"`` with
its reason on ``wasxfail`` (not in a ``(path, line, reason)`` ``longrepr`` tuple), so
these pin that both kinds of skip keep their reason.
"""

from __future__ import annotations

from types import SimpleNamespace

from tools.ci.execution_recorder import _known_bug_meta, _Recorder


def _report(**fields) -> SimpleNamespace:
    """A minimal stand-in for a pytest ``TestReport`` (only the fields read)."""
    base = {"nodeid": "tests/x.py::t", "when": "call", "outcome": "passed"}
    base.update(fields)
    return SimpleNamespace(**base)


def _recorder() -> _Recorder:
    return _Recorder(inventory_path=None, execution_path=None)


def test_record_report_keeps_the_reason_when_a_plain_skip_happens_at_setup() -> None:
    rec = _recorder()
    rec.record_report(
        _report(
            when="setup",
            outcome="skipped",
            longrepr=("tests/x.py", 3, "Skipped: LibreOffice is not installed"),
        )
    )
    assert rec.skip_reasons["tests/x.py::t"] == "Skipped: LibreOffice is not installed"
    assert rec.outcomes["tests/x.py::t"]["skipped"] == 1


def test_record_report_records_the_xfail_reason_when_the_node_xfails() -> None:
    rec = _recorder()
    rec.record_report(
        _report(
            outcome="skipped",
            wasxfail="ISS-104 unfixed",
            longrepr="AssertionError: traceback text, not a tuple",
        )
    )
    assert rec.skip_reasons["tests/x.py::t"] == "xfail: ISS-104 unfixed"
    assert rec.outcomes["tests/x.py::t"]["skipped"] == 1


def test_record_report_marks_an_xfail_even_when_it_has_no_reason() -> None:
    rec = _recorder()
    rec.record_report(_report(outcome="skipped", wasxfail="", longrepr="traceback"))
    assert rec.skip_reasons["tests/x.py::t"] == "xfail"


def test_record_report_records_no_skip_reason_when_the_node_passes() -> None:
    rec = _recorder()
    rec.record_report(_report())
    assert "tests/x.py::t" not in rec.skip_reasons
    assert rec.outcomes["tests/x.py::t"]["passed"] == 1


# ── known-bug metadata (strict xfail + issue marker) ────────────────────────


class _Mark(SimpleNamespace):
    """Minimal ``pytest.Mark`` stand-in (``name`` / ``args`` / ``kwargs``)."""


class _Item:
    """Minimal collected-item stand-in for ``record_item`` / ``_known_bug_meta``."""

    def __init__(self, marks: list[_Mark], *, xfail_strict_ini: bool = False) -> None:
        self.nodeid = "tests/x.py::t"
        self.path = "tests/x.py"
        self._marks = marks
        self.config = SimpleNamespace(
            getini=lambda name: xfail_strict_ini if name == "xfail_strict" else None
        )

    def iter_markers(self, name: str | None = None):
        return (m for m in self._marks if name is None or m.name == name)

    def get_closest_marker(self, name: str):
        return next(self.iter_markers(name), None)


def _xfail(**kwargs) -> _Mark:
    return _Mark(name="xfail", args=(), kwargs=kwargs)


def _issue(card: str) -> _Mark:
    return _Mark(name="issue", args=(card,), kwargs={})


def test_known_bug_meta_is_strict_when_the_xfail_marker_is_strict() -> None:
    meta = _known_bug_meta(_Item([_xfail(strict=True), _issue("ISS-104")]))
    assert meta == {"strict_xfail": True, "issues": ["ISS-104"]}


def test_known_bug_meta_is_not_strict_when_strict_is_false() -> None:
    meta = _known_bug_meta(_Item([_xfail(strict=False), _issue("ISS-104")]))
    assert meta["strict_xfail"] is False


def test_known_bug_meta_uses_the_ini_default_when_strict_is_not_given() -> None:
    assert _known_bug_meta(_Item([_xfail()], xfail_strict_ini=True))["strict_xfail"]
    assert not _known_bug_meta(_Item([_xfail()]))["strict_xfail"]


def test_known_bug_meta_is_not_strict_when_the_xfail_never_runs() -> None:
    """run=False never executes, so it could never flip red when fixed."""
    meta = _known_bug_meta(_Item([_xfail(strict=True, run=False), _issue("ISS-1")]))
    assert meta["strict_xfail"] is False


def test_known_bug_meta_is_not_strict_when_there_is_no_xfail_marker() -> None:
    """An imperative pytest.xfail() leaves no marker and can never be strict."""
    assert _known_bug_meta(_Item([_issue("ISS-1")])) == {
        "strict_xfail": False,
        "issues": ["ISS-1"],
    }


def test_record_report_flags_an_xfail_as_xfailed_but_not_a_plain_skip() -> None:
    rec = _recorder()
    rec.record_report(_report(outcome="skipped", wasxfail="ISS-1", longrepr="tb"))
    rec.record_report(
        _report(
            nodeid="tests/x.py::s",
            when="setup",
            outcome="skipped",
            longrepr=("tests/x.py", 1, "Skipped: no chromium"),
        )
    )
    assert rec.xfailed == {"tests/x.py::t"}
