"""Declared-signal od_context parity at the launch boundary — D-15/C (SC-001 / INV-1).

The launch boundary must load template/DS ``od_context`` keyed on the DECLARED manifest
signal (``context_providers: [opendesign]``), producing the SAME dict the old
pipeline-name branch (``pipeline_type == "od_prototype"/"od_ppt"``) produced. These pin
byte-identity across the Task-2 rewire, and are the INV-1 proof that the kernel keys on a
declared capability rather than a hardcoded workflow name.

Pure: resolves manifest context and compares dicts. No store, no HTTP, no engine — the
template/DS ids are offline-resolvable under ``skills/opendesign/design-templates``. The
ENDPOINT half of this file (pre-mint rejection, the mint, the driver, parent-link
ownership) counts real rows and lives in
``tests/integration/api/test_rest_run_launch_api.py``.
"""

from __future__ import annotations

import pytest


# ────────────────────────────────────────────────────────────────────────────
# 4. D-15/C — declared-signal od_context parity (SC-001 / INV-1)
#
# The launch boundary must load template/DS od_context keyed on the DECLARED
# manifest signal (``context_providers: [opendesign]``), producing the SAME dict
# the old pipeline-name branch (``pipeline_type == "od_prototype"/"od_ppt"``)
# produced. These pin byte-identity across the Task-2 rewire: the parity/None/
# rejection/REST-revision cases pass against the CURRENT name-branch and must keep
# passing against the declared-signal seam; the three ``resolve_launch_od_context``
# seam cases are the Task-2 gate (RED until the seam exists).
#
# AUDIT (Task-1 finding, contradicts RESEARCH A1 "two"): EXACTLY THREE manifests
# declare ``context_providers: [opendesign]`` — prototype, ppt, ppt_revision
# (formerly named od_ppt/od_ppt_revision — collapsed onto the ppt/ppt_revision
# ids, see agents/registry.py). The seam therefore preserves ppt_revision's
# per-boundary behavior: REST → None (this file), WS → non-fatal ppt loader
# (the seam ``fatal=False`` cases below).
# ────────────────────────────────────────────────────────────────────────────

# Offline-resolvable ids (present under skills/opendesign/design-templates).
_PROTO_TEMPLATE = "web-prototype"
_PROTO_DS = "material"
_PPT_TEMPLATE = "html-ppt"
_BAD_TEMPLATE = "definitely-not-a-real-template-xyz"


def _launch_body(**kw):
    from app.api.run_commands import LaunchCommand

    kw.setdefault("message", "build it")
    return LaunchCommand(**kw)


def test_prototype_launch_od_context_parity():
    """``prototype`` builds the SAME od_context dict ``load_prototype_od_context``
    produces directly.

    Was ``test_od_prototype_launch_od_context_parity``: the alias was the only label
    that could reach this, because eligibility excluded a base with a dedicated
    ``od_`` alias from its own declared ``opendesign`` capability. The plain name
    now does what the alias used to — this is the assertion that the collapse
    preserved the behaviour rather than dropping it."""
    from agents.execution_engine.od_context import load_prototype_od_context

    from app.api.run_commands import _resolve_launch_agents

    body = _launch_body(
        pipeline_type="prototype",
        template_id=_PROTO_TEMPLATE,
        design_system_id=_PROTO_DS,
    )
    base, od_context = _resolve_launch_agents(body)
    expected = load_prototype_od_context(
        _PROTO_TEMPLATE, _PROTO_DS, custom_ds_body=None, custom_template_body=None
    )
    assert base == "prototype"
    assert od_context == expected


def test_ppt_launch_od_context_parity():
    """ppt resolves base 'ppt' AND builds the SAME od_context dict
    ``load_ppt_od_context`` produces directly (declared-signal == name-branch)."""
    from agents.execution_engine.od_context import load_ppt_od_context

    from app.api.run_commands import _resolve_launch_agents

    body = _launch_body(pipeline_type="ppt", template_id=_PPT_TEMPLATE)
    base, od_context = _resolve_launch_agents(body)
    expected = load_ppt_od_context(
        _PPT_TEMPLATE, None, custom_ds_body=None, custom_template_body=None
    )
    assert base == "ppt"
    assert od_context == expected


def test_undeclared_pipeline_launches_with_none_od_context():
    """A pipeline whose resolved manifest does NOT declare opendesign
    (user_stories) launches with od_context = None — unchanged for all non-OD
    workflows."""
    from app.api.run_commands import _resolve_launch_agents

    body = _launch_body(pipeline_type="user_stories")
    base, od_context = _resolve_launch_agents(body)
    assert base == "user_stories"
    assert od_context is None


def test_unknown_pipeline_type_rejected_in_resolver():
    """An unknown/unsupported pipeline_type still rejects pre-mint with
    invalid_pipeline_type (rejection path preserved through the seam)."""
    from fastapi import HTTPException

    from app.api.run_commands import _resolve_launch_agents

    body = _launch_body(pipeline_type="totally_made_up")
    with pytest.raises(HTTPException) as ei:
        _resolve_launch_agents(body)
    assert ei.value.detail["code"] == "invalid_pipeline_type"


def test_ppt_revision_rest_keeps_none():
    """REST parity: ppt_revision (declares opendesign) does NOT load od_context
    on the REST boundary — preserved as None, matching today's fall-through
    (websocket.py loads it NON-FATALLY; the REST twin never did)."""
    from app.api.run_commands import _resolve_launch_agents

    body = _launch_body(pipeline_type="ppt_revision", template_id=_PPT_TEMPLATE)
    base, od_context = _resolve_launch_agents(body)
    assert base == "ppt_revision"
    assert od_context is None


# ── The seam cases (Task-2 gate — RED until launch_context.py exists) ──────────


def test_seam_prototype_parity_via_declared_signal():
    """The shared seam resolves ``prototype`` through the DECLARED opendesign signal
    to the SAME dict the loader produces (name-free eligibility).

    This is now eligibility's WHOLE rule. It used to carry a second clause excluding
    any base with a dedicated ``od_`` alias, which is what made this assertion pass
    for ``od_prototype`` and fail for ``prototype``."""
    from agents.execution_engine.od_context import load_prototype_od_context

    from app.api.launch_context import resolve_launch_od_context

    base, od_context = resolve_launch_od_context(
        "prototype",
        _PROTO_TEMPLATE,
        _PROTO_DS,
        custom_ds_body=None,
        custom_template_body=None,
        fatal=True,
    )
    expected = load_prototype_od_context(
        _PROTO_TEMPLATE, _PROTO_DS, custom_ds_body=None, custom_template_body=None
    )
    assert base == "prototype"
    assert od_context == expected


def test_seam_undeclared_returns_none():
    """A pipeline that does not declare opendesign resolves to od_context None
    through the seam (the SC-001 win — eligibility is the declared signal)."""
    from app.api.launch_context import resolve_launch_od_context

    base, od_context = resolve_launch_od_context(
        "user_stories",
        None,
        None,
        custom_ds_body=None,
        custom_template_body=None,
        fatal=True,
    )
    assert base == "user_stories"
    assert od_context is None


def test_seam_fatal_propagates_lookup_error():
    """On the fatal path a bad template raises LookupError so the caller shapes the
    rejection (V5 input-validation preserved)."""
    from app.api.launch_context import resolve_launch_od_context

    with pytest.raises(LookupError):
        resolve_launch_od_context(
            "ppt",
            _BAD_TEMPLATE,
            None,
            custom_ds_body=None,
            custom_template_body=None,
            fatal=True,
        )


def test_seam_ppt_revision_non_fatal_swallows_lookup_error():
    """WS arm parity: ppt_revision loads NON-FATALLY — a failing template lookup
    returns od_context None instead of raising (reproduces websocket.py:1741-1753)."""
    from app.api.launch_context import resolve_launch_od_context

    base, od_context = resolve_launch_od_context(
        "ppt_revision",
        _BAD_TEMPLATE,
        None,
        custom_ds_body=None,
        custom_template_body=None,
        fatal=False,
    )
    assert base == "ppt_revision"
    assert od_context is None


def test_seam_ppt_revision_non_fatal_loads_when_resolvable():
    """The non-fatal arm still LOADS the SAME od_context dict when the template
    resolves (ppt-family loader profile)."""
    from agents.execution_engine.od_context import load_ppt_od_context

    from app.api.launch_context import resolve_launch_od_context

    base, od_context = resolve_launch_od_context(
        "ppt_revision",
        _PPT_TEMPLATE,
        None,
        custom_ds_body=None,
        custom_template_body=None,
        fatal=False,
    )
    expected = load_ppt_od_context(
        _PPT_TEMPLATE, None, custom_ds_body=None, custom_template_body=None
    )
    assert base == "ppt_revision"
    assert od_context == expected
