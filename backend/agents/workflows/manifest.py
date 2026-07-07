"""agents/workflows/manifest.py — workflow.yaml loader + validator (MAN-01).

Reads ``<base_dir>/<workflow_id>/workflow.yaml`` into a typed ``WorkflowManifest``
dataclass, mirroring the proven ``agents/loader.py`` pattern: dataclass +
``yaml.safe_load`` + per-field validation that NAMES the offending field
(``ManifestValidationError(field)``). NOT Pydantic (D-10 / §6 / §32).

Strict-key rejection (D-08 / INV-5): only the keys in ``_ALLOWED_TOP_KEYS`` are
permitted at the top level. Any extra key (``when:`` / ``if:`` / ``for:`` /
``${...}`` …) is rejected — a control-flow / DSL construct has nowhere to live,
which is exactly what keeps manifests pure data (INV-5).

Security (T-04-03): the file is parsed with ``yaml.safe_load`` ONLY — never the
unsafe full loaders — so a ``!!python/object`` tag cannot construct an arbitrary
object (RCE surface).

Public API:
    load_manifest(workflow_id: str, base_dir: Path) -> WorkflowManifest
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml  # PyYAML — already an in-repo dependency (transitive via python-frontmatter)


class ManifestValidationError(Exception):
    """Raised when a workflow.yaml has invalid or missing fields.

    The message always NAMES the offending field/key (MAN-01) so the author can
    locate the problem. Carries only repo-authored config text — no secret/PII
    surface (T-04-05).
    """


# ---------------------------------------------------------------------------
# Data model (mirrors agents/loader.py::AgentSpec — required-then-defaulted)
# ---------------------------------------------------------------------------


@dataclass
class WorkflowManifest:
    """Parsed representation of a workflow.yaml file (D-10).

    Required fields must be supplied; optional fields default to the §6 posture.
    Raw ``steps`` dicts are carried verbatim — the compiler (04-03) turns them
    into typed ``Step`` objects. ``steps`` may be empty (the reverse_engineer
    empty-plan stub, D-05).
    """

    # ── Required ──────────────────────────────────────────────────────────
    id: str
    steps: list                       # raw step dicts; compiler builds Step (may be [])
    deliverable: dict                 # {strategy: ..., name: ...}
    planner: str                      # "run" | "skip"
    clarify: dict                     # {mode, defaults}

    # ── Optional with defaults ────────────────────────────────────────────
    context_providers: list = field(default_factory=list)
    # input_providers: declared image/binary input_provider capability names
    # (image-input Wave 1). Dormant — no manifest declares it this wave. Pure data.
    input_providers: list = field(default_factory=list)
    seed_files: dict = field(default_factory=dict)
    # allowed_workers: the workflow-level named-worker allow-list (Phase 11 / FANOUT-03).
    # A heterogeneous fan-out step may only spawn a named worker listed here (validated
    # against the agent registry by run_fanout before any spawn). Pure data (INV-5).
    allowed_workers: list = field(default_factory=list)
    version: int = 1

    # ── Catalog / presentation (Plan 20-01) — inert, additive ─────────────
    # Discovery metadata for the data-driven workflow catalog. NEVER read by the
    # compiler/kernel (parity proof 20-SPEC §4) — defaults keep every existing
    # golden manifest byte-identical (INV-3). `user_launchable` gates whether a
    # workflow shows in the user-facing catalog; it does NOT authorize a run
    # (launch stays tier-gated server-side, T-20-02). Pure data (INV-5).
    user_launchable: bool = False
    display_name: str | None = None
    description: str | None = None
    icon: str | None = None
    launch_surface: str | None = None

    # ── Forward / inert (D-06) ────────────────────────────────────────────
    model: dict | None = None
    limits: dict | None = None


# ---------------------------------------------------------------------------
# Strict top-level key allow-list (D-08 / INV-5)
# ---------------------------------------------------------------------------

# EXACTLY the keys a manifest may declare. A control-flow / DSL field has
# nowhere to live — anything else is rejected by name.
_ALLOWED_TOP_KEYS: frozenset[str] = frozenset(
    {
        "id",
        "version",
        "model",
        "planner",
        "clarify",
        "context_providers",
        "input_providers",
        "seed_files",
        "allowed_workers",
        "deliverable",
        "limits",
        "steps",
        # ── Catalog / presentation (Plan 20-01) — presentation/visibility only,
        # never control flow; when/if/for/expr stay rejected (INV-5). ────────
        "user_launchable",
        "display_name",
        "description",
        "icon",
        "launch_surface",
    }
)

# The five fields that MUST be present (MAN-01).
_REQUIRED_KEYS: tuple[str, ...] = ("id", "steps", "deliverable", "planner", "clarify")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_manifest(workflow_id: str, base_dir: Path) -> WorkflowManifest:
    """Read ``<base_dir>/<workflow_id>/workflow.yaml`` and return a WorkflowManifest.

    Raises:
        FileNotFoundError: if the workflow.yaml does not exist.
        ManifestValidationError: if the top level is not a mapping, an unknown
            top-level key is present (D-08), a required field is missing
            (MAN-01), or a field has an invalid type. The message NAMES the
            offending field/key.
        yaml.YAMLError: if the file is not parseable as safe YAML (e.g. a
            ``!!python/object`` tag — never constructed, T-04-03).
    """
    base_dir = Path(base_dir)
    path = base_dir / workflow_id / "workflow.yaml"

    # ── Existence check ───────────────────────────────────────────────────
    if not path.exists():
        raise FileNotFoundError(f"workflow.yaml not found: {path}")

    # ── Parse (safe_load ONLY — T-04-03) ──────────────────────────────────
    raw_text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw_text) or {}

    return _build_manifest(data, path)


# ---------------------------------------------------------------------------
# Internal helpers (mirror agents/loader.py::_build_spec / _require_* idiom)
# ---------------------------------------------------------------------------


def _build_manifest(data: object, path: Path) -> WorkflowManifest:
    """Validate parsed YAML and construct a WorkflowManifest.

    Raises ManifestValidationError for any structural/field problem (naming the
    offending field/key).
    """
    file_str = str(path)

    # ── Top level must be a mapping ───────────────────────────────────────
    if not isinstance(data, dict):
        raise ManifestValidationError(
            f"{file_str}: top-level must be a mapping, got "
            f"{type(data).__name__!r}"
        )

    # ── Strict-key rejection (D-08 / INV-5) ───────────────────────────────
    extra = set(data) - set(_ALLOWED_TOP_KEYS)
    if extra:
        raise ManifestValidationError(
            f"{file_str}: unknown top-level key(s) {sorted(extra)} — manifests "
            f"are pure data; a control-flow/DSL field has nowhere to live (INV-5)"
        )

    # ── Required fields present (MAN-01 — name the missing one) ────────────
    for req in _REQUIRED_KEYS:
        if req not in data:
            raise ManifestValidationError(
                f"{file_str}: missing required field '{req}'"
            )

    # ── Per-field type checks (each error NAMES the field) ─────────────────
    manifest_id = _require_str(data, "id", file_str)
    planner = _require_str(data, "planner", file_str)

    deliverable = _require_dict(data, "deliverable", file_str)
    clarify = _require_dict(data, "clarify", file_str)

    steps = data["steps"]
    if not isinstance(steps, list):  # steps:[] is valid (reverse_engineer, D-05)
        raise ManifestValidationError(
            f"{file_str}: field 'steps' must be a list, got "
            f"{type(steps).__name__!r}"
        )

    context_providers = _optional_list(data, "context_providers", file_str)
    input_providers = _optional_list(data, "input_providers", file_str)
    seed_files = _optional_dict(data, "seed_files", file_str, default_factory=dict)
    allowed_workers = _optional_list(data, "allowed_workers", file_str)
    version = _optional_int(data, "version", file_str, default=1)

    # ── Catalog / presentation fields (Plan 20-01) — inert, type-checked ───
    user_launchable = _optional_bool(data, "user_launchable", file_str, default=False)
    display_name = _optional_str(data, "display_name", file_str)
    description = _optional_str(data, "description", file_str)
    icon = _optional_str(data, "icon", file_str)
    launch_surface = _optional_str(data, "launch_surface", file_str)

    # ── Forward / inert fields (D-06) — type-checked, not consumed ─────────
    model = _optional_dict(data, "model", file_str, default_factory=lambda: None)
    limits = _optional_dict(data, "limits", file_str, default_factory=lambda: None)

    return WorkflowManifest(
        id=manifest_id,
        steps=steps,
        deliverable=deliverable,
        planner=planner,
        clarify=clarify,
        context_providers=context_providers,
        input_providers=input_providers,
        seed_files=seed_files,
        allowed_workers=allowed_workers,
        version=version,
        user_launchable=user_launchable,
        display_name=display_name,
        description=description,
        icon=icon,
        launch_surface=launch_surface,
        model=model,
        limits=limits,
    )


def _require_str(data: dict, key: str, file_str: str) -> str:
    """Extract a required non-empty string field (names the field on error)."""
    value = data.get(key)
    if not isinstance(value, str):
        raise ManifestValidationError(
            f"{file_str}: field '{key}' must be a string, got "
            f"{type(value).__name__!r} ({value!r})"
        )
    if not value.strip():
        raise ManifestValidationError(
            f"{file_str}: field '{key}' must be a non-empty string"
        )
    return value


def _require_dict(data: dict, key: str, file_str: str) -> dict:
    """Extract a required mapping field (names the field on error)."""
    value = data.get(key)
    if not isinstance(value, dict):
        raise ManifestValidationError(
            f"{file_str}: field '{key}' must be a mapping, got "
            f"{type(value).__name__!r}"
        )
    return value


def _optional_list(data: dict, key: str, file_str: str) -> list:
    """Extract an optional list field (defaults to []; names the field on error)."""
    value = data.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise ManifestValidationError(
            f"{file_str}: field '{key}' must be a list, got "
            f"{type(value).__name__!r}"
        )
    return value


def _optional_dict(data: dict, key: str, file_str: str, default_factory):
    """Extract an optional mapping field (names the field on error).

    Returns ``default_factory()`` when the key is absent or null.
    """
    if key not in data or data[key] is None:
        return default_factory()
    value = data[key]
    if not isinstance(value, dict):
        raise ManifestValidationError(
            f"{file_str}: field '{key}' must be a mapping, got "
            f"{type(value).__name__!r}"
        )
    return value


def _optional_int(data: dict, key: str, file_str: str, default: int) -> int:
    """Extract an optional integer field (names the field on error)."""
    value = data.get(key, default)
    if value is None:
        return default
    # bool is an int subclass — reject it explicitly.
    if not isinstance(value, int) or isinstance(value, bool):
        raise ManifestValidationError(
            f"{file_str}: field '{key}' must be an integer, got "
            f"{type(value).__name__!r} ({value!r})"
        )
    return value


def _optional_bool(data: dict, key: str, file_str: str, default: bool) -> bool:
    """Extract an optional boolean field (names the field on error).

    The INVERSE of ``_optional_int``'s bool trap: ``bool`` IS an ``int`` subclass,
    so an int like ``user_launchable: 1`` must NOT be silently accepted as a
    truthy bool. Accept ONLY a real ``bool``; reject everything else (including
    ints/strings) naming the field. Returns ``default`` when the key is absent or
    null.
    """
    value = data.get(key, default)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ManifestValidationError(
            f"{file_str}: field '{key}' must be a boolean, got "
            f"{type(value).__name__!r} ({value!r})"
        )
    return value


def _optional_str(data: dict, key: str, file_str: str) -> str | None:
    """Extract an optional string field (names the field on error).

    Mirrors ``_optional_int``'s shape but returns ``str | None`` (default
    ``None``): absent or null → ``None``; a non-string value is rejected naming
    the field.
    """
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ManifestValidationError(
            f"{file_str}: field '{key}' must be a string, got "
            f"{type(value).__name__!r} ({value!r})"
        )
    return value
