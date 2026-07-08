"""Tests for the ``context_provider:uploaded_files`` capability (UPLD-03 / 30-02).

Covers:
  * the provider is registered, resolvable, and keyed on the DECLARED capability
    name (``.name == "uploaded_files"``) — never a workflow name (SC-001/INV-1);
  * ``load(ctx)`` reads the run's OWN ``.uploads`` sidecar (via the ``ctx.runner``
    sandbox handle) and returns a ``{"uploaded_files_context": ...}`` block carrying
    the extracted doc text;
  * the self-gate on the ``uploaded_files`` inject token in
    ``ctx.current_spec_injects`` (mirrors opendesign's per-injects gate — T-30-08);
  * degrade-to-``{}`` on: un-gated inject, no sidecar (dormant), empty/corrupt
    manifest, missing sidecar text;
  * own-run-only reads (the provider resolves the sandbox strictly from the
    ``ctx.runner`` handle — no cross-owner / source_run_id path exists, T-30-06);
  * the registry lockstep — ``len(_KNOWN) == 66`` and the
    ``(context_provider, uploaded_files)`` pair is registered.

Task 2 adds the end-to-end sticky-context proof (present in EVERY agent_input) +
the SC-001 zero-engine-edit + INV-3 dormancy assertions, driving the engine's
generic ``_compose_context_message`` injector directly.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from agents.capabilities import registry as registry_mod
from agents.capabilities.registry import CapabilityRegistry, _KNOWN


_UPLOADS_PREFIX = ".uploads/"


# ── Fakes: an own-run sandbox + a runner handle carrying it ────────────────────


class _FakeSandbox:
    """In-memory stand-in for ``RunSandbox`` — ``read(relpath) -> str | None``.

    Mirrors the 30-01 contract: ``.uploads/manifest.json`` is a JSON array of
    ``{name, mime, has_text}`` entries; each extractable doc has a ``<name>.txt``
    sidecar. Missing file → ``None`` (the real ``RunSandbox.read`` contract).
    """

    def __init__(self, files: dict[str, str] | None = None) -> None:
        self._files = dict(files or {})

    def read(self, relpath: str) -> str | None:
        return self._files.get(relpath)

    def write(self, relpath: str, content: str) -> None:
        self._files[relpath] = content


def _stage_uploads(entries: list[dict], texts: dict[str, str]) -> _FakeSandbox:
    """Build a sandbox with a ``.uploads`` manifest + the given sidecar texts."""
    sb = _FakeSandbox()
    sb.write(f"{_UPLOADS_PREFIX}manifest.json", json.dumps(entries))
    for name, text in texts.items():
        sb.write(f"{_UPLOADS_PREFIX}{name}.txt", text)
    return sb


def _ctx(sandbox, *, injects=("uploaded_files",)):
    runner = SimpleNamespace(sandbox=sandbox)
    return SimpleNamespace(
        runner=runner,
        current_spec_injects=set(injects),
        run_id="r-upld-1",
        user_id="o-upld-1",
    )


def _load(ctx):
    from agents.capabilities.context_providers.uploaded_files import (
        UploadedFilesProvider,
    )

    provider = UploadedFilesProvider()
    assert provider.name == "uploaded_files"
    return asyncio.run(provider.load(ctx))


# ── provider behavior ──────────────────────────────────────────────────────────


def test_provider_surfaces_uploaded_doc_text() -> None:
    sb = _stage_uploads(
        [{"name": "brief.pdf", "mime": "application/pdf", "has_text": True}],
        {"brief.pdf": "The product brief: build a dark-theme dashboard."},
    )
    blocks = _load(_ctx(sb))
    assert set(blocks) == {"uploaded_files_context"}
    body = blocks["uploaded_files_context"]
    assert "build a dark-theme dashboard" in body
    assert "brief.pdf" in body


def test_provider_composes_multiple_docs_in_order() -> None:
    sb = _stage_uploads(
        [
            {"name": "a.pdf", "mime": "application/pdf", "has_text": True},
            {"name": "b.docx", "mime": "application/x", "has_text": True},
        ],
        {"a.pdf": "ALPHA TEXT", "b.docx": "BETA TEXT"},
    )
    body = _load(_ctx(sb))["uploaded_files_context"]
    assert "ALPHA TEXT" in body and "BETA TEXT" in body
    assert body.index("ALPHA TEXT") < body.index("BETA TEXT")


def test_self_gate_returns_empty_when_inject_absent() -> None:
    sb = _stage_uploads(
        [{"name": "brief.pdf", "mime": "application/pdf", "has_text": True}],
        {"brief.pdf": "should never surface"},
    )
    # current_spec_injects lacks the uploaded_files token → {} (T-30-08 self-gate).
    assert _load(_ctx(sb, injects=())) == {}
    assert _load(_ctx(sb, injects=("images", "template"))) == {}


def test_dormant_when_no_sidecar() -> None:
    # No .uploads/manifest.json staged → provider degrades to {} (dormant).
    assert _load(_ctx(_FakeSandbox())) == {}


def test_empty_manifest_returns_empty() -> None:
    sb = _FakeSandbox()
    sb.write(f"{_UPLOADS_PREFIX}manifest.json", json.dumps([]))
    assert _load(_ctx(sb)) == {}


def test_corrupt_manifest_degrades_to_empty() -> None:
    sb = _FakeSandbox()
    sb.write(f"{_UPLOADS_PREFIX}manifest.json", "{ this is not json")
    assert _load(_ctx(sb)) == {}


def test_entry_without_text_is_skipped() -> None:
    # has_text False (or a missing sidecar) contributes no section → dormant.
    sb = _stage_uploads(
        [{"name": "logo.png", "mime": "image/png", "has_text": False}],
        {},
    )
    assert _load(_ctx(sb)) == {}


def test_missing_sidecar_text_is_skipped() -> None:
    # Manifest claims text but the sidecar is absent → that entry is skipped.
    sb = _FakeSandbox()
    sb.write(
        f"{_UPLOADS_PREFIX}manifest.json",
        json.dumps([{"name": "brief.pdf", "mime": "application/pdf", "has_text": True}]),
    )
    assert _load(_ctx(sb)) == {}


def test_no_runner_handle_degrades_to_empty() -> None:
    ctx = SimpleNamespace(current_spec_injects={"uploaded_files"})
    assert _load(ctx) == {}


def test_reads_only_own_run_sandbox_no_cross_owner_path() -> None:
    # T-30-06: the provider must reach disk ONLY via the ctx.runner sandbox handle
    # (the own-run sandbox). It must NOT honor any source_run_id / cross-owner
    # accessor. A ctx carrying a decoy foreign sandbox on an unrelated attr must be
    # ignored — only ctx.runner.sandbox is consulted.
    own = _stage_uploads(
        [{"name": "own.pdf", "mime": "application/pdf", "has_text": True}],
        {"own.pdf": "OWN RUN TEXT"},
    )
    foreign = _stage_uploads(
        [{"name": "foreign.pdf", "mime": "application/pdf", "has_text": True}],
        {"foreign.pdf": "FOREIGN OWNER SECRET"},
    )
    ctx = _ctx(own)
    ctx.source_run_id = "another-owners-run"
    ctx.foreign_sandbox = foreign
    body = _load(ctx)["uploaded_files_context"]
    assert "OWN RUN TEXT" in body
    assert "FOREIGN OWNER SECRET" not in body


# ── registry lockstep ──────────────────────────────────────────────────────────


def test_uploaded_files_is_registered_and_resolves() -> None:
    registry_mod.discover()
    reg = CapabilityRegistry()
    assert reg.is_registered("context_provider", "uploaded_files") is True
    impl = reg.resolve("context_provider", "uploaded_files")
    assert getattr(impl, "name", None) == "uploaded_files"


def test_known_count_is_sixty_six() -> None:
    assert len(_KNOWN) == 66
    assert ("context_provider", "uploaded_files") in _KNOWN
