"""Image-input Wave-3 opt-in delivery proof (quick-260707-gvq T3.3).

End-to-end proof that the DATA-ONLY opt-in (prototype manifest
``input_providers: [run_images]`` + ``prototype-specify`` ``injects:[…, images]``)
DELIVERS a multimodal image content-block through the REAL compiled plan + REAL
loaded specs — with zero kernel/engine edit (SC-001).

Two declaration pins + two behavioral arms:

  * pin A — ``compile_for_run("prototype").input_providers == ["run_images"]``.
  * pin B — ``"images" in load_agent_spec("prototype-specify").injects``.
  * DELIVERS — the opted-in order-1 spec-writer, with a populated
    ``ectx.run_images``, yields EXACTLY one base64 image block.
  * DORMANT control — a NON-opted agent (``prototype-plan``, no ``images``
    inject) with the SAME ``ectx`` yields ``[]`` (the per-agent-local gate holds
    after the opt-in — re-proves the T-gvq-02 information-disclosure boundary).

Mirrors the harness in ``test_image_input_wiring.py``: ``registry.discover()`` binds
the ``run_images`` impl, an ``ExecutionContext`` carries the run threads, and the
async ``ExecutionEngine._compose_input_blocks`` gate is driven directly.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agents.capabilities import registry as registry_mod
from agents.execution_engine.context import ExecutionContext
from agents.execution_engine.engine import ExecutionEngine, compile_for_run
from agents.loader import load_agent_spec


_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


# ---------------------------------------------------------------------------
# Declaration pins
# ---------------------------------------------------------------------------


def test_prototype_manifest_declares_run_images_input_provider() -> None:
    # pin A — the manifest opt-in compiles onto CompiledWorkflow.input_providers.
    compiled = compile_for_run("prototype")
    assert compiled.input_providers == ["run_images"]


def test_prototype_specify_declares_images_inject() -> None:
    # pin B — the order-1 spec-writer opts into image content-blocks.
    spec = load_agent_spec("prototype-specify")
    assert "images" in spec.injects


# ---------------------------------------------------------------------------
# Behavioral arms — REAL compiled plan + REAL loaded specs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_optin_delivers_image_block_for_real_specify_spec() -> None:
    registry_mod.discover()  # bind the run_images input_provider impl

    ectx = ExecutionContext(run_id="r-gvq", owner_id="o-gvq")
    ectx.run_images = [{"mime_type": "image/png", "data": _B64}]
    # Source the providers from the REAL compiled plan — not a literal.
    ectx.compiled_input_providers = compile_for_run("prototype").input_providers
    ectx.current_step = SimpleNamespace(injects=[])

    spec = load_agent_spec("prototype-specify")  # REAL spec (images in injects)
    blocks = await ExecutionEngine()._compose_input_blocks(spec, ectx)

    assert blocks == [
        {
            "type": "image",
            "source_type": "base64",
            "mime_type": "image/png",
            "data": _B64,
        }
    ]


@pytest.mark.asyncio
async def test_optin_dormant_for_non_opted_prototype_plan() -> None:
    # Control: prototype-plan does NOT declare images → [] even with the SAME
    # populated carrier + the same compiled input_providers (per-agent gate holds).
    registry_mod.discover()

    ectx = ExecutionContext(run_id="r-gvq2", owner_id="o-gvq2")
    ectx.run_images = [{"mime_type": "image/png", "data": _B64}]
    ectx.compiled_input_providers = compile_for_run("prototype").input_providers
    ectx.current_step = SimpleNamespace(injects=[])

    spec = load_agent_spec("prototype-plan")  # REAL spec (no images inject)
    assert "images" not in spec.injects
    assert await ExecutionEngine()._compose_input_blocks(spec, ectx) == []
