"""PPTX Export Service — Executes PptxGenJS code server-side via Node.js.

Extracts the generatePresentation() function from Agent 3's output
and runs it with Node.js to produce a real .pptx file.
"""

import os
import re
import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).parent.parent.parent.parent / "frontend"
NODE_MODULES_PPTXGENJS = FRONTEND_DIR / "node_modules" / "pptxgenjs"


def generate_pptx_from_code(js_code: str, title: str = "Presentation") -> bytes:
    """Execute PptxGenJS code server-side and return .pptx bytes."""

    func_code = js_code.strip()

    # Strip markdown fences
    if func_code.startswith("```"):
        func_code = re.sub(r'^```(?:javascript|js)?\s*\n?', '', func_code)
        func_code = re.sub(r'\n?```\s*$', '', func_code)

    pptxgenjs_path = str(NODE_MODULES_PPTXGENJS).replace("\\", "/")

    # Sanitize: fix common corruption patterns
    # 1. Remove # from hex colors
    func_code = re.sub(r'color:\s*"#([0-9A-Fa-f]{6})"', r'color: "\1"', func_code)
    func_code = re.sub(r"color:\s*'#([0-9A-Fa-f]{6})'", r"color: '\1'", func_code)
    # 2. Fix 8-char hex colors
    func_code = re.sub(r'color:\s*"([0-9A-Fa-f]{8})"', lambda m: f'color: "{m.group(1)[:6]}"', func_code)
    # 3. Fix negative shadow offsets
    func_code = re.sub(r'offset:\s*-(\d+)', r'offset: \1', func_code)
    # 4. Remove standalone .line property access (crashes in Node)
    lines = func_code.split('\n')
    safe_lines = []
    for line in lines:
        stripped = line.strip()
        if (stripped and not stripped.startswith('//') and
                '.line.' in stripped and 'line:' not in stripped and
                'addShape' not in stripped and 'addText' not in stripped):
            safe_lines.append(f'  // skipped: {stripped}')
        else:
            safe_lines.append(line)
    func_code = '\n'.join(safe_lines)

    # Replace writeFile/save with write("nodebuffer")
    for pattern in [
        r'(?:await\s+)?pres\.writeFile\s*\(\s*\{[^}]*\}\s*\)',
        r'(?:await\s+)?pres\.writeFile\s*\([^)]*\)',
        r'(?:await\s+)?pres\.save\s*\([^)]*\)',
    ]:
        func_code = re.sub(pattern, 'return pres.write("nodebuffer")', func_code)
    func_code = func_code.replace('return return', 'return')

    # Make function async
    if 'async function generatePresentation' not in func_code:
        func_code = func_code.replace('function generatePresentation', 'async function generatePresentation')

    # Wrap in one if no function found
    if 'function generatePresentation' not in func_code:
        func_code = f"async function generatePresentation() {{\n{func_code}\n}}"

    temp_dir = tempfile.mkdtemp(prefix="pptx_export_")
    js_file = os.path.join(temp_dir, "input.js")
    out_file = os.path.join(temp_dir, "output.pptx")
    out_path = out_file.replace("\\", "/")

    node_script = f'''
const fs = require("fs");
const Module = require("module");
const _orig = Module._resolveFilename;
Module._resolveFilename = function(req, parent, isMain, opts) {{
  if (req === "pptxgenjs") return require.resolve("{pptxgenjs_path}");
  return _orig.call(this, req, parent, isMain, opts);
}};
const _pptx = require("{pptxgenjs_path}");
global.PptxGenJS = _pptx;
global.pptxgen = _pptx;

{func_code}

const _FallbackPptx = require("{pptxgenjs_path}");
const _OrigFunc = generatePresentation;
generatePresentation = async function() {{
  try {{
    const r = await _OrigFunc();
    return r;
  }} catch(e) {{
    console.error("Crashed:", e.message, "- creating fallback");
    const p = new _FallbackPptx();
    p.layout = "LAYOUT_16x9";
    const s = p.addSlide();
    s.background = {{ color: "FFFFFF" }};
    s.addText("Export error: " + e.message, {{x:0.5,y:2,w:9,h:1,fontSize:14,color:"1A1A1A"}});
    return await p.write("nodebuffer");
  }}
}};

async function main() {{
  try {{
    let r = generatePresentation();
    if (r && typeof r.then === "function") r = await r;
    if (Buffer.isBuffer(r)) {{
      fs.writeFileSync("{out_path}", r);
      process.stdout.write("OK");
    }} else if (r instanceof Uint8Array) {{
      fs.writeFileSync("{out_path}", Buffer.from(r));
      process.stdout.write("OK");
    }} else {{
      const p = new _FallbackPptx();
      p.layout = "LAYOUT_16x9";
      const s = p.addSlide();
      s.addText("Export failed: no buffer returned", {{x:0.5,y:2,w:9,h:1,fontSize:14,color:"1A1A1A"}});
      const buf = await p.write("nodebuffer");
      fs.writeFileSync("{out_path}", buf);
      process.stdout.write("OK");
    }}
  }} catch(e) {{
    process.stderr.write("Fatal: " + e.message);
    process.exit(1);
  }}
}}
main();
'''

    with open(js_file, "w", encoding="utf-8") as f:
        f.write(node_script)

    try:
        result = subprocess.run(
            ["node", js_file],
            capture_output=True, text=True, timeout=30, cwd=temp_dir
        )

        if not os.path.exists(out_file):
            err = result.stderr.strip()[:300] or "PPTX file not created"
            logger.error(f"Node.js PPTX generation failed: {err}")
            raise RuntimeError(f"PPTX generation failed: {err}")

        with open(out_file, "rb") as f:
            pptx_bytes = f.read()

        logger.info(f"Generated PPTX: {len(pptx_bytes)} bytes")
        return pptx_bytes

    finally:
        try:
            if os.path.exists(js_file): os.unlink(js_file)
            if os.path.exists(out_file): os.unlink(out_file)
            os.rmdir(temp_dir)
        except Exception:
            pass
