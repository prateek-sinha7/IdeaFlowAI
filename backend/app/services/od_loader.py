"""OpenDesign content loader.

Reads template SKILL.md and design-system DESIGN.md files from the repo's
``skills/opendesign/`` directory. Used by the new prototype flow to populate
the gallery and to compose Agent 2's system prompt.

Filesystem layout (relative to repo root):

    skills/opendesign/
      design-templates/<id>/SKILL.md      ← frontmatter + body
      design-templates/<id>/example.html  ← visual preview
      design-systems/<id>/DESIGN.md       ← 9-section spec
      craft/<name>.md                     ← brand-agnostic rules

The loader caches parsed results in-process; rerun the backend after editing
the underlying files.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("app.services.od_loader")


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# This file lives at <repo>/backend/app/services/od_loader.py — climb four
# parents to reach the repo root, then descend into skills/opendesign.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_OD_ROOT = _REPO_ROOT / "skills" / "opendesign"
_TEMPLATES_DIR = _OD_ROOT / "design-templates"
_DESIGN_SYSTEMS_DIR = _OD_ROOT / "design-systems"
_CRAFT_DIR = _OD_ROOT / "craft"


# ---------------------------------------------------------------------------
# Frontmatter parser
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n(.*)\Z", re.DOTALL)


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split ``--- yaml --- body`` into (frontmatter dict, body str).

    Returns ({}, full_text) when the document has no frontmatter so callers
    can treat the body uniformly.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm_raw, body = m.group(1), m.group(2)
    try:
        fm = yaml.safe_load(fm_raw) or {}
    except yaml.YAMLError as exc:
        logger.warning("Frontmatter parse failed: %s", exc)
        fm = {}
    if not isinstance(fm, dict):
        fm = {}
    return fm, body


def _read_file(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return None


def _humanize_slug(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").strip().title()


def _flatten_description(value: Any) -> str:
    """Frontmatter ``description`` is sometimes a single line, sometimes a
    block scalar (``|``). Collapse to a single string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return " ".join(str(x).strip() for x in value)
    return str(value).strip()


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


def _load_one_template(folder: Path) -> dict[str, Any] | None:
    """Parse one template folder into the shape exposed to the API."""
    skill_path = folder / "SKILL.md"
    if not skill_path.is_file():
        return None

    raw = _read_file(skill_path)
    if raw is None:
        return None

    fm, body = _parse_frontmatter(raw)
    od = fm.get("od") or {}
    if not isinstance(od, dict):
        od = {}

    template_id = folder.name
    return {
        "id": template_id,
        "name": fm.get("name") or _humanize_slug(template_id),
        "description": _flatten_description(fm.get("description")),
        "mode": od.get("mode"),
        "platform": od.get("platform"),
        "scenario": od.get("scenario"),
        "triggers": fm.get("triggers") or [],
        "design_system": od.get("design_system") or {},
        "craft_required": (od.get("craft") or {}).get("requires") or [],
        "inputs": od.get("inputs") or [],
        "outputs": od.get("outputs") or {},
        "example_prompt": od.get("example_prompt") or fm.get("example_prompt"),
        "has_preview": (folder / "example.html").is_file(),
        "has_own_seed": (folder / "assets" / "template.html").is_file(),
        "body": body,
    }


@lru_cache(maxsize=1)
def _all_templates() -> list[dict[str, Any]]:
    """Parse every template folder once. Cached for the process lifetime."""
    if not _TEMPLATES_DIR.is_dir():
        logger.error("Templates directory missing: %s", _TEMPLATES_DIR)
        return []
    result: list[dict[str, Any]] = []
    for folder in sorted(_TEMPLATES_DIR.iterdir()):
        if not folder.is_dir():
            continue
        parsed = _load_one_template(folder)
        if parsed is not None:
            result.append(parsed)
    logger.info("Loaded %d OpenDesign templates from %s", len(result), _TEMPLATES_DIR)
    return result


def list_prototype_templates() -> list[dict[str, Any]]:
    """Return the gallery list: only ``od.mode == "prototype"`` templates,
    stripped of the heavy ``body`` field."""
    out = []
    for t in _all_templates():
        if t.get("mode") != "prototype":
            continue
        # Return a slim view — body is large and not needed for the gallery.
        out.append({k: v for k, v in t.items() if k != "body"})
    return out


def get_template(template_id: str) -> dict[str, Any] | None:
    """Full template payload incl. ``body`` (the SKILL.md content after
    frontmatter). Returns ``None`` for unknown ids."""
    for t in _all_templates():
        if t["id"] == template_id:
            return t
    return None


def get_template_seed(template_id: str) -> str | None:
    """Return the content of the template's own ``assets/template.html`` seed,
    or ``None`` if the template doesn't ship one.

    Several prototype templates (mobile-app, web-prototype, live-dashboard,
    etc.) include their own HTML/CSS seed that the SKILL.md instructs the agent
    to copy as the starting point. Injecting this seed into the Composer's
    user message instead of the generic Flowin SPA seed gives much higher
    fidelity — e.g. the iPhone 15 Pro frame for mobile-app.
    """
    seed_path = _TEMPLATES_DIR / template_id / "assets" / "template.html"
    if not seed_path.is_file():
        return None
    return _read_file(seed_path)


def get_template_references(template_id: str) -> dict[str, str]:
    """Return all ``*.md`` files from the template's ``references/`` folder.

    These are critical quality documents — layout libraries, P0/P1/P2
    checklists, component inventories, connector policies — that the SKILL.md
    workflow explicitly instructs the agent to read before writing any HTML.

    Without injecting these, the agent writes CSS from scratch and ignores
    the paste-ready section skeletons and quality gates the template ships.

    Returns a dict mapping filename stem → file body, e.g.:
        {"layouts": "# Web prototype layouts ...", "checklist": "# Web prototype checklist ..."}
    Returns an empty dict if the template has no references/ folder.
    """
    refs_dir = _TEMPLATES_DIR / template_id / "references"
    if not refs_dir.is_dir():
        return {}
    out: dict[str, str] = {}
    for path in sorted(refs_dir.glob("*.md")):
        # Skip README files — they describe the directory, not a rule
        if path.stem.lower() == "readme":
            continue
        body = _read_file(path)
        if body is not None:
            out[path.stem] = body
    if out:
        logger.debug(
            "Loaded %d reference file(s) for template '%s': %s",
            len(out), template_id, list(out.keys()),
        )
    return out


def get_template_preview_path(template_id: str) -> Path | None:
    """Filesystem path to the template's example.html, or ``None`` if the
    template doesn't exist or has no preview file."""
    t = get_template(template_id)
    if t is None or not t.get("has_preview"):
        return None
    return _TEMPLATES_DIR / template_id / "example.html"


# ---------------------------------------------------------------------------
# Design systems
# ---------------------------------------------------------------------------

_CATEGORY_RE = re.compile(r"^>\s*Category:\s*(.+?)\s*$", re.MULTILINE)
_BLURB_RE = re.compile(
    r"^>\s*Category:[^\n]*\n>\s*(.+?)\s*$", re.MULTILINE
)
_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def _load_one_design_system(folder: Path) -> dict[str, Any] | None:
    """Parse one DESIGN.md into the API shape. Design systems don't use YAML
    frontmatter — metadata is encoded in early blockquote lines."""
    if folder.name.startswith("_"):
        # _schema is convention for the folder that documents the format.
        return None
    design_path = folder / "DESIGN.md"
    if not design_path.is_file():
        return None

    raw = _read_file(design_path)
    if raw is None:
        return None

    cat_match = _CATEGORY_RE.search(raw)
    blurb_match = _BLURB_RE.search(raw)
    h1_match = _H1_RE.search(raw)

    return {
        "id": folder.name,
        "name": h1_match.group(1) if h1_match else _humanize_slug(folder.name),
        "category": cat_match.group(1) if cat_match else "Uncategorised",
        "description": blurb_match.group(1) if blurb_match else "",
        "has_preview": (folder / "components.html").is_file(),
        "body": raw,
    }


@lru_cache(maxsize=1)
def _all_design_systems() -> list[dict[str, Any]]:
    if not _DESIGN_SYSTEMS_DIR.is_dir():
        logger.error("Design-systems directory missing: %s", _DESIGN_SYSTEMS_DIR)
        return []
    result: list[dict[str, Any]] = []
    for folder in sorted(_DESIGN_SYSTEMS_DIR.iterdir()):
        if not folder.is_dir():
            continue
        parsed = _load_one_design_system(folder)
        if parsed is not None:
            result.append(parsed)
    logger.info("Loaded %d OpenDesign design systems from %s", len(result), _DESIGN_SYSTEMS_DIR)
    return result


def list_design_systems() -> list[dict[str, Any]]:
    """Slim list for the picker dropdown — no ``body``."""
    return [
        {k: v for k, v in ds.items() if k != "body"}
        for ds in _all_design_systems()
    ]


def get_design_system(ds_id: str) -> dict[str, Any] | None:
    for ds in _all_design_systems():
        if ds["id"] == ds_id:
            return ds
    return None


def get_design_system_preview_path(ds_id: str) -> Path | None:
    """Filesystem path to the design system's components.html, or None if it
    doesn't exist or has no preview file."""
    ds = get_design_system(ds_id)
    if ds is None or not ds.get("has_preview"):
        return None
    return _DESIGN_SYSTEMS_DIR / ds_id / "components.html"


# ---------------------------------------------------------------------------
# Craft rules
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _all_craft_rules() -> dict[str, str]:
    """Map craft rule name (stem of filename, e.g. ``anti-ai-slop``) to body."""
    if not _CRAFT_DIR.is_dir():
        logger.error("Craft directory missing: %s", _CRAFT_DIR)
        return {}
    out: dict[str, str] = {}
    for path in sorted(_CRAFT_DIR.glob("*.md")):
        # Skip README/AGENTS index files — they describe the directory,
        # they don't carry a rule the agent should ingest.
        if path.stem.lower() in {"readme", "agents"}:
            continue
        body = _read_file(path)
        if body is not None:
            out[path.stem] = body
    return out


def get_craft_rules(names: list[str]) -> dict[str, str]:
    """Return the subset of craft rules requested by an ``od.craft.requires``
    list. Unknown names are silently skipped — the caller can detect by
    comparing keys."""
    rules = _all_craft_rules()
    return {name: rules[name] for name in names if name in rules}
