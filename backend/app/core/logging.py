"""Logging configuration for the app -- extracted out of app.main so main.py
isn't carrying ~190 lines of formatter/handler setup. Defines the formatters,
the request-id contextvar/filter, and `configure_logging()`, which installs
the handler + formatter and sets per-package levels; call it once at startup,
before any app.* module that logs is imported.
"""

import json
import logging
import os
import sys
import zlib
import contextvars

# `settings` in app.main and `_early_settings` below (imported before
# logging setup) are the SAME object -- Settings() is instantiated once at
# module import in app.core.config and both names bind to it. Kept as two
# names deliberately: `_early_settings` documents "this is read before
# logging.basicConfig runs" at its use site.

from app.core.config import settings as _early_settings  # noqa: E402 - needed before logging setup

# M-02: the request ID nginx generates ($request_id, forwarded as the
# X-Request-ID header by velocityai-proxy-headers.conf) or, absent nginx (local
# dev / a direct request), one minted here. A contextvar (not a global) so
# concurrent requests on the same process never see each other's ID -- every
# log line emitted while handling a request carries it via the logging filter
# below, which is what lets an operator grep one nginx access-log line's
# request_id and pull every app-log line that same request produced.
_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


class _RequestIdFilter(logging.Filter):
    """Stamps the CURRENT request's ID onto every LogRecord (M-02)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_var.get()
        return True


class _JsonFormatter(logging.Formatter):
    """M-06: JSON log lines with static service/environment fields + request_id.

    Replaces the previous pipe-delimited text format, which carried none of
    service/environment/request_id and required string-parsing to filter in
    CloudWatch Logs Insights. ``sort_keys`` kept off for formatter perf; field
    order is fixed by the dict literal below, which is good enough for grep/
    Insights (both parse full JSON, not positionally).
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": self.formatTime(record, LOG_DATE_FORMAT),
            "level": record.levelname,
            "service": _early_settings.SERVICE_NAME,
            "environment": _early_settings.ENV,
            "request_id": getattr(record, "request_id", "-"),
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


class _PrettyFormatter(logging.Formatter):
    """Human-readable, coloured single-line console format for local dev.

    Never used in production (see format selection below) -- the JSON shape
    production log ingestion depends on is untouched by this class.
    """

    # Data-driven logger-name -> short COMPONENT label. Exact matches first;
    # `_PREFIX_COMPONENTS` covers the `app.api.*` family; anything unmapped
    # falls back to the logger name's last dotted segment, truncated to 10.
    _COMPONENTS: dict[str, str] = {
        "agents.factory": "factory",
        "app.agents.skill_staging": "staging",
        "app.agents.deep_agent_runner": "runner",
        "agents.execution_engine.engine": "engine",
        "app.agents.sandbox": "sandbox",
        "app.main": "main",
        "app.agents.model_factory": "model",
        "app.agents.model_output": "model",
        "app.agents.tool_output": "tool",
        "app.agents.checkpointer": "checkpt",
        "app.agents.skills": "skills",
        "agents.execution_engine.kernel_services": "kernel",
        "agents.planner.smart_planner": "planner",
        "app.core.config": "config",
        # getLogger(__name__) modules under agents/execution_engine/
        "agents.execution_engine.state_machine": "state",
        "agents.execution_engine.clarify_engine": "clarify",
        "agents.execution_engine.resolver": "resolver",
        "agents.execution_engine.fanout": "fanout",
        "agents.execution_engine.od_context": "od_ctx",
        # getLogger(__name__) truncates "conditional" -> "conditiona" at width
        # 10 (off-by-one, reads as a cut-off word) — spell it out explicitly.
        "agents.capabilities.gates.conditional": "condition",
    }
    _PREFIX_COMPONENTS: dict[str, str] = {
        "app.api": "api",
        "app.agents.validators": "validator",
        "app.services": "service",
    }
    _WIDTH = 10

    # One stable colour per component. Palette sourced from
    # to-be-architecture.html's CSS custom properties (:root, ~line 10) --
    # 24-bit truecolor equivalents of that document's ACCENT colours (not the
    # pastel plane fills, which are ~240 luminance and unreadable as terminal
    # text on a dark background), assigned so each component's hue matches
    # the architecture plane it belongs to. Do NOT "tidy" this back to the
    # basic 8-colour ANSI set -- it is a fixed, explicit dict (not a hash of
    # the name) so colours never change between runs, and every hex here must
    # trace back to that document.
    # Any label NOT in this dict falls back to `_PALETTE`, selected by
    # `zlib.crc32(label)` (see `_color_for`) -- crc32 is deterministic across
    # processes (unlike `hash()`, which is randomised per-process), so an
    # unmapped component still gets a stable colour instead of flat white.
    _COLORS: dict[str, str] = {
        "factory": "\033[38;2;180;83;9m",  # #b45309 amber (execution plane)
        "staging": "\033[38;2;245;217;168m",  # #f5d9a8 pale amber (execution plane)
        "skills": "\033[38;2;245;217;168m",  # #f5d9a8 pale amber (execution plane)
        # Same amber as `factory` on purpose: both are execution plane, and this
        # must match the `tool` colour run.hello_html.http uses so one tool call
        # looks the same in the backend log and the harness transcript. (#123f6e
        # navy was tried and rejected -- luminance 57 is unreadable on black.)
        "tool": "\033[38;2;180;83;9m",  # #b45309 amber (execution plane)
        "runner": "\033[38;2;109;40;217m",  # #6d28d9 violet (runtime plane)
        "planner": "\033[38;2;109;40;217m",  # #6d28d9 violet (runtime plane)
        "engine": "\033[38;2;15;118;110m",  # #0f766e teal (control plane)
        "kernel": "\033[38;2;15;118;110m",  # #0f766e teal (control plane)
        "clarify": "\033[38;2;15;118;110m",  # #0f766e teal (control plane)
        "state": "\033[38;2;36;89;143m",  # #24598f steel (control plane)
        "resolver": "\033[38;2;36;89;143m",  # #24598f steel (control plane)
        "checkpt": "\033[38;2;36;89;143m",  # #24598f steel (runtime plane)
        "fanout": "\033[38;2;29;78;216m",  # #1d4ed8 blue (control plane)
        "sandbox": "\033[38;2;148;163;184m",  # #94a3b8 slate (data plane)
        "od_ctx": "\033[38;2;148;163;184m",  # #94a3b8 slate (data plane)
        "model": "\033[38;2;185;212;244m",  # #b9d4f4 pale blue (runtime plane)
        "api": "\033[38;2;37;99;235m",  # #2563eb blue (experience plane)
        "validator": "\033[38;2;180;83;9m",  # #b45309 amber (execution plane)
        "service": "\033[38;2;100;116;139m",  # #64748b muted
        "config": "\033[38;2;100;116;139m",  # #64748b muted
        "main": "\033[38;2;203;213;225m",  # #cbd5e1
    }
    _PALETTE: tuple[str, ...] = (
        "\033[38;2;37;99;235m",  # #2563eb blue
        "\033[38;2;15;118;110m",  # #0f766e teal
        "\033[38;2;180;83;9m",  # #b45309 amber
        "\033[38;2;109;40;217m",  # #6d28d9 violet
        "\033[38;2;36;89;143m",  # #24598f steel
        "\033[38;2;148;163;184m",  # #94a3b8 slate
        "\033[38;2;185;212;244m",  # #b9d4f4 pale blue
        "\033[38;2;245;217;168m",  # #f5d9a8 pale amber
        "\033[38;2;100;116;139m",  # #64748b muted
        "\033[38;2;29;78;216m",  # #1d4ed8 blue
    )
    _BOLD = "\033[1m"
    _DIM = "\033[2m"
    _WARN_COLOR = "\033[38;2;180;83;9m"  # #b45309 amber
    _ERROR_COLOR = "\033[38;2;185;28;28m"  # #b91c1c red
    _RESET = "\033[0m"

    def __init__(self, use_color: bool = True):
        super().__init__()
        self.use_color = use_color

    def _component(self, logger_name: str) -> str:
        if logger_name in self._COMPONENTS:
            return self._COMPONENTS[logger_name]
        for prefix, label in self._PREFIX_COMPONENTS.items():
            if logger_name == prefix or logger_name.startswith(prefix + "."):
                return label
        return logger_name.rsplit(".", 1)[-1][: self._WIDTH]

    def _color_for(self, label: str) -> str:
        if label in self._COLORS:
            return self._COLORS[label]
        return self._PALETTE[zlib.crc32(label.encode()) % len(self._PALETTE)]

    def format(self, record: logging.LogRecord) -> str:
        time_str = self.formatTime(record, "%H:%M:%S")
        component = self._component(record.name).ljust(self._WIDTH)
        message = record.getMessage()

        # Truncated to 8 chars -- the full 32-char id wraps every line in a
        # terminal; `_JsonFormatter` still emits the full id, untouched.
        request_id = getattr(record, "request_id", "-")[:8]
        rid_suffix = f"  {request_id}" if request_id and request_id != "-" else ""

        if record.levelno >= logging.ERROR:
            tag = "ERROR "
        elif record.levelno >= logging.WARNING:
            tag = "WARN  "
        else:
            tag = ""

        if not self.use_color:
            line = f"{time_str}  {component}  {tag}{message}{rid_suffix}"
        else:
            # Single path for every level: the component label is always
            # coloured + bold (DEBUG included -- several truecolor accents
            # read dim on a black background, bold keeps them scannable), so
            # it stays legible at DEBUG -- only the message (and request-id
            # suffix) get dimmed.
            label = f"{self._BOLD}{self._color_for(component.strip())}{component}{self._RESET}"
            if record.levelno >= logging.ERROR:
                tag_str = f"{self._ERROR_COLOR}ERROR{self._RESET} "
            elif record.levelno >= logging.WARNING:
                tag_str = f"{self._WARN_COLOR}WARN{self._RESET}  "
            else:
                tag_str = ""
            # Message styling follows the level, so severity is readable from
            # the text itself and not just the tag: DEBUG recedes (dim), INFO
            # is plain, WARNING/ERROR carry the amber/red of their tag across
            # the whole line -- a red line should look wrong at a glance.
            if record.levelno >= logging.ERROR:
                msg_str = f"{self._ERROR_COLOR}{message}{self._RESET}"
            elif record.levelno >= logging.WARNING:
                msg_str = f"{self._WARN_COLOR}{message}{self._RESET}"
            elif record.levelno == logging.DEBUG:
                msg_str = f"{self._DIM}{message}{self._RESET}"
            else:
                msg_str = message
            rid_str = f"{self._DIM}{rid_suffix}{self._RESET}" if rid_suffix else ""
            line = f"{time_str}  {label}  {tag_str}{msg_str}{rid_str}"

        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)

        return line


LOG_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


def _resolve_app_level(configured: str) -> int:
    """Turn ``LOG_LEVEL_APP`` into a real level, never ``None``.

    Unset means INFO -- the production level -- regardless of ENV. Verbosity is
    opt-in per environment (backend/.env sets DEBUG locally), so a deployment
    that says nothing gets the conservative level rather than whatever its ENV
    string happens to imply. These loggers carry prompts and model output at
    DEBUG, so the quiet default is the safe one to fall back to (M-06/H-06).

    An UNRECOGNISED value also falls back to INFO, and says so. The previous
    ``getattr(logging, name, None)`` returned ``None`` for a typo, and
    ``setLevel(None)`` raises -- so one bad character in an env var took the
    process down at startup instead of degrading to a sane level.
    """
    if configured:
        name = configured.strip().upper()
        # getLevelNamesMapping() (3.11+) rather than getLevelName(str), whose
        # str -> int direction is deprecated.
        level = logging.getLevelNamesMapping().get(name)
        if level is not None:
            return level
        logging.getLogger("app.core.logging").warning(
            "LOG_LEVEL_APP=%r is not a known level -- falling back to INFO "
            "(expected DEBUG/INFO/WARNING/ERROR/CRITICAL)",
            configured,
        )
        return logging.INFO
    return logging.INFO


def configure_logging() -> None:
    """Install handler + formatter and set per-package levels. Idempotent-safe to call once at startup."""

    # Format choice: LOG_FORMAT="json"/"pretty" wins explicitly; otherwise pretty
    # in local development, json everywhere else (production log ingestion parses
    # JSON -- never silently switch it to pretty). Colour is then dropped (not the
    # pretty layout itself) whenever the stream isn't a TTY -- piping to a file or
    # `tee`, as run-http.sh does for transcripts -- or NO_COLOR is set, or
    # TERM=dumb.
    _log_format = _early_settings.LOG_FORMAT.lower()
    if _log_format not in ("json", "pretty"):
        _log_format = "pretty" if _early_settings.ENV.lower() == "development" else "json"

    _log_handler = logging.StreamHandler(sys.stdout)
    if _log_format == "pretty":
        _use_color = (
            hasattr(_log_handler.stream, "isatty")
            and _log_handler.stream.isatty()
            and not os.environ.get("NO_COLOR")
            and os.environ.get("TERM") != "dumb"
        )
        _log_handler.setFormatter(_PrettyFormatter(use_color=_use_color))
    else:
        _log_handler.setFormatter(_JsonFormatter())
    _log_handler.addFilter(_RequestIdFilter())

    logging.basicConfig(level=logging.INFO, handlers=[_log_handler])

    # M-06: app.agents / app.api carry prompts/payloads/user content at DEBUG.
    # Previously HARDCODED to DEBUG in every environment. Now set explicitly per
    # environment via LOG_LEVEL_APP (backend/.env sets DEBUG locally, production
    # sets WARNING), defaulting to INFO when unset -- so a DEBUG-level prompt
    # dump is opt-in, not the always-on default, once these logs ship off-box to
    # CloudWatch (H-06).
    _app_log_level = _resolve_app_level(_early_settings.LOG_LEVEL_APP)
    logging.getLogger("app").setLevel(_app_log_level)
    logging.getLogger("app.agents").setLevel(_app_log_level)
    logging.getLogger("app.api").setLevel(_app_log_level)
    # The whole ``agents`` package, not hand-picked submodules: tracing a run means
    # following it across factory -> model_factory -> engine -> state_machine ->
    # graph -> validators, and a level set on one submodule leaves the next hop
    # silent. Same environment gate as ``app`` above, so prod stays at INFO.
    logging.getLogger("agents").setLevel(_app_log_level)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
