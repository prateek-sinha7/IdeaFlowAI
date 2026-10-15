"""ISS-104 / ISS-885 / ISS-888 — shutdown-path comments must cite by symbol, not by line.

Reads files as TEXT only (never imports app.*). A ``file.py:<line>`` cite goes stale as
the cited file grows; name the function/symbol instead. Likewise a restated value
(``read_timeout=N``) must agree with the code that sets it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_API = _ROOT / "backend" / "app" / "api"
_SCANNED = [
    _API / "run_shutdown.py",
    _API / "run_engine.py",
    _API / "run_stream.py",
    _ROOT / "backend" / "app" / "core" / "config.py",
    _ROOT / "backend" / "docker-entrypoint.sh",
    _ROOT / "backend" / "tests" / "unit" / "services" / "test_shutdown_reachability.py",
]
# Any name.ext:N / name.ext :N, a bare :NNN, or prose "line N" (also wrapped, also
# across a "#" comment break). ponytail: regex only, a cite spelled out in words escapes.
_LINE_CITE = re.compile(
    r"[\w./-]+\.[A-Za-z]{1,5} ?:\d+|(?<![\w/.]):\d{3,}|\blines?[\s#]+\d+"
)


@pytest.mark.issue("ISS-104")
@pytest.mark.issue("ISS-885")
def test_no_line_number_cites_in_shutdown_path_files():
    """ISS-104, ISS-885 — cite by symbol (function/class name), never file:line."""
    hits = []
    for path in _SCANNED:
        assert path.exists(), f"scanned file moved or deleted: {path}"
        text = path.read_text()  # whole text, so a cite wrapped across lines is seen
        for m in _LINE_CITE.finditer(text):
            n = text.count("\n", 0, m.start()) + 1
            hits.append(f"{path.name}:{n}: {m.group(0)}")
    assert not hits, "line-number cites found:\n" + "\n".join(hits)


@pytest.mark.issue("ISS-888")
def test_shutdown_comment_read_timeout_matches_model_factory():
    """ISS-888 — comments restating ``read_timeout=N`` must match model_factory."""
    real = re.search(
        r"read_timeout=(\d+)",
        (_ROOT / "backend" / "app" / "agents" / "model_factory.py").read_text(),
    )
    assert real, "model_factory sets no read_timeout literal"
    stated = set(
        re.findall(r"read_timeout=(\d+)", (_API / "run_shutdown.py").read_text())
    )
    assert stated <= {
        real.group(1)
    }, f"comment says {stated}, code says {real.group(1)}"


@pytest.mark.issue("ISS-903")
@pytest.mark.parametrize(
    "text",
    [
        "see main.py:238",
        "test_run_stream_pool_leak.py:196-238",
        "run_commands.py :399/:421",
        "registers the queue at :1734",
        "(:2514/:3621)",
        "scripts/start.sh:27",
    ],
)
def test_line_cite_pattern_flags_every_cite_shape(text):
    """ISS-903 — _LINE_CITE must flag name.ext:N, name.ext :N and bare :NNN cites."""
    assert _LINE_CITE.search(text), f"not flagged: {text!r}"


@pytest.mark.issue("ISS-903")
@pytest.mark.parametrize(
    "text", ["localhost:3000", "0.0.0.0:8000", "12:30:45", "ISS-104: see FIX-690"]
)
def test_line_cite_pattern_ignores_non_cites(text):
    """ISS-903 — widening _LINE_CITE must not flag ports, times or ISS prose."""
    assert not _LINE_CITE.search(text)


@pytest.mark.issue("ISS-903")
def test_shutdown_reachability_has_no_line_cites():
    """ISS-903 — test_shutdown_reachability.py must cite by symbol, not file:line."""
    wide = re.compile(r"[\w./-]+\.[A-Za-z]{1,5} ?:\d+|(?<![\w/.]):\d{3,}")
    path = _ROOT / "backend/tests/unit/services/test_shutdown_reachability.py"
    hits = [
        f"{n}: {m.group(0)}"
        for n, line in enumerate(path.read_text().splitlines(), 1)
        for m in wide.finditer(line)
    ]
    assert not hits, "line cites remain:\n" + "\n".join(hits)


# What the _SCANNED comments name instead of a line number (ISS-104's anchor list), by the
# file that holds it. Plain text, not ast: runs_left_for_boot_restore is a dict key.
# ponytail: hand-kept, so it can drift from the comments; derive it from them if it does.
_ANCHORS = {
    "backend/app/api/run_commands.py": [
        "NEVER cancel it on",
        'type="chat_reply"',
        "def post_message",
        "def _drive_launch_to_queue",
        "def _drive_revision_to_queue",
        "def resume_run_endpoint",
    ],
    "backend/agents/execution_engine/engine.py": [
        "def execute(",
        "sink.persist(",
        "def _execute_impl(",
        "def _run_agent(",
        "def _run_review_gate(",
        "def _run_validation_fix_loop(",
        "def _run_spec_revision_sub_pipeline(",
    ],
    "backend/app/api/run_shutdown.py": [
        "def shutdown_run_infrastructure",
        "def _drain_then_cancel",
        "runs_left_for_boot_restore",
    ],
    "backend/app/agents/model_factory.py": ["def build_model", "read_timeout"],
    "backend/app/agents/checkpointer.py": ["def close_checkpointer"],
    "backend/app/main.py": ["restore_non_terminal_runs()"],
    "backend/tests/unit/app/test_run_stream_pool_leak.py": [
        "def test_stream_endpoint_returns_connections",
    ],
    "docker-compose.yml": ["stop_grace_period"],
}


@pytest.mark.issue("ISS-1085")
def test_symbols_named_by_shutdown_path_comments_still_exist():
    """ISS-1085 — renaming a symbol a comment names fails here, not silently."""
    missing = [
        f"{rel}: {anchor!r}"
        for rel, anchors in _ANCHORS.items()
        for anchor in anchors
        if anchor not in (_ROOT / rel).read_text()
    ]
    assert not missing, "anchors the comments name are gone:\n" + "\n".join(missing)


# Cites INTO the guarded files from anywhere else in backend/. core/config is qualified
# because a bare config.py:N also matches uvicorn's.
_INBOUND_CITE = re.compile(
    r"\b(?:run_shutdown|run_engine|run_stream|checkpointer|docker-entrypoint|"
    r"test_shutdown_reachability|core/config)\.(?:py|sh) ?:\d+"
)


@pytest.mark.issue("ISS-1083")
def test_no_line_number_cites_into_shutdown_path_files_from_elsewhere():
    """ISS-1083 — no backend file cites a guarded module by line number."""
    backend = _ROOT / "backend"
    hits = []
    for path in backend.rglob("*"):
        if ".venv" in path.parts or path.suffix not in {
            ".py",
            ".sh",
            ".yml",
            ".md",
            ".toml",
        }:
            continue
        if not path.is_file():
            continue
        text = path.read_text(errors="ignore")
        for m in _INBOUND_CITE.finditer(text):
            n = text.count("\n", 0, m.start()) + 1
            hits.append(f"{path.relative_to(backend)}:{n}: {m.group(0)}")
    assert not hits, "line-number cites into shutdown-path files:\n" + "\n".join(hits)
