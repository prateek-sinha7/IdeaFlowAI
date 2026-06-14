"""Unit tests for agents/workflows/manifest.py — load_manifest + validation.

Covers MAN-01 / D-08 / D-10:
  - A well-formed workflow.yaml loads into a populated WorkflowManifest.
  - A manifest missing each required field raises ManifestValidationError that
    NAMES the offending field (MAN-01).
  - A manifest with an unknown/extra top-level key is rejected, naming the key
    (D-08 / INV-5 — a control-flow field has nowhere to live).
  - steps: [] is valid (reverse_engineer empty-plan stub, D-05).
  - The loader uses yaml.safe_load — a YAML !!python/object tag is NOT
    constructed (T-04-03).
  - A missing workflow.yaml raises FileNotFoundError.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.workflows.manifest import (
    ManifestValidationError,
    WorkflowManifest,
    load_manifest,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WELL_FORMED = """\
id: demo
planner: run
clarify:
  mode: auto
  defaults: [target_audience, scope]
deliverable:
  strategy: streamed_text
  name: output.md
context_providers: [previous_run]
seed_files: {}
version: 1
steps:
  - agent: demo-agent
    strategy: single_shot
"""


def _write_manifest(base_dir: Path, workflow_id: str, text: str) -> Path:
    """Write ``<base_dir>/<workflow_id>/workflow.yaml`` and return the dir."""
    wf_dir = base_dir / workflow_id
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / "workflow.yaml").write_text(text, encoding="utf-8")
    return base_dir


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_loads_well_formed_manifest(tmp_path: Path):
    base = _write_manifest(tmp_path, "demo", _WELL_FORMED)

    manifest = load_manifest("demo", base)

    assert isinstance(manifest, WorkflowManifest)
    assert manifest.id == "demo"
    assert manifest.planner == "run"
    assert manifest.clarify == {"mode": "auto", "defaults": ["target_audience", "scope"]}
    assert manifest.deliverable == {"strategy": "streamed_text", "name": "output.md"}
    assert manifest.context_providers == ["previous_run"]
    assert manifest.seed_files == {}
    assert manifest.version == 1
    assert isinstance(manifest.steps, list) and len(manifest.steps) == 1
    assert manifest.steps[0]["agent"] == "demo-agent"


# ---------------------------------------------------------------------------
# Missing required field — names the field (MAN-01)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("missing", ["id", "steps", "deliverable", "planner", "clarify"])
def test_missing_field_named(tmp_path: Path, missing: str):
    # Build a YAML doc omitting exactly one required field.
    lines = {
        "id": "id: demo",
        "planner": "planner: run",
        "clarify": "clarify: {mode: auto}",
        "deliverable": "deliverable: {strategy: streamed_text}",
        "steps": "steps: []",
    }
    doc = "\n".join(v for k, v in lines.items() if k != missing) + "\n"
    base = _write_manifest(tmp_path, "demo", doc)

    with pytest.raises(ManifestValidationError) as exc:
        load_manifest("demo", base)

    assert missing in str(exc.value), (
        f"error message must name the missing field {missing!r}: {exc.value}"
    )


# ---------------------------------------------------------------------------
# Optional catalog/presentation fields (Plan 20-01) — inert, additive
# ---------------------------------------------------------------------------


def test_loads_optional_catalog_fields(tmp_path: Path):
    # A manifest declaring all 5 new keys parses each into its typed field.
    doc = _WELL_FORMED + (
        "user_launchable: true\n"
        "display_name: Demo Workflow\n"
        "description: A demo\n"
        "icon: rocket\n"
        "launch_surface: wizard\n"
    )
    base = _write_manifest(tmp_path, "demo", doc)

    m = load_manifest("demo", base)

    assert m.user_launchable is True
    assert m.display_name == "Demo Workflow"
    assert m.description == "A demo"
    assert m.icon == "rocket"
    assert m.launch_surface == "wizard"


def test_optional_catalog_fields_default_when_absent(tmp_path: Path):
    # The well-formed manifest declares NONE of the 5 keys → defaults.
    base = _write_manifest(tmp_path, "demo", _WELL_FORMED)

    m = load_manifest("demo", base)

    assert m.user_launchable is False
    assert m.display_name is None
    assert m.description is None
    assert m.icon is None
    assert m.launch_surface is None


def test_user_launchable_rejects_non_bool(tmp_path: Path):
    # bool is an int subclass; `user_launchable: 1` (an int) must NOT be silently
    # accepted as truthy — the helper accepts only real bools and names the field.
    doc = _WELL_FORMED + "user_launchable: 1\n"
    base = _write_manifest(tmp_path, "demo", doc)

    with pytest.raises(ManifestValidationError) as exc:
        load_manifest("demo", base)

    assert "user_launchable" in str(exc.value), (
        f"error message must name 'user_launchable': {exc.value}"
    )


def test_display_name_rejects_non_str(tmp_path: Path):
    # A non-string display_name is rejected, naming the field.
    doc = _WELL_FORMED + "display_name:\n  - not\n  - a\n  - string\n"
    base = _write_manifest(tmp_path, "demo", doc)

    with pytest.raises(ManifestValidationError) as exc:
        load_manifest("demo", base)

    assert "display_name" in str(exc.value), (
        f"error message must name 'display_name': {exc.value}"
    )


# ---------------------------------------------------------------------------
# Strict-key rejection — names the unknown key (D-08 / INV-5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_key", ["when", "if", "for", "expr"])
def test_rejects_unknown_key(tmp_path: Path, bad_key: str):
    doc = _WELL_FORMED + f"{bad_key}: something\n"
    base = _write_manifest(tmp_path, "demo", doc)

    with pytest.raises(ManifestValidationError) as exc:
        load_manifest("demo", base)

    assert bad_key in str(exc.value), (
        f"error message must name the unknown key {bad_key!r}: {exc.value}"
    )


# ---------------------------------------------------------------------------
# Empty steps is valid (reverse_engineer stub, D-05)
# ---------------------------------------------------------------------------


def test_empty_steps_ok(tmp_path: Path):
    doc = """\
id: reverse_engineer
planner: run
clarify: {mode: auto}
deliverable: {strategy: streamed_text}
steps: []
"""
    base = _write_manifest(tmp_path, "reverse_engineer", doc)

    manifest = load_manifest("reverse_engineer", base)

    assert manifest.steps == []


def test_steps_must_be_a_list(tmp_path: Path):
    doc = """\
id: demo
planner: run
clarify: {mode: auto}
deliverable: {strategy: streamed_text}
steps: not-a-list
"""
    base = _write_manifest(tmp_path, "demo", doc)

    with pytest.raises(ManifestValidationError) as exc:
        load_manifest("demo", base)

    assert "steps" in str(exc.value)


# ---------------------------------------------------------------------------
# safe_load — no arbitrary-object construction (T-04-03)
# ---------------------------------------------------------------------------


def test_safe_load_rejects_python_object_tag(tmp_path: Path):
    # A !!python/object/apply tag would, under yaml.load/FullLoader, construct an
    # arbitrary object (RCE surface). yaml.safe_load raises a ConstructorError
    # instead of building it.
    doc = """\
id: demo
planner: run
clarify: {mode: auto}
deliverable: {strategy: streamed_text}
steps: !!python/object/apply:os.system ["echo pwned"]
"""
    base = _write_manifest(tmp_path, "demo", doc)

    # Either the YAML parser refuses the tag (ConstructorError, the safe_load
    # signal) or — if a future loader catches it — a ManifestValidationError.
    # In NO case must os.system be invoked / the object be constructed.
    with pytest.raises(Exception) as exc:
        load_manifest("demo", base)

    # The safe loader names the unconstructable tag; assert it did not silently
    # build a list of one constructed object.
    assert "python/object" in str(exc.value) or isinstance(
        exc.value, ManifestValidationError
    )


# ---------------------------------------------------------------------------
# Missing file
# ---------------------------------------------------------------------------


def test_missing_workflow_yaml_raises_file_not_found(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_manifest("does-not-exist", tmp_path)


def test_non_mapping_top_level_rejected(tmp_path: Path):
    base = _write_manifest(tmp_path, "demo", "- just\n- a\n- list\n")

    with pytest.raises(ManifestValidationError):
        load_manifest("demo", base)
