"""Unit tests for the dev-upload fail-fast additions in ``app/api/run_files.py``.

* ``declares_file_extract`` — the name-free plan predicate the launch gate uses.
* ``ingest_staged_uploads`` — WARNs when ingest ends with no document persisted
  (so ``.uploads/manifest.json`` was never written), and stays best-effort.

Filesystem use is confined to ``tmp_path`` (``settings.RUNS_ROOT`` is pointed at
it); ``_persist_documents`` — the DB/disk writer — is replaced by an autospec.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest import mock

import pytest

import app.api.run_files as run_files
from app.api.run_files import declares_file_extract, ingest_staged_uploads

_USER = "user-1"
_RUN = "run-1"
_STAGE = "0123456789abcdef0123456789abcdef"
_ABSENT = "manifest.json is absent"


def _plan(*tool_sets):
    return SimpleNamespace(
        steps=[SimpleNamespace(tools=SimpleNamespace(tool_sets=ts)) for ts in tool_sets]
    )


@pytest.fixture
def runs_root(tmp_path, monkeypatch):
    """Point RUNS_ROOT at tmp_path so stage dirs resolve inside the test sandbox."""
    monkeypatch.setattr(run_files.settings, "RUNS_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture
def persist_documents(monkeypatch):
    """Autospec of _persist_documents: isolates ingest from the DB and the run sandbox."""
    fake = mock.create_autospec(run_files._persist_documents, return_value=[])
    monkeypatch.setattr(run_files, "_persist_documents", fake)
    return fake


def _make_stage(
    runs_root, stage_id: str = _STAGE, files: dict[str, bytes] | None = None
):
    stage_dir = runs_root / _USER / f"staged-{stage_id}"
    stage_dir.mkdir(parents=True)
    for name, data in (files or {}).items():
        (stage_dir / name).write_bytes(data)
    return stage_dir


def _warnings(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]


def test_declares_file_extract_true_when_any_step_has_tool_set():
    assert declares_file_extract(_plan(None, ["documents", "file_extract"])) is True


@pytest.mark.parametrize(
    "plan",
    [
        None,
        SimpleNamespace(steps=None),
        _plan(),
        _plan(None, []),
        _plan(["documents"]),
        SimpleNamespace(steps=[SimpleNamespace(tools=None)]),
    ],
)
def test_declares_file_extract_false_when_plan_none_or_no_tool_set(plan):
    assert declares_file_extract(plan) is False


async def test_ingest_staged_uploads_warns_manifest_absent_when_no_stage_persisted(
    runs_root, persist_documents, caplog
):
    caplog.set_level(logging.WARNING, logger="app.api.run_files")

    await ingest_staged_uploads(
        user_id=_USER, workspace_id=None, run_id=_RUN, stage_ids=[_STAGE, "bad id"]
    )

    persist_documents.assert_not_called()
    absent = [w for w in _warnings(caplog) if _ABSENT in w]
    assert absent == [
        "staged upload ingest finished but .uploads/manifest.json is absent: "
        f"run={_RUN} stages=2 persisted=0"
    ]


async def test_ingest_staged_uploads_warns_manifest_absent_when_persist_raises(
    runs_root, persist_documents, caplog
):
    caplog.set_level(logging.WARNING, logger="app.api.run_files")
    stage_dir = _make_stage(runs_root, files={"doc.pdf": b"%PDF-1.4"})
    persist_documents.side_effect = OSError("disk full")

    await ingest_staged_uploads(
        user_id=_USER, workspace_id=None, run_id=_RUN, stage_ids=[_STAGE]
    )

    assert any(_ABSENT in w for w in _warnings(caplog))
    assert not stage_dir.exists()


async def test_ingest_staged_uploads_no_manifest_warning_when_stage_persisted(
    runs_root, persist_documents, caplog
):
    caplog.set_level(logging.WARNING, logger="app.api.run_files")
    _make_stage(runs_root, files={"doc.pdf": b"%PDF-1.4"})

    await ingest_staged_uploads(
        user_id=_USER, workspace_id=None, run_id=_RUN, stage_ids=[_STAGE]
    )

    persist_documents.assert_awaited_once()
    assert not any(_ABSENT in w for w in _warnings(caplog))


async def test_ingest_staged_uploads_no_manifest_warning_when_no_stage_ids(
    runs_root, persist_documents, caplog
):
    caplog.set_level(logging.WARNING, logger="app.api.run_files")

    await ingest_staged_uploads(
        user_id=_USER, workspace_id=None, run_id=_RUN, stage_ids=[]
    )

    assert _warnings(caplog) == []
