"""Property tests for the change summary and the launch needs.

# Feature: ai-workflow-builder, Property 10: Change summary and launch needs are exact

For any manifest, the change summary from that manifest to itself is empty.
For any pair of manifests, ``added`` and ``removed`` are exactly the
differences of their step keys and ``reordered`` is true if and only if the
common keys appear in a different relative order. For any manifest, the launch
needs are exactly those its declared providers, tool sets, MCP and integration
entries and ``seed_files`` call for, and adding such a declaration never
removes a need.

**Validates: Requirements 7.7, 7.13, 23.17**

The oracles in this file are written from design 3.5.4 and do not call the
production helpers. Generated manifests give every step of one level a unique
key, so the ``#2`` suffix rule for repeated keys (task 9.4) is not exercised
here; the self-comparison test uses manifests with repeated and missing keys.
Key pools are small so two generated manifests often share steps.
"""

from __future__ import annotations

import copy
from collections.abc import Iterator, Mapping
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from app.agents.workflow_builder.change_summary import summarize
from app.agents.workflow_builder.launch_needs import derive

# --- change summary: strategies ---------------------------------------------

_AGENTS = ["agent-a", "agent-b", "agent-c"]
_INSTANCES = ["inst-1", "inst-2", "inst-3"]

_GATES = st.one_of(
    st.none(),
    st.just([]),
    st.lists(st.sampled_from(["g1", "g2"]), min_size=1, max_size=2),
)
_VALIDATORS = st.one_of(
    st.none(),
    st.just([]),
    st.lists(st.sampled_from(["v1", "v2"]), min_size=1, max_size=2),
)
_MODELS = st.one_of(st.none(), st.sampled_from(["model-1", "model-2"]))
_PROMPTS = st.one_of(st.none(), st.sampled_from(["", "prompt one", "prompt two"]))

_FIELDS = ("gates", "validators", "model", "prompt")


def _own_key(step: Mapping[str, Any]) -> str:
    """Key of a generated step: its instance id for custom agents, else its agent."""
    if step["agent"] == "custom-agent":
        return str(step["instance_id"])
    return str(step["agent"])


@st.composite
def _step(draw: st.DrawFn, depth: int) -> dict[str, Any]:
    """One step with a known key, optional change-tracked fields and sub-steps."""
    if draw(st.booleans()):
        step: dict[str, Any] = {
            "agent": "custom-agent",
            "instance_id": draw(st.sampled_from(_INSTANCES)),
        }
    else:
        step = {"agent": draw(st.sampled_from(_AGENTS))}
    for field, strategy in (
        ("gates", _GATES),
        ("validators", _VALIDATORS),
        ("model", _MODELS),
        ("prompt", _PROMPTS),
    ):
        if draw(st.booleans()):
            step[field] = draw(strategy)
    if depth > 0 and draw(st.booleans()):
        step["subagents"] = {"steps": draw(_steps(depth - 1))}
    return step


def _steps(depth: int, min_size: int = 0) -> st.SearchStrategy[list[dict[str, Any]]]:
    """A step list whose members have unique keys."""
    return st.lists(_step(depth), min_size=min_size, max_size=4, unique_by=_own_key)


_MANIFESTS = st.one_of(
    st.just({}),
    st.builds(lambda steps: {"steps": steps}, _steps(2)),
)

_MESSY_STEP = st.fixed_dictionaries(
    {},
    optional={
        "agent": st.one_of(st.none(), st.sampled_from([*_AGENTS, "custom-agent"])),
        "instance_id": st.one_of(st.none(), st.sampled_from(["", *_INSTANCES])),
        "gates": _GATES,
        "validators": _VALIDATORS,
        "model": _MODELS,
        "prompt": _PROMPTS,
        "tools": st.one_of(st.none(), st.just({"exec": False, "read_files": True})),
    },
)
_MESSY_MANIFESTS = st.builds(
    lambda steps, extra: {"steps": steps, **extra},
    st.lists(_MESSY_STEP, max_size=5),
    st.dictionaries(
        st.sampled_from(["name", "description"]), st.text(max_size=5), max_size=2
    ),
)

# --- change summary: oracle -------------------------------------------------


def _flatten(
    steps: list[dict[str, Any]], prefix: str = ""
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Depth-first (key, step) pairs; a nested key is ``parent/child``."""
    for step in steps:
        key = f"{prefix}/{_own_key(step)}" if prefix else _own_key(step)
        yield key, step
        yield from _flatten((step.get("subagents") or {}).get("steps") or [], key)


def _keyed(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return dict(_flatten(manifest.get("steps") or []))


def _field(step: Mapping[str, Any], field: str) -> Any:
    """Field value as canonicalisation leaves it: null and an empty gates list are absent."""
    value = step.get(field)
    if value is None or (field == "gates" and value == []):
        return None
    return value


def _expected_summary(
    baseline: Mapping[str, Any], draft: Mapping[str, Any]
) -> dict[str, Any]:
    before = _keyed(baseline)
    after = _keyed(draft)
    common = [key for key in after if key in before]
    shared_in_baseline = [key for key in before if key in after]

    def differing(field: str) -> list[str]:
        return [
            key
            for key in common
            if _field(before[key], field) != _field(after[key], field)
        ]

    return {
        "added": [key for key in after if key not in before],
        "removed": [key for key in before if key not in after],
        "reordered": shared_in_baseline != common,
        "gates_changed": differing("gates"),
        "validators_changed": differing("validators"),
        "models_changed": differing("model"),
        "prompts_changed": len(differing("prompt")),
    }


# --- change summary: properties ---------------------------------------------


@settings(max_examples=100, deadline=None)
@given(manifest=st.one_of(_MANIFESTS, _MESSY_MANIFESTS))
def test_summarize_is_empty_when_manifest_compared_with_itself(
    manifest: dict[str, Any],
) -> None:
    summary = summarize(manifest, copy.deepcopy(manifest))

    assert summary.added == []
    assert summary.removed == []
    assert summary.reordered is False
    assert summary.gates_changed == []
    assert summary.validators_changed == []
    assert summary.models_changed == []
    assert summary.prompts_changed == 0


@settings(max_examples=100, deadline=None)
@given(baseline=_MANIFESTS, draft=_MANIFESTS)
def test_summarize_matches_oracle_when_manifests_differ(
    baseline: dict[str, Any], draft: dict[str, Any]
) -> None:
    baseline_before = copy.deepcopy(baseline)
    draft_before = copy.deepcopy(draft)

    summary = summarize(baseline, draft)

    assert summary.model_dump() == _expected_summary(baseline, draft)
    assert baseline == baseline_before
    assert draft == draft_before


@settings(max_examples=100, deadline=None)
@given(data=st.data(), steps=_steps(2, min_size=2))
def test_summarize_reordered_only_when_steps_permuted(
    data: st.DataObject, steps: list[dict[str, Any]]
) -> None:
    order = data.draw(st.permutations(range(len(steps))))
    baseline = {"steps": steps}
    draft = {"steps": [copy.deepcopy(steps[index]) for index in order]}

    summary = summarize(baseline, draft)

    assert summary.reordered is (list(order) != list(range(len(steps))))
    assert summary.added == []
    assert summary.removed == []
    assert summary.gates_changed == []
    assert summary.validators_changed == []
    assert summary.models_changed == []
    assert summary.prompts_changed == 0


# --- launch needs: strategies -----------------------------------------------

_PROVIDERS = ["uploaded_files", "opendesign", "previous_run", "web_search"]
_TOOL_SETS = ["file_extract", "web_fetch", "code_search"]
_SERVERS = ["github", "jira", "notion"]
_SCOPES = ["github_read", "gitlab_read", "jira_read", "slack_post", "linear"]

# Restated from design 3.5.4 and the catalog "Integration scopes" (task 9.4).
_SCOPE_SERVER = {
    "github_read": "github",
    "gitlab_read": "gitlab",
    "jira_read": "jira",
    "slack_post": "slack",
}

_MCP_ENTRIES = st.builds(
    lambda server, tool: f"{server}.{tool}",
    st.sampled_from(_SERVERS),
    st.sampled_from(["read", "search"]),
)
_TOOLS = st.fixed_dictionaries(
    {},
    optional={
        "tool_sets": st.lists(st.sampled_from(_TOOL_SETS), max_size=3),
        "mcp": st.lists(_MCP_ENTRIES, max_size=3),
        "integrations": st.lists(st.sampled_from(_SCOPES), max_size=3),
        "exec": st.booleans(),
    },
)


@st.composite
def _need_step(draw: st.DrawFn, depth: int) -> dict[str, Any]:
    step: dict[str, Any] = {"agent": draw(st.sampled_from(_AGENTS))}
    if draw(st.booleans()):
        step["tools"] = draw(_TOOLS)
    if depth > 0 and draw(st.booleans()):
        step["subagents"] = {"steps": draw(st.lists(_need_step(depth - 1), max_size=2))}
    return step


@st.composite
def _need_manifests(draw: st.DrawFn, min_steps: int = 0) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "steps": draw(st.lists(_need_step(2), min_size=min_steps, max_size=3)),
    }
    if draw(st.booleans()):
        manifest["context_providers"] = draw(
            st.lists(st.sampled_from(_PROVIDERS), max_size=3, unique=True)
        )
    if draw(st.booleans()):
        seed: dict[str, Any] = {}
        if draw(st.booleans()):
            seed["from_run"] = draw(
                st.one_of(
                    st.none(), st.lists(st.sampled_from(["run-1", "run-2"]), max_size=2)
                )
            )
        if draw(st.booleans()):
            seed["previous_run"] = draw(st.sampled_from(["run-9", ""]))
        manifest["seed_files"] = seed
    return manifest


# --- launch needs: oracle ---------------------------------------------------


def _all_steps(steps: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    for step in steps:
        yield step
        yield from _all_steps((step.get("subagents") or {}).get("steps") or [])


def _expected_needs(manifest: Mapping[str, Any]) -> list[tuple[str, str | None]]:
    """Needs in the documented order: uploads, design, connectors by name, source run."""
    providers = set(manifest.get("context_providers") or [])
    steps = list(_all_steps(manifest.get("steps") or []))
    tools = [step.get("tools") or {} for step in steps]

    expected: list[tuple[str, str | None]] = []
    if "uploaded_files" in providers or any(
        "file_extract" in t.get("tool_sets", []) for t in tools
    ):
        expected.append(("uploads", None))
    if "opendesign" in providers:
        expected.append(("design", None))

    servers = {entry.split(".")[0] for t in tools for entry in t.get("mcp", [])}
    servers |= {
        _SCOPE_SERVER.get(scope, scope)
        for t in tools
        for scope in t.get("integrations", [])
    }
    expected.extend(("connector", name) for name in sorted(servers))

    if (manifest.get("seed_files") or {}).get("from_run"):
        expected.append(("source_run", None))
    return expected


def _as_pairs(manifest: Mapping[str, Any]) -> list[tuple[str, str | None]]:
    return [(need.kind, need.detail) for need in derive(manifest)]


# --- launch needs: properties -----------------------------------------------


@settings(max_examples=100, deadline=None)
@given(manifest=_need_manifests())
def test_derive_matches_oracle_when_manifest_declares_needs(
    manifest: dict[str, Any],
) -> None:
    before = copy.deepcopy(manifest)

    pairs = _as_pairs(manifest)

    assert pairs == _expected_needs(manifest)
    assert len(pairs) == len(set(pairs))
    assert manifest == before


@settings(max_examples=100, deadline=None)
@given(
    data=st.data(),
    manifest=_need_manifests(min_steps=1),
    declaration=st.sampled_from(
        [
            "uploaded_files",
            "opendesign",
            "file_extract",
            "mcp",
            "integration",
            "from_run",
        ]
    ),
)
def test_derive_keeps_every_need_when_declaration_added(
    data: st.DataObject, manifest: dict[str, Any], declaration: str
) -> None:
    extended = copy.deepcopy(manifest)
    step = extended["steps"][0]
    tools = step.setdefault("tools", {})
    if declaration in ("uploaded_files", "opendesign"):
        extended["context_providers"] = [
            *extended.get("context_providers", []),
            declaration,
        ]
    elif declaration == "file_extract":
        tools["tool_sets"] = [*tools.get("tool_sets", []), "file_extract"]
    elif declaration == "mcp":
        tools["mcp"] = [*tools.get("mcp", []), data.draw(_MCP_ENTRIES)]
    elif declaration == "integration":
        tools["integrations"] = [
            *tools.get("integrations", []),
            data.draw(st.sampled_from(_SCOPES)),
        ]
    else:
        seed = dict(extended.get("seed_files") or {})
        seed["from_run"] = [*(seed.get("from_run") or []), "run-added"]
        extended["seed_files"] = seed

    before = set(_as_pairs(manifest))
    after_pairs = _as_pairs(extended)

    assert before <= set(after_pairs)
    assert after_pairs == _expected_needs(extended)
