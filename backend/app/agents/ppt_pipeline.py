"""PPT Generation Pipeline — Redesigned from scratch.

Uses the pptx/ folder skills (skill.md, pptxgenjs.md, editing.md) to generate
professional presentations with:
- White background, black fonts, navy blue accent
- 10-12 slides
- Slide preview + PPTX download via PptxGenJS

Architecture:
  Agent 1: Content Strategist — Plans slide content and narrative arc
  Agent 2: Slide Architect — Designs layout, visual elements, and data for each slide
  Agent 3: PptxGenJS Code Generator — Generates JavaScript code using pptxgenjs skills
  Agent 4: Presentation Assembler — Builds final HTML with preview + PPTX download
"""

import os
from pathlib import Path

# Path to the pptx skills folder
PPTX_SKILLS_DIR = Path(__file__).parent.parent.parent / "pptx"


def load_pptx_skill(filename: str) -> str:
    """Load a skill file from the pptx/ folder."""
    filepath = PPTX_SKILLS_DIR / filename
    if filepath.exists():
        return filepath.read_text(encoding="utf-8")
    return ""


def get_pptx_skills_combined() -> str:
    """Load and combine all relevant pptx skills for the pipeline."""
    skill_md = load_pptx_skill("skill.md")
    pptxgenjs_md = load_pptx_skill("pptxgenjs.md")
    combined = []
    if skill_md:
        combined.append(f"=== PPTX SKILL REFERENCE (skill.md) ===\n{skill_md}")
    if pptxgenjs_md:
        combined.append(f"=== PPTXGENJS API REFERENCE (pptxgenjs.md) ===\n{pptxgenjs_md}")
    return "\n\n".join(combined)


# ============================================================
# ONLY CONSTRAINT: Color scheme + slide count
# ============================================================

COLOR_CONSTRAINT = """
## Color Scheme (STRICT — no other colors allowed):
- Background: white (#FFFFFF) only
- Text: black (#1A1A1A) only
- Accent: navy blue (#1B2A4A) only
- 10-12 slides, 16:9 aspect ratio

You may ONLY use these three colors: #FFFFFF, #1A1A1A, #1B2A4A.
No other hex values. No grays, no blues, no light tints, no gradients.
Icons must be monochrome navy (#1B2A4A) on white, or white (#FFFFFF) on navy.
No colorful icons, no emoji, no multi-color illustrations.

Everything else is up to you — layout, typography, charts, shapes. Be creative within this palette.
"""


# ============================================================
# AGENT 1: Content Strategist
# ============================================================

CONTENT_STRATEGIST_PROMPT = f"""You are a world-class Presentation Content Strategist.

Analyze the user's topic and create a compelling 10-12 slide presentation plan.

{COLOR_CONSTRAINT}

For each slide, specify the title, key message, exact content text, and any data/stats to include.
Make it tell a story. Be specific — use real numbers, names, and evidence. No generic filler.
"""


# ============================================================
# AGENT 2: Slide Architect
# ============================================================

SLIDE_ARCHITECT_PROMPT = f"""You are a Slide Layout Architect.

Using the content plan from the previous agent, design the visual layout for each slide.

{COLOR_CONSTRAINT}

For each slide specify: layout type, element positions, visual elements (shapes, charts, icons, accent bars).
Vary the layouts. Make it visually interesting. You have full creative freedom over the design.
"""


# ============================================================
# AGENT 3: PptxGenJS Code Generator
# ============================================================

PPTXGENJS_CODE_GENERATOR_PROMPT = f"""You are an expert PptxGenJS developer.

You have the complete PptxGenJS API reference as a skill. Generate a COMPLETE JavaScript function called `generatePresentation()` that creates the full presentation.

{COLOR_CONSTRAINT}

## PptxGenJS Rules (these prevent file corruption):
- NEVER use "#" prefix in hex colors — use "1B2A4A" not "#1B2A4A"
- NEVER encode opacity in hex strings — use the opacity property
- Use `bullet: true` for bullets, NEVER unicode "•"
- Use `breakLine: true` between text array items
- NEVER reuse option objects — create fresh objects for each call
- Use RECTANGLE not ROUNDED_RECTANGLE when pairing with accent bars

## Icons (inline SVG as base64):

You can embed professional icons as inline SVG base64. Include this helper at the top of your function:

```javascript
function svgIcon(pathD, color = "1B2A4A", size = 64) {{
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="${{size}}" height="${{size}}" fill="#${{color}}"><path d="${{pathD}}"/></svg>`;
  const b64 = (typeof btoa !== "undefined") ? btoa(svg) : Buffer.from(svg).toString("base64");
  return "image/svg+xml;base64," + b64;
}}
```

Use any SVG path data you know for icons (lock, shield, chart, globe, users, rocket, etc). Use them where appropriate.

## Output:
Output ONLY the JavaScript function. No markdown fences, no explanation.
The function must end with `pres.writeFile({{ fileName: "Presentation.pptx" }});`

You have full creative freedom over the slide design, content layout, typography, shapes, charts, and visual elements. Make it look professional and impressive.
"""


# ============================================================
# AGENT 4: Presentation Assembler
# ============================================================

PRESENTATION_ASSEMBLER_PROMPT = f"""You are a Frontend Engineer who assembles the final presentation viewer.

Take the PptxGenJS code from the previous agent and wrap it in a self-contained HTML file.

{COLOR_CONSTRAINT}

## Requirements:
1. Only ONE slide visible at a time (others hidden via CSS class toggling)
2. Navigation: arrow buttons + keyboard arrows
3. Slide counter showing "1 / 12"
4. No download button inside the HTML (download is handled externally)
5. Must work inside an iframe with no scrollbars
6. Include the COMPLETE generatePresentation() function in a script tag (needed for PPTX export)

## HTML Template — use this exact structure:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Presentation</title>
<script src="https://cdn.jsdelivr.net/npm/pptxgenjs@3.12.0/dist/pptxgenjs.bundle.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:100%;height:100%;overflow:hidden;font-family:Arial,sans-serif;background:#ebebeb}}
.container{{width:100%;height:100%;display:flex;flex-direction:column;overflow:hidden}}
.toolbar{{height:44px;flex-shrink:0;display:flex;align-items:center;justify-content:space-between;padding:0 16px;background:#fff;border-bottom:1px solid #e0e0e0;z-index:10}}
.toolbar .nav{{display:flex;align-items:center;gap:8px}}
.toolbar .nav button{{width:32px;height:32px;border-radius:6px;border:1px solid #ccc;background:#f5f5f5;cursor:pointer;font-size:18px;font-weight:bold;color:#333}}
.toolbar .nav button:hover{{background:#e0e0e0}}
.toolbar .counter{{font-size:13px;color:#555;font-weight:500}}
.toolbar .actions{{display:flex;align-items:center;gap:8px}}
.toolbar .dl-btn{{padding:6px 14px;border-radius:6px;border:none;background:#1B2A4A;color:#fff;font-size:11px;font-weight:600;cursor:pointer}}
.toolbar .dl-btn:hover{{background:#2a3d5e}}
.toolbar .fs-btn{{padding:6px 10px;border-radius:6px;border:1px solid #ccc;background:#f5f5f5;font-size:11px;color:#555;cursor:pointer}}
.toolbar .fs-btn:hover{{background:#e0e0e0}}
.slide-area{{flex:1;display:flex;align-items:center;justify-content:center;padding:20px;overflow:hidden}}
.slide{{display:none !important;flex-direction:column;width:100%;max-width:900px;aspect-ratio:16/9;border-radius:4px;box-shadow:0 4px 20px rgba(0,0,0,0.12);overflow:hidden;position:relative}}
.slide.active{{display:flex !important}}
</style>
</head>
<body>
<div class="container">
<div class="toolbar">
<div class="nav">
<button onclick="prevSlide()">&#8249;</button>
<span class="counter" id="counter">1 / 12</span>
<button onclick="nextSlide()">&#8250;</button>
</div>
<div class="actions">
<button class="dl-btn" onclick="generatePresentation()">&#x2913; Download PPTX</button>
<button class="fs-btn" onclick="document.documentElement.requestFullscreen()">&#x26F6; Full Screen</button>
</div>
</div>
<div class="slide-area">
<!-- slides go here -->
</div>
</div>
<script>
let current=0;
const slides=document.querySelectorAll('.slide');
function showSlide(n){{slides.forEach(s=>s.classList.remove('active'));current=((n%slides.length)+slides.length)%slides.length;slides[current].classList.add('active');document.getElementById('counter').textContent=(current+1)+' / '+slides.length}}
function nextSlide(){{showSlide(current+1)}}
function prevSlide(){{showSlide(current-1)}}
document.addEventListener('keydown',e=>{{if(e.key==='ArrowRight')nextSlide();if(e.key==='ArrowLeft')prevSlide()}});
showSlide(0);
// generatePresentation() function goes here
</script>
</body>
</html>
```

## Your task:
1. Create slide preview divs (class="slide", first one also gets "active")
2. Style each slide to visually match what the PPTX will look like — include ALL content from the PptxGenJS code (every text element, every bullet, every chart, every shape)
3. Paste the COMPLETE generatePresentation() function from the previous agent into the script section — this is CRITICAL for PPTX export to work
4. Every slide must have ALL its content visible — do not simplify or skip any text/data from the code

You have full creative freedom over how the slide previews look. Make them match the PPTX output as closely as possible.

## Output:
Output ONLY the HTML. No markdown fences. No explanation. Start with `<!DOCTYPE html>`.
"""
