"""Context seeding via the ``previous_run`` provider (R-09 / D-06) —
pipeline-agnostic (formerly "L3").

The provider (``agents/capabilities/context_providers/previous_run.py``)
is, by its own module docstring, "Workflow-agnostic" — wired into 5
pipelines' manifests (app_builder_revision, od_ppt_revision,
prototype_revision, ppt_revision, user_stories_revision; grep-verified, see
PLAN.md's "Amendment 1"), not specific to any one of them. This is where
the user's instruction is EXTRACTED from the framed message and becomes
``ctx.revision_instruction`` — the exact value a fix-loop later re-injects
and any fulfillment check judges against. If this layer mis-parses, every
downstream "did we fix it" signal judges the wrong instruction.

The test fixture below is a small INLINE string, not any one pipeline's
real prototype fixture — the provider genuinely doesn't care what the
existing-artifact content IS (HTML, a deck outline, anything), only that it
round-trips through the framing markers unchanged. Reusing a prototype HTML
fixture here would have been an accidental, misleading coupling to one
pipeline's domain.

Asserts, against the real provider with a stub runner/sandbox (no kernel):
  * ``ctx.revision_original_html`` == the framed EXISTING block;
  * the artifact is seeded into the sandbox under ``deliverable.name``;
  * ``ctx.revision_instruction`` == the framed REVISION REQUEST text;
  * the runner's message is slimmed to a file pointer (no giant inline content);
  * the declared-revision gate: ``is_revision_workflow=False`` seeds nothing;
  * parent reference files (design.md/spec.md) seed via ``read_parent_file``.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.eval

INSTRUCTION = "Make the Save button on Settings actually save"

# Deliberately generic — the provider is content-agnostic (see module
# docstring above); this is NOT a prototype/HTML fixture on purpose.
# No trailing newline: the provider's marker extraction strips surrounding
# whitespace (framing artifact, not content), so the stashed/seeded value
# is the stripped block — this constant must already match that contract.
SAMPLE_ARTIFACT = "line one\nline two\nline three"


def _framed(content: str) -> str:
    return (
        "=== REVISION REQUEST ===\n"
        f"{INSTRUCTION}\n"
        "=== END REQUEST ===\n\n"
        "=== EXISTING PROTOTYPE HTML ===\n"
        f"{content}\n"
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
def provider():
    from agents.capabilities.context_providers.previous_run import PreviousRunProvider

    return PreviousRunProvider()


@pytest.mark.asyncio
async def test_original_content_and_instruction_stashed(provider) -> None:
    ctx = _Ctx(_StubRunner(_framed(SAMPLE_ARTIFACT)))
    await provider.load(ctx)

    assert ctx.revision_original_html == SAMPLE_ARTIFACT
    assert ctx.revision_instruction == INSTRUCTION


@pytest.mark.asyncio
async def test_artifact_seeded_and_message_slimmed(provider) -> None:
    runner = _StubRunner(_framed(SAMPLE_ARTIFACT))
    ctx = _Ctx(runner)
    await provider.load(ctx)

    # Seeded under the declared deliverable name, byte-identical.
    assert runner.sandbox.files["prototype.html"] == SAMPLE_ARTIFACT
    # Slimmed: the inline content replaced by a file pointer; instruction intact.
    assert "=== EXISTING PROTOTYPE HTML ===" not in runner.user_message
    assert "prototype.html" in runner.user_message
    assert INSTRUCTION in runner.user_message


@pytest.mark.asyncio
async def test_non_revision_workflow_never_seeds(provider) -> None:
    """The declared-intent gate (WR-06): revises_existing=False → no seed,
    no stash — a stray parent_run_id on a forward build must do nothing."""
    runner = _StubRunner(_framed(SAMPLE_ARTIFACT))
    ctx = _Ctx(runner, is_revision=False, parent_run_id="stray-parent")
    await provider.load(ctx)

    assert runner.sandbox.files == {}
    assert getattr(ctx, "revision_instruction", None) is None


@pytest.mark.asyncio
async def test_parent_reference_files_seed(provider) -> None:
    runner = _StubRunner(
        _framed(SAMPLE_ARTIFACT),
        parent_files={"design.md": "# Design\nsample tokens", "spec.md": "# Spec\nSample spec."},
    )
    ctx = _Ctx(runner, parent_run_id="parent-run-123")
    await provider.load(ctx)

    assert runner.sandbox.files.get("design.md") == "# Design\nsample tokens"
    assert runner.sandbox.files.get("spec.md") == "# Spec\nSample spec."
