"""Unit tests for ``app.core.logging`` (formatters, request-id filter, level resolution, setup).

Isolation notes
---------------
* ``logging.basicConfig`` is a no-op when the root logger already has handlers, and pytest
  attaches its own capture handlers to the root logger during every phase. Each
  ``configure_logging()`` test therefore runs inside ``_pristine_root()``, which empties the
  root logger IN PLACE for the duration of the call and restores it in a ``finally`` (inside
  the same test phase, so pytest's per-phase handlers are never re-attached stale).
* ``_restore_logging_globals`` (autouse) snapshots/restores the per-package logger levels the
  module writes to and resets the ``_request_id_var`` contextvar.
* Time is never read from the wall clock: records get ``created = 0.0`` and formatters use
  ``time.gmtime`` so ``%H:%M:%S`` is the literal ``00:00:00``.
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import re
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import PurePosixPath
from types import SimpleNamespace

import pytest

import app.core.logging as app_logging
from app.core.logging import (
    _JsonFormatter,
    _PrettyFormatter,
    _request_id_var,
    _RequestIdFilter,
    _resolve_app_level,
    configure_logging,
)

_UNSET = object()

_LEVELED_LOGGERS = (
    "app",
    "app.agents",
    "app.api",
    "agents",
    "uvicorn.access",
    "httpx",
    "httpcore",
)


# --------------------------------------------------------------------------- helpers


@pytest.fixture(autouse=True)
def _restore_logging_globals() -> Iterator[None]:
    """Snapshot/restore per-package logger levels and reset the request-id contextvar."""
    saved = {name: logging.getLogger(name).level for name in _LEVELED_LOGGERS}
    token = _request_id_var.set("-")
    try:
        yield
    finally:
        _request_id_var.reset(token)
        for name, level in saved.items():
            logging.getLogger(name).setLevel(level)


@pytest.fixture(autouse=True)
def _clean_colour_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove NO_COLOR / TERM so the developer's real environment never leaks in."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("TERM", raising=False)


@contextlib.contextmanager
def _pristine_root() -> Iterator[logging.Logger]:
    """Give the body an empty root logger at WARNING; restore handlers + level afterwards."""
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    root.handlers[:] = []
    root.setLevel(logging.WARNING)
    try:
        yield root
    finally:
        created = [h for h in root.handlers if h not in saved_handlers]
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)
        for handler in created:
            handler.close()


def _make_record(
    *,
    name: str = "app.main",
    level: int = logging.INFO,
    msg: str = "hello",
    args: tuple[object, ...] = (),
    exc_info: object = None,
    request_id: object = _UNSET,
) -> logging.LogRecord:
    """Build a LogRecord stamped at the epoch, optionally carrying a request_id."""
    record = logging.LogRecord(name, level, "/x.py", 1, msg, args, exc_info)  # type: ignore[arg-type]
    record.created = 0.0
    if request_id is not _UNSET:
        record.request_id = request_id
    return record


def _exc_info() -> tuple[type[BaseException], BaseException, object]:
    """Return a real (type, value, traceback) triple for ValueError('boom')."""
    try:
        raise ValueError("boom")
    except ValueError:
        return sys.exc_info()  # type: ignore[return-value]


def _pretty(*, use_color: bool) -> _PrettyFormatter:
    formatter = _PrettyFormatter(use_color=use_color)
    formatter.converter = time.gmtime
    return formatter


def _json_formatter() -> _JsonFormatter:
    formatter = _JsonFormatter()
    formatter.converter = time.gmtime
    return formatter


def _patch_settings(monkeypatch: pytest.MonkeyPatch, **overrides: object) -> None:
    """Replace ``app.core.logging._early_settings`` (the name the module looks up)."""
    values: dict[str, object] = {
        "SERVICE_NAME": "svc-test",
        "ENV": "staging",
        "LOG_FORMAT": "",
        "LOG_LEVEL_APP": "",
    }
    values.update(overrides)
    monkeypatch.setattr(app_logging, "_early_settings", SimpleNamespace(**values))


class _TtyStream(io.StringIO):
    """A text stream that claims to be a terminal."""

    def isatty(self) -> bool:
        return True


class _NoIsattyStream:
    """A write-only stream object without an ``isatty`` attribute."""

    def write(self, _text: str) -> int:
        return 0

    def flush(self) -> None:
        return None


@dataclass(frozen=True)
class _Installed:
    handlers: tuple[logging.Handler, ...]
    root_level: int


def _configure(
    monkeypatch: pytest.MonkeyPatch,
    *,
    log_format: str = "json",
    env: str = "production",
    app_level: str = "",
    stream: object | None = None,
    pre_handlers: tuple[logging.Handler, ...] = (),
) -> _Installed:
    """Run ``configure_logging()`` against a pristine root with patched settings/stdout."""
    _patch_settings(
        monkeypatch, LOG_FORMAT=log_format, ENV=env, LOG_LEVEL_APP=app_level
    )
    fake_stdout = stream if stream is not None else io.StringIO()
    monkeypatch.setattr(app_logging, "sys", SimpleNamespace(stdout=fake_stdout))
    with _pristine_root() as root:
        for handler in pre_handlers:
            root.addHandler(handler)
        configure_logging()
        return _Installed(tuple(root.handlers), root.level)


# --------------------------------------------------------------------------- _RequestIdFilter


class TestRequestIdFilter:
    # Plan #1 | B1
    def test_filter_stamps_dash_when_no_request_id_is_set(self) -> None:
        # Arrange
        record = _make_record()

        # Act
        _RequestIdFilter().filter(record)

        # Assert
        assert record.request_id == "-"  # type: ignore[attr-defined]

    # Plan #2 | B1
    def test_filter_stamps_current_value_when_request_id_is_set(self) -> None:
        # Arrange
        _request_id_var.set("req-abc")
        record = _make_record()

        # Act
        _RequestIdFilter().filter(record)

        # Assert
        assert record.request_id == "req-abc"  # type: ignore[attr-defined]

    # Plan #3 | B1
    def test_filter_overwrites_attribute_when_record_already_has_request_id(
        self,
    ) -> None:
        # Arrange
        _request_id_var.set("fresh")
        record = _make_record(request_id="stale")

        # Act
        _RequestIdFilter().filter(record)

        # Assert
        assert record.request_id == "fresh"  # type: ignore[attr-defined]

    # Plan #4 | B1
    def test_filter_returns_true_when_record_is_filtered(self) -> None:
        # Arrange
        record = _make_record()

        # Act
        result = _RequestIdFilter().filter(record)

        # Assert
        assert result is True


# --------------------------------------------------------------------------- _JsonFormatter


class TestJsonFormatterFormat:
    # Plan #5 | B3, B3b
    def test_format_returns_expected_fields_when_record_has_request_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        _patch_settings(monkeypatch, SERVICE_NAME="svc-test", ENV="staging")
        record = _make_record(request_id="req-1")

        # Act
        parsed = json.loads(_json_formatter().format(record))

        # Assert
        parsed.pop("time")
        assert parsed == {
            "level": "INFO",
            "service": "svc-test",
            "environment": "staging",
            "request_id": "req-1",
            "logger": "app.main",
            "message": "hello",
        }

    # Plan #6 | B3
    def test_format_orders_keys_as_time_level_service_environment_request_id_logger_message_when_formatting(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        _patch_settings(monkeypatch)
        record = _make_record(request_id="req-1")

        # Act
        parsed = json.loads(_json_formatter().format(record))

        # Assert
        assert list(parsed) == [
            "time",
            "level",
            "service",
            "environment",
            "request_id",
            "logger",
            "message",
        ]

    # Plan #7 | B3
    def test_format_renders_iso_time_from_record_created_when_converter_is_gmtime(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # ASSUMPTION: the "%z" suffix depends on the host time zone even with a gmtime
        # converter (platform strftime), so only its shape is pinned, not its value.
        # Arrange
        _patch_settings(monkeypatch)
        record = _make_record(request_id="req-1")

        # Act
        rendered = json.loads(_json_formatter().format(record))["time"]

        # Assert
        assert rendered[:19] == "1970-01-01T00:00:00"
        assert re.fullmatch(r"[+-]\d{4}", rendered[19:]) is not None

    # Plan #8 | B3b
    def test_format_defaults_request_id_to_dash_when_record_lacks_attribute(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        _patch_settings(monkeypatch)
        record = _make_record()

        # Act
        parsed = json.loads(_json_formatter().format(record))

        # Assert
        assert parsed["request_id"] == "-"

    # Plan #9 | B2
    def test_format_includes_formatted_traceback_when_record_has_exc_info(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        _patch_settings(monkeypatch)
        record = _make_record(level=logging.ERROR, exc_info=_exc_info())

        # Act
        parsed = json.loads(_json_formatter().format(record))

        # Assert
        assert parsed["exc_info"].startswith("Traceback (most recent call last):")
        assert parsed["exc_info"].endswith("ValueError: boom")

    # Plan #10 | B3
    def test_format_omits_exc_info_key_when_record_has_no_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        _patch_settings(monkeypatch)
        record = _make_record(exc_info=None)

        # Act
        parsed = json.loads(_json_formatter().format(record))

        # Assert
        assert "exc_info" not in parsed

    # Plan #11
    def test_format_interpolates_message_args_when_record_has_args(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        _patch_settings(monkeypatch)
        record = _make_record(msg="hello %s", args=("world",))

        # Act
        parsed = json.loads(_json_formatter().format(record))

        # Assert
        assert parsed["message"] == "hello world"

    # Plan #12
    def test_format_keeps_non_ascii_characters_when_message_is_unicode(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        _patch_settings(monkeypatch)
        record = _make_record(msg="héllo ✓")

        # Act
        output = _json_formatter().format(record)

        # Assert
        assert '"message": "héllo ✓"' in output
        assert "\\u" not in output

    # Plan #13
    def test_format_stringifies_value_when_setting_is_not_json_serialisable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        _patch_settings(monkeypatch, SERVICE_NAME=PurePosixPath("svc-path"))
        record = _make_record()

        # Act
        parsed = json.loads(_json_formatter().format(record))

        # Assert
        assert parsed["service"] == "svc-path"


# --------------------------------------------------------------------------- _PrettyFormatter


class TestPrettyFormatterInit:
    # Plan #14 | B20
    def test_init_enables_colour_when_no_argument_given(self) -> None:
        # Arrange / Act
        formatter = _PrettyFormatter()

        # Assert
        assert formatter.use_color is True

    # Plan #15 | B20
    def test_init_disables_colour_when_use_color_false(self) -> None:
        # Arrange / Act
        formatter = _PrettyFormatter(use_color=False)

        # Assert
        assert formatter.use_color is False


class TestPrettyFormatterComponent:
    # Plan #16 | B4
    @pytest.mark.parametrize(
        ("logger_name", "expected"),
        [
            ("agents.factory", "factory"),
            ("app.main", "main"),
            ("app.agents.skills", "skills"),
            ("agents.capabilities.gates.conditional", "condition"),
            ("app.core.config", "config"),
        ],
        ids=["factory", "main", "skills", "conditional-respelled", "config"],
    )
    def test_component_returns_mapped_label_when_name_is_exact_match(
        self, logger_name: str, expected: str
    ) -> None:
        # Arrange
        formatter = _PrettyFormatter()

        # Act
        label = formatter._component(logger_name)

        # Assert
        assert label == expected

    # Plan #17 | B5, B6, B7b
    @pytest.mark.parametrize(
        ("logger_name", "expected"),
        [
            ("app.api", "api"),
            ("app.api.auth", "api"),
            ("app.api.v1.runs", "api"),
            ("app.services", "service"),
            ("app.services.order", "service"),
            ("app.agents.validators", "validator"),
            ("app.agents.validators.schema", "validator"),
        ],
        ids=[
            "api-equal",
            "api-child",
            "api-deep",
            "service-equal",
            "service-child",
            "validator-equal",
            "validator-child",
        ],
    )
    def test_component_returns_prefix_label_when_name_is_in_prefix_family(
        self, logger_name: str, expected: str
    ) -> None:
        # Arrange
        formatter = _PrettyFormatter()

        # Act
        label = formatter._component(logger_name)

        # Assert
        assert label == expected

    # Plan #18 | B6, B7
    @pytest.mark.parametrize(
        ("logger_name", "expected"),
        [
            ("app.apixyz", "apixyz"),
            ("app.servicesx", "servicesx"),
            ("app.agents.validatorsx", "validators"),  # 11 chars -> cut to width 10
        ],
        ids=["api-near-miss", "services-near-miss", "validators-near-miss"],
    )
    def test_component_falls_back_to_last_segment_when_name_only_resembles_a_prefix(
        self, logger_name: str, expected: str
    ) -> None:
        # Arrange
        formatter = _PrettyFormatter()

        # Act
        label = formatter._component(logger_name)

        # Assert
        assert label == expected

    # Plan #19 | B7
    @pytest.mark.parametrize(
        ("logger_name", "expected"),
        [
            ("other.pkg.mod", "mod"),
            ("plain", "plain"),
            ("a.b.1234567890", "1234567890"),
            ("a.b.12345678901", "1234567890"),
            ("a.b.abcdefghijklmnop", "abcdefghij"),
            ("plainlogger", "plainlogge"),
            ("", ""),
        ],
        ids=[
            "short-segment",
            "no-dot",
            "exactly-width",
            "one-over-width",
            "long-segment",
            "no-dot-long",
            "empty-name",
        ],
    )
    def test_component_truncates_last_segment_to_width_when_name_is_unmapped(
        self, logger_name: str, expected: str
    ) -> None:
        # Arrange
        formatter = _PrettyFormatter()

        # Act
        label = formatter._component(logger_name)

        # Assert
        assert label == expected


class TestPrettyFormatterColorFor:
    # Plan #20 | B8
    @pytest.mark.parametrize(
        ("label", "expected"),
        [
            ("factory", "\033[38;2;180;83;9m"),
            ("main", "\033[38;2;203;213;225m"),
            ("engine", "\033[38;2;15;118;110m"),
            ("api", "\033[38;2;37;99;235m"),
            ("config", "\033[38;2;100;116;139m"),
        ],
        ids=["factory", "main", "engine", "api", "config"],
    )
    def test_color_for_returns_mapped_colour_when_label_is_in_colour_map(
        self, label: str, expected: str
    ) -> None:
        # Arrange
        formatter = _PrettyFormatter()

        # Act
        colour = formatter._color_for(label)

        # Assert
        assert colour == expected

    # Plan #21 | B9
    # crc32 values below were computed offline once and pinned (crc32 % 10 = bucket).
    @pytest.mark.parametrize(
        ("label", "expected"),
        [
            ("alpha", "\033[38;2;37;99;235m"),  # crc32 3504355690 -> bucket 0
            ("beta", "\033[38;2;15;118;110m"),  # crc32 2408645731 -> bucket 1
            ("zzz", "\033[38;2;180;83;9m"),  # crc32 3274128842 -> bucket 2
            ("weirdname", "\033[38;2;36;89;143m"),  # crc32 2714878214 -> bucket 4
            ("unknown", "\033[38;2;245;217;168m"),  # crc32 2904991687 -> bucket 7
            ("gamma", "\033[38;2;29;78;216m"),  # crc32 3292778609 -> bucket 9
        ],
        ids=["bucket-0", "bucket-1", "bucket-2", "bucket-4", "bucket-7", "bucket-9"],
    )
    def test_color_for_returns_crc32_palette_colour_when_label_is_unmapped(
        self, label: str, expected: str
    ) -> None:
        # Arrange
        formatter = _PrettyFormatter()

        # Act
        colour = formatter._color_for(label)

        # Assert
        assert colour == expected


class TestPrettyFormatterFormat:
    # Plan #22 | B10, B14, B17
    def test_format_returns_plain_line_when_info_without_request_id_and_colour_off(
        self,
    ) -> None:
        # Arrange
        record = _make_record()

        # Act
        line = _pretty(use_color=False).format(record)

        # Assert
        assert line == "00:00:00  main        hello"

    # Plan #23 | B12, B13, B14
    @pytest.mark.parametrize(
        ("levelno", "expected"),
        [
            (5, "00:00:00  main        hello"),
            (10, "00:00:00  main        hello"),
            (20, "00:00:00  main        hello"),
            (25, "00:00:00  main        hello"),
            (29, "00:00:00  main        hello"),
            (30, "00:00:00  main        WARN  hello"),
            (35, "00:00:00  main        WARN  hello"),
            (39, "00:00:00  main        WARN  hello"),
            (40, "00:00:00  main        ERROR hello"),
            (50, "00:00:00  main        ERROR hello"),
        ],
        ids=[
            "below-debug",
            "debug",
            "info",
            "between-info-warning",
            "just-below-warning",
            "warning",
            "between-warning-error",
            "just-below-error",
            "error",
            "critical",
        ],
    )
    def test_format_prefixes_level_tag_when_colour_off(
        self, levelno: int, expected: str
    ) -> None:
        # Arrange
        record = _make_record(level=levelno)

        # Act
        line = _pretty(use_color=False).format(record)

        # Assert
        assert line == expected

    # Plan #24 | B17
    @pytest.mark.parametrize(
        ("request_id", "expected"),
        [
            ("abcdefghijklmnop", "00:00:00  main        hello  abcdefgh"),
            ("abc", "00:00:00  main        hello  abc"),
            ("abcdefgh", "00:00:00  main        hello  abcdefgh"),
        ],
        ids=["truncated-to-8", "short-id", "exactly-8"],
    )
    def test_format_appends_truncated_request_id_when_colour_off(
        self, request_id: str, expected: str
    ) -> None:
        # Arrange
        record = _make_record(request_id=request_id)

        # Act
        line = _pretty(use_color=False).format(record)

        # Assert
        assert line == expected

    # Plan #25 | B17
    @pytest.mark.parametrize(
        "request_id", ["-", "", _UNSET], ids=["dash", "empty", "missing"]
    )
    def test_format_omits_request_id_suffix_when_id_is_dash_or_empty_or_missing(
        self, request_id: object
    ) -> None:
        # Arrange
        record = _make_record(request_id=request_id)

        # Act
        line = _pretty(use_color=False).format(record)

        # Assert
        assert line == "00:00:00  main        hello"

    # Plan #26 | B19
    def test_format_appends_traceback_when_colour_off_and_record_has_exc_info(
        self,
    ) -> None:
        # Arrange
        record = _make_record(level=logging.INFO, exc_info=_exc_info())

        # Act
        lines = _pretty(use_color=False).format(record).split("\n")

        # Assert
        assert lines[0] == "00:00:00  main        hello"
        assert lines[1] == "Traceback (most recent call last):"
        assert lines[-1] == "ValueError: boom"

    # Plan #27 | B7
    def test_format_uses_fallback_component_label_when_logger_unmapped(self) -> None:
        # Arrange
        record = _make_record(name="some.pkg.averyverylongname")

        # Act
        line = _pretty(use_color=False).format(record)

        # Assert
        assert line == "00:00:00  averyveryl  hello"

    # Plan #28
    def test_format_interpolates_message_args_when_colour_off(self) -> None:
        # Arrange
        record = _make_record(msg="n=%d", args=(3,))

        # Act
        line = _pretty(use_color=False).format(record)

        # Assert
        assert line == "00:00:00  main        n=3"

    # Plan #29 | B11, B15, B16
    @pytest.mark.parametrize(
        ("levelno", "expected"),
        [
            (5, "00:00:00  \033[1m\033[38;2;203;213;225mmain      \033[0m  hello"),
            (
                10,
                "00:00:00  \033[1m\033[38;2;203;213;225mmain      \033[0m  "
                "\033[2mhello\033[0m",
            ),
            (15, "00:00:00  \033[1m\033[38;2;203;213;225mmain      \033[0m  hello"),
            (20, "00:00:00  \033[1m\033[38;2;203;213;225mmain      \033[0m  hello"),
            (25, "00:00:00  \033[1m\033[38;2;203;213;225mmain      \033[0m  hello"),
            (
                30,
                "00:00:00  \033[1m\033[38;2;203;213;225mmain      \033[0m  "
                "\033[38;2;180;83;9mWARN\033[0m  \033[38;2;180;83;9mhello\033[0m",
            ),
            (
                35,
                "00:00:00  \033[1m\033[38;2;203;213;225mmain      \033[0m  "
                "\033[38;2;180;83;9mWARN\033[0m  \033[38;2;180;83;9mhello\033[0m",
            ),
            (
                39,
                "00:00:00  \033[1m\033[38;2;203;213;225mmain      \033[0m  "
                "\033[38;2;180;83;9mWARN\033[0m  \033[38;2;180;83;9mhello\033[0m",
            ),
            (
                40,
                "00:00:00  \033[1m\033[38;2;203;213;225mmain      \033[0m  "
                "\033[38;2;185;28;28mERROR\033[0m \033[38;2;185;28;28mhello\033[0m",
            ),
            (
                50,
                "00:00:00  \033[1m\033[38;2;203;213;225mmain      \033[0m  "
                "\033[38;2;185;28;28mERROR\033[0m \033[38;2;185;28;28mhello\033[0m",
            ),
        ],
        ids=[
            "below-debug-plain",
            "debug-dim",
            "between-debug-info-plain",
            "info-plain",
            "between-info-warning-plain",
            "warning-amber",
            "between-warning-error-amber",
            "just-below-error-amber",
            "error-red",
            "critical-red",
        ],
    )
    def test_format_styles_label_and_message_by_level_when_colour_on(
        self, levelno: int, expected: str
    ) -> None:
        # Arrange
        record = _make_record(level=levelno)

        # Act
        line = _pretty(use_color=True).format(record)

        # Assert
        assert line == expected

    # Plan #30 | B18
    def test_format_dims_request_id_suffix_when_colour_on(self) -> None:
        # Arrange
        record = _make_record(request_id="abcdefghijklmnop")

        # Act
        line = _pretty(use_color=True).format(record)

        # Assert
        assert line == (
            "00:00:00  \033[1m\033[38;2;203;213;225mmain      \033[0m  hello"
            "\033[2m  abcdefgh\033[0m"
        )

    # Plan #31 | B17, B18
    @pytest.mark.parametrize("request_id", ["-", ""], ids=["dash", "empty"])
    def test_format_omits_dim_suffix_when_colour_on_and_request_id_is_dash_or_empty(
        self, request_id: str
    ) -> None:
        # Arrange
        record = _make_record(request_id=request_id)

        # Act
        line = _pretty(use_color=True).format(record)

        # Assert
        assert line == "00:00:00  \033[1m\033[38;2;203;213;225mmain      \033[0m  hello"

    # Plan #32 | B9, B11
    def test_format_uses_palette_colour_for_label_when_component_unmapped_and_colour_on(
        self,
    ) -> None:
        # Arrange
        record = _make_record(name="some.alpha")  # label "alpha" -> crc32 bucket 0

        # Act
        line = _pretty(use_color=True).format(record)

        # Assert
        assert line == "00:00:00  \033[1m\033[38;2;37;99;235malpha     \033[0m  hello"

    # Plan #33 | B11, B19
    def test_format_appends_traceback_after_coloured_line_when_record_has_exc_info(
        self,
    ) -> None:
        # Arrange
        record = _make_record(exc_info=_exc_info())

        # Act
        lines = _pretty(use_color=True).format(record).split("\n")

        # Assert
        assert (
            lines[0]
            == "00:00:00  \033[1m\033[38;2;203;213;225mmain      \033[0m  hello"
        )
        assert lines[1] == "Traceback (most recent call last):"
        assert lines[-1] == "ValueError: boom"


# --------------------------------------------------------------------------- _resolve_app_level


def _own_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "app.core.logging"]


class TestResolveAppLevel:
    # Plan #34 | B22
    @pytest.mark.parametrize(
        ("configured", "expected"),
        [
            ("DEBUG", 10),
            ("INFO", 20),
            ("WARNING", 30),
            ("ERROR", 40),
            ("CRITICAL", 50),
            ("debug", 10),
            ("Error", 40),
            ("  warning  ", 30),
            ("\tINFO\n", 20),
            ("WARN", 30),
            ("FATAL", 50),
            # ASSUMPTION: NOTSET is a recognised level name (0), so it is returned as-is
            # rather than treated as a typo; setLevel(0) then means "inherit".
            ("NOTSET", 0),
        ],
        ids=[
            "debug",
            "info",
            "warning",
            "error",
            "critical",
            "lower-case",
            "mixed-case",
            "padded",
            "tab-newline",
            "warn-alias",
            "fatal-alias",
            "notset-zero",
        ],
    )
    def test_resolve_app_level_returns_level_when_name_is_known(
        self, configured: str, expected: int
    ) -> None:
        # Arrange / Act
        level = _resolve_app_level(configured)

        # Assert
        assert level == expected

    # Plan #35 | B22
    def test_resolve_app_level_does_not_log_when_name_is_known(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Arrange
        caplog.set_level(logging.WARNING, logger="app.core.logging")

        # Act
        _resolve_app_level("DEBUG")

        # Assert
        assert _own_records(caplog) == []

    # Plan #36 | B23
    @pytest.mark.parametrize(
        "configured",
        ["VERBOSE", "10", "DEBUG!", "   ", "WARNING;"],
        ids=["typo", "numeric", "punctuation", "whitespace-only", "trailing-semicolon"],
    )
    def test_resolve_app_level_returns_info_when_value_is_unrecognised(
        self, configured: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Arrange
        caplog.set_level(logging.WARNING, logger="app.core.logging")

        # Act
        level = _resolve_app_level(configured)

        # Assert
        assert level == 20

    # Plan #37 | B23
    @pytest.mark.parametrize(
        ("configured", "expected_message"),
        [
            (
                "VERBOSE",
                "LOG_LEVEL_APP='VERBOSE' is not a known level -- falling back to INFO "
                "(expected DEBUG/INFO/WARNING/ERROR/CRITICAL)",
            ),
            (
                " typo ",
                "LOG_LEVEL_APP=' typo ' is not a known level -- falling back to INFO "
                "(expected DEBUG/INFO/WARNING/ERROR/CRITICAL)",
            ),
        ],
        ids=["upper-case", "original-string-not-normalised"],
    )
    def test_resolve_app_level_logs_one_warning_with_original_value_when_value_is_unrecognised(
        self,
        configured: str,
        expected_message: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # Arrange
        caplog.set_level(logging.WARNING, logger="app.core.logging")

        # Act
        _resolve_app_level(configured)

        # Assert
        records = _own_records(caplog)
        assert len(records) == 1
        assert records[0].levelno == 30
        assert records[0].getMessage() == expected_message

    # Plan #38 | B21
    def test_resolve_app_level_returns_info_when_value_is_empty(self) -> None:
        # Arrange / Act
        level = _resolve_app_level("")

        # Assert
        assert level == 20

    # Plan #39 | B21
    def test_resolve_app_level_does_not_log_when_value_is_empty(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Arrange
        caplog.set_level(logging.WARNING, logger="app.core.logging")

        # Act
        _resolve_app_level("")

        # Assert
        assert _own_records(caplog) == []


# --------------------------------------------------------------------------- configure_logging


class TestConfigureLogging:
    # Plan #40 | B24, B25, B26
    @pytest.mark.parametrize(
        ("log_format", "env", "expected_type"),
        [
            ("json", "development", _JsonFormatter),
            ("pretty", "production", _PrettyFormatter),
            ("JSON", "development", _JsonFormatter),
            ("PRETTY", "production", _PrettyFormatter),
            ("", "development", _PrettyFormatter),
            ("", "Development", _PrettyFormatter),
            ("", "production", _JsonFormatter),
            ("", "staging", _JsonFormatter),
            ("xml", "development", _PrettyFormatter),
            ("xml", "production", _JsonFormatter),
        ],
        ids=[
            "explicit-json-wins-over-dev",
            "explicit-pretty-wins-over-prod",
            "json-upper-case",
            "pretty-upper-case",
            "auto-development",
            "auto-development-mixed-case",
            "auto-production",
            "auto-staging",
            "unrecognised-format-in-development",
            "unrecognised-format-in-production",
        ],
    )
    def test_configure_logging_selects_formatter_when_format_and_env_combination(
        self,
        monkeypatch: pytest.MonkeyPatch,
        log_format: str,
        env: str,
        expected_type: type[logging.Formatter],
    ) -> None:
        # Arrange / Act
        installed = _configure(monkeypatch, log_format=log_format, env=env)

        # Assert
        assert type(installed.handlers[0].formatter) is expected_type

    # Plan #41 | B27, B28, B29, B30, B31
    @pytest.mark.parametrize(
        ("stream_factory", "no_color", "term", "expected"),
        [
            (_TtyStream, None, None, True),
            (_TtyStream, "1", None, False),
            (_TtyStream, "", None, True),
            (_TtyStream, None, "dumb", False),
            (_TtyStream, None, "xterm-256color", True),
            (io.StringIO, None, None, False),
            (_NoIsattyStream, None, None, False),
        ],
        ids=[
            "tty-no-env",
            "tty-no-color-set",
            "tty-no-color-empty",
            "tty-term-dumb",
            "tty-term-xterm",
            "not-a-tty",
            "stream-without-isatty",
        ],
    )
    def test_configure_logging_sets_colour_when_pretty_format_and_terminal_conditions(
        self,
        monkeypatch: pytest.MonkeyPatch,
        stream_factory: type,
        no_color: str | None,
        term: str | None,
        expected: bool,
    ) -> None:
        # ASSUMPTION: an empty NO_COLOR ("") counts as unset (truthiness check in the
        # module), so colour stays on; only a non-empty NO_COLOR disables it.
        # Arrange
        if no_color is not None:
            monkeypatch.setenv("NO_COLOR", no_color)
        if term is not None:
            monkeypatch.setenv("TERM", term)

        # Act
        installed = _configure(
            monkeypatch, log_format="pretty", stream=stream_factory()
        )

        # Assert
        assert installed.handlers[0].formatter.use_color is expected  # type: ignore[union-attr]

    # Plan #42 | B33
    def test_configure_logging_installs_single_stream_handler_on_stdout_when_root_has_no_handlers(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        fake_stdout = io.StringIO()

        # Act
        installed = _configure(monkeypatch, stream=fake_stdout)

        # Assert
        assert len(installed.handlers) == 1
        assert type(installed.handlers[0]) is logging.StreamHandler
        assert installed.handlers[0].stream is fake_stdout  # type: ignore[attr-defined]

    # Plan #43 | B32
    def test_configure_logging_attaches_one_request_id_filter_when_handler_installed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange / Act
        installed = _configure(monkeypatch)

        # Assert
        filters = installed.handlers[0].filters
        assert len(filters) == 1
        assert type(filters[0]) is _RequestIdFilter

    # Plan #44 | B33
    def test_configure_logging_sets_root_level_to_info_when_root_was_at_warning(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange / Act (the pristine root starts at WARNING == 30)
        installed = _configure(monkeypatch)

        # Assert
        assert installed.root_level == 20

    # Plan #45 | B33
    def test_configure_logging_keeps_existing_handlers_when_root_already_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # ASSUMPTION: current behaviour is that logging.basicConfig(...) without force=True
        # silently does nothing when the root logger already has a handler, so
        # configure_logging() does not replace or add to it (nor change the root level).
        # Arrange
        existing = logging.NullHandler()

        # Act
        installed = _configure(monkeypatch, pre_handlers=(existing,))

        # Assert
        assert installed.handlers == (existing,)
        assert installed.root_level == 30

    # Plan #46 | B34
    @pytest.mark.parametrize(
        "logger_name",
        ["app", "app.agents", "app.api", "agents"],
        ids=["app", "app-agents", "app-api", "agents"],
    )
    def test_configure_logging_sets_app_family_level_when_log_level_app_is_debug(
        self, monkeypatch: pytest.MonkeyPatch, logger_name: str
    ) -> None:
        # Arrange
        logging.getLogger(logger_name).setLevel(logging.CRITICAL)

        # Act
        _configure(monkeypatch, app_level="DEBUG")

        # Assert
        assert logging.getLogger(logger_name).level == 10

    # Plan #47 | B34
    @pytest.mark.parametrize(
        ("app_level", "expected"),
        [("", 20), ("warning", 30), ("ERROR", 40), ("bogus", 20)],
        ids=["unset-info", "lower-case-warning", "error", "unrecognised-info"],
    )
    def test_configure_logging_sets_app_level_from_setting(
        self, monkeypatch: pytest.MonkeyPatch, app_level: str, expected: int
    ) -> None:
        # Arrange
        logging.getLogger("app").setLevel(logging.CRITICAL)

        # Act
        _configure(monkeypatch, app_level=app_level)

        # Assert
        assert logging.getLogger("app").level == expected

    # Plan #48 | B35
    @pytest.mark.parametrize(
        "logger_name",
        ["uvicorn.access", "httpx", "httpcore"],
        ids=["uvicorn-access", "httpx", "httpcore"],
    )
    def test_configure_logging_pins_third_party_loggers_to_warning_when_log_level_app_is_debug(
        self, monkeypatch: pytest.MonkeyPatch, logger_name: str
    ) -> None:
        # Arrange
        logging.getLogger(logger_name).setLevel(logging.DEBUG)

        # Act
        _configure(monkeypatch, app_level="DEBUG")

        # Assert
        assert logging.getLogger(logger_name).level == 30

    # Plan #49 | B26, B32
    def test_configure_logging_emits_json_line_with_request_id_when_json_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        stream = io.StringIO()
        _patch_settings(
            monkeypatch,
            SERVICE_NAME="svc-test",
            ENV="production",
            LOG_FORMAT="json",
            LOG_LEVEL_APP="",
        )
        monkeypatch.setattr(app_logging, "sys", SimpleNamespace(stdout=stream))

        # Act
        with _pristine_root():
            configure_logging()
            _request_id_var.set("req-42")
            logging.getLogger("tests.logging_probe").info("hello %s", "world")

        # Assert
        parsed = json.loads(stream.getvalue())
        parsed.pop("time")
        assert parsed == {
            "level": "INFO",
            "service": "svc-test",
            "environment": "production",
            "request_id": "req-42",
            "logger": "tests.logging_probe",
            "message": "hello world",
        }
