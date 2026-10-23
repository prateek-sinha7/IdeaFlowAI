#!/usr/bin/env python3
"""Generate a template-contract-compliant example.html from Figma frame data.

Usage:
    python3 figma_to_html.py \
        --frames context/design/template/figma/frames.json \
        --tokens context/design/tokens.css \
        --prefix fg \
        --out context/design/template/example.html

Input frames.json schema:
[
  {
    "index": 0,
    "filename": "frame-1.png",
    "screen": "Dashboard",
    "description": "Dashboard overview",
    "layout": "sidebar-nav",
    "source": ".figma/frame-1.png"
  }, ...
]

Output: example.html with:
  - All CSS vars from tokens.css in :root
  - .nav-item[data-go] for each frame (contract requirement)
  - section.pattern[data-pattern] for each frame (contract requirement)
  - is-active class on first nav item
  - Sidebar or topbar layout based on dominant_layout
  - Inline <script> for nav switching

Template contract satisfied:
  - <main> present as content area
  - >= 2 .nav-item[data-go] elements before <main>
  - is-active on first nav item
  - One section.pattern[data-pattern] per frame
  - :root declares --bg --surface --fg --muted --border --accent
  - Self-contained (no external URLs except optional Google Fonts)

Pure Python stdlib. No Chrome, no LLM, no backend venv required.
"""
from __future__ import annotations

import argparse
import html as html_module
import json
import re
import sys
from pathlib import Path


# ── CSS parsing ───────────────────────────────────────────────────────────────

def _parse_root_vars(tokens_source: str) -> dict[str, str]:
    """Extract :root CSS variable declarations from a CSS file or markdown :root block."""
    # Strip comments first
    clean = re.sub(r"/\*.*?\*/", "", tokens_source, flags=re.S)
    # Find the first plain :root block
    m = re.search(r"(?<![\w\]\)-]):root\s*\{([^}]*)\}", clean)
    if not m:
        # Fallback: look for :root { ... } even if preceded by something unusual
        m = re.search(r":root\s*\{([^}]*)\}", clean)
    if not m:
        return {}
    decl_re = re.compile(r"(--[\w-]+)\s*:\s*([^;]+);")
    return {k: v.strip() for k, v in decl_re.findall(m.group(1))}


def _read_tokens_source(tokens_path: Path) -> str:
    """Read a .css file or a markdown file containing a :root block."""
    content = tokens_path.read_text(encoding="utf-8")
    # If it's a markdown file, find the :root block inside a fenced code block or prose
    if tokens_path.suffix in (".md", ".markdown"):
        # Extract from fenced code block first
        code_block = re.search(r"```(?:css)?\s*\n(.*?)\n```", content, re.S)
        if code_block:
            return code_block.group(1)
        # Otherwise look for :root directly in the prose
        return content
    return content


# ── layout helpers ────────────────────────────────────────────────────────────

def _determine_layout(frames: list[dict]) -> str:
    """Determine the dominant layout from frames' layout fields."""
    layouts: list[str] = [f.get("layout", "").lower() for f in frames if f.get("layout")]
    if not layouts:
        return "sidebar-nav"
    # topbar wins if any frame has it
    for layout in layouts:
        if "topbar" in layout or "topnav" in layout or "top-nav" in layout:
            return "topbar-nav"
    return "sidebar-nav"


def _to_pattern_id(index: int, screen: str) -> str:
    """Convert frame index + screen name to a pattern id like screen-0."""
    return f"screen-{index}"


# ── HTML generation ───────────────────────────────────────────────────────────

def _root_block(css_vars: dict[str, str], indent: str = "    ") -> str:
    """Render a :root { ... } block from a dict of CSS vars."""
    lines = []
    for name, value in css_vars.items():
        lines.append(f"{indent}  {name}: {value};")
    return f"{indent}:root {{\n" + "\n".join(lines) + f"\n{indent}}}"


def _sidebar_html(
    frames: list[dict],
    css_vars: dict[str, str],
    prefix: str,
) -> str:
    """Generate a sidebar-nav layout HTML."""
    nav_items = []
    for i, frame in enumerate(frames):
        screen = html_module.escape(frame.get("screen", f"Screen {i}"))
        pattern_id = _to_pattern_id(i, screen)
        active_class = " is-active" if i == 0 else ""
        nav_items.append(
            f'      <button class="nav-item{active_class}" data-go="{pattern_id}">'
            f"{screen}</button>"
        )

    pattern_sections = []
    for i, frame in enumerate(frames):
        screen = html_module.escape(frame.get("screen", f"Screen {i}"))
        desc = html_module.escape(frame.get("description", screen))
        pattern_id = _to_pattern_id(i, screen)
        filename = frame.get("filename") or frame.get("name", f"frame-{i + 1}.png")
        display_style = "flex" if i == 0 else "none"
        pattern_sections.append(
            f"      <!-- PATTERN {pattern_id} - {desc} -->\n"
            f'      <section class="pattern" data-pattern="{pattern_id}" style="display:{display_style}">\n'
            f'        <!-- Figma frame: {frame.get("source", f".figma/{filename}")} -->\n'
            f'        <div class="{prefix}-frame-placeholder">\n'
            f'          <img src="../figma/{html_module.escape(filename)}" '
            f'alt="{screen}" style="max-width:100%;opacity:0.25;pointer-events:none;">\n'
            f'          <p style="color:var(--muted);margin-top:var(--space-3,12px)">'
            f"{screen} — build from {html_module.escape(filename)}</p>\n"
            f"        </div>\n"
            f"      </section>"
        )

    nav_html = "\n".join(nav_items)
    patterns_html = "\n\n".join(pattern_sections)
    root_css = _root_block(css_vars)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Figma Design</title>
  <style>
{root_css}

    /* ── Reset ─────────────────────────────────────────────── */
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--fg);
      font-family: var(--font-body, system-ui, sans-serif);
      font-size: var(--text-base, 15px);
    }}

    /* ── App shell ──────────────────────────────────────────── */
    .app {{ display: flex; height: 100vh; overflow: hidden; }}

    /* ── Sidebar nav ────────────────────────────────────────── */
    .sidebar {{
      width: 240px;
      flex: none;
      background: var(--surface);
      border-right: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      gap: 2px;
      padding: var(--space-3, 12px) var(--space-2, 8px);
      overflow-y: auto;
    }}

    .nav-item {{
      display: block;
      width: 100%;
      padding: var(--space-2, 8px) var(--space-3, 12px);
      border: none;
      border-radius: var(--radius-sm, 4px);
      background: transparent;
      color: var(--fg);
      font: inherit;
      font-size: var(--text-sm, 13px);
      text-align: left;
      cursor: pointer;
      transition: background 120ms ease;
    }}

    .nav-item.is-active,
    .nav-item:hover {{
      background: var(--accent);
      color: var(--on-accent, var(--accent-on, #fff));
    }}

    /* ── Content area ───────────────────────────────────────── */
    main {{
      flex: 1;
      overflow-y: auto;
      background: var(--bg);
    }}

    /* ── Patterns ───────────────────────────────────────────── */
    .pattern {{
      width: 100%;
      min-height: 100%;
      padding: var(--space-6, 24px);
      flex-direction: column;
      align-items: flex-start;
      gap: var(--space-4, 16px);
    }}

    .{prefix}-frame-placeholder {{
      max-width: 960px;
    }}
  </style>
</head>
<body>
  <div class="app">
    <nav class="sidebar" aria-label="Application navigation">
{nav_html}
    </nav>

    <main>
{patterns_html}
    </main>
  </div>

  <script>
    (function () {{
      var navItems = document.querySelectorAll('.nav-item[data-go]');
      var patterns = document.querySelectorAll('.pattern');

      navItems.forEach(function (btn) {{
        btn.addEventListener('click', function () {{
          navItems.forEach(function (b) {{ b.classList.remove('is-active'); }});
          patterns.forEach(function (p) {{ p.style.display = 'none'; }});
          btn.classList.add('is-active');
          var targetId = btn.getAttribute('data-go');
          patterns.forEach(function (p) {{
            if (p.getAttribute('data-pattern') === targetId) p.style.display = 'flex';
          }});
        }});
      }});
    }})();
  </script>
</body>
</html>"""


def _topbar_html(
    frames: list[dict],
    css_vars: dict[str, str],
    prefix: str,
) -> str:
    """Generate a topbar-nav layout HTML."""
    nav_items = []
    for i, frame in enumerate(frames):
        screen = html_module.escape(frame.get("screen", f"Screen {i}"))
        pattern_id = _to_pattern_id(i, screen)
        active_class = " is-active" if i == 0 else ""
        nav_items.append(
            f'        <button class="nav-item{active_class}" data-go="{pattern_id}">'
            f"{screen}</button>"
        )

    pattern_sections = []
    for i, frame in enumerate(frames):
        screen = html_module.escape(frame.get("screen", f"Screen {i}"))
        desc = html_module.escape(frame.get("description", screen))
        pattern_id = _to_pattern_id(i, screen)
        filename = frame.get("filename") or frame.get("name", f"frame-{i + 1}.png")
        display_style = "block" if i == 0 else "none"
        pattern_sections.append(
            f"      <!-- PATTERN {pattern_id} - {desc} -->\n"
            f'      <section class="pattern" data-pattern="{pattern_id}" style="display:{display_style}">\n'
            f'        <!-- Figma frame: {frame.get("source", f".figma/{filename}")} -->\n'
            f'        <div class="{prefix}-frame-placeholder">\n'
            f'          <img src="../figma/{html_module.escape(filename)}" '
            f'alt="{screen}" style="max-width:100%;opacity:0.25;pointer-events:none;">\n'
            f'          <p style="color:var(--muted);margin-top:var(--space-3,12px)">'
            f"{screen} — build from {html_module.escape(filename)}</p>\n"
            f"        </div>\n"
            f"      </section>"
        )

    nav_html = "\n".join(nav_items)
    patterns_html = "\n\n".join(pattern_sections)
    root_css = _root_block(css_vars)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Figma Design</title>
  <style>
{root_css}

    /* ── Reset ─────────────────────────────────────────────── */
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--fg);
      font-family: var(--font-body, system-ui, sans-serif);
      font-size: var(--text-base, 15px);
    }}

    /* ── App shell ──────────────────────────────────────────── */
    .app {{ display: flex; flex-direction: column; height: 100vh; overflow: hidden; }}

    /* ── Topbar nav ─────────────────────────────────────────── */
    .topbar {{
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      gap: var(--space-1, 4px);
      padding: 0 var(--space-4, 16px);
      height: 56px;
      flex: none;
    }}

    .nav-item {{
      padding: var(--space-2, 8px) var(--space-3, 12px);
      border: none;
      background: transparent;
      color: var(--fg);
      font: inherit;
      font-size: var(--text-sm, 13px);
      cursor: pointer;
      border-radius: var(--radius-sm, 4px);
      transition: background 120ms ease;
    }}

    .nav-item.is-active,
    .nav-item:hover {{
      background: var(--accent);
      color: var(--on-accent, var(--accent-on, #fff));
    }}

    /* ── Content area ───────────────────────────────────────── */
    main {{
      flex: 1;
      overflow-y: auto;
      background: var(--bg);
    }}

    /* ── Patterns ───────────────────────────────────────────── */
    .pattern {{
      width: 100%;
      min-height: 100%;
      padding: var(--space-6, 24px);
    }}

    .{prefix}-frame-placeholder {{
      max-width: 960px;
    }}
  </style>
</head>
<body>
  <div class="app">
    <header class="topbar">
      <nav aria-label="Application navigation">
{nav_html}
      </nav>
    </header>

    <main>
{patterns_html}
    </main>
  </div>

  <script>
    (function () {{
      var navItems = document.querySelectorAll('.nav-item[data-go]');
      var patterns = document.querySelectorAll('.pattern');

      navItems.forEach(function (btn) {{
        btn.addEventListener('click', function () {{
          navItems.forEach(function (b) {{ b.classList.remove('is-active'); }});
          patterns.forEach(function (p) {{ p.style.display = 'none'; }});
          btn.classList.add('is-active');
          var targetId = btn.getAttribute('data-go');
          patterns.forEach(function (p) {{
            if (p.getAttribute('data-pattern') === targetId) p.style.display = 'block';
          }});
        }});
      }});
    }})();
  </script>
</body>
</html>"""


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Generate template-contract-compliant example.html from Figma frames"
    )
    ap.add_argument("--frames", required=True, help="Path to frames.json")
    ap.add_argument(
        "--tokens", required=True,
        help="Path to tokens.css (or design-system.md containing a :root block)"
    )
    ap.add_argument("--prefix", default="fg", help="CSS class prefix (e.g. fg)")
    ap.add_argument("--out", required=True, help="Output path for example.html")
    args = ap.parse_args()

    frames_path = Path(args.frames)
    tokens_path = Path(args.tokens)
    out_path = Path(args.out)

    # Validate inputs
    if not frames_path.is_file():
        print(f"ERROR: frames.json not found: {frames_path}", file=sys.stderr)
        return 1
    if not tokens_path.is_file():
        print(f"ERROR: tokens source not found: {tokens_path}", file=sys.stderr)
        return 1

    # Parse frames
    try:
        frames = json.loads(frames_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"ERROR: failed to parse frames.json: {e}", file=sys.stderr)
        return 1

    if not frames:
        print("ERROR: frames.json is empty — at least one frame required", file=sys.stderr)
        return 1

    # Parse CSS vars from tokens source
    try:
        tokens_source = _read_tokens_source(tokens_path)
    except OSError as e:
        print(f"ERROR: failed to read tokens source: {e}", file=sys.stderr)
        return 1

    css_vars = _parse_root_vars(tokens_source)
    if not css_vars:
        print(
            "WARNING: no :root CSS variables found in tokens source — "
            "example.html will have an empty :root block",
            file=sys.stderr,
        )

    # Determine layout
    layout = _determine_layout(frames)

    # Generate HTML
    if layout == "topbar-nav":
        html_content = _topbar_html(frames, css_vars, args.prefix)
    else:
        html_content = _sidebar_html(frames, css_vars, args.prefix)

    # Write output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_content, encoding="utf-8")

    print(f"wrote {out_path}")
    print(f"  layout: {layout}  frames: {len(frames)}  css vars: {len(css_vars)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
