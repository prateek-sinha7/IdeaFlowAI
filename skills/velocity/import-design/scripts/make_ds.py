#!/usr/bin/env python3
"""Generate tokens.css and components.html for a design system from a mapping.

Usage:
    python3 make_ds.py <mapping.json> --dest <od-root>/design-systems/<id>

mapping.json (written by the agent after reading the source):
{
  "id": "acme",                       # folder name, kebab-case
  "name": "Acme",                     # brand name (H1 is "Design System Inspired by <name>")
  "lang": "en",
  "summary": "one line for the header comment",
  "provenance": "where the values came from (export / url / spec) and what was authored",
  "fonts_href": "https://fonts.googleapis.com/css2?family=...&display=swap",   # or "" for system fonts
  "tokens":     { "--bg": "#fafafa", ... },     # every A1 token (8 identity + 18 structure) is REQUIRED;
                                                # A2 omitted -> schema fallback; B-slot omitted -> alias
  "notes":      { "--danger": "critical red, NOT a variant of --accent" },  # optional inline comments
  "extensions": { "--info": "#1f5fa8" },        # optional brand-only tokens (need a BRAND_EXTENSIONS entry)
  "themes":     { "[data-theme=\\"dark\\"]": { "--bg": "#111" } },  # optional extra theme blocks: override EVERY
                                                # surface/fg/border/semantic/accent-state token
  "button_radius": "--radius-pill",             # optional: radius token for buttons (pill-button brands)
  "signature_html": "<section ...>...</section>"  # optional: brand components (brand bar, chips, domain
                                                # component) rendered after the hero; var(--*) only
}
"provenance" and "notes" are written INTO tokens.css: no scratch or absolute paths.

Writes <dest>/tokens.css and <dest>/components.html. components.html carries the
:root block VERBATIM (same declarations as tokens.css) and uses only var(--*).
Never touches DESIGN.md. Prints the BRAND_EXTENSIONS snippet when extensions are used.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ds_schema import load_schema, od_root_from  # noqa: E402

GROUPS = [
    ("Surface", ["--bg", "--surface", "--surface-warm"]),
    ("Foreground", ["--fg", "--fg-2", "--muted", "--meta"]),
    ("Border", ["--border", "--border-soft"]),
    ("Accent", ["--accent", "--accent-on", "--accent-hover", "--accent-active"]),
    ("Semantic", ["--success", "--warn", "--danger"]),
    ("Type families", ["--font-display", "--font-body", "--font-mono"]),
    ("Type scale", ["--text-xs", "--text-sm", "--text-base", "--text-lg", "--text-xl", "--text-2xl", "--text-3xl", "--text-4xl",
                    "--leading-body", "--leading-tight", "--tracking-display"]),
    ("Spacing", ["--space-1", "--space-2", "--space-3", "--space-4", "--space-5", "--space-6", "--space-8", "--space-12",
                 "--section-y-desktop", "--section-y-tablet", "--section-y-phone"]),
    ("Radius", ["--radius-sm", "--radius-md", "--radius-lg", "--radius-pill"]),
    ("Elevation & focus", ["--elev-flat", "--elev-ring", "--elev-raised", "--focus-ring"]),
    ("Motion", ["--motion-fast", "--motion-base", "--ease-standard"]),
    ("Layout", ["--container-max", "--container-gutter-desktop", "--container-gutter-tablet", "--container-gutter-phone"]),
]


def build_root(m: dict, schema: dict) -> tuple[list[tuple[str, str, str]], list[str]]:
    """[(name, value, comment)] in schema group order, plus errors."""
    toks = m.get("tokens", {})
    notes = m.get("notes", {})
    by = {t["name"]: t for t in schema["tokens"]}
    errors, rows = [], []
    groups = list(GROUPS)
    grouped = {n for _, ns in GROUPS for n in ns}
    extra = [n for n in by if n not in grouped]
    if extra:
        groups.append(("Other schema tokens", extra))
    for title, names in groups:
        rows.append(("", "", f"── {title} ", "head"))
        for n in names:
            t = by.get(n)
            if t is None:
                continue
            if n in toks and str(toks[n]).strip():
                rows.append((n, str(toks[n]).strip(), notes.get(n, ""), "given"))
            elif t["layer"] == "A2" and "fallback" in t:
                rows.append((n, t["fallback"], (notes.get(n, "") + " (schema default)").strip(), "default"))
            elif t["layer"] == "B-slot" and "aliasTo" in t:
                rows.append((n, t["aliasTo"], (notes.get(n, "") + " (alias: no separate tier)").strip(), "alias"))
            else:
                errors.append(f"{n} ({t['layer']}) has no value and no default -- it must be authored")
    for k, v in list(toks.items()) + list((m.get("extensions") or {}).items()):
        v = str(v)
        if v.count("(") != v.count(")") or re.search(r"\)\s+\(|\b(authored|source|todo|tbd)\b|[;{}]", v, re.I):
            errors.append(f"{k}: value {v!r} is not plain CSS -- notes like '(authored)' go in mapping.notes")
    unknown = [k for k in toks if k not in by]
    if unknown:
        errors.append(f"tokens not in the schema (move them to 'extensions'): {unknown}")
    ext = m.get("extensions", {})
    if ext:
        rows.append(("", "", "── Brand extensions (BRAND_EXTENSIONS allowlist) ", "head"))
        for n, v in ext.items():
            rows.append((n, str(v).strip(), notes.get(n, ""), "extension"))
    return rows, errors


def css_lines(rows: list[tuple[str, str, str]], indent: str) -> str:
    out = []
    for n, v, c, _ in rows:
        if not n:
            out.append(f"\n{indent}/* {c}{'─' * max(0, 60 - len(c))} */")
            continue
        out.append(f"{indent}{n}: {v};" + (f"  /* {c} */" if c else ""))
    return "\n".join(out).lstrip("\n")


def theme_blocks(m: dict, indent: str = "") -> str:
    blocks = []
    for sel, decls in (m.get("themes") or {}).items():
        body = "\n".join(f"{indent}  {k}: {v};" for k, v in decls.items())
        blocks.append(f"{indent}{sel} {{\n{body}\n{indent}}}")
    return "\n\n".join(blocks)


def tokens_css(m: dict, rows) -> str:
    themes = theme_blocks(m)
    return f"""/* ─────────────────────────────────────────────────────────────────────────
 * design-systems/{m['id']}/tokens.css
 *
 * Structured token bindings for the {m['name']}-inspired design system.
 * {m.get('summary', '').strip()}
 *
 * This file is the machine-readable form of the values described in
 * DESIGN.md. Agents paste the `:root {{ … }}` block verbatim into the first
 * <style> of every artifact and then reference values only via var(--name).
 * components.html carries the same :root block -- keep them in sync.
 *
 * Provenance: {m.get('provenance', '').strip()}
 * Generated by the import-design skill; edit values here AND in
 * components.html, or re-run make_ds.py from the mapping.
 * ───────────────────────────────────────────────────────────────────────── */

:root {{
{css_lines(rows, '  ')}
}}
{chr(10) + themes + chr(10) if themes else ''}"""


def components_html(m: dict, rows) -> str:
    name = html.escape(m["name"])
    lang = m.get("lang", "en")
    href = m.get("fonts_href", "")
    link = (
        '    <link rel="preconnect" href="https://fonts.googleapis.com" />\n'
        '    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />\n'
        f'    <link href="{html.escape(href)}" rel="stylesheet" />\n'
    ) if href else ""
    color_names = [n for n, v, _, _ in rows if n and (re.match(r"^(#|rgb|hsl|oklch|color-mix|var\(--(bg|surface|fg|muted|border|accent))", v) or n in ("--success", "--warn", "--danger"))
                   and not n.startswith(("--font", "--text", "--space", "--radius", "--elev", "--focus", "--motion", "--ease", "--container", "--section", "--leading", "--tracking"))]
    ext_names = set((m.get("extensions") or {}).keys())
    info_var = "--info" if "--info" in ext_names else "--accent"
    btn_radius = m.get("button_radius", "--radius-sm")
    signature = m.get("signature_html", "")
    swatches = "\n".join(
        f'          <div class="swatch"><span class="chip" style="background:var({n})"></span><code>{n}</code></div>'
        for n in color_names
    )
    scale = "\n".join(
        f'          <div class="type-row"><code>{n}</code><span style="font-size:var({n})">{s}</span></div>'
        for n, s in [("--text-4xl", "Display"), ("--text-3xl", "Heading 1"), ("--text-2xl", "Section"), ("--text-xl", "Heading 2"),
                     ("--text-lg", "Heading 3"), ("--text-base", "Body text"), ("--text-sm", "Small text"), ("--text-xs", "Caption")]
    )
    spaces = "\n".join(
        f'          <div class="space-row"><code>{n}</code><span class="bar" style="width:var({n})"></span></div>'
        for n in ["--space-1", "--space-2", "--space-3", "--space-4", "--space-5", "--space-6", "--space-8", "--space-12"]
    )
    radii = "\n".join(f'          <div class="radius" style="border-radius:var({n})"><code>{n}</code></div>' for n in ["--radius-sm", "--radius-md", "--radius-lg", "--radius-pill"])
    elevs = "\n".join(f'          <div class="card" style="box-shadow:var({n})"><code>{n}</code><p>Surface with {n[2:]}.</p></div>' for n in ["--elev-flat", "--elev-ring", "--elev-raised"])
    themes = theme_blocks(m, "      ")
    return f"""<!doctype html>
<html lang="{lang}">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{name} — reference components</title>
    <meta name="description" content="Reference fixture for design-systems/{m['id']}. Every visible value comes from tokens.css via var(--*)." />
{link}
    <style>
      /* :root paste — sourced verbatim from design-systems/{m['id']}/tokens.css.
         Keep this block in sync when tokens.css changes. */
      :root {{
{css_lines(rows, '        ')}
      }}
{themes}
    </style>
    <style>
      *, *::before, *::after {{ box-sizing: border-box; }}
      html {{ -webkit-text-size-adjust: 100%; }}
      body {{ margin: 0; background: var(--bg); color: var(--fg); font-family: var(--font-body);
        font-size: var(--text-base); line-height: var(--leading-body); }}
      h1, h2, h3 {{ font-family: var(--font-display); line-height: var(--leading-tight); margin: 0 0 var(--space-3); }}
      h1 {{ font-size: var(--text-4xl); letter-spacing: var(--tracking-display); }}
      h2 {{ font-size: var(--text-2xl); }}
      h3 {{ font-size: var(--text-lg); }}
      p {{ margin: 0 0 var(--space-3); }}
      code {{ font-family: var(--font-mono); font-size: var(--text-xs); color: var(--meta); }}
      .wrap {{ max-width: var(--container-max); margin: 0 auto; padding: 0 var(--container-gutter-desktop); }}
      section {{ padding: var(--section-y-desktop) 0; border-bottom: 1px solid var(--border-soft); }}
      .eyebrow {{ font-size: var(--text-xs); text-transform: uppercase; letter-spacing: .08em; color: var(--muted); margin-bottom: var(--space-2); }}
      .bar-top {{ background: var(--surface); border-bottom: 1px solid var(--border); }}
      .bar-top .wrap {{ display: flex; align-items: center; gap: var(--space-6); height: 64px; }}
      .brand {{ font-family: var(--font-display); font-weight: 700; font-size: var(--text-lg); color: var(--fg); }}
      .bar-top nav {{ display: flex; gap: var(--space-4); flex: 1; }}
      .bar-top nav a {{ color: var(--fg-2); text-decoration: none; font-size: var(--text-sm); }}
      .bar-top nav a[aria-current] {{ color: var(--accent); font-weight: 600; }}
      .lead {{ font-size: var(--text-lg); color: var(--fg-2); max-width: 60ch; }}
      .row {{ display: flex; flex-wrap: wrap; gap: var(--space-3); align-items: center; }}
      .btn {{ font: inherit; font-size: var(--text-sm); font-weight: 600; padding: var(--space-2) var(--space-4); min-height: 40px;
        border-radius: var({btn_radius}); border: 1px solid transparent; cursor: pointer;
        transition: background var(--motion-fast) var(--ease-standard), box-shadow var(--motion-fast) var(--ease-standard); }}
      .btn:focus-visible {{ outline: none; box-shadow: var(--focus-ring); }}
      .btn-primary {{ background: var(--accent); color: var(--accent-on); }}
      .btn-primary:hover {{ background: var(--accent-hover); }}
      .btn-primary:active {{ background: var(--accent-active); }}
      .btn-secondary {{ background: var(--surface); color: var(--fg); border-color: var(--border); }}
      .btn-secondary:hover {{ background: var(--surface-warm); }}
      .btn-ghost {{ background: transparent; color: var(--accent); }}
      .btn-danger {{ background: var(--danger); color: var(--accent-on); }}
      .btn[disabled] {{ opacity: .45; cursor: not-allowed; }}
      .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: var(--space-4); }}
      .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md); padding: var(--space-5); }}
      .swatches {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: var(--space-3); }}
      .swatch {{ display: flex; align-items: center; gap: var(--space-2); }}
      .swatch .chip {{ width: 40px; height: 40px; border-radius: var(--radius-sm); box-shadow: var(--elev-ring); flex: none; }}
      .type-row {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-4); padding: var(--space-2) 0; border-bottom: 1px solid var(--border-soft); }}
      .type-row span {{ min-width: 0; overflow-wrap: anywhere; }}
      .type-row code {{ width: 120px; flex: none; }}
      .type-row span {{ font-family: var(--font-display); line-height: var(--leading-tight); }}
      .mono {{ font-family: var(--font-mono); font-variant-numeric: tabular-nums; }}
      label {{ display: block; font-size: var(--text-sm); font-weight: 600; margin-bottom: var(--space-1); }}
      .field {{ margin-bottom: var(--space-4); }}
      input[type=text], select, textarea {{ font: inherit; width: 100%; padding: var(--space-2) var(--space-3); min-height: 40px;
        background: var(--surface); color: var(--fg); border: 1px solid var(--border); border-radius: var(--radius-sm); }}
      input[type=text]:focus, select:focus, textarea:focus {{ outline: none; border-color: var(--accent); box-shadow: var(--focus-ring); }}
      .help {{ font-size: var(--text-xs); color: var(--muted); margin-top: var(--space-1); }}
      .error input {{ border-color: var(--danger); }} .error .help {{ color: var(--danger); }}
      .check {{ display: flex; gap: var(--space-2); align-items: center; font-weight: 400; }}
      .check input {{ accent-color: var(--accent); width: 18px; height: 18px; }}
      table {{ width: 100%; border-collapse: collapse; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md); overflow: hidden; }}
      th, td {{ text-align: left; padding: var(--space-3) var(--space-4); border-bottom: 1px solid var(--border-soft); font-size: var(--text-sm); }}
      th {{ background: var(--surface-warm); color: var(--muted); font-weight: 600; font-size: var(--text-xs); text-transform: uppercase; letter-spacing: .04em; }}
      .badge {{ display: inline-flex; align-items: center; gap: var(--space-1); padding: 2px var(--space-2); border-radius: var(--radius-pill);
        font-size: var(--text-xs); font-weight: 600; border: 1px solid currentColor; }}
      .ok {{ color: var(--success); }} .warn {{ color: var(--warn); }} .bad {{ color: var(--danger); }} .info {{ color: var({info_var}); }}
      .alert {{ border-left: 4px solid currentColor; background: var(--surface); padding: var(--space-3) var(--space-4); border-radius: var(--radius-sm);
        box-shadow: var(--elev-ring); margin-bottom: var(--space-3); }}
      .alert p {{ color: var(--fg); margin: 0; }}
      .space-row {{ display: flex; align-items: center; gap: var(--space-4); padding: var(--space-1) 0; }}
      .space-row code {{ width: 100px; }} .space-row .bar {{ height: 12px; background: var(--accent); border-radius: 2px; }}
      .radii {{ display: flex; gap: var(--space-4); flex-wrap: wrap; }}
      .radius {{ width: 120px; height: 72px; background: var(--surface); border: 1px solid var(--border); display: grid; place-items: center; }}
      footer {{ padding: var(--space-8) 0; color: var(--muted); font-size: var(--text-sm); }}
      @media (max-width: 1023px) {{ section {{ padding: var(--section-y-tablet) 0; }} .wrap {{ padding: 0 var(--container-gutter-tablet); }} }}
      @media (max-width: 639px) {{ section {{ padding: var(--section-y-phone) 0; }} .wrap {{ padding: 0 var(--container-gutter-phone); }}
        h1 {{ font-size: var(--text-3xl); }} .bar-top nav {{ display: none; }} }}
      @media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; }} }}
    </style>
  </head>
  <body>
    <header class="bar-top" data-od-id="header">
      <div class="wrap">
        <span class="brand">{name}</span>
        <nav aria-label="Primary"><a href="#hero" aria-current="page">Overview</a><a href="#palette">Colour</a><a href="#type">Type</a><a href="#controls">Controls</a><a href="#data">Data</a></nav>
        <button class="btn btn-primary" type="button">Primary action</button>
      </div>
    </header>
    <main>
      <section id="hero" data-od-id="hero">
        <div class="wrap">
          <div class="eyebrow">{name} design system</div>
          <h1>Every value on this page is a token.</h1>
          <p class="lead">Colours, type, spacing, radius, elevation and motion all resolve through var(--*) from tokens.css.</p>
          <div class="row"><button class="btn btn-primary" type="button">Get started</button><button class="btn btn-secondary" type="button">Learn more</button><button class="btn btn-ghost" type="button">Ghost link</button></div>
        </div>
      </section>
{signature}
      <section id="palette" data-od-id="palette">
        <div class="wrap">
          <h2>Colour</h2>
          <div class="swatches">
{swatches}
          </div>
        </div>
      </section>
      <section id="type" data-od-id="type">
        <div class="wrap">
          <h2>Type scale</h2>
{scale}
          <p class="mono" style="margin-top:var(--space-4)">Mono 0123456789 · AB-1234 · 12:45</p>
        </div>
      </section>
      <section id="controls" data-od-id="form">
        <div class="wrap grid">
          <div>
            <h2>Buttons</h2>
            <div class="row"><button class="btn btn-primary" type="button">Primary</button><button class="btn btn-secondary" type="button">Secondary</button><button class="btn btn-ghost" type="button">Ghost</button><button class="btn btn-danger" type="button">Destructive</button><button class="btn btn-primary" type="button" disabled>Disabled</button></div>
          </div>
          <form onsubmit="return false">
            <h2>Form</h2>
            <div class="field"><label for="f1">Full name</label><input id="f1" type="text" placeholder="Jane Doe" /><div class="help">As it appears on the document.</div></div>
            <div class="field error"><label for="f2">Reference</label><input id="f2" type="text" value="12" aria-invalid="true" /><div class="help">Enter six characters.</div></div>
            <div class="field"><label for="f3">Option</label><select id="f3"><option>First option</option><option>Second option</option></select></div>
            <label class="check"><input type="checkbox" checked /> Remember this choice</label>
          </form>
        </div>
      </section>
      <section id="cards" data-od-id="features">
        <div class="wrap">
          <h2>Surfaces &amp; elevation</h2>
          <div class="grid">
{elevs}
          </div>
        </div>
      </section>
      <section id="data" data-od-id="data">
        <div class="wrap">
          <h2>Data &amp; status</h2>
          <div class="alert ok"><p><strong>Saved.</strong> The change is live.</p></div>
          <div class="alert warn"><p><strong>Check this.</strong> One item needs a review.</p></div>
          <div class="alert bad"><p><strong>Failed.</strong> Nothing was changed.</p></div>
          <table>
            <thead><tr><th>Item</th><th>Owner</th><th>Status</th><th>Value</th></tr></thead>
            <tbody>
              <tr><td>Alpha</td><td>Team A</td><td><span class="badge ok">Done</span></td><td class="mono">1,240</td></tr>
              <tr><td>Beta</td><td>Team B</td><td><span class="badge warn">At risk</span></td><td class="mono">860</td></tr>
              <tr><td>Gamma</td><td>Team C</td><td><span class="badge bad">Blocked</span></td><td class="mono">35</td></tr>
              <tr><td>Delta</td><td>Team D</td><td><span class="badge info">New</span></td><td class="mono">—</td></tr>
            </tbody>
          </table>
        </div>
      </section>
      <section id="scale" data-od-id="scale">
        <div class="wrap grid">
          <div><h2>Spacing</h2>
{spaces}
          </div>
          <div><h2>Radius</h2><div class="radii">
{radii}
          </div></div>
        </div>
      </section>
    </main>
    <footer><div class="wrap">{name} — reference components. Generated from tokens.css.</div></footer>
  </body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mapping")
    ap.add_argument("--dest", required=True)
    ap.add_argument("--print-extensions", action="store_true", help="only print the BRAND_EXTENSIONS snippet for tokens.schema.ts")
    a = ap.parse_args()
    m = json.loads(Path(a.mapping).read_text())
    for k in ("id", "name", "tokens"):
        if k not in m:
            print(f"mapping.json needs '{k}'")
            return 2
    dest = Path(a.dest).resolve()
    if dest.name != m["id"]:
        print(f"--dest folder name '{dest.name}' must equal id '{m['id']}'")
        return 2
    schema = load_schema(od_root_from(dest.parent))
    rows, errors = build_root(m, schema)
    allowed = set(schema["extensions"].get(m["id"], []))
    need = [n for n in m.get("extensions", {}) if n not in allowed and not any(n.startswith(p) for p in schema["prefixes"])]
    snippet = ("  " + f'{m["id"]}: [\n' + "\n".join(f'    "{n}", // {m.get("notes", {}).get(n, "brand-only token")}' for n in need) + "\n  ],") if need else ""
    if a.print_extensions:
        print(snippet or f"nothing to add: every extension is already allowlisted for '{m['id']}'")
        print("(--print-extensions writes no files; run make_ds.py again without it to generate)")
        return 0
    if errors:
        print("\n".join("ERROR: " + e for e in errors))
        return 1
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "tokens.css").write_text(tokens_css(m, rows), encoding="utf-8")
    (dest / "components.html").write_text(components_html(m, rows), encoding="utf-8")
    print(f"wrote {dest/'tokens.css'} ({sum(1 for r in rows if r[0])} declarations) and {dest/'components.html'}")
    authored = [r[0] for r in rows if r[0] and r[3] == "given" and "authored" in r[2].lower()]
    sourced = [r[0] for r in rows if r[0] and r[3] == "given" and r[0] not in authored]
    for label, names in (("schema tokens from the source", sourced), ("schema tokens authored (note says authored)", authored),
                         ("schema defaults (A2)", [r[0] for r in rows if r[3] == "default"]),
                         ("aliases (B-slot)", [r[0] for r in rows if r[3] == "alias"]),
                         ("brand extensions", [r[0] for r in rows if r[3] == "extension"])):
        print(f"{label} ({len(names)}): {', '.join(names)}")
    if need:
        print("\nNOT YET ALLOWLISTED -- add to BRAND_EXTENSIONS in design-systems/_schema/tokens.schema.ts, then validate:\n" + snippet)
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
