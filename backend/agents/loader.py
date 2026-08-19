"""agents/loader.py — reads and parses AGENT.md files from disk.

Public API:
    load_agent_spec(agent_id: str) -> AgentSpec
    list_agent_ids(pipeline_type: str) -> list[str]

Each agent lives in agents/prompts/{agent_id}/AGENT.md with YAML frontmatter
for metadata and a markdown body for the system prompt.

Caching: parsed AgentSpec instances are stored in the module-level
_SPEC_CACHE dict. Repeated calls for the same agent_id return the cached
instance without re-reading the file.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from pathlib import Path

import frontmatter  # python-frontmatter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# agents/ package root (this file lives in agents/)
_AGENTS_DIR = Path(__file__).resolve().parent
_PROMPTS_DIR = _AGENTS_DIR / "prompts"
_WORKFLOWS_DIR = _AGENTS_DIR / "workflows"

# NOTE: ``SUPPORTED_PIPELINE_TYPES`` is DERIVED from disk and is defined at the
# BOTTOM of this module — it calls ``list_agent_ids``-adjacent helpers that must
# already exist. See "Supported pipeline types" there.


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class AgentSpec:
    """Parsed representation of an AGENT.md file.

    Required fields must be supplied explicitly; optional fields have defaults
    that match the spec (tools=[], guardrails=[], context_from=[], icon="🤖",
    estimated_duration=3.0).

    Instances are immutable after construction — the loader caches them and
    never mutates them.
    """

    # ── Required ──────────────────────────────────────────────────────────
    id: str                    # kebab-case, matches directory name
    name: str                  # Human-readable display name
    role: str                  # Short role description for UI
    pipeline_type: str         # One of SUPPORTED_PIPELINE_TYPES
    order: int                 # Execution order within pipeline (ascending)
    max_tokens: int            # Output token limit (1–32768)
    prompt_body: str           # Raw markdown text after YAML closing ---

    # ── Optional with defaults ────────────────────────────────────────────
    tools: list[str] = field(default_factory=list)
    guardrails: list[str] = field(default_factory=list)
    context_from: list[str] = field(default_factory=list)
    icon: str = "🤖"
    estimated_duration: float = 3.0
    # Longer UI-facing blurb (API/frontend agent listings). Optional in the
    # frontmatter; when absent (the common case — most AGENT.md files omit it)
    # the loader falls back to `role` so this is always a non-empty string.
    description: str = ""

    # ── Phase 1 extensions — Typed Produces/Consumes contract model ───────
    # All optional with empty-list/None defaults for backward compatibility.
    # Existing AGENT.md files without these fields load unchanged.
    produces: list[str] = field(default_factory=list)   # Artifact_Types this agent produces
    consumes: list[str] = field(default_factory=list)   # Artifact_Types this agent requires
    gate: str | None = None                              # Human_Gate | Validation_Gate | None
    injects: list[str] = field(default_factory=list)    # subset of [template, design_system, craft]

    # ── Phase 6 extension — optional model id (D-09; MODEL-01) ───────────
    # Optional AGENT.md `model` id; absent → None. Backs tier 3 (agent-default)
    # of the resolver's model-precedence. Loader enforces a type guard only;
    # catalog-membership validation is deferred to RESOLVE time in 06-03.
    model: str | None = None

    # ── Template marker (spec 012, ADR-0005) ─────────────────────────────
    # ``template: true`` means this folder exists to be INSTANTIATED, never to
    # be a pipeline member: `custom-agent` is the blank agent a composed
    # workflow clones N times, each clone getting the synthetic id
    # ``<base>:<instance_id>`` minted by the compiler.
    #
    # This replaces the former hand-maintained template-id name list.
    # A template still has to declare a `pipeline_type` (every AGENT.md does),
    # but that declaration must NOT put it in a roster — before this flag the
    # only way to express that was to hardcode the id in the loader.
    template: bool = False


class AgentSpecError(Exception):
    """Raised when an AGENT.md file has invalid or missing fields."""


# ---------------------------------------------------------------------------
# Module-level cache
# ---------------------------------------------------------------------------

_SPEC_CACHE: dict[str, AgentSpec] = {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_agent_spec(agent_id: str) -> AgentSpec:
    """Read agents/prompts/{agent_id}/AGENT.md and return a parsed AgentSpec.

    Results are cached in _SPEC_CACHE; subsequent calls for the same agent_id
    return the cached instance without re-reading the file.

    Raises:
        FileNotFoundError: if the directory or AGENT.md does not exist.
        PermissionError: if the file cannot be read due to permissions.
        AgentSpecError: if a required field is missing or has an invalid value.
    """
    if agent_id in _SPEC_CACHE:
        return _SPEC_CACHE[agent_id]

    # ── Synthetic ids (custom-agent:<instance_id>) ──────────────────────────
    # Resolve the base spec through the normal path, then overlay the full
    # synthetic id. Display name / composed prompt are the factory's job
    # (T11) — the loader only reads files.
    if ":" in agent_id:
        base, _, _instance = agent_id.partition(":")
        base_spec = load_agent_spec(base)
        spec = replace(base_spec, id=agent_id)
        _SPEC_CACHE[agent_id] = spec
        return spec

    agent_dir = _PROMPTS_DIR / agent_id
    agent_file = agent_dir / "AGENT.md"

    # ── Existence checks ──────────────────────────────────────────────────
    if not agent_dir.exists():
        raise FileNotFoundError(
            f"Agent directory not found: {agent_dir}"
        )
    if not agent_file.exists():
        raise FileNotFoundError(
            f"AGENT.md not found: {agent_file}"
        )

    # ── Read file ─────────────────────────────────────────────────────────
    try:
        raw_text = agent_file.read_text(encoding="utf-8")
    except PermissionError as exc:
        raise PermissionError(
            f"Cannot read AGENT.md (permission denied): {agent_file}"
        ) from exc

    # ── Parse YAML frontmatter ────────────────────────────────────────────
    try:
        post = frontmatter.loads(raw_text)
    except Exception as exc:
        raise AgentSpecError(
            f"Failed to parse YAML frontmatter in {agent_file}: {exc}"
        ) from exc

    metadata = post.metadata
    prompt_body = post.content  # text after the closing ---

    # ── Validate and extract fields ───────────────────────────────────────
    spec = _build_spec(metadata, prompt_body, agent_file)

    _SPEC_CACHE[agent_id] = spec
    return spec


def list_agent_ids(pipeline_type: str) -> list[str]:
    """Return all agent IDs for the given pipeline_type, sorted by order ascending.

    Scans agents/prompts/ for all AGENT.md files whose pipeline_type field
    matches the given value.

    Returns an empty list if no agents match or the pipeline_type is unknown.

    Raises:
        AgentSpecError: if two agents in the same pipeline share the same order.
    """
    if not _PROMPTS_DIR.exists():
        return []

    matching: list[AgentSpec] = []

    for agent_dir in _PROMPTS_DIR.iterdir():
        if not agent_dir.is_dir():
            continue
        agent_file = agent_dir / "AGENT.md"
        if not agent_file.exists():
            continue
        try:
            spec = load_agent_spec(agent_dir.name)
        except (FileNotFoundError, PermissionError, AgentSpecError):
            # Skip agents that can't be loaded when scanning
            logger.warning(
                "Skipping agent %s during list_agent_ids scan (load failed)",
                agent_dir.name,
            )
            continue

        # ``template: true`` agents (e.g. custom-agent) exist to be
        # INSTANTIATED, never to be pipeline members — see AgentSpec.template.
        # This check must happen AFTER load_agent_spec: the flag lives in the
        # parsed spec, not in the directory name.
        if spec.template:
            continue

        if spec.pipeline_type == pipeline_type:
            matching.append(spec)

    # ── Duplicate order detection ─────────────────────────────────────────
    order_map: dict[int, str] = {}
    for spec in matching:
        if spec.order in order_map:
            raise AgentSpecError(
                f"Duplicate order={spec.order} within pipeline_type='{pipeline_type}': "
                f"agents '{order_map[spec.order]}' and '{spec.id}' share the same order value"
            )
        order_map[spec.order] = spec.id

    # Sort by order ascending and return IDs
    matching.sort(key=lambda s: s.order)
    return [s.id for s in matching]


def iter_agent_specs() -> Iterator[AgentSpec]:
    """Yield every loadable AgentSpec under agents/prompts/.

    This is the single discovery scan behind SUPPORTED_PIPELINE_TYPES,
    PIPELINE_AGENTS (registry) and the flat agent-library pool
    (get_all_agents_flat) — those three all need "every AGENT.md on disk"
    and previously each carried their own copy of this loop.

    Same tolerance as list_agent_ids: a directory without an AGENT.md is
    skipped, and a broken AGENT.md is skipped (never fatal) rather than
    aborting the whole scan. Template agents (``template: true``) ARE
    included — callers that only want pipeline members filter them out
    themselves (see AgentSpec.template).
    """
    if not _PROMPTS_DIR.exists():
        return

    for agent_dir in _PROMPTS_DIR.iterdir():
        if not agent_dir.is_dir():
            continue
        if not (agent_dir / "AGENT.md").exists():
            continue
        try:
            yield load_agent_spec(agent_dir.name)
        except (FileNotFoundError, PermissionError, AgentSpecError):
            # Skip agents that can't be loaded when scanning
            logger.warning(
                "Skipping agent %s during iter_agent_specs scan (load failed)",
                agent_dir.name,
            )
            continue


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_spec(
    metadata: dict,
    prompt_body: str,
    agent_file: Path,
) -> AgentSpec:
    """Validate frontmatter metadata and construct an AgentSpec.

    Raises AgentSpecError for any missing or invalid field.
    """
    file_path_str = str(agent_file)

    # ── Required string fields ────────────────────────────────────────────
    agent_id = _require_nonempty_str(metadata, "id", file_path_str)
    name = _require_nonempty_str(metadata, "name", file_path_str)
    role = _require_nonempty_str(metadata, "role", file_path_str)

    # ── pipeline_type ─────────────────────────────────────────────────────
    # Shape only (non-empty string). There is deliberately NO allow-list check
    # here any more (ADR-0005): SUPPORTED_PIPELINE_TYPES is now DERIVED — partly
    # FROM the values agents declare — so validating against it would be
    # circular, and the frozenset it replaced was the thing that made adding a
    # workflow a source-code edit (SC-001).
    #
    # TRADE-OFF (accepted, see the module footer): a typo'd `pipeline_type`
    # used to raise here. It now creates its own empty bucket instead. A
    # startup consistency check (every declared pipeline_type has a manifest,
    # every manifest has agents or is deliberately empty) is the intended
    # replacement and is NOT implemented yet.
    pipeline_type = _require_nonempty_str(metadata, "pipeline_type", file_path_str)

    # ── order ─────────────────────────────────────────────────────────────
    raw_order = metadata.get("order")
    if raw_order is None:
        raise AgentSpecError(
            f"Missing required field 'order' in {file_path_str}"
        )
    if not isinstance(raw_order, int) or isinstance(raw_order, bool):
        raise AgentSpecError(
            f"Invalid field 'order' in {file_path_str}: "
            f"expected a positive integer, got {type(raw_order).__name__!r} ({raw_order!r})"
        )
    if raw_order < 1:
        raise AgentSpecError(
            f"Invalid field 'order' in {file_path_str}: "
            f"must be a positive integer (>= 1), got {raw_order}"
        )
    order: int = raw_order

    # ── max_tokens ────────────────────────────────────────────────────────
    raw_max_tokens = metadata.get("max_tokens")
    if raw_max_tokens is None:
        raise AgentSpecError(
            f"Missing required field 'max_tokens' in {file_path_str}"
        )
    if not isinstance(raw_max_tokens, int) or isinstance(raw_max_tokens, bool):
        raise AgentSpecError(
            f"Invalid field 'max_tokens' in {file_path_str}: "
            f"expected an integer, got {type(raw_max_tokens).__name__!r} ({raw_max_tokens!r})"
        )
    if not (1 <= raw_max_tokens <= 32768):
        raise AgentSpecError(
            f"Invalid field 'max_tokens' in {file_path_str}: "
            f"must be in range 1–32768, got {raw_max_tokens}"
        )
    max_tokens: int = raw_max_tokens

    # ── prompt_body ───────────────────────────────────────────────────────
    if not prompt_body or not prompt_body.strip():
        raise AgentSpecError(
            f"Invalid 'prompt body' in {file_path_str}: "
            f"the text after the YAML frontmatter closing '---' must contain "
            f"at least one non-whitespace character"
        )

    # ── Optional fields with defaults ────────────────────────────────────
    tools = _optional_list_of_str(metadata, "tools", file_path_str, default=[])
    guardrails = _optional_list_of_str(metadata, "guardrails", file_path_str, default=[])
    context_from = _optional_list_of_str(metadata, "context_from", file_path_str, default=[])

    raw_icon = metadata.get("icon", "🤖")
    if not isinstance(raw_icon, str):
        raise AgentSpecError(
            f"Invalid field 'icon' in {file_path_str}: "
            f"expected a string, got {type(raw_icon).__name__!r}"
        )
    icon: str = raw_icon if raw_icon else "🤖"

    raw_duration = metadata.get("estimated_duration", 3.0)
    if not isinstance(raw_duration, (int, float)) or isinstance(raw_duration, bool):
        raise AgentSpecError(
            f"Invalid field 'estimated_duration' in {file_path_str}: "
            f"expected a float, got {type(raw_duration).__name__!r}"
        )
    estimated_duration: float = float(raw_duration)

    # ── description (optional) ────────────────────────────────────────────
    # Longer UI-facing blurb. Optional; if present it must be a string, but
    # absence must NEVER raise (no required-field validation). When absent or
    # blank, fall back to `role` — the existing required field — so callers
    # (API / frontend) always get a non-empty description without a mass
    # backfill of the existing AGENT.md files.
    raw_description = metadata.get("description")
    if raw_description is not None and not isinstance(raw_description, str):
        raise AgentSpecError(
            f"Invalid field 'description' in {file_path_str}: "
            f"expected a string or null, got {type(raw_description).__name__!r}"
        )
    description: str = (
        raw_description.strip()
        if isinstance(raw_description, str) and raw_description.strip()
        else role
    )

    # ── Phase 1 extensions: produces, consumes, gate, injects ────────────
    produces = _optional_list_of_str(metadata, "produces", file_path_str, default=[])
    consumes = _optional_list_of_str(metadata, "consumes", file_path_str, default=[])
    injects = _optional_list_of_str(metadata, "injects", file_path_str, default=[])

    raw_gate = metadata.get("gate", None)
    if raw_gate is not None:
        if not isinstance(raw_gate, str):
            raise AgentSpecError(
                f"Invalid field 'gate' in {file_path_str}: "
                f"expected a string or null, got {type(raw_gate).__name__!r}"
            )
        if raw_gate not in ("Human_Gate", "Validation_Gate"):
            raise AgentSpecError(
                f"Invalid field 'gate' in {file_path_str}: "
                f"must be 'Human_Gate', 'Validation_Gate', or absent/null — got {raw_gate!r}"
            )
    gate: str | None = raw_gate

    # ── model (optional) ──────────────────────────────────────────────────
    # Optional AGENT.md model id (D-09; MODEL-01). Absent → None for every
    # agent (no existing AGENT.md declares it). Type guard only: a present
    # value must be a string; catalog-membership validation is deferred to
    # RESOLVE time in the resolver (06-03) so the loader gains no catalog
    # import and the all-agents schema test is unaffected by catalog contents.
    raw_model = metadata.get("model")
    if raw_model is not None and not isinstance(raw_model, str):
        raise AgentSpecError(
            f"Invalid field 'model' in {file_path_str}: "
            f"expected a string or null, got {type(raw_model).__name__!r}"
        )
    model: str | None = raw_model

    # ── template (optional) ───────────────────────────────────────────────
    # Strict bool: `template: "yes"` / `template: 1` must NOT be coerced —
    # a folder silently failing to mark itself a template would rejoin the
    # roster and break its pipeline's membership assertion.
    raw_template = metadata.get("template", False)
    if not isinstance(raw_template, bool):
        raise AgentSpecError(
            f"Invalid field 'template' in {file_path_str}: "
            f"expected a bool, got {type(raw_template).__name__!r}"
        )
    template: bool = raw_template

    return AgentSpec(
        id=agent_id,
        name=name,
        role=role,
        pipeline_type=pipeline_type,
        order=order,
        max_tokens=max_tokens,
        prompt_body=prompt_body,
        tools=tools,
        guardrails=guardrails,
        context_from=context_from,
        icon=icon,
        estimated_duration=estimated_duration,
        description=description,
        produces=produces,
        consumes=consumes,
        gate=gate,
        injects=injects,
        model=model,
        template=template,
    )


def _require_nonempty_str(metadata: dict, field: str, file_path: str) -> str:
    """Extract a required non-empty string field from frontmatter metadata."""
    value = metadata.get(field)
    if value is None:
        raise AgentSpecError(
            f"Missing required field '{field}' in {file_path}"
        )
    if not isinstance(value, str):
        raise AgentSpecError(
            f"Invalid field '{field}' in {file_path}: "
            f"expected a string, got {type(value).__name__!r} ({value!r})"
        )
    if not value.strip():
        raise AgentSpecError(
            f"Invalid field '{field}' in {file_path}: "
            f"value must be a non-empty string"
        )
    return value


def _optional_list_of_str(
    metadata: dict,
    field: str,
    file_path: str,
    default: list[str],
) -> list[str]:
    """Extract an optional list-of-strings field from frontmatter metadata."""
    value = metadata.get(field, default)
    if value is None:
        return list(default)
    if not isinstance(value, list):
        raise AgentSpecError(
            f"Invalid field '{field}' in {file_path}: "
            f"expected a list of strings, got {type(value).__name__!r}"
        )
    result: list[str] = []
    for i, item in enumerate(value):
        if not isinstance(item, str):
            raise AgentSpecError(
                f"Invalid field '{field}[{i}]' in {file_path}: "
                f"expected a string, got {type(item).__name__!r} ({item!r})"
            )
        result.append(item)
    return result


# ---------------------------------------------------------------------------
# Supported pipeline types (derived from disk — spec 012, ADR-0005)
# ---------------------------------------------------------------------------
#
# Was a hand-maintained frozenset: a forgotten edit silently broke discovery for
# a new pipeline. Now DERIVED at import from three disk-backed sources (ADR-0005,
# SC-001 — launchability keyed on a declared flag, never a hardcoded name list):
#
#   (a) directories under agents/workflows/ containing a workflow.yaml;
#   (b) every `pipeline_type` declared by an AGENT.md — keeps types with agents
#       but no manifest yet, e.g. `spec_kit`, which owns the deep-planner every
#       pipeline runs;
#
# There used to be a third source, `_ID_ALIAS_TYPES` — hand-listed run-label
# aliases with no manifest and no agents, which therefore could not be derived
# from disk the way (a) and (b) are. It held `od_prototype` /
# `od_prototype_revision`; collapsing those labels onto `prototype` /
# `prototype_revision` emptied it, and an empty union operand is just dead code.
# Every supported pipeline type is now derivable from disk, with no exceptions.
#
# CONSEQUENCE (ADR-0005): the set went 17 -> 21, gaining the sample_* fixtures.
# Three cannot run; they are excluded by PROPERTY (does every step's agent load?),
# never by name — tests/agents/test_compiled_plan_runs.py::_every_step_agent_loads.
def _discover_supported_pipeline_types() -> frozenset[str]:
    """Compute SUPPORTED_PIPELINE_TYPES from disk, once, at import time.

    Unions the three sources described above. This function is called exactly
    once (see the module-level assignment immediately below it) — callers
    that need the set read the cached ``SUPPORTED_PIPELINE_TYPES`` constant,
    they never call this function again.
    """
    types: set[str] = set()

    # (a) authored workflow manifests
    if _WORKFLOWS_DIR.exists():
        for entry in _WORKFLOWS_DIR.iterdir():
            if entry.is_dir() and (entry / "workflow.yaml").exists():
                types.add(entry.name)

    # (b) pipeline_type declared by any loadable AGENT.md
    for spec in iter_agent_specs():
        types.add(spec.pipeline_type)

    return frozenset(types)


SUPPORTED_PIPELINE_TYPES: frozenset[str] = _discover_supported_pipeline_types()


# ---------------------------------------------------------------------------
# Template agent ids (derived from disk — spec 012)
# ---------------------------------------------------------------------------
#
# Replaces the former hand-maintained template-id name list (see the
# AgentSpec.template field docstring above for that history). Computed once
# at import time (same caching rule as SUPPORTED_PIPELINE_TYPES
# above) so callers like registry.get_all_agents_flat() read a constant
# instead of re-scanning agents/prompts/ on every call.
TEMPLATE_AGENT_IDS_BY_FLAG: frozenset[str] = frozenset(
    spec.id for spec in iter_agent_specs() if spec.template
)
