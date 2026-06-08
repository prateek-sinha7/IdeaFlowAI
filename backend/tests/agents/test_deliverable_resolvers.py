"""Wave-0 unit tests for the four ``DeliverableResolver`` capabilities
(07-02 / PARITY-02 + PARITY-07).

Each resolver satisfies the ``DeliverableResolver`` port (``name`` attr +
``def resolve(self, ctx) -> Any``) and reaches the sandbox / serialize / count
ONLY through the ``ctx.runner`` handle (the D-03 KernelServices seam) — never a
direct ``app.*`` import. The resolvers choose the deliverable by
``deliverable.name`` / ``deliverable.strategy``, NEVER by a ``pipeline_type``
branch (INV-1).

The tests drive each resolver against a FAKE ``ctx.runner`` whose ``sandbox``
is a real temp ``RunSandbox`` so the serialize/count byte contract is exercised
against the live ``app.agents.sandbox`` helpers (reached via the handle).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.capabilities.deliverables.single_file import SingleFileResolver
from agents.capabilities.deliverables.serialized_sandbox import SerializedSandboxResolver
from agents.capabilities.deliverables.streamed_text import StreamedTextResolver
from agents.capabilities.deliverables.ppt import PptResolver
from app.agents.sandbox import (
    RunSandbox,
    count_sandbox_deliverables,
    serialize_sandbox_deliverable,
)


# ===========================================================================
# Fakes — a ctx + a ctx.runner handle whose sandbox is a real RunSandbox
# ===========================================================================


class _FakeRunner:
    """Minimal ctx.runner stand-in — exposes the sandbox + serialize/count.

    These three helpers (``sandbox`` / ``serialize_sandbox_deliverable`` /
    ``count_sandbox_deliverables``) are the surface the deliverable resolvers
    reach through the handle (NEVER a direct app.* import — Pitfall 4).
    """

    def __init__(self, sandbox) -> None:
        self.sandbox = sandbox

    def serialize_sandbox_deliverable(self, root):
        return serialize_sandbox_deliverable(root)

    def count_sandbox_deliverables(self, root):
        return count_sandbox_deliverables(root)


class _Deliverable:
    def __init__(self, name=None, strategy=None) -> None:
        self.name = name
        self.strategy = strategy


class _Ctx:
    """Minimal ExecutionContext stand-in for the resolvers."""

    def __init__(self, runner, *, deliverable=None, last_streamed="",
                 revision_original_html="") -> None:
        self.runner = runner
        self.deliverable = deliverable or _Deliverable()
        self.last_streamed = last_streamed
        self.revision_original_html = revision_original_html


@pytest.fixture
def sandbox(tmp_path):
    """A real RunSandbox rooted under a temp RUNS_ROOT."""
    return RunSandbox("tester", "run-deliv", runs_root=str(tmp_path))


# ===========================================================================
# SingleFileResolver — reads deliverable.name from the sandbox
# ===========================================================================


def test_single_file_reads_named_file_from_sandbox(sandbox):
    sandbox.write("prototype.html", "<!doctype html><html>built</html>")
    ctx = _Ctx(
        _FakeRunner(sandbox),
        deliverable=_Deliverable(name="prototype.html", strategy="single_file"),
        last_streamed="STREAMED",
    )
    out = SingleFileResolver().resolve(ctx)
    assert out == "<!doctype html><html>built</html>"


def test_single_file_default_name_is_prototype_html(sandbox):
    sandbox.write("prototype.html", "<html>default</html>")
    ctx = _Ctx(
        _FakeRunner(sandbox),
        deliverable=_Deliverable(strategy="single_file"),  # name omitted
    )
    assert SingleFileResolver().resolve(ctx) == "<html>default</html>"


def test_single_file_falls_back_to_last_streamed(sandbox):
    # File absent → fall back to last-streamed.
    ctx = _Ctx(
        _FakeRunner(sandbox),
        deliverable=_Deliverable(name="prototype.html"),
        last_streamed="<html>streamed</html>",
    )
    assert SingleFileResolver().resolve(ctx) == "<html>streamed</html>"


def test_single_file_falls_back_to_seeded_original_when_no_stream(sandbox):
    # File absent + no usable stream → the previous_run-seeded original.
    ctx = _Ctx(
        _FakeRunner(sandbox),
        deliverable=_Deliverable(name="prototype.html"),
        last_streamed="",
        revision_original_html="<html>ORIGINAL</html>",
    )
    assert SingleFileResolver().resolve(ctx) == "<html>ORIGINAL</html>"


def test_single_file_never_reads_pipeline_type(sandbox):
    # A ctx WITHOUT a pipeline_type attribute must still resolve (no branch on it).
    sandbox.write("prototype.html", "<html>ok</html>")
    ctx = _Ctx(_FakeRunner(sandbox), deliverable=_Deliverable(name="prototype.html"))
    assert not hasattr(ctx, "pipeline_type")
    assert SingleFileResolver().resolve(ctx) == "<html>ok</html>"


# ===========================================================================
# SerializedSandboxResolver — the code-gen filename:-block bundle
# ===========================================================================


def test_serialized_sandbox_returns_filename_block_bundle(sandbox):
    sandbox.write("a.py", "print('a')\n")
    sandbox.write("b.py", "print('b')\n")
    ctx = _Ctx(_FakeRunner(sandbox))
    out = SerializedSandboxResolver().resolve(ctx)
    # Byte-identical to the live serializer (the filename:-block UI contract).
    assert out == serialize_sandbox_deliverable(sandbox.root)
    assert "```filename: a.py" in out
    assert "```filename: b.py" in out


def test_serialized_sandbox_does_not_claim_when_empty(sandbox):
    # 0 deliverable files → the resolver does not claim it (count > 0 guard).
    ctx = _Ctx(_FakeRunner(sandbox))
    assert SerializedSandboxResolver().resolve(ctx) is None


# ===========================================================================
# StreamedTextResolver — _unwrap_artifact(last_streamed)
# ===========================================================================


def test_streamed_text_unwraps_artifact(sandbox):
    ctx = _Ctx(
        _FakeRunner(sandbox),
        last_streamed="<artifact>INNER DELIVERABLE</artifact>",
    )
    assert StreamedTextResolver().resolve(ctx) == "INNER DELIVERABLE"


def test_streamed_text_passthrough_without_wrapper(sandbox):
    ctx = _Ctx(_FakeRunner(sandbox), last_streamed="plain text deliverable")
    assert StreamedTextResolver().resolve(ctx) == "plain text deliverable"


# ===========================================================================
# PptResolver — carousel-sanitize + artifact-unwrap (owns BOTH behaviors)
# ===========================================================================


_CAROUSEL_DECK = """<!doctype html><html><head><style>
.stage { transform: translateX(-100vw); }
.slide { display: grid; }
.slide:not(.active) { display: none; }
</style></head><body>
<div class="stage"><section class="slide"></section><section class="slide"></section></div>
</body></html>"""


def test_ppt_strips_carousel_hiding_css(sandbox):
    ctx = _Ctx(_FakeRunner(sandbox), last_streamed=_CAROUSEL_DECK)
    out = PptResolver().resolve(ctx)
    # The slide-hiding rule that breaks the carousel is removed; the base
    # .slide{display:grid} the carousel relies on is preserved.
    assert ".slide:not(.active)" not in out
    assert "display: grid" in out


def test_ppt_unwraps_artifact_after_sanitize(sandbox):
    ctx = _Ctx(
        _FakeRunner(sandbox),
        last_streamed="<artifact>plain deck no carousel</artifact>",
    )
    assert PptResolver().resolve(ctx) == "plain deck no carousel"


def test_ppt_matches_engine_transform_byte_for_byte(sandbox):
    # The resolver's output equals the engine's _unwrap_artifact(_sanitize(...)).
    from agents.execution_engine.engine import (
        _sanitize_carousel_deck_html,
        _unwrap_artifact,
    )

    ctx = _Ctx(_FakeRunner(sandbox), last_streamed=_CAROUSEL_DECK)
    expected = _unwrap_artifact(_sanitize_carousel_deck_html(_CAROUSEL_DECK))
    assert PptResolver().resolve(ctx) == expected
