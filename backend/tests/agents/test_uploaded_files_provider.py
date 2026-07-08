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
  * the registry lockstep — the ``_KNOWN`` drift-guard count matches (see the assert
    below) and the ``(context_provider, uploaded_files)`` pair is registered.

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


def test_known_count_is_sixty_eight() -> None:
    assert len(_KNOWN) == 68
    assert ("context_provider", "uploaded_files") in _KNOWN


# ── Task 2: end-to-end sticky proof + SC-001 zero-engine-edit + INV-3 dormancy ──
#
# Drives the engine's GENERIC ``_compose_context_message`` injector DIRECTLY with a
# scripted ``ExecutionContext`` (no live model / DB / Bedrock) — the SAME path the
# per-agent dispatch composes context through. A TEST-ONLY fixture "workflow" (a list
# of specs each declaring ``injects:[uploaded_files]`` + a run whose ``.uploads``
# sidecar is staged) proves the uploaded doc text is present in EVERY agent_input.
# No real manifest ships an uploaded_files opt-in, so the goldens stay dormant (INV-3).

from agents.execution_engine.context import ExecutionContext  # noqa: E402
from agents.execution_engine.engine import ExecutionEngine  # noqa: E402

_UPLOAD_TEXT = "PRODUCT BRIEF: build a dark-theme analytics dashboard for ops."
_OPT_IN_PROVIDERS = ["uploaded_files"]


def _spec(agent_id: str, *, injects=("uploaded_files",)):
    """A minimal agnostic spec: only ``injects`` opts into the provider loop."""
    return SimpleNamespace(
        id=agent_id, name=agent_id.title(), role="tester",
        injects=list(injects), tools=[], consumes=[],
    )


def _staged_ectx(providers=_OPT_IN_PROVIDERS) -> ExecutionContext:
    """An ExecutionContext whose own-run sandbox carries a staged .uploads sidecar."""
    sb = _stage_uploads(
        [{"name": "brief.pdf", "mime": "application/pdf", "has_text": True}],
        {"brief.pdf": _UPLOAD_TEXT},
    )
    ectx = ExecutionContext(run_id="r-sticky-1", owner_id="o-sticky-1")
    ectx.runner = SimpleNamespace(sandbox=sb)
    # The engine threads the run's declared context_providers onto ectx at run entry
    # (engine.py: ectx.compiled_context_providers = list(compiled.context_providers)).
    ectx.compiled_context_providers = list(providers)
    return ectx


async def _compose(engine, ectx, spec, ordered) -> str:
    return await engine._compose_context_message(
        spec=spec, index=ordered.index(spec), ordered_agents=ordered,
        user_message="build me a thing", planning_context={}, ectx=ectx,
    )


@pytest.mark.asyncio
async def test_uploaded_text_is_sticky_in_every_agent_input() -> None:
    # A 3-agent opted-in workflow: the uploaded doc text must appear in the composed
    # context for EVERY agent (sticky — the provider re-reads the durable sidecar each
    # dispatch), not just the first.
    engine = ExecutionEngine()
    ectx = _staged_ectx()
    ordered = [_spec("plan"), _spec("build"), _spec("review")]

    for spec in ordered:
        msg = await _compose(engine, ectx, spec, ordered)
        assert _UPLOAD_TEXT in msg, f"upload text missing from {spec.id} agent_input"
        assert "## Uploaded Files" in msg
        assert "brief.pdf" in msg


@pytest.mark.asyncio
async def test_non_opted_agent_gets_no_uploaded_block() -> None:
    # An agent that does NOT declare injects:[uploaded_files] must not see the block,
    # even in a workflow whose manifest declares the provider (T-30-08 stale-inject).
    engine = ExecutionEngine()
    ectx = _staged_ectx()
    opted = _spec("opted")
    bare = _spec("bare", injects=())
    ordered = [opted, bare]

    opted_msg = await _compose(engine, ectx, opted, ordered)
    bare_msg = await _compose(engine, ectx, bare, ordered)
    assert _UPLOAD_TEXT in opted_msg
    assert _UPLOAD_TEXT not in bare_msg
    assert "## Uploaded Files" not in bare_msg


@pytest.mark.asyncio
async def test_sc001_engine_has_zero_reference_to_the_capability() -> None:
    # SC-001: the capability is picked up PURELY via the existing generic
    # context_provider loop — the kernel knows nothing of it by name. Prove the engine
    # source carries ZERO textual reference to "uploaded_files" (no hardwiring): the
    # opt-in is manifest (context_providers:[uploaded_files]) + AGENT.md
    # (injects:[uploaded_files]) only, requiring no engine edit.
    import inspect
    import agents.execution_engine.engine as engine_mod

    source = inspect.getsource(engine_mod)
    assert "uploaded_files" not in source, (
        "engine.py references 'uploaded_files' — SC-001 requires zero engine coupling"
    )


@pytest.mark.asyncio
async def test_inv3_dormant_case_is_byte_identical_to_baseline() -> None:
    # INV-3 dormancy: a run that does NOT opt in (no uploaded_files in the compiled
    # context_providers) produces a context_message with NO uploaded-files block AND is
    # byte-identical to the pre-capability baseline (a run with the sidecar absent).
    engine = ExecutionEngine()
    spec = _spec("solo")
    ordered = [spec]

    # (a) provider NOT declared on the run (compiled_context_providers=[]), sidecar staged.
    dormant = _staged_ectx(providers=[])
    dormant_msg = await _compose(engine, ectx=dormant, spec=spec, ordered=ordered)

    # (b) pre-capability baseline: no provider, no sidecar at all.
    baseline_ectx = ExecutionContext(run_id="r-baseline", owner_id="o-baseline")
    baseline_ectx.runner = SimpleNamespace(sandbox=_FakeSandbox())
    baseline_ectx.compiled_context_providers = []
    baseline_msg = await _compose(engine, ectx=baseline_ectx, spec=spec, ordered=ordered)

    assert "## Uploaded Files" not in dormant_msg
    assert _UPLOAD_TEXT not in dormant_msg
    # Byte-identical: the dormant capability perturbs nothing (INV-3).
    assert dormant_msg == baseline_msg
