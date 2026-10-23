#!/usr/bin/env python3
"""Convert Design Ingestor visual observations to source.json + mapping.json.

Usage:
    python3 figma_extract.py \
        --manifest .figma/manifest.json \
        --obs context/design/observations.json \
        --out context/design/

Input observations.json schema:
{
  "frames": [
    {
      "index": 0, "name": "frame-1.png", "screen": "Dashboard",
      "layout": "sidebar-nav|topbar-nav|centered|dashboard|split",
      "bg": "#hex", "fg": "#hex", "accent": "#hex",
      "surface": "#hex", "surface_2": "#hex", "border": "#hex",
      "muted": "#hex", "on_accent": "#ffffff",
      "font_weight": "light|regular|medium|semibold",
      "font_density": "compact|comfortable|spacious",
      "font_family_hint": "Inter, system-ui, sans-serif"
    }, ...
  ],
  "dominant_layout": "sidebar-nav",
  "color_scheme": "dark|light|mixed",
  "suggested_name": "MyApp Design"
}

Outputs:
  <out>/source.json   — read_source.py-compatible schema
  <out>/mapping.json  — make_ds.py input (ready to generate tokens.css)

Pure Python stdlib. No network, no backend venv required.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path


# ── helpers ───────────────────────────────────────────────────────────────────

def _to_kebab(name: str) -> str:
    """Convert a display name to a kebab-case id."""
    s = re.sub(r"[^a-zA-Z0-9 ]", "", name.lower().strip())
    return re.sub(r"\s+", "-", s)


def _darken_hex(hex_color: str, percent: int = 15) -> str:
    """Darken a hex color by a given percentage (0-100)."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    try:
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        factor = 1 - (percent / 100)
        r = max(0, int(r * factor))
        g = max(0, int(g * factor))
        b = max(0, int(b * factor))
        return f"#{r:02x}{g:02x}{b:02x}"
    except (ValueError, IndexError):
        return hex_color if hex_color.startswith("#") else f"#{hex_color}"


def _normalize_hex(value: str | None) -> str | None:
    """Normalize a hex color to lowercase #rrggbb form; return None on failure."""
    if not value:
        return None
    v = value.strip().lstrip("#").lower()
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) == 6 and all(c in "0123456789abcdef" for c in v):
        return f"#{v}"
    return None


def _dominant(values: list[str]) -> str | None:
    """Return the most frequently occurring non-null value."""
    counts: Counter[str] = Counter(v for v in values if v)
    return counts.most_common(1)[0][0] if counts else None


def _text_scale(base_px: int) -> dict[str, str]:
    """Build an 8-step type scale anchored on base_px."""
    # Steps below base: xs, sm
    # Steps above base: lg, xl, 2xl, 3xl, 4xl
    # Scale ratios (roughly 1.25 major-third below/above)
    xs = max(10, round(base_px * 0.73))
    sm = max(12, round(base_px * 0.87))
    lg = round(base_px * 1.13)
    xl = round(base_px * 1.33)
    x2l = round(base_px * 1.6)
    x3l = round(base_px * 2.0)
    x4l = round(base_px * 2.4)
    return {
        "--text-xs": f"{xs}px",
        "--text-sm": f"{sm}px",
        "--text-base": f"{base_px}px",
        "--text-lg": f"{lg}px",
        "--text-xl": f"{xl}px",
        "--text-2xl": f"{x2l}px",
        "--text-3xl": f"{x3l}px",
        "--text-4xl": f"{x4l}px",
    }


def _base_px_from_density(density: str | None) -> int:
    """Map font density to base pixel size."""
    mapping = {"compact": 14, "comfortable": 16, "spacious": 17}
    return mapping.get(str(density).lower() if density else "", 15)


# ── aggregation ───────────────────────────────────────────────────────────────

_COLOR_FIELDS = (
    "bg", "fg", "accent", "surface", "surface_2", "border", "muted", "on_accent"
)


def _aggregate_tokens(frames: list[dict]) -> dict[str, str]:
    """Aggregate hex values across frames by dominant frequency per role."""
    buckets: dict[str, list[str]] = {f: [] for f in _COLOR_FIELDS}
    densities: list[str] = []
    font_hints: list[str] = []

    for frame in frames:
        for field in _COLOR_FIELDS:
            raw = frame.get(field)
            normalized = _normalize_hex(str(raw)) if raw else None
            if normalized:
                buckets[field].append(normalized)
        if frame.get("font_density"):
            densities.append(str(frame["font_density"]).lower())
        if frame.get("font_family_hint"):
            font_hints.append(str(frame["font_family_hint"]).strip())

    result: dict[str, str] = {}
    for field in _COLOR_FIELDS:
        dominant = _dominant(buckets[field])
        if dominant:
            result[field] = dominant

    return result, densities, font_hints  # type: ignore[return-value]


# ── source.json builder ───────────────────────────────────────────────────────

def _build_source_json(
    manifest: list[dict],
    obs: dict,
    color_map: dict[str, str],
    font_family: str,
) -> dict:
    """Build a read_source.py-compatible source.json."""
    root_vars: dict[str, str] = {}
    for field, css_var in (
        ("bg", "--bg"),
        ("fg", "--fg"),
        ("accent", "--accent"),
        ("surface", "--surface"),
        ("surface_2", "--surface-2"),
        ("border", "--border"),
        ("muted", "--muted"),
        ("on_accent", "--on-accent"),
    ):
        if color_map.get(field):
            root_vars[css_var] = color_map[field]

    # Color frequency map from all frames
    colors: dict[str, int] = Counter()
    for frame in obs.get("frames", []):
        for field in _COLOR_FIELDS:
            raw = frame.get(field)
            normalized = _normalize_hex(str(raw)) if raw else None
            if normalized:
                colors[normalized] += 1

    font_families = []
    if font_family:
        first_family = font_family.split(",")[0].strip().strip("'\"")
        if first_family:
            font_families.append(first_family)

    return {
        "kind": "figma-frames",
        "root": ".figma/",
        "docs": [],
        "variables": {
            ":root": root_vars,
        },
        "fonts": {
            "families": font_families,
            "google_imports": [],
        },
        "themes": {},
        "breakpoints": [],
        "colors": dict(colors),
        "manifest_tokens": [],
        "components": [],
        "warnings": [],
    }


# ── mapping.json builder ──────────────────────────────────────────────────────

def _build_mapping_json(
    obs: dict,
    color_map: dict[str, str],
    densities: list[str],
    font_hints: list[str],
) -> dict:
    """Build a make_ds.py-compatible mapping.json."""
    suggested_name = obs.get("suggested_name", "Figma Design") or "Figma Design"
    ds_id = _to_kebab(suggested_name)

    # Font family
    font_family = _dominant(font_hints) or "system-ui, sans-serif"
    # Ensure generic fallback
    if "sans-serif" not in font_family and "system-ui" not in font_family:
        font_family = f"{font_family}, system-ui, sans-serif"

    # Base text size from dominant density
    dominant_density = _dominant(densities) or "comfortable"
    base_px = _base_px_from_density(dominant_density)
    type_scale = _text_scale(base_px)

    # Core identity tokens from aggregation
    bg = color_map.get("bg", "#ffffff")
    fg = color_map.get("fg", "#000000")
    accent = color_map.get("accent", "#0066cc")
    accent_dark = _darken_hex(accent, 15)
    surface = color_map.get("surface", bg)
    border = color_map.get("border", "#cccccc")
    muted = color_map.get("muted", "#666666")
    on_accent = color_map.get("on_accent", "#ffffff")

    # Derive section spacing from density
    density_spacing = {
        "compact":      ("48px", "32px", "24px"),
        "comfortable":  ("64px", "48px", "32px"),
        "spacious":     ("80px", "64px", "48px"),
    }
    sec_desktop, sec_tablet, sec_phone = density_spacing.get(
        dominant_density, ("64px", "48px", "32px")
    )

    tokens: dict[str, str] = {
        # ── A1-identity tokens ──────────────────────────────────────────
        "--bg": bg,
        "--fg": fg,
        "--accent": accent,
        "--accent-on": on_accent,           # schema name is --accent-on
        "--surface": surface,
        "--border": border,
        "--muted": muted,
        "--font-display": font_family,
        "--font-body": font_family,
        # ── A1-structure: line heights ──────────────────────────────────
        "--leading-body": "1.6",
        "--leading-tight": "1.25",
        # ── A1-structure: tracking ──────────────────────────────────────
        "--tracking-display": "-0.015em",
        # ── A1-structure: section rhythm ────────────────────────────────
        "--section-y-desktop": sec_desktop,
        "--section-y-tablet": sec_tablet,
        "--section-y-phone": sec_phone,
        # ── A1-structure: layout grid ───────────────────────────────────
        "--container-max": "1280px",
        "--container-gutter-desktop": "32px",
        "--container-gutter-tablet": "24px",
        "--container-gutter-phone": "16px",
    }
    tokens.update(type_scale)

    notes: dict[str, str] = {
        "--text-base": f"{base_px}px, authored from {dominant_density} density signal",
        "--leading-body": "1.6, authored standard",
        "--leading-tight": "1.25, authored standard",
        "--tracking-display": "-0.015em, authored standard",
        "--section-y-desktop": f"{sec_desktop}, authored from {dominant_density} density",
        "--section-y-tablet": f"{sec_tablet}, authored from {dominant_density} density",
        "--section-y-phone": f"{sec_phone}, authored from {dominant_density} density",
        "--container-max": "1280px, authored standard",
        "--container-gutter-desktop": "32px, authored standard",
        "--container-gutter-tablet": "24px, authored standard",
        "--container-gutter-phone": "16px, authored standard",
    }

    return {
        "id": ds_id,
        "name": suggested_name,
        "summary": "Derived from Figma screen exports via visual analysis",
        "provenance": "Visual token extraction from Figma PNG frames by the Design Ingestor agent",
        "fonts_href": "",
        "tokens": tokens,
        "notes": notes,
        "extensions": {},
        "themes": {},
    }


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Convert Design Ingestor observations → source.json + mapping.json"
    )
    ap.add_argument("--manifest", required=True, help="Path to .figma/manifest.json")
    ap.add_argument("--obs", required=True, help="Path to context/design/observations.json")
    ap.add_argument("--out", required=True, help="Output directory for source.json and mapping.json")
    args = ap.parse_args()

    manifest_path = Path(args.manifest)
    obs_path = Path(args.obs)
    out_dir = Path(args.out)

    # Validate inputs
    if not manifest_path.is_file():
        print(f"ERROR: manifest not found: {manifest_path}", file=sys.stderr)
        return 1
    if not obs_path.is_file():
        print(f"ERROR: observations not found: {obs_path}", file=sys.stderr)
        return 1

    # Parse inputs
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"ERROR: failed to parse manifest: {e}", file=sys.stderr)
        return 1

    try:
        obs = json.loads(obs_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"ERROR: failed to parse observations: {e}", file=sys.stderr)
        return 1

    frames = obs.get("frames", [])
    if not frames:
        print("WARNING: observations.json has no frames — using defaults", file=sys.stderr)

    # Aggregate
    color_map, densities, font_hints = _aggregate_tokens(frames)

    # Dominant font family
    font_family = _dominant(font_hints) or "system-ui, sans-serif"
    if "sans-serif" not in font_family and "system-ui" not in font_family:
        font_family = f"{font_family}, system-ui, sans-serif"

    # Build output files
    source = _build_source_json(manifest, obs, color_map, font_family)
    mapping = _build_mapping_json(obs, color_map, densities, font_hints)

    # Write outputs
    out_dir.mkdir(parents=True, exist_ok=True)
    source_path = out_dir / "source.json"
    mapping_path = out_dir / "mapping.json"

    source_path.write_text(json.dumps(source, indent=2, ensure_ascii=False), encoding="utf-8")
    mapping_path.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"wrote {source_path}")
    print(f"wrote {mapping_path}")
    print(f"  id={mapping['id']}  name={mapping['name']}")
    print(f"  tokens: {len(mapping['tokens'])} entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
