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
    build_manifest_from_dict(data: object, source_label: str) -> WorkflowManifest
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
class ChainEntry:
    """One entry in a workflow's chained_from consent list (Plan 34-01).

    Represents a source workflow that may offer "chain into me" after its run.
    """
    id: str
    beta: bool = False
    text: str = ""  # action label for the chain-suggestion UI (e.g., "Ship the code")


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
    # is_beta: catalog-only display flag (Plan 20-01 sibling). Marks a
    # user_launchable workflow as "Coming Soon" in the catalog — greyed out,
    # non-interactive, sorted after the non-beta rows. It does NOT authorize
    # or block a run server-side (launch stays tier-gated, T-20-02); the FE is
    # the sole enforcement point, same division of responsibility as
    # user_launchable. Pure data (INV-5). Default False keeps every existing
    # golden manifest byte-identical (INV-3).
    is_beta: bool = False
    # name: primary display name for the workflow (e.g., "App Builder",
    # "Presentation", "User Stories"). Used as the main UI label. Plain text,
    # typically 1-3 words. Presentation only (INV-5).
    name: str | None = None
    display_name: str | None = None
    # short_name: a concise, noun-phrase label for ultra-tight UI surfaces where
    # the full display_name's action-phrase sentence ("Build an end-to-end
    # application") is too long — chiefly the chain-suggestion chips ("chain
    # into X") introduced alongside `chained_from` (Plan 34-01). Presentation
    # only, never read by the compiler/kernel (INV-5/INV-3).
    short_name: str | None = None
    description: str | None = None
    icon: str | None = None
    launch_surface: str | None = None

    # ── Chaining (Plan 34-01) — inert, additive ────────────────────────────
    # Backend-owned "chain into next workflow" graph — REPLACES the formerly
    # frontend-hardcoded CHAIN_OPTIONS/CHAINABLE_FROM_TYPES allow-lists
    # (frontend/src/lib/workflowChaining.ts). Pure DATA (INV-5): the compiler/
    # kernel never reads this field; only GET /api/workflows and the FE's
    # catalog-derived chaining selector consume it. Default keeps every
    # existing golden manifest byte-identical (INV-3).
    #
    # chained_from: authored on the TARGET's own manifest — the list of source
    # workflow ids that are allowed to offer "chain into me" after THEIR run
    # completes. This is a consent list, not a derived inverse: a source
    # manifest cannot fabricate a chain relationship the target didn't opt
    # into. Each entry is a plain workflow id, OPTIONALLY suffixed with
    # ":beta" (e.g. "prototype:beta") to mark that SPECIFIC edge as "Coming
    # Soon" even though the target workflow itself is not is_beta and is
    # otherwise fully launchable on its own catalog card (e.g. app_builder is
    # not beta, but the prototype -> app_builder chain edge is). Parsed into
    # ``ChainEntry`` objects (source_id, beta, text) by ``_optional_chained_from``.
    chained_from: list = field(default_factory=list)  # list[ChainEntry]

    # ── Chat / concierge (Plan 33-05) — inert DATA, INV-5 ─────────────────
    # An OPTIONAL per-workflow chat block: free-form suggestions / concierge
    # notes a custom workflow AUTHORS. It is pure DATA — the run Concierge
    # (chat:concierge) reads it via ``getattr(compiled, "chat", {})`` and the FE
    # surfaces it as suggested topics. NOTHING in the compiler/kernel branches on
    # this block (no control-flow construct keys off it anywhere — INV-5); the
    # compiler only CARRIES it verbatim onto ``CompiledWorkflow.chat``. Default
    # ``{}`` keeps every existing manifest byte-identical (INV-3), so the 5
    # characterization goldens are untouched.
    chat: dict = field(default_factory=dict)

    # ── Capabilities (Spec 012 / R-07, R-08) — inert DATA, INV-5 ──────────
    # An OPTIONAL per-workflow capabilities block: ``{"internet": bool}`` only.
    # Defaults to ``{}`` (no capabilities enabled). Pure DATA — the engine reads
    # it via ``compiled.capabilities.get("internet")`` to bind the internet tools
    # (T24); the compiler only CARRIES it verbatim onto ``CompiledWorkflow``.
    # Validation ensures only "internet" key is present with a bool value.
    # Default ``{}`` keeps every existing manifest byte-identical (INV-3).
    capabilities: dict = field(default_factory=dict)

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
        "is_beta",
        "name",
        "display_name",
        "short_name",
        "description",
        "icon",
        "launch_surface",
        # ── Chaining (Plan 34-01) — pure DATA, never control flow (INV-5) ──
        "chained_from",
        # ── Chat / concierge (Plan 33-05) — pure DATA, never control flow (INV-5) ──
        "chat",
        # ── Capabilities (Spec 012 / R-07, R-08) — pure DATA, never control flow (INV-5) ──
        "capabilities",
    }
)

# The five fields that MUST be present (MAN-01).
_REQUIRED_KEYS: tuple[str, ...] = ("id", "steps", "deliverable", "planner", "clarify")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_manifest(workflow_id: str, base_dir: Path) -> WorkflowManifest:
    """Read ``<base_dir>/<workflow_id>/workflow.yaml`` and return a WorkflowManifest.

    A thin file-reading wrapper (R-26): existence check, read, ``yaml.safe_load``,
    then delegate to ``build_manifest_from_dict`` with the file path as the
    error-message source label.

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

    return build_manifest_from_dict(data, str(path))


# ---------------------------------------------------------------------------
# Internal helpers (mirror agents/loader.py::_build_spec / _require_* idiom)
# ---------------------------------------------------------------------------


def build_manifest_from_dict(data: object, source_label: str) -> WorkflowManifest:
    """Validate already-parsed manifest data and construct a WorkflowManifest.

    R-26: the single validator both file-backed (``load_manifest``) and
    DB-stored (``workflows.manifest_json``) workflows pass through — a DB
    manifest cannot carry anything a file manifest cannot. ``data`` must
    already be parsed (this function does no YAML parsing itself, T-04-03);
    ``source_label`` identifies the manifest's origin in error messages (a
    file path for file-backed manifests, e.g. ``"workflow:<uuid>"`` for a DB
    manifest) so a DB manifest's errors are still locatable.

    Raises ManifestValidationError for any structural/field problem (naming the
    offending field/key).
    """
    file_str = source_label

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
    is_beta = _optional_bool(data, "is_beta", file_str, default=False)
    name = _optional_str(data, "name", file_str)
    display_name = _optional_str(data, "display_name", file_str)
    short_name = _optional_str(data, "short_name", file_str)
    description = _optional_str(data, "description", file_str)
    icon = _optional_str(data, "icon", file_str)
    launch_surface = _optional_str(data, "launch_surface", file_str)

    # ── Chaining field (Plan 34-01) — inert, type-checked ──────────────────
    chained_from = _optional_chained_from(data, "chained_from", file_str)

    # ── Chat / concierge block (Plan 33-05) — optional DATA (INV-5) ────────
    # Type-checked as a mapping (names the field on error) then carried verbatim;
    # absent/null ⇒ {} (parity). No control-flow keys off it (INV-5).
    chat = _optional_dict(data, "chat", file_str, default_factory=dict)

    # ── Capabilities block (Spec 012 / R-07, R-08) — optional DATA (INV-5) ──
    # Type-checked as a mapping (names the field on error); contains only
    # "internet" key with a bool value. Validation names the field on error.
    capabilities = _optional_dict(data, "capabilities", file_str, default_factory=dict)
    if capabilities:
        # Validate that only "internet" key is present
        if set(capabilities.keys()) != {"internet"}:
            extra = set(capabilities.keys()) - {"internet"}
            raise ManifestValidationError(
                f"{file_str}: field 'capabilities' contains unknown key(s) "
                f"{sorted(extra)} — only 'internet' is allowed"
            )
        # Validate that "internet" value is a bool
        if not isinstance(capabilities["internet"], bool):
            raise ManifestValidationError(
                f"{file_str}: field 'capabilities.internet' must be a boolean, got "
                f"{type(capabilities['internet']).__name__!r} "
                f"({capabilities['internet']!r})"
            )

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
        is_beta=is_beta,
        name=name,
        display_name=display_name,
        short_name=short_name,
        description=description,
        icon=icon,
        launch_surface=launch_surface,
        chained_from=chained_from,
        chat=chat,
        capabilities=capabilities,
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


def _optional_chained_from(data: dict, key: str, file_str: str) -> list:
    """Extract the optional ``chained_from`` consent list (Plan 34-01).

    Defaults to ``[]``. Supports both string format (legacy) and object format:

    String format (legacy): Each entry is a plain string: a bare source
    workflow id (e.g. ``"prototype"``), or the same id suffixed with
    ``":beta"`` (e.g. ``"prototype:beta"``).

    Object format (new): Each entry is a mapping with:
      - `id` (required): source workflow id
      - `beta` (optional, default False): marks this edge as "Coming Soon"
      - `text` (optional, default ""): action label for the chain-suggestion UI

    Returns a list of ``ChainEntry`` objects.
    """
    value = data.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise ManifestValidationError(
            f"{file_str}: field '{key}' must be a list, got "
            f"{type(value).__name__!r}"
        )
    parsed: list = []
    for i, entry in enumerate(value):
        if isinstance(entry, str):
            # Legacy string format: "prototype" or "prototype:beta"
            if not entry.strip():
                raise ManifestValidationError(
                    f"{file_str}: field '{key}' entries must be non-empty strings, "
                    f"got {entry!r}"
                )
            if ":" in entry:
                source_id, _, suffix = entry.partition(":")
                if suffix != "beta":
                    raise ManifestValidationError(
                        f"{file_str}: field '{key}' entry {entry!r} has an "
                        f"unrecognised suffix {suffix!r} — only ':beta' is allowed"
                    )
                beta = True
            else:
                source_id, beta = entry, False
            source_id = source_id.strip()
            if not source_id:
                raise ManifestValidationError(
                    f"{file_str}: field '{key}' entry {entry!r} has an empty id"
                )
            parsed.append(ChainEntry(id=source_id, beta=beta, text=""))
        elif isinstance(entry, dict):
            # New object format: {id: ..., beta: ..., text: ...}
            source_id = entry.get("id", "").strip()
            if not source_id:
                raise ManifestValidationError(
                    f"{file_str}: field '{key}' entry {i} missing or empty 'id'"
                )
            beta = entry.get("beta", False)
            if not isinstance(beta, bool):
                raise ManifestValidationError(
                    f"{file_str}: field '{key}' entry {i} 'beta' must be boolean, "
                    f"got {type(beta).__name__!r}"
                )
            text = entry.get("text", "")
            if not isinstance(text, str):
                raise ManifestValidationError(
                    f"{file_str}: field '{key}' entry {i} 'text' must be string, "
                    f"got {type(text).__name__!r}"
                )
            parsed.append(ChainEntry(id=source_id, beta=beta, text=text))
        else:
            raise ManifestValidationError(
                f"{file_str}: field '{key}' entry {i} must be string or mapping, "
                f"got {type(entry).__name__!r}"
            )
    return parsed
