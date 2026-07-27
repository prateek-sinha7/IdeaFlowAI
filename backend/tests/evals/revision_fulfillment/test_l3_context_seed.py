"""L3 — context seeding via the ``previous_run`` provider (R-09 / D-06).

The provider (``agents/capabilities/context_providers/previous_run.py``) is
where the user's instruction is EXTRACTED from the framed message and becomes
``ctx.revision_instruction`` — the exact value the post-step fix-loop later
re-injects (L4) and the Phase-3 fulfillment check will judge against. If this
layer mis-parses, every downstream "did we fix it" signal judges the wrong
instruction.

Asserts, against the real provider with a stub runner/sandbox (no kernel):
  * ``ctx.revision_original_html`` == the framed EXISTING block;
  * the artifact is seeded into the sandbox under ``deliverable.name``;
  * ``ctx.revision_instruction`` == the framed REVISION REQUEST text;
  * the runner's message is slimmed to a file pointer (no giant inline HTML);
  * the declared-revision gate: ``is_revision_workflow=False`` seeds nothing;
  * parent reference files (design.md/spec.md) seed via ``read_parent_file``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.evals.conftest import FIXTURES_DIR

pytestmark = pytest.mark.eval

INSTRUCTION = "Make the Save button on Settings actually save"


def _framed(html: str) -> str:
    return (
        "=== REVISION REQUEST ===\n"
        f"{INSTRUCTION}\n"
        "=== END REQUEST ===\n\n"
        "=== EXISTING PROTOTYPE HTML ===\n"
        f"{html}\n"
        "=== END EXISTING HTML ==="
    )


class _DictSandbox:
    """Minimal sandbox stub: write() into a dict (the provider's only need)."""

    def __init__(self) -> None:
        self.files: dict[str, str] = {}

    def write(self, name: str, content: str) -> None:
        self.files[name] = content


class _StubRunner:
    def __init__(self, user_message: str, parent_files: dict[str, str] | None = None):
        self.user_message = user_message
        self.sandbox = _DictSandbox()
        self._parent_files = parent_files or {}

    def read_parent_file(self, parent_run_id: str, name: str) -> str:
        return self._parent_files.get(name, "")


class _StubDeliverable:
    name = "prototype.html"


class _Ctx:
    """Attribute-bag ctx (the provider reads everything via getattr)."""

    def __init__(self, runner, *, is_revision: bool = True, parent_run_id=None):
        self.runner = runner
        self.is_revision_workflow = is_revision
        self.parent_run_id = parent_run_id
        self.deliverable = _StubDeliverable()
        self.scoped_store = None
        self.seed_files = {}


@pytest.fixture
def mini_html() -> str:
    # .strip(): the provider's marker extraction strips surrounding whitespace
    # (framing artifact, not content) — the stashed/seeded HTML is the stripped
    # block, so the fixture comparison value matches that contract.
    return (FIXTURES_DIR / "mini_prototype.html").read_text(encoding="utf-8").strip()


@pytest.fixture
def provider():
    from agents.capabilities.context_providers.previous_run import PreviousRunProvider

    return PreviousRunProvider()


@pytest.mark.asyncio
async def test_original_html_and_instruction_stashed(provider, mini_html) -> None:
    ctx = _Ctx(_StubRunner(_framed(mini_html)))
    await provider.load(ctx)

    assert ctx.revision_original_html == mini_html
    assert ctx.revision_instruction == INSTRUCTION


@pytest.mark.asyncio
async def test_artifact_seeded_and_message_slimmed(provider, mini_html) -> None:
    runner = _StubRunner(_framed(mini_html))
    ctx = _Ctx(runner)
    await provider.load(ctx)

    # Seeded under the declared deliverable name, byte-identical.
    assert runner.sandbox.files["prototype.html"] == mini_html
    # Slimmed: the inline HTML replaced by a file pointer; instruction intact.
    assert "=== EXISTING PROTOTYPE HTML ===" not in runner.user_message
    assert "prototype.html" in runner.user_message
    assert INSTRUCTION in runner.user_message


@pytest.mark.asyncio
async def test_non_revision_workflow_never_seeds(provider, mini_html) -> None:
    """The declared-intent gate (WR-06): revises_existing=False → no seed,
    no stash — a stray parent_run_id on a forward build must do nothing."""
    runner = _StubRunner(_framed(mini_html))
    ctx = _Ctx(runner, is_revision=False, parent_run_id="stray-parent")
    await provider.load(ctx)

    assert runner.sandbox.files == {}
    assert getattr(ctx, "revision_instruction", None) is None


@pytest.mark.asyncio
async def test_parent_reference_files_seed(provider, mini_html) -> None:
    design = (FIXTURES_DIR / "design.md").read_text(encoding="utf-8")
    runner = _StubRunner(
        _framed(mini_html),
        parent_files={"design.md": design, "spec.md": "# Spec\nMini admin."},
    )
    ctx = _Ctx(runner, parent_run_id="parent-run-123")
    await provider.load(ctx)

    assert runner.sandbox.files.get("design.md") == design
    assert runner.sandbox.files.get("spec.md") == "# Spec\nMini admin."
