"""Tests for the image-input Wave-1 backend spine (260707-edw T1.1-T1.4).

Covers behavior set (a) from the plan:
  * the ``run_images`` ``input_provider`` capability shapes ``ctx.run_images`` into
    base64 multimodal content-blocks (or ``[]`` when empty), preserving order;
  * the module-level ``_normalize_run_images`` seam canonicalizes/drops carrier
    entries;
  * the registry lockstep — ``("input_provider","run_images")`` is registered,
    resolves to an impl whose ``.name == "run_images"``, and the ``_KNOWN`` drift-guard
    count matches (T1.4 also reconciled the pre-existing KAN-73 ``hook:audit_logger``
    drift; the count was later bumped for the 30-02 ``uploaded_files`` provider and the
    two 33 D-08 bounded-chat-history capabilities — see the assert below).

DORMANT: no workflow opts in this wave; these tests exercise the capability +
seam directly.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agents.capabilities import registry as registry_mod
from agents.capabilities.registry import CapabilityRegistry, _KNOWN


# --- run_images capability --------------------------------------------------


def _load(run_images):
    """Instantiate the capability and load blocks off a stub ctx."""
    from agents.capabilities.input_providers.run_images import RunImagesProvider

    ctx = SimpleNamespace(run_images=run_images)
    provider = RunImagesProvider()
    assert provider.name == "run_images"
    import asyncio

    return asyncio.run(provider.load(ctx))


def test_run_images_shapes_a_single_block() -> None:
    blocks = _load([{"mime_type": "image/png", "data": "AAAA"}])
    assert blocks == [
        {
            "type": "image",
            "source_type": "base64",
            "mime_type": "image/png",
            "data": "AAAA",
        }
    ]


def test_run_images_empty_none_absent_return_empty() -> None:
    assert _load([]) == []
    assert _load(None) == []
    # absent attr → []
    from agents.capabilities.input_providers.run_images import RunImagesProvider
    import asyncio

    assert asyncio.run(RunImagesProvider().load(SimpleNamespace())) == []


def test_run_images_preserves_order_for_multiple() -> None:
    blocks = _load(
        [
            {"mime_type": "image/png", "data": "AA"},
            {"mime_type": "image/jpeg", "data": "BB"},
            {"mime_type": "image/webp", "data": "CC"},
        ]
    )
    assert [b["data"] for b in blocks] == ["AA", "BB", "CC"]
    assert [b["mime_type"] for b in blocks] == ["image/png", "image/jpeg", "image/webp"]
    assert all(
        b["type"] == "image" and b["source_type"] == "base64" for b in blocks
    )


def test_run_images_capability_never_reads_current_spec_injects() -> None:
    # The stale-field leak vector: the capability must NOT gate on
    # ctx.current_spec_injects (gating is the caller's job, Task 3). A ctx whose
    # current_spec_injects is empty but run_images is populated still yields blocks.
    ctx = SimpleNamespace(
        run_images=[{"mime_type": "image/png", "data": "AA"}],
        current_spec_injects=set(),
    )
    from agents.capabilities.input_providers.run_images import RunImagesProvider
    import asyncio

    assert asyncio.run(RunImagesProvider().load(ctx)) != []


# --- _normalize_run_images seam ---------------------------------------------


def test_normalize_run_images_canonicalizes_and_drops() -> None:
    from agents.execution_engine.engine import _normalize_run_images

    out = _normalize_run_images(
        [
            {"name": "x.png", "mime_type": "image/png", "data": "AA"},
            {"mimeType": "image/jpeg", "data": "BB"},  # alias accepted
            {"mime_type": "image/gif"},  # missing data → dropped
            {"data": "CC"},  # missing mime → dropped
        ]
    )
    assert out == [
        {"mime_type": "image/png", "data": "AA"},
        {"mime_type": "image/jpeg", "data": "BB"},
    ]


def test_normalize_run_images_none_and_empty() -> None:
    from agents.execution_engine.engine import _normalize_run_images

    assert _normalize_run_images(None) == []
    assert _normalize_run_images([]) == []


# --- registry lockstep ------------------------------------------------------


def test_run_images_is_registered_and_resolves() -> None:
    registry_mod.discover()
    reg = CapabilityRegistry()
    assert reg.is_registered("input_provider", "run_images") is True
    impl = reg.resolve("input_provider", "run_images")
    assert getattr(impl, "name", None) == "run_images"


def test_known_count_is_sixty_eight() -> None:
    assert len(_KNOWN) == 68
