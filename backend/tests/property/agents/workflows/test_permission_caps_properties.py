"""Hypothesis invariants for the connected-app decisions in ``permission_caps``.

For any trust value and any grant list: effective connectors are non-empty only
for ``db``/``user``; the selections overlay never adds connectors to a plan that
does not admit them; the run-level union and the per-step filter never widen a
grant.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from agents.workflows import permission_caps as caps
from agents.workflows.plan import CompiledWorkflow, Step, ToolPermissions
from tests.property.budget import examples

_ADMITTED = {"db", "user"}

_trust = st.one_of(
    st.sampled_from(["db", "user", "file", "builtin", "", "DB", "User", "admin"]),
    st.none(),
    st.text(max_size=12),
)
_name = st.from_regex(r"[a-z][a-z0-9_]{0,10}__[a-z][a-z0-9_]{0,15}", fullmatch=True)
_grant = st.lists(_name, max_size=12)
_bools = st.booleans()


def _tools(connectors: list[str]) -> ToolPermissions:
    return ToolPermissions(connectors=list(connectors))


def _plan(grants: list[list[str]], *, admits: bool) -> CompiledWorkflow:
    steps = [Step(agent_id=f"agent-{i}", tools=_tools(g)) for i, g in enumerate(grants)]
    return CompiledWorkflow(id="demo", steps=steps, admits_connector_grants=admits)


@settings(max_examples=examples(200, quick=50))
@given(trust=_trust, grant=_grant)
def test_apply_cap_leaves_connectors_only_when_trust_is_db_or_user(
    trust: str | None, grant: list[str]
) -> None:
    effective = caps.apply_cap(_tools(grant), trust)

    if trust in _ADMITTED:
        assert effective.connectors == grant
    else:
        assert effective.connectors == []


@settings(max_examples=examples(200, quick=50))
@given(trust=_trust, grant=_grant)
def test_apply_cap_never_adds_a_name_when_resolving(
    trust: str | None, grant: list[str]
) -> None:
    effective = caps.apply_cap(_tools(grant), trust)

    assert set(effective.connectors) <= set(grant)


@settings(max_examples=examples(200, quick=50))
@given(trust=_trust)
def test_connector_grants_permitted_matches_the_trust_set_when_any_value(
    trust: str | None,
) -> None:
    assert caps.connector_grants_permitted(trust) is (trust in _ADMITTED)


@settings(max_examples=examples(100, quick=50))
@given(grant=_grant)
def test_apply_cap_does_not_mutate_the_request_when_resolving(
    grant: list[str],
) -> None:
    request = _tools(grant)

    effective = caps.apply_cap(request, "user")
    effective.connectors.append("extra__tool")

    assert request.connectors == grant


@settings(max_examples=examples(200, quick=50))
@given(
    named=st.fixed_dictionaries(
        {"connectors": _grant},
        optional={"write_files": _bools, "read_files": _bools},
    )
)
def test_overlay_tool_slots_drops_connectors_when_plan_does_not_admit(
    named: dict,
) -> None:
    overlay = caps.overlay_tool_slots(named, admits=False)

    assert "connectors" not in overlay
    assert overlay == {k: v for k, v in named.items() if k != "connectors"}


@settings(max_examples=examples(100, quick=50))
@given(
    named=st.fixed_dictionaries(
        {"connectors": _grant}, optional={"write_files": _bools}
    )
)
def test_overlay_tool_slots_keeps_every_slot_when_plan_admits(named: dict) -> None:
    overlay = caps.overlay_tool_slots(named, admits=True)

    assert overlay == named
    assert overlay is not named


@settings(max_examples=examples(200, quick=50))
@given(grants=st.lists(_grant, min_size=1, max_size=5))
def test_connector_tool_grants_is_empty_when_plan_does_not_admit(
    grants: list[list[str]],
) -> None:
    assert caps.connector_tool_grants(_plan(grants, admits=False)) == frozenset()


@settings(max_examples=examples(200, quick=50))
@given(grants=st.lists(_grant, min_size=1, max_size=5))
def test_connector_tool_grants_is_the_union_of_step_grants_when_plan_admits(
    grants: list[list[str]],
) -> None:
    expected = frozenset(name for grant in grants for name in grant)

    assert caps.connector_tool_grants(_plan(grants, admits=True)) == expected


@settings(max_examples=examples(100, quick=50))
@given(count=st.integers(min_value=1, max_value=5), admits=_bools)
def test_connector_tool_grants_is_empty_when_no_step_names_a_connector(
    count: int, admits: bool
) -> None:
    plan = _plan([[] for _ in range(count)], admits=admits)

    assert caps.connector_tool_grants(plan) == frozenset()


@settings(max_examples=examples(200, quick=50))
@given(grant=_grant, pool_names=st.lists(_name, max_size=12))
def test_bound_connector_tools_returns_only_granted_names_that_are_in_the_pool(
    grant: list[str], pool_names: list[str]
) -> None:
    pool = {name: object() for name in pool_names}

    bound = caps.bound_connector_tools(_tools(grant), pool)

    allowed = {id(pool[n]) for n in grant if n in pool}
    assert {id(tool) for tool in bound} == allowed
    assert len(bound) == len(allowed)


@settings(max_examples=examples(100, quick=50))
@given(pool_names=st.lists(_name, max_size=12))
def test_bound_connector_tools_returns_nothing_when_no_step_is_bound(
    pool_names: list[str],
) -> None:
    pool = {name: object() for name in pool_names}

    assert caps.bound_connector_tools(None, pool) == []


@settings(max_examples=examples(200, quick=50))
@given(grant=_grant, other=_grant)
def test_bound_connector_tools_never_returns_a_name_the_step_did_not_grant(
    grant: list[str], other: list[str]
) -> None:
    pool = {name: object() for name in [*grant, *other]}

    bound = caps.bound_connector_tools(_tools(grant), pool)

    assert {id(tool) for tool in bound} <= {id(pool[n]) for n in grant}


@settings(max_examples=examples(100, quick=50))
@given(grant=_grant)
def test_without_connector_grants_empties_the_grant_and_keeps_other_levers(
    grant: list[str],
) -> None:
    step = Step(
        agent_id="a", tools=ToolPermissions(write_files=True, connectors=list(grant))
    )

    stripped = caps.without_connector_grants(step)

    assert stripped.tools.connectors == []
    assert stripped.tools.write_files is True
    assert step.tools.connectors == grant
