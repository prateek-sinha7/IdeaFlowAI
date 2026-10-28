#!/usr/bin/env python3
"""Generate tokens.css and components.html for a design system from a mapping.

Sandbox-compatible copy of import-design/scripts/make_ds.py.
Key change: supports OD_SCHEMA_PATH env var to locate tokens.schema.ts
without requiring the full skills/opendesign/ catalog, AND skips the
dest-name == id check when OD_SCHEMA_PATH is set (sandbox mode).

Usage:
    OD_SCHEMA_PATH=skills/figma-ingestor/scripts/schema \
    python3 make_ds.py <mapping.json> --dest context/design/

mapping.json (written by figma_extract.py or by the agent):
{
  "id": "acme",
  "name": "Acme",
  "lang": "en",
  "summary": "one line for the header comment",
  "provenance": "where the values came from",
  "fonts_href": "https://fonts.googleapis.com/...",  # or "" for system fonts
  "tokens": { "--bg": "#fafafa", ... },
  "notes":   { "--danger": "critical red" },
  "extensions": {},
  "themes": {},
  "button_radius": "--radius-sm",  # optional
  "signature_html": ""             # optional
}

Writes <dest>/tokens.css and <dest>/components.html.
"""

from __future__ import annotations

import argparse
import html
import json
import os
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
    (
        "Type scale",
        [
            "--text-xs",
            "--text-sm",
            "--text-base",
            "--text-lg",
            "--text-xl",
            "--text-2xl",
            "--text-3xl",
            "--text-4xl",
            "--leading-body",
            "--leading-tight",
            "--tracking-display",
        ],
    ),
    (
        "Spacing",
        [
            "--space-1",
            "--space-2",
            "--space-3",
            "--space-4",
            "--space-5",
            "--space-6",
            "--space-8",
            "--space-12",
            "--section-y-desktop",
            "--section-y-tablet",
            "--section-y-phone",
        ],
    ),
    ("Radius", ["--radius-sm", "--radius-md", "--radius-lg", "--radius-pill"]),
    (
        "Elevation & focus",
        ["--elev-flat", "--elev-ring", "--elev-raised", "--focus-ring"],
    ),
    ("Motion", ["--motion-fast", "--motion-base", "--ease-standard"]),
    (
        "Layout",
        [
            "--container-max",
            "--container-gutter-desktop",
            "--container-gutter-tablet",
            "--container-gutter-phone",
        ],
    ),
]


def build_root(
    m: dict, schema: dict
) -> tuple[list[tuple[str, str, str, str]], list[str]]:
    """[(name, value, comment, kind)] in schema group order, plus errors."""
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
                rows.append(
                    (
                        n,
                        t["fallback"],
                        (notes.get(n, "") + " (schema default)").strip(),
                        "default",
                    )
                )
            elif t["layer"] == "B-slot" and "aliasTo" in t:
                rows.append(
                    (
                        n,
                        t["aliasTo"],
                        (notes.get(n, "") + " (alias: no separate tier)").strip(),
                        "alias",
                    )
                )
            else:
                errors.append(
                    f"{n} ({t['layer']}) has no value and no default -- it must be authored"
                )
    for k, v in list(toks.items()) + list((m.get("extensions") or {}).items()):
        v = str(v)
        if v.count("(") != v.count(")") or re.search(
            r"\)\s+\(|\b(authored|source|todo|tbd)\b|[;{}]", v, re.I
        ):
            errors.append(
                f"{k}: value {v!r} is not plain CSS -- notes like '(authored)' go in mapping.notes"
            )
    unknown = [k for k in toks if k not in by]
    if unknown:
        errors.append(
            f"tokens not in the schema (move them to 'extensions'): {unknown}"
        )
    ext = m.get("extensions", {})
    if ext:
        rows.append(
            ("", "", "── Brand extensions (BRAND_EXTENSIONS allowlist) ", "head")
        )
        for n, v in ext.items():
            rows.append((n, str(v).strip(), notes.get(n, ""), "extension"))
    return rows, errors


def css_lines(rows: list[tuple], indent: str) -> str:
    out = []
    for n, v, c, _ in rows:
        if not n:
            out.append(f"\n{indent}/* {c}{'─' * max(0, 60 - len(c))} */")
            continue
        out.append(f"{indent}{n}: {v};" + (f"  /* {c} */" if c else ""))
    return "\n".join(out).lstrip("\n")


def theme_blocks(m: dict, indent: str = "") -> str:
    css_rules = []
    for sel, decls in (m.get("themes") or {}).items():
        body = "\n".join(f"{indent}  {k}: {v};" for k, v in decls.items())
        css_rules.append(f"{indent}{sel} {{\n{body}\n{indent}}}")
    return "\n\n".join(css_rules)


def tokens_css(m: dict, rows: list) -> str:
    themes = theme_blocks(m)
    return (
        f"/* ─────────────────────────────────────────────────────────────────────────\n"
        f" * design-systems/{m['id']}/tokens.css\n"
        f" *\n"
        f" * Structured token bindings for the {m['name']}-inspired design system.\n"
        f" * {m.get('summary', '').strip()}\n"
        f" *\n"
        f" * Provenance: {m.get('provenance', '').strip()}\n"
        f" * ───────────────────────────────────────────────────────────────────────── */\n"
        f"\n"
        f":root {{\n"
        f"{css_lines(rows, '  ')}\n"
        f"}}\n" + (("\n" + themes + "\n") if themes else "")
    )


def components_html(m: dict, rows: list) -> str:
    name = html.escape(m["name"])
    lang = m.get("lang", "en")
    href = m.get("fonts_href", "")
    link = (
        (
            '    <link rel="preconnect" href="https://fonts.googleapis.com" />\n'
            '    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />\n'
            f'    <link href="{html.escape(href)}" rel="stylesheet" />\n'
        )
        if href
        else ""
    )

    color_names = [
        n
        for n, v, _, _ in rows
        if n
        and (
            re.match(
                r"^(#|rgb|hsl|oklch|color-mix|var\(--(bg|surface|fg|muted|border|accent))",
                v,
            )
            or n in ("--success", "--warn", "--danger")
        )
        and not n.startswith(
            (
                "--font",
                "--text",
                "--space",
                "--radius",
                "--elev",
                "--focus",
                "--motion",
                "--ease",
                "--container",
                "--section",
                "--leading",
                "--tracking",
            )
        )
    ]
    ext_names = set((m.get("extensions") or {}).keys())
    info_var = "--info" if "--info" in ext_names else "--accent"
    btn_radius = m.get("button_radius", "--radius-sm")
    signature = m.get("signature_html", "")

    swatches = "\n".join(
        f'          <div class="swatch"><span class="chip" style="background:var({n})"></span>'
        f"<code>{n}</code></div>"
        for n in color_names
    )
    scale = "\n".join(
        f'          <div class="type-row"><code>{n}</code>'
        f'<span style="font-size:var({n})">{s}</span></div>'
        for n, s in [
            ("--text-4xl", "Display"),
            ("--text-3xl", "Heading 1"),
            ("--text-2xl", "Section"),
            ("--text-xl", "Heading 2"),
            ("--text-lg", "Heading 3"),
            ("--text-base", "Body text"),
            ("--text-sm", "Small text"),
            ("--text-xs", "Caption"),
        ]
    )
    spaces = "\n".join(
        f'          <div class="space-row"><code>{n}</code>'
        f'<span class="bar" style="width:var({n})"></span></div>'
        for n in [
            "--space-1",
            "--space-2",
            "--space-3",
            "--space-4",
            "--space-5",
            "--space-6",
            "--space-8",
            "--space-12",
        ]
    )
    radii = "\n".join(
        f'          <div class="radius" style="border-radius:var({n})"><code>{n}</code></div>'
        for n in ["--radius-sm", "--radius-md", "--radius-lg", "--radius-pill"]
    )
    elevs = "\n".join(
        f'          <div class="card" style="box-shadow:var({n})">'
        f"<code>{n}</code><p>Surface with {n[2:]}.</p></div>"
        for n in ["--elev-flat", "--elev-ring", "--elev-raised"]
    )
    themes = theme_blocks(m, "      ")

    return f"""<!doctype html>
<html lang="{lang}">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{name} — reference components</title>
{link}
    <style>
      /* :root — sourced verbatim from tokens.css */
      :root {{
{css_lines(rows, '        ')}
      }}
{themes}
    </style>
    <style>
      *, *::before, *::after {{ box-sizing: border-box; }}
      body {{ margin: 0; background: var(--bg); color: var(--fg);
        font-family: var(--font-body); font-size: var(--text-base);
        line-height: var(--leading-body); }}
      h1, h2, h3 {{ font-family: var(--font-display); line-height: var(--leading-tight); margin: 0 0 var(--space-3); }}
      h1 {{ font-size: var(--text-4xl); letter-spacing: var(--tracking-display); }}
      h2 {{ font-size: var(--text-2xl); }}
      h3 {{ font-size: var(--text-lg); }}
      p {{ margin: 0 0 var(--space-3); }}
      code {{ font-family: var(--font-mono); font-size: var(--text-xs); color: var(--meta); }}
      .wrap {{ max-width: var(--container-max); margin: 0 auto; padding: 0 var(--container-gutter-desktop); }}
      section {{ padding: var(--section-y-desktop) 0; border-bottom: 1px solid var(--border-soft); }}
      .bar-top {{ background: var(--surface); border-bottom: 1px solid var(--border); }}
      .bar-top .wrap {{ display: flex; align-items: center; gap: var(--space-6); height: 64px; }}
      .brand {{ font-family: var(--font-display); font-weight: 700; font-size: var(--text-lg); color: var(--fg); }}
      .btn {{ font: inherit; font-size: var(--text-sm); font-weight: 600; padding: var(--space-2) var(--space-4);
        min-height: 40px; border-radius: var({btn_radius}); border: 1px solid transparent; cursor: pointer; }}
      .btn-primary {{ background: var(--accent); color: var(--accent-on); }}
      .btn-secondary {{ background: var(--surface); color: var(--fg); border-color: var(--border); }}
      .btn-ghost {{ background: transparent; color: var(--accent); }}
      .btn-danger {{ background: var(--danger); color: var(--accent-on); }}
      .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: var(--space-4); }}
      .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md); padding: var(--space-5); }}
      .swatches {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: var(--space-3); }}
      .swatch {{ display: flex; align-items: center; gap: var(--space-2); }}
      .swatch .chip {{ width: 40px; height: 40px; border-radius: var(--radius-sm); flex: none; }}
      .type-row {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-4);
        padding: var(--space-2) 0; border-bottom: 1px solid var(--border-soft); }}
      .space-row {{ display: flex; align-items: center; gap: var(--space-4); padding: var(--space-1) 0; }}
      .space-row code {{ width: 100px; }} .space-row .bar {{ height: 12px; background: var(--accent); border-radius: 2px; }}
      .radii {{ display: flex; gap: var(--space-4); flex-wrap: wrap; }}
      .radius {{ width: 120px; height: 72px; background: var(--surface); border: 1px solid var(--border);
        display: grid; place-items: center; }}
      .badge {{ display: inline-flex; align-items: center; padding: 2px var(--space-2);
        border-radius: var(--radius-pill); font-size: var(--text-xs); font-weight: 600; border: 1px solid currentColor; }}
      .ok {{ color: var(--success); }} .warn {{ color: var(--warn); }}
      .bad {{ color: var(--danger); }} .info {{ color: var({info_var}); }}
    </style>
  </head>
  <body>
    <header class="bar-top"><div class="wrap"><span class="brand">{name}</span></div></header>
    <main>
      <section id="palette"><div class="wrap">
        <h2>Colour</h2>
        <div class="swatches">
{swatches}
        </div>
      </div></section>
      <section id="type"><div class="wrap">
        <h2>Type scale</h2>
{scale}
      </div></section>
      <section id="controls"><div class="wrap grid">
        <div>
          <h2>Buttons</h2>
          <div style="display:flex;flex-wrap:wrap;gap:var(--space-2)">
            <button class="btn btn-primary" type="button">Primary</button>
            <button class="btn btn-secondary" type="button">Secondary</button>
            <button class="btn btn-ghost" type="button">Ghost</button>
            <button class="btn btn-danger" type="button">Destructive</button>
          </div>
        </div>
      </div></section>
      <section id="cards"><div class="wrap">
        <h2>Elevation</h2><div class="grid">
{elevs}
        </div>
      </div></section>
      <section id="scale"><div class="wrap grid">
        <div><h2>Spacing</h2>
{spaces}
        </div>
        <div><h2>Radius</h2><div class="radii">
{radii}
        </div></div>
      </div></section>
{signature}
    </main>
    <footer><div class="wrap" style="padding:var(--space-8) 0;color:var(--muted);font-size:var(--text-sm)">{name} — reference components. Generated from tokens.css.</div></footer>
  </body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Generate tokens.css and components.html from a mapping.json"
    )
    ap.add_argument("mapping", help="Path to mapping.json")
    ap.add_argument(
        "--dest",
        required=True,
        help="Output directory for tokens.css and components.html",
    )
    ap.add_argument(
        "--print-extensions",
        action="store_true",
        help="Only print the BRAND_EXTENSIONS snippet; write no files",
    )
    a = ap.parse_args()

    m = json.loads(Path(a.mapping).read_text(encoding="utf-8"))
    for k in ("id", "name", "tokens"):
        if k not in m:
            print(f"mapping.json needs '{k}'", file=sys.stderr)
            return 2

    dest = Path(a.dest).resolve()

    # In sandbox mode (OD_SCHEMA_PATH set), allow any dest name.
    # In catalog mode, dest name must equal id so od_root_from can walk up.
    sandbox_mode = bool(os.environ.get("OD_SCHEMA_PATH"))
    if not sandbox_mode and dest.name != m["id"]:
        print(
            f"--dest folder name '{dest.name}' must equal id '{m['id']}'. "
            f"Set OD_SCHEMA_PATH to skip this check in sandbox mode.",
            file=sys.stderr,
        )
        return 2

    # Load the schema (OD_SCHEMA_PATH is checked by od_root_from via ds_schema.py)
    schema = load_schema(od_root_from(dest.parent if not sandbox_mode else dest))
    rows, errors = build_root(m, schema)

    allowed = set(schema["extensions"].get(m["id"], []))
    need = [
        n
        for n in m.get("extensions", {})
        if n not in allowed and not any(n.startswith(p) for p in schema["prefixes"])
    ]
    snippet = (
        (
            "  "
            + f'{m["id"]}: [\n'
            + "\n".join(
                f'    "{n}", // {m.get("notes", {}).get(n, "brand-only token")}'
                for n in need
            )
            + "\n  ],"
        )
        if need
        else ""
    )

    if a.print_extensions:
        print(snippet or f"nothing to add for '{m['id']}'")
        return 0

    if errors:
        print("\n".join("ERROR: " + e for e in errors), file=sys.stderr)
        return 1

    dest.mkdir(parents=True, exist_ok=True)
    (dest / "tokens.css").write_text(tokens_css(m, rows), encoding="utf-8")
    (dest / "components.html").write_text(components_html(m, rows), encoding="utf-8")

    decl_count = sum(1 for r in rows if r[0])
    print(f"wrote {dest / 'tokens.css'} ({decl_count} declarations)")
    print(f"wrote {dest / 'components.html'}")

    for label, names in (
        ("from mapping", [r[0] for r in rows if r[0] and r[3] == "given"]),
        ("schema defaults", [r[0] for r in rows if r[3] == "default"]),
        ("aliases", [r[0] for r in rows if r[3] == "alias"]),
        ("extensions", [r[0] for r in rows if r[3] == "extension"]),
    ):
        if names:
            print(
                f"  {label} ({len(names)}): {', '.join(names[:5])}{'…' if len(names) > 5 else ''}"
            )

    if need:
        print(
            f"\nNOT YET ALLOWLISTED — add to BRAND_EXTENSIONS in tokens.schema.ts:\n{snippet}",
            file=sys.stderr,
        )
        return 4

    return 0


if __name__ == "__main__":
    sys.exit(main())
