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
from dataclasses import dataclass, field
from pathlib import Path

import frontmatter  # python-frontmatter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supported pipeline types (single source of truth — also used by registry)
# ---------------------------------------------------------------------------

SUPPORTED_PIPELINE_TYPES: frozenset[str] = frozenset(
    {
        "user_stories",
        "user_stories_revision",
        "ppt",
        "ppt_revision",
        "od_ppt",
        "od_ppt_revision",
        "prototype",
        "prototype_revision",
        "prototype_v1",          # retired Approach 1 agents — kept for reference
        "app_builder",
        "app_builder_revision",
        "mulesoft_to_springboot",
        "dotnet_to_azure",
        "reverse_engineer",
        "custom",
        "spec_kit",
    }
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# agents/ package root (this file lives in agents/)
_AGENTS_DIR = Path(__file__).resolve().parent
_PROMPTS_DIR = _AGENTS_DIR / "prompts"


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
    pipeline_type = _require_nonempty_str(metadata, "pipeline_type", file_path_str)
    if pipeline_type not in SUPPORTED_PIPELINE_TYPES:
        raise AgentSpecError(
            f"Invalid field 'pipeline_type' in {file_path_str}: "
            f"'{pipeline_type}' is not one of the supported pipeline types "
            f"({sorted(SUPPORTED_PIPELINE_TYPES)})"
        )

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
