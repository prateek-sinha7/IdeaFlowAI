"""ISS-1118 / QA-KB-103 - an unchanged override of a built-in must save.

The canvas sends the built-in's own engineer-only references (compaction,
post_step) back unchanged. ``compile_override_steps`` checks them at
trust="user" with no baseline and refuses them. Correct behaviour: a reference
the target built-in's own step already declares is admitted; one the user adds
is still refused.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from agents.workflows.manifest import load_manifest

_WF_DIR = Path(__file__).resolve().parents[2] / "agents" / "workflows"
_BUILTINS = [
    "app_builder",
    "prototype",
    "prototype_feature_revision",
    "prototype_large_revision",
    "prototype_revision",
]


@pytest.fixture
def registry():
    from agents.execution_engine.engine import _CAPABILITY_REGISTRY

    return _CAPABILITY_REGISTRY


@pytest.mark.issue("ISS-1118")
@pytest.mark.parametrize("wid", _BUILTINS)
def test_unchanged_builtin_steps_pass_user_trust_override(wid, registry):
    """ISS-1118 - the built-in's own steps, re-sent unchanged, must compile."""
    from agents.execution_engine.overrides import compile_override_steps

    steps = copy.deepcopy(list(load_manifest(wid, _WF_DIR).steps))
    compile_override_steps(wid, steps, registry)


@pytest.mark.issue("ISS-1118")
def test_added_engineer_only_ref_still_refused(registry):
    """Control: a compaction the file step does not declare stays refused."""
    from agents.execution_engine.overrides import compile_override_steps
    from agents.workflows.compiler import CompilerError

    steps = copy.deepcopy(list(load_manifest("prototype", _WF_DIR).steps))
    # drop the inherited ref from prototype-build, add it to a step that lacks it
    for s in steps:
        s.pop("compaction", None)
    steps[0]["compaction"] = "html_skeleton"
    with pytest.raises(CompilerError, match="not user-allowed"):
        compile_override_steps("prototype", steps, registry)
