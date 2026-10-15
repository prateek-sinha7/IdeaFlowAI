"""agents/capabilities/prototype_ui_extract.py — mechanical: extract_prototype_ui.

Reads the look and feel of the prototype the backlog is written against, by code, in
headless Chromium — no model involved. Whatever the design came from (a wizard
template and design system, a custom HTML, a site), it ends up in ``prototype.html``,
so the rendered prototype is the one source of truth for UI and UX.

Where the prototype comes from, in order:
  1. ``.context/prototype.html`` — installed by ``chain_context`` when the run was
     chained from a ``prototype_v2`` run (its ``.chain/`` payload).
  2. The first ``.html``/``.htm`` upload in ``.uploads/``.
  3. None — ``build/ui/source.json`` says so and nothing else is written; the UI/UX
     writer then records that no visual source was given, never invents one.

A chained prototype is also STAGED as an upload (``.uploads/prototype.html`` plus a
``.uploads/manifest.json`` entry), which is why this step runs first: the Reading
Planner discovers its inputs from that manifest, so the prototype's screens reach the
synthesis and the stories exactly as if the user had uploaded it.

Writes ``build/ui/``:
  source.json       where the prototype came from (or why there is none)
  tokens.json       the effective CSS variables, the palette by usage and role, fonts,
                    type scale, radii, shadows and the brand the PDF is themed with
  components.json   one record per component kind found on the opening screen, with
                    its computed style and a screenshot ``components/<kind>.png``
  navigation.json   every screen (title, screenshot) and every ``goes to`` edge
  screens/          ``html_extract``'s per-screen materialisation (text.md + image-1.png)
"""

from __future__ import annotations

import asyncio
import colorsys
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, AsyncIterator

from agents.capabilities.registry import register

logger = logging.getLogger(__name__)

UI_DIR = "build/ui"
CHAINED_SOURCE = ".context/prototype.html"
UPLOADS_DIR = ".uploads"

# The variable names a design system uses for its brand colour, most specific first.
_BRAND_VARS = (
    "--color-primary",
    "--primary",
    "--brand",
    "--color-brand",
    "--primary-color",
    "--accent",
    "--color-accent",
)

_COMPONENTS = {
    "button_primary": ".btn-primary, button.primary, .button-primary, button[type=submit]",
    "button": "button, .btn, [role=button]",
    "input": (
        "input[type=text], input[type=email], input[type=password], input[type=search], "
        "input[type=tel], input[type=number], input[type=date], input:not([type])"
    ),
    "select": "select",
    "textarea": "textarea",
    "checkbox": "input[type=checkbox], input[type=radio]",
    "table": "table",
    "card": ".card, [class*=card]",
    "badge": ".badge, .tag, .chip, .pill, [class*=badge], [class*=status]",
    "navigation": "nav, [role=navigation], .sidebar, aside",
    "header": "header, [role=banner]",
    "tabs": "[role=tablist], .tabs",
    "alert": "[role=alert], .alert, .toast, .banner",
    "dialog": "dialog[open], [role=dialog], .modal",
    "link": "a[href]",
}

_PROBE_JS = """(kinds) => {
  const visible = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const root = getComputedStyle(document.documentElement);
  const names = new Set();
  const walk = (rules) => { for (const r of rules) {
    if (r.style) for (const p of r.style) if (p.startsWith('--')) names.add(p);
    if (r.cssRules) walk(r.cssRules); } };
  for (const sheet of document.styleSheets) { try { walk(sheet.cssRules); } catch (e) {} }
  const variables = {};
  for (const n of names) { const v = root.getPropertyValue(n).trim(); if (v) variables[n] = v; }

  const tally = {colors: {}, fonts: {}, sizes: {}, radii: {}, shadows: {}};
  const add = (m, k, role) => { if (!k) return; m[k] = m[k] || {count: 0, roles: {}}; m[k].count++;
    if (role) m[k].roles[role] = (m[k].roles[role] || 0) + 1; };
  for (const e of document.querySelectorAll('body, body *')) {
    if (!visible(e)) continue;
    const s = getComputedStyle(e);
    const hasText = [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (hasText) { add(tally.colors, s.color, 'text'); add(tally.fonts, s.fontFamily);
      add(tally.sizes, s.fontSize + '|' + s.fontWeight + '|' + e.tagName.toLowerCase()); }
    if (s.backgroundColor && !/rgba\\(0, 0, 0, 0\\)|transparent/.test(s.backgroundColor))
      add(tally.colors, s.backgroundColor, 'background');
    if (parseFloat(s.borderTopWidth) > 0 && s.borderTopStyle !== 'none') add(tally.colors, s.borderTopColor, 'border');
    if (s.borderTopLeftRadius && s.borderTopLeftRadius !== '0px') add(tally.radii, s.borderTopLeftRadius);
    if (s.boxShadow && s.boxShadow !== 'none') add(tally.shadows, s.boxShadow);
  }

  const components = {};
  const keys = ['color', 'backgroundColor', 'borderTopColor', 'borderTopWidth', 'borderTopLeftRadius',
                'fontFamily', 'fontSize', 'fontWeight', 'paddingTop', 'paddingLeft', 'boxShadow', 'height'];
  for (const [kind, sel] of Object.entries(kinds)) {
    let found = null;
    try { found = [...document.querySelectorAll(sel)].find(e => visible(e)
      && e.getBoundingClientRect().width < 1400 && !e.closest('[data-ui-probe]')); } catch (e) {}
    if (!found) continue;
    found.setAttribute('data-ui-probe', kind);
    const s = getComputedStyle(found);
    const style = {}; for (const k of keys) style[k] = s[k];
    components[kind] = {tag: found.tagName.toLowerCase(), classes: found.className && String(found.className),
                        text: (found.innerText || found.value || '').trim().slice(0, 60), style};
  }
  const b = getComputedStyle(document.body);
  return {title: document.title, variables, tally, components,
          body: {fontFamily: b.fontFamily, color: b.color, background: b.backgroundColor, fontSize: b.fontSize}};
}"""


# ── colour helpers ────────────────────────────────────────────────────────────────

_RGB = re.compile(
    r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,\s/]+([\d.]+))?\s*\)"
)
_HEX = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def to_hex(value: str) -> str | None:
    """``rgb(...)``/``rgba(...)``/``#abc``/``#aabbcc`` → ``#AABBCC``; transparent → None."""
    value = (value or "").strip()
    m = _HEX.match(value)
    if m:
        h = m.group(1)
        h = "".join(c * 2 for c in h) if len(h) == 3 else h
        return f"#{h.upper()}"
    m = _RGB.match(value)
    if not m:
        return None
    if m.group(4) is not None and float(m.group(4)) == 0:
        return None
    r, g, b = (round(float(m.group(i))) for i in (1, 2, 3))
    return f"#{r:02X}{g:02X}{b:02X}"


def _saturation(hex_color: str) -> tuple[float, float]:
    r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    _h, lightness, sat = colorsys.rgb_to_hls(r, g, b)
    return sat, lightness


def readable_on(hex_color: str) -> str:
    """White or near-black, whichever contrasts more with ``hex_color``. 0.179 is the
    WCAG relative luminance at which the two contrast equally."""

    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(int(hex_color[i : i + 2], 16) / 255) for i in (1, 3, 5))
    return "#FFFFFF" if 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.179 else "#15161A"


def build_tokens(probe: dict) -> dict:
    """The raw browser probe → ``tokens.json``: palette by usage with roles and the
    variables naming each colour, fonts, type scale, radii, shadows and the brand."""
    variables = probe.get("variables") or {}
    by_hex: dict[str, list[str]] = {}
    for name, value in variables.items():
        h = to_hex(value)
        if h:
            by_hex.setdefault(h, []).append(name)

    palette: dict[str, dict] = {}
    for raw, info in (probe.get("tally") or {}).get("colors", {}).items():
        h = to_hex(raw)
        if not h:
            continue
        entry = palette.setdefault(h, {"hex": h, "count": 0, "roles": {}})
        entry["count"] += info["count"]
        for role, n in info["roles"].items():
            entry["roles"][role] = entry["roles"].get(role, 0) + n
    colors = sorted(palette.values(), key=lambda c: -c["count"])
    for c in colors:
        c["variables"] = sorted(by_hex.get(c["hex"], []))
    # A declared colour the opening screen never shows is still part of the system.
    shown = {c["hex"] for c in colors}
    for h, names in sorted(by_hex.items()):
        if h not in shown:
            colors.append(
                {"hex": h, "count": 0, "roles": {}, "variables": sorted(names)}
            )

    def ranked(key: str) -> list[dict]:
        items = (probe.get("tally") or {}).get(key, {})
        return [
            {"value": k, "count": v["count"]}
            for k, v in sorted(items.items(), key=lambda kv: -kv[1]["count"])
        ]

    scale = []
    for item in ranked("sizes"):
        size, weight, tag = (item["value"].split("|") + ["", "", ""])[:3]
        scale.append(
            {"size": size, "weight": weight, "tag": tag, "count": item["count"]}
        )

    body = probe.get("body") or {}
    brand = None
    for name in _BRAND_VARS:
        brand = to_hex(variables.get(name, ""))
        if brand:
            break
    if not brand:  # the most-used saturated background: buttons, headers, active states
        saturated = [
            c
            for c in colors
            if "background" in c["roles"]
            and _saturation(c["hex"])[0] > 0.35
            and 0.15 < _saturation(c["hex"])[1] < 0.85
        ]
        brand = saturated[0]["hex"] if saturated else None
    return {
        "title": probe.get("title") or "",
        "variables": variables,
        "colors": colors,
        "fonts": ranked("fonts"),
        "type_scale": scale,
        "radii": ranked("radii"),
        "shadows": ranked("shadows"),
        "body": {
            "font_family": body.get("fontFamily"),
            "font_size": body.get("fontSize"),
            "text": to_hex(body.get("color", "")),
            "background": to_hex(body.get("background", "")),
        },
        "brand": (
            {"primary": brand, "on_primary": readable_on(brand)} if brand else None
        ),
    }


# ── navigation from html_extract's per-screen pages ───────────────────────────────

_SCREEN_TITLE = re.compile(r"^# Screen: (.+)$", re.M)
_SCREEN_ID = re.compile(r"^id: ([^\s·]+)", re.M)
_GOTO = re.compile(r"^\| (.+?) \| .*?data-goto=([\w-]+).*\|\s*$", re.M)


def build_navigation(screens_dir: Path) -> dict:
    screens, edges = [], []
    for page in sorted((screens_dir / "pages").glob("*/text.md")):
        text = page.read_text(encoding="utf-8", errors="replace")
        title, sid = _SCREEN_TITLE.search(text), _SCREEN_ID.search(text)
        if not (title and sid):
            continue
        image = page.parent / "image-1.png"
        screens.append(
            {
                "id": sid.group(1),
                "title": title.group(1).strip(),
                "screenshot": f"{UI_DIR}/screens/pages/{page.parent.name}/image-1.png"
                if image.exists()
                else None,
            }
        )
        seen = set()
        for label, target in _GOTO.findall(text):
            if (target, label) not in seen:
                seen.add((target, label))
                edges.append(
                    {"from": sid.group(1), "to": target, "label": label.strip()}
                )
    return {"screens": screens, "edges": edges}


# ── the step ──────────────────────────────────────────────────────────────────────


def find_source(sandbox: Any) -> str | None:
    """The prototype this backlog is written against, as a sandbox path, or None."""
    if sandbox.path_for(CHAINED_SOURCE).is_file():
        return CHAINED_SOURCE
    uploads = sandbox.path_for(UPLOADS_DIR)
    if uploads.is_dir():
        html_files = [
            p
            for p in sorted(uploads.iterdir())
            if p.is_file() and p.suffix.lower() in (".html", ".htm")
        ]
        # Prefer a file whose name starts with "prototype" (the canonical name
        # for chained or uploaded prototype HTML). Without this guard, sorted()
        # would return the first alphabetical HTML upload, which might be an
        # unrelated document (e.g. "docker-commands-reference.html").
        for p in html_files:
            if p.stem.lower().startswith("prototype"):
                return f"{UPLOADS_DIR}/{p.name}"
        # Fall back to any HTML upload if no prototype-named file exists.
        if html_files:
            return f"{UPLOADS_DIR}/{html_files[0].name}"
    return None


def stage_chained_prototype(sandbox: Any) -> bool:
    """Copy a chained ``.context/prototype.html`` into ``.uploads/`` and its manifest.

    Returns True when it staged one. An upload of the same name wins — the user's own
    file is never replaced."""
    chained = sandbox.path_for(CHAINED_SOURCE)
    target = sandbox.path_for(f"{UPLOADS_DIR}/prototype.html")
    if not chained.is_file() or target.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(chained.read_bytes())
    manifest_path = sandbox.path_for(f"{UPLOADS_DIR}/manifest.json")
    try:
        entries = (
            json.loads(manifest_path.read_text()) if manifest_path.exists() else []
        )
    except ValueError:
        entries = []
    if not any(
        isinstance(e, dict) and e.get("name") == "prototype.html" for e in entries
    ):
        entries.append(
            {"name": "prototype.html", "mime": "text/html", "has_text": False}
        )
    manifest_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2))
    return True


async def _probe(source: Path, out: Path) -> tuple[dict, dict]:
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--no-sandbox"])
        try:
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            await page.goto(
                source.resolve().as_uri(), wait_until="load", timeout=60_000
            )
            await page.evaluate("document.fonts.ready")
            probe = await page.evaluate(_PROBE_JS, _COMPONENTS)
            (out / "components").mkdir(parents=True, exist_ok=True)
            for kind, record in (probe.get("components") or {}).items():
                try:
                    await page.locator(f'[data-ui-probe="{kind}"]').first.screenshot(
                        path=str(out / "components" / f"{kind}.png"), timeout=10_000
                    )
                    record["screenshot"] = f"{UI_DIR}/components/{kind}.png"
                except Exception as exc:  # noqa: BLE001 — a missing crop never loses the record
                    record["screenshot"] = None
                    logger.info(
                        "extract_prototype_ui: no screenshot for %s (%s)", kind, exc
                    )
            components = probe.get("components") or {}
            for record in components.values():  # colours as #RRGGBB, like tokens.json
                for key in ("color", "backgroundColor", "borderTopColor"):
                    record["style"][key] = (
                        to_hex(record["style"].get(key, "")) or "transparent"
                    )
            return probe, components
        finally:
            await browser.close()


async def extract_prototype_ui(sandbox: Any, materialise_html: Any) -> str:
    """Write ``build/ui/`` from the prototype; return the step's one-line reply.

    ``materialise_html`` is injected by the caller (``ctx.runner.materialise_html``)
    rather than imported here — a capability must not import the app layer directly
    (Ports & Adapters; see KernelServices.materialise_html)."""
    out = sandbox.path_for(UI_DIR)
    out.mkdir(parents=True, exist_ok=True)
    # The screenshots are regenerated from the prototype on any rerun, and the
    # run-history commit's binary scan refuses PNGs: keep them out of git.
    (out / ".gitignore").write_text("*.png\n")
    staged = stage_chained_prototype(sandbox)
    source = find_source(sandbox)
    if source is None:
        (out / "source.json").write_text(
            json.dumps(
                {
                    "source": None,
                    "reason": "No prototype: no chained prototype.html and no HTML upload.",
                },
                indent=2,
            )
        )
        return "No prototype to extract: no chained prototype.html and no HTML upload."

    path = sandbox.path_for(source)
    try:
        probe, components = await _probe(path, out)
    except Exception as exc:  # noqa: BLE001 — no browser means no UI facts, never a failed run
        (out / "source.json").write_text(
            json.dumps(
                {
                    "source": source,
                    "reason": f"The prototype could not be rendered: {exc}",
                },
                indent=2,
            )
        )
        return f"Prototype {source} could not be rendered: {exc}"

    tokens = build_tokens(probe)
    (out / "tokens.json").write_text(json.dumps(tokens, indent=2))
    (out / "components.json").write_text(json.dumps(components, indent=2))

    screens_dir = out / "screens"
    await asyncio.to_thread(
        materialise_html,
        path.resolve(),
        path.read_bytes(),
        screens_dir,
        path.name,
        "screens",
    )
    navigation = build_navigation(screens_dir)
    (out / "navigation.json").write_text(json.dumps(navigation, indent=2))
    (out / "source.json").write_text(
        json.dumps({"source": source, "reason": None}, indent=2)
    )
    return (
        ("Staged the chained prototype as .uploads/prototype.html. " if staged else "")
        + f"Extracted the look and feel of {source}: {len(tokens['colors'])} colours, "
        f"{len(tokens['fonts'])} font(s), {len(components)} component kinds, "
        f"{len(navigation['screens'])} screens, {len(navigation['edges'])} navigation edges."
    )


@register(
    "mechanical",
    "extract_prototype_ui",
    user_allowed=True,
    description=(
        "Reads the look and feel of the prototype a workflow is written against — a chained "
        "prototype_v2 run's prototype.html, or an uploaded HTML — by rendering it in a headless "
        "browser. Pure code, no AI. Writes build/ui/: the effective design tokens (palette by "
        "usage, fonts, type scale, radii, shadows, brand colour), one screenshot per component "
        "kind, one screenshot per screen and the navigation between screens."
    ),
    reads=[".context/prototype.html", ".uploads/"],
    process=(
        "Renders the prototype in a headless browser and measures what it shows: design tokens, "
        "a screenshot per component kind and per screen, and the navigation between screens. "
        "With no prototype it writes only build/ui/source.json, saying why."
    ),
    writes=[
        "build/ui/source.json",
        "build/ui/tokens.json",
        "build/ui/components.json",
        "build/ui/navigation.json",
        "build/ui/components/",
        "build/ui/screens/",
        "build/ui/.gitignore",
        ".uploads/prototype.html",
    ],
)
class _ExtractPrototypeUiRegistryStub:
    """Registry entry for the palette; the engine dispatches the strategy below."""


class MechanicalExtractPrototypeUiStrategy:
    """``strategy``-shaped adapter for ``mechanical: extract_prototype_ui``."""

    name = "extract_prototype_ui"

    def __init__(self, *, spec: Any, index: int, total: int, results: list) -> None:
        self._spec = spec
        self._index = index
        self._total = total
        self._results = results

    async def run(self, step: Any, ctx: Any) -> AsyncIterator[dict]:
        spec = self._spec
        yield {
            "type": "agent_start",
            "data": {
                "agent_id": spec.id,
                "name": spec.name,
                "role": getattr(spec, "role", None),
                "icon": getattr(spec, "icon", None),
                "index": self._index,
                "total": self._total,
            },
        }
        started = time.time()
        content = await extract_prototype_ui(
            ctx.runner.sandbox, ctx.runner.materialise_html
        )
        yield {"type": "agent_chunk", "data": {"agent_id": spec.id, "chunk": content}}
        duration = time.time() - started
        self._results.append(
            {
                "agent_id": spec.id,
                "name": spec.name,
                "role": getattr(spec, "role", None),
                "icon": getattr(spec, "icon", None),
                "output": content,
                "duration": duration,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
            }
        )
        yield {
            "type": "agent_complete",
            "data": {
                "agent_id": spec.id,
                "name": spec.name,
                "duration": round(duration, 2),
                "output_length": len(content),
                "index": self._index,
                "total": self._total,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            },
        }
