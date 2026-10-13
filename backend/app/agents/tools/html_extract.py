"""app/agents/tools/html_extract.py — HTML/HTM materialisation for extract_text (spec 021).

Ported from the JS the user reviewed in revision 1 of the backlog workflow
(a Screen Inventory agent + per-screen Readers driving the ``playwright`` tool set
with these exact scripts). Revision 2 moves the browser work into code — no prompt
runs JavaScript any more; a prompt just calls ``extract_text`` and reads pages,
same as for a PDF.

TWO ROUTES, exactly like the rest of ``extract_text``:
  browser — Playwright's SYNC API (the tool runs in a worker thread via
            asyncio.to_thread; no event loop runs there, so the async API cannot be
            driven without a nested loop, and the sync API is the documented way to
            drive Playwright from a plain thread). Sees every screen a script
            builds at runtime, and screenshots each one.
  static  — stdlib ``html.parser`` only, when Chromium cannot launch. Same page
            format, same screen-detection rules "as far as static markup allows"
            (spec §6.1) — no live layout, no computed style, no scripts run — so it
            can miss a screen a script builds and it never screenshots anything.

One page per screen, then a scripts index, then the app's own scripts (a library —
external `src`, or a minified bundle — and the prototype shell's own runtime are
listed, never copied), then inline handlers if any. Manifest keys match the PDF
route's (spec §6.1) plus ``rendered_by``, ``static_reason`` and ``screens``.

Never raises on a browser failure — that IS the static-fallback trigger
(``BrowserUnavailable``). A genuine bug elsewhere still raises, and the caller
(``file_extract_tools._extract_html_sync``) is what applies the tool's
never-raise-to-the-agent discipline.
"""

from __future__ import annotations

import hashlib
import html.parser
import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Browser scripts — copied verbatim from workflow.rev1.yaml (DETECT / FORCE /
# EXTRACT / LIST / READ / HANDLERS). FORCE and EXTRACT take the screen's
# selector as a page.evaluate() ARGUMENT (function-form) instead of the old
# prompt's string substitution into a literal "SELECTOR" placeholder — the only
# change made to any of them. READ is parameterised the same way for the same
# reason (its old form patched literal INDEX/OFFSET numbers into the text).
# ---------------------------------------------------------------------------

_DETECT_SCRIPT = r"""
(() => {
  const clean = s => (s || "").replace(/\s+/g, " ").trim();
  const slug = s => clean(s).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40);
  const CONTROLS = "input,select,textarea,button,a[href],[role=button],[onclick],table";
  const DIALOG = "dialog,[role=dialog],[id*=modal],[id*=dialog],[class*=modal],[class*=dialog]";
  const selectorOf = el => {
    if (el.id) return "#" + CSS.escape(el.id);
    const parts = [];
    let n = el;
    while (n && n.nodeType === 1 && n !== document.body) {
      let i = 1, s = n;
      while ((s = s.previousElementSibling)) if (s.tagName === n.tagName) i++;
      parts.unshift(n.tagName.toLowerCase() + ":nth-of-type(" + i + ")");
      if (n.parentElement && n.parentElement.id) { parts.unshift("#" + CSS.escape(n.parentElement.id)); break; }
      n = n.parentElement;
    }
    return parts.join(" > ");
  };
  const titleOf = el => clean(el.getAttribute("aria-label") || el.getAttribute("title") || (el.querySelector("h1,h2,h3,legend,caption") || {}).textContent || el.id || el.textContent).slice(0, 80);
  const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const shell = !!window.__prototype;
  const found = [];
  if (shell) {
    document.querySelectorAll("section.screen").forEach(el => found.push({ el, kind: "page", show: "window.__prototype.show('" + el.id + "')" }));
    document.querySelectorAll("div.dialog").forEach(el => found.push({ el, kind: "dialog", show: "window.__prototype.openDialog('" + el.id + "')" }));
  } else {
    const cand = Array.from(document.querySelectorAll("section,form,main > *," + DIALOG + ",[id*=screen],[id*=page],[id*=view],[id*=step],[class*=screen],[class*=page],[class*=view],[class*=step]"))
      .filter(el => el !== document.body && el.querySelector(CONTROLS));
    const isWrapper = el => cand.filter(o => o !== el && el.contains(o)).length >= 2;
    const kept = cand.filter(el => !isWrapper(el));
    const top = kept.filter(el => !kept.some(o => o !== el && o.contains(el)));
    top.forEach(el => found.push({ el, kind: el.matches(DIALOG) ? "dialog" : "page", show: visible(el) ? "visible" : "force" }));
    if (!found.length) document.querySelectorAll("h1,h2").forEach(h => found.push({ el: h, kind: "section", show: "visible" }));
    if (!found.length) found.push({ el: document.body, kind: "page", show: "visible" });
  }
  const seen = {};
  const screens = found.map((f, i) => {
    let id = f.el.id ? slug(f.el.id) : slug(titleOf(f.el));
    if (!id) id = "screen-" + (i + 1);
    if (seen[id]) { seen[id] += 1; id = id + "-" + seen[id]; } else { seen[id] = 1; }
    return { id, title: titleOf(f.el) || id, kind: f.kind, selector: f.el === document.body ? "body" : selectorOf(f.el), show: f.show, controls: f.el.querySelectorAll(CONTROLS).length };
  });
  return JSON.stringify({ shell: shell ? "prototype_v2" : "generic", title: clean(document.title), screens });
})()
"""

_FORCE_SCRIPT = r"""
(rootSel) => {
  const el = document.querySelector(rootSel);
  if (!el) return "not found";
  let n = el;
  while (n && n !== document.body) {
    n.hidden = false;
    n.removeAttribute("aria-hidden");
    if (getComputedStyle(n).display === "none") n.style.display = "block";
    if (getComputedStyle(n).visibility === "hidden") n.style.visibility = "visible";
    if (n.tagName === "DIALOG" && !n.open) { try { n.show(); } catch (e) {} }
    n = n.parentElement;
  }
  el.scrollIntoView();
  return "shown";
}
"""

_EXTRACT_SCRIPT = r"""
(rootSel) => {
  const root = document.querySelector(rootSel);
  if (!root) return JSON.stringify({ error: "selector not found" });
  const clean = s => (s || "").replace(/\s+/g, " ").trim();
  const nodes = [root];
  if (/^H[12]$/.test(root.tagName)) {
    let n = root.nextElementSibling;
    while (n && n.tagName !== root.tagName && n.tagName !== "H1") { nodes.push(n); n = n.nextElementSibling; }
  }
  const all = sel => nodes.flatMap(n => [...(n.matches(sel) ? [n] : []), ...n.querySelectorAll(sel)]);
  const KEEP = /^(id|name|type|required|pattern|min|max|minlength|maxlength|step|placeholder|disabled|readonly|multiple|value|checked|selected|href|target|onclick|onchange|oninput|onsubmit|role|hidden|title|aria-.+|data-.+)$/;
  const attrs = el => { const o = {}; for (const a of el.attributes) if (KEEP.test(a.name)) o[a.name] = a.value; return o; };
  const labelOf = el => {
    if (el.id) { const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]'); if (l) return clean(l.textContent); }
    const w = el.closest("label"); if (w) return clean(w.textContent);
    const f = el.closest(".field,.form-group,.form-field,[class*=field]");
    if (f) { const t = f.querySelector("label,.label"); if (t) return clean(t.textContent); }
    return clean(el.getAttribute("aria-label") || el.getAttribute("placeholder") || el.name || el.id);
  };
  const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const cls = el => (typeof el.className === "string" ? el.className : "");
  const fields = all("input,select,textarea").map(el => ({
    label: labelOf(el),
    control: el.tagName === "SELECT" ? (el.multiple ? "multi-select" : "dropdown") : el.tagName === "TEXTAREA" ? "textarea" : (el.type || "text"),
    attrs: attrs(el),
    options: el.tagName === "SELECT" ? [...el.options].map(o => clean(o.textContent) + (o.value && o.value !== clean(o.textContent) ? " [value=" + o.value + "]" : "")) : undefined,
    visible: visible(el)
  }));
  const actions = all("button,a,[role=button],[onclick],[data-goto],[data-opens],[data-submit],[data-closes],[data-tab],[data-show],[data-hide]").map(el => ({
    text: clean(el.textContent) || el.getAttribute("aria-label") || el.title || "", tag: el.tagName.toLowerCase(), attrs: attrs(el), visible: visible(el)
  }));
  const tables = all("table").map(t => ({
    caption: clean((t.caption || {}).textContent),
    columns: [...t.querySelectorAll("thead th, tr:first-child th")].map(h => clean(h.textContent)),
    rows: [...t.querySelectorAll("tbody tr")].slice(0, 5).map(r => [...r.cells].map(c => clean(c.textContent))),
    row_count: t.querySelectorAll("tbody tr").length
  }));
  const headings = all("h1,h2,h3,h4,h5,legend,caption").map(h => clean(h.textContent)).filter(Boolean);
  const hidden = all("[hidden],.state,.error,.alert,.toast,[role=alert],[aria-live],dialog,[role=dialog]")
    .filter(el => !visible(el) || el.matches(".state,[role=alert],[aria-live]"))
    .map(el => ({ id: el.id, class: cls(el), text: clean(el.textContent).slice(0, 500) }));
  const text = nodes.map(n => clean(n.textContent)).join(" | ");
  return JSON.stringify({ headings, fields, actions, tables, hidden, text_length: text.length, text: text.slice(0, 40000) });
}
"""

_LIST_SCRIPT = r"""
(() => JSON.stringify([...document.scripts].map((s, i) => ({ i, src: s.src || "", length: (s.textContent || "").length, defines_prototype: /__prototype\s*=/.test(s.textContent || ""), first: (s.textContent || "").trim().slice(0, 120) }))))()
"""

_READ_SCRIPT = r"""
([idx, offset]) => (document.scripts[idx].textContent || "").slice(offset, offset + 20000)
"""

_HANDLERS_SCRIPT = r"""
(() => JSON.stringify([...document.querySelectorAll("*")].flatMap(el => [...el.attributes].filter(a => /^on/.test(a.name)).map(a => ({ element: el.tagName.toLowerCase() + (el.id ? "#" + el.id : ""), text: (el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 60), event: a.name, code: a.value })))))()
"""

_VIEWPORT = {"width": 1280, "height": 900}
_GOTO_TIMEOUT_MS = 30000
_SCREENSHOT_TIMEOUT_MS = 5000

# fenced-block cap per Script <n> page (spec §6.1) — a script bigger than this
# spans several pages of the SAME heading, READ in slices.
_SCRIPT_CHUNK_CHARS = 20_000

# ponytail: "minified bundle" is an average-line-length heuristic, not a real
# parser — a hand-written 300-char line would misclassify as a library, and a
# minifier that keeps newlines would misclassify as the app's own code. Upgrade
# path if that ever bites: sniff a source map comment or a known bundler banner
# instead of measuring line length.
_MINIFIED_AVG_LINE_CHARS = 300


class BrowserUnavailable(Exception):
    """Playwright/Chromium could not run this page. The caller falls back to static."""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def materialise_html(
    source_path: Path,
    source_bytes: bytes,
    doc_dir: Path,
    filename: str,
    slug: str,
) -> dict:
    """Materialise one HTML/HTM upload into ``doc_dir`` (``.extract/html/<slug>/``).

    Folder-is-the-state: an existing ``manifest.json`` whose ``source_sha256``
    matches these bytes means nothing is rebuilt. A mismatch (or no manifest at
    all) discards the folder and rebuilds it from a temp dir, renamed into place
    in one atomic step — never a partially-written folder on disk.

    Returns a dict with ``rebuilt`` (bool), ``rendered_by`` ("chromium" |
    "static"), ``static_reason`` (str | None) and the full ``manifest`` dict —
    everything ``file_extract_tools._extract_html_sync`` needs for its receipt.
    """
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()

    existing = _read_json(doc_dir / "manifest.json")
    if existing is not None and existing.get("source_sha256") == source_sha256:
        return {
            "rebuilt": False,
            "rendered_by": existing.get("rendered_by", "chromium"),
            "static_reason": existing.get("static_reason"),
            "manifest": existing,
        }

    if doc_dir.exists():
        shutil.rmtree(doc_dir, ignore_errors=True)

    doc_dir.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = doc_dir.parent / f".tmp-{slug}-{uuid.uuid4().hex}"
    pages_dir = tmp_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    try:
        screen_records, script_records, handler_records = _gather_browser(source_path)
        rendered_by, static_reason = "chromium", None
    except BrowserUnavailable as exc:
        rendered_by, static_reason = "static", str(exc)
        screen_records, script_records, handler_records = _gather_static(source_bytes)

    manifest_pages: dict[str, dict] = {}
    screens_meta: list[dict] = []
    page_num = 0

    for rec in screen_records:
        page_num += 1
        page_dir = pages_dir / f"{page_num:02d}"
        page_dir.mkdir(parents=True, exist_ok=True)
        manifest_pages[str(page_num)] = _write_screen_page(page_dir, rec)
        screens_meta.append(
            {
                "page": page_num,
                "id": rec["id"],
                "title": rec["title"],
                "kind": rec["kind"],
            }
        )

    if script_records:
        page_num += 1
        page_dir = pages_dir / f"{page_num:02d}"
        page_dir.mkdir(parents=True, exist_ok=True)
        md = _render_scripts_index_md(script_records)
        (page_dir / "text.md").write_text(md)
        manifest_pages[str(page_num)] = {"images": [], "chars": len(md)}

        for rec in script_records:
            content = rec.get("content")
            if rec["category"] != "own" or not content:
                continue
            chunks = [
                content[i : i + _SCRIPT_CHUNK_CHARS]
                for i in range(0, len(content), _SCRIPT_CHUNK_CHARS)
            ] or [""]
            for part, chunk in enumerate(chunks, start=1):
                page_num += 1
                page_dir = pages_dir / f"{page_num:02d}"
                page_dir.mkdir(parents=True, exist_ok=True)
                md = _render_script_chunk_md(
                    rec["index"], rec["src"], part, len(chunks), chunk
                )
                (page_dir / "text.md").write_text(md)
                manifest_pages[str(page_num)] = {"images": [], "chars": len(md)}

    if handler_records:
        page_num += 1
        page_dir = pages_dir / f"{page_num:02d}"
        page_dir.mkdir(parents=True, exist_ok=True)
        md = _render_handlers_md(handler_records)
        (page_dir / "text.md").write_text(md)
        manifest_pages[str(page_num)] = {"images": [], "chars": len(md)}

    page_count = page_num
    pages_list = sorted(int(k) for k in manifest_pages)

    # Reuse the PDF route's shard packer and image-token constant rather than a
    # second copy of either — a DEFERRED import, so it only runs once this
    # module (and file_extract_tools, which is what got us here) are both fully
    # loaded. Breaks the cycle: file_extract_tools imports html_extract lazily
    # too (see its module docstring's "lazy import" convention).
    from app.agents.tools import file_extract_tools as _fet

    page_tokens: dict[int, int] = {}
    for n in pages_list:
        meta = manifest_pages[str(n)]
        tok = meta["chars"] // 4
        for name in meta["images"]:
            try:
                from PIL import Image

                with Image.open(pages_dir / f"{n:02d}" / name) as im:
                    tok += (im.width * im.height) // _fet._PIXELS_PER_IMAGE_TOKEN
            except OSError:
                continue
        page_tokens[n] = tok

    shards = _fet._build_shards(slug, "html", pages_list, page_tokens)
    shard_basis = {
        "safe_budget": _fet._SHARD_SAFE_BUDGETS[_fet._SHARD_DEFAULT_MODEL],
        "agent_reserve": _fet._SHARD_RESERVE_TOKENS,
        "usable": _fet._SHARD_SAFE_BUDGETS[_fet._SHARD_DEFAULT_MODEL]
        - _fet._SHARD_RESERVE_TOKENS,
        "model": _fet._SHARD_DEFAULT_MODEL,
        "page_cap": _fet._SHARD_PAGE_CAP,
    }
    total_chars = sum(manifest_pages[str(n)]["chars"] for n in pages_list)

    manifest = {
        "source": filename,
        "source_sha256": source_sha256,
        "source_format": "html",
        "converted_by": None,
        "slug": slug,
        "page_count": page_count,
        # No pdfium render scale applies here; screenshots are taken 1:1 against
        # the fixed viewport above. Kept as a float so the key's TYPE matches the
        # PDF manifest's (spec §6.1 "the PDF manifest's keys").
        "scale": 1.0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pages": {str(n): manifest_pages[str(n)] for n in pages_list},
        "shards": shards,
        "shard_basis": shard_basis,
        "totals": {"chars": total_chars, "screens": len(screens_meta)},
        "rendered_by": rendered_by,
        "static_reason": static_reason,
        "screens": screens_meta,
    }
    (tmp_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    doc_ref_re = _fet._DOC_REF_RE
    doc_parts = []
    for n in pages_list:
        text_path = pages_dir / f"{n:02d}" / "text.md"
        text = text_path.read_text() if text_path.is_file() else ""
        text = doc_ref_re.sub(rf"@[[pages/{n:02d}/\1]]", text)
        doc_parts.append(
            f"\n\n<!-- ================= PAGE {n} ================= -->\n\n" + text
        )
    (tmp_dir / "document.md").write_text("".join(doc_parts))

    os.rename(tmp_dir, doc_dir)

    return {
        "rebuilt": True,
        "rendered_by": rendered_by,
        "static_reason": static_reason,
        "manifest": manifest,
    }


def _read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Browser route
# ---------------------------------------------------------------------------


def _gather_browser(source_path: Path) -> tuple[list[dict], list[dict], list[dict]]:
    """Run DETECT, then per-screen show+EXTRACT+screenshot, then the scripts phase.

    Raises BrowserUnavailable on any Playwright/Chromium failure — the ONLY
    signal materialise_html uses to fall back to the static route.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        raise BrowserUnavailable(f"Playwright unavailable: {exc}") from exc

    try:
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(args=["--no-sandbox"])
            except Exception as exc:  # noqa: BLE001
                raise BrowserUnavailable(f"Chromium unavailable: {exc}") from exc
            try:
                page = browser.new_page(viewport=_VIEWPORT)
                uri = source_path.as_uri()
                page.goto(uri, wait_until="load", timeout=_GOTO_TIMEOUT_MS)
                detect = json.loads(page.evaluate(_DETECT_SCRIPT))

                screen_records: list[dict] = []
                for s in detect.get("screens", []):
                    selector = s.get("selector", "")
                    show = s.get("show", "visible")
                    if show == "force":
                        page.goto(uri, wait_until="load", timeout=_GOTO_TIMEOUT_MS)
                        try:
                            page.evaluate(_FORCE_SCRIPT, selector)
                        except Exception:  # noqa: BLE001 — extract whatever is there
                            pass
                    elif show != "visible":
                        # A shell show/openDialog call, e.g. window.__prototype.show('id').
                        try:
                            page.evaluate(show)
                        except Exception:  # noqa: BLE001
                            pass

                    extract = json.loads(page.evaluate(_EXTRACT_SCRIPT, selector))
                    screenshot = _screenshot_screen(page, selector)
                    screen_records.append(
                        _screen_record_from_extract(s, extract, screenshot)
                    )

                scripts_list = json.loads(page.evaluate(_LIST_SCRIPT))
                script_records = []
                for entry in scripts_list:
                    idx = entry["i"]
                    src = entry.get("src") or ""
                    length = entry.get("length", 0)
                    if entry.get("defines_prototype"):
                        script_records.append(
                            {
                                "index": idx,
                                "src": src,
                                "length": length,
                                "category": "shell_runtime",
                                "content": None,
                            }
                        )
                        continue
                    if src:
                        script_records.append(
                            {
                                "index": idx,
                                "src": src,
                                "length": length,
                                "category": "library",
                                "content": None,
                            }
                        )
                        continue
                    content = _read_script_content(page, idx)
                    category = "library" if _looks_minified(content) else "own"
                    script_records.append(
                        {
                            "index": idx,
                            "src": src,
                            "length": len(content),
                            "category": category,
                            "content": content if category == "own" else None,
                        }
                    )

                handler_records = json.loads(page.evaluate(_HANDLERS_SCRIPT))
            finally:
                browser.close()
    except BrowserUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 — any other failure degrades to static
        raise BrowserUnavailable(f"browser extraction failed: {exc}") from exc

    return screen_records, script_records, handler_records


def _screenshot_screen(page: Any, selector: str) -> bytes | None:
    """The screen element's screenshot, or a viewport screenshot if it has no box."""
    try:
        return page.locator(selector).screenshot(timeout=_SCREENSHOT_TIMEOUT_MS)
    except Exception:  # noqa: BLE001 — no box (zero-size / detached) → viewport
        try:
            return page.screenshot()
        except Exception:  # noqa: BLE001
            return None


def _read_script_content(page: Any, idx: int) -> str:
    parts: list[str] = []
    offset = 0
    while True:
        chunk = page.evaluate(_READ_SCRIPT, [idx, offset])
        parts.append(chunk)
        if len(chunk) < _SCRIPT_CHUNK_CHARS:
            break
        offset += _SCRIPT_CHUNK_CHARS
    return "".join(parts)


def _looks_minified(text: str) -> bool:
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if not lines:
        return False
    avg = sum(len(ln) for ln in lines) / len(lines)
    return avg > _MINIFIED_AVG_LINE_CHARS


def _screen_record_from_extract(
    s: dict, extract: dict, screenshot: bytes | None
) -> dict:
    if "error" in extract:
        return {
            "id": s["id"],
            "title": s.get("title") or s["id"],
            "kind": s.get("kind", "page"),
            "selector": s.get("selector", ""),
            "show": s.get("show", ""),
            "fields": [],
            "actions": [],
            "tables": [],
            "hidden": [],
            "text": f"(extraction error: {extract['error']})",
            "text_length": 0,
            "screenshot": screenshot,
        }
    text = extract.get("text", "")
    return {
        "id": s["id"],
        "title": s.get("title") or s["id"],
        "kind": s.get("kind", "page"),
        "selector": s.get("selector", ""),
        "show": s.get("show", ""),
        "fields": extract.get("fields", []),
        "actions": extract.get("actions", []),
        "tables": extract.get("tables", []),
        "hidden": extract.get("hidden", []),
        "text": text,
        "text_length": extract.get("text_length", len(text)),
        "screenshot": screenshot,
    }


# ---------------------------------------------------------------------------
# Static route — stdlib html.parser, no browser
# ---------------------------------------------------------------------------


_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class _Node:
    __slots__ = ("tag", "attrs", "children", "parent", "data")

    def __init__(
        self,
        tag: str | None,
        attrs: dict | None = None,
        parent: "_Node | None" = None,
        data: str | None = None,
    ):
        self.tag = tag  # None for a text node
        self.attrs = attrs or {}
        self.children: list[_Node] = []
        self.parent = parent
        self.data = data


class _TreeBuilder(html.parser.HTMLParser):
    """A minimal DOM-ish tree — just enough to replicate DETECT's CSS-selector rules."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("html")
        self._stack: list[_Node] = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(
            tag,
            {k: (v if v is not None else "") for k, v in attrs},
            parent=self._stack[-1],
        )
        self._stack[-1].children.append(node)
        if tag not in _VOID_TAGS:
            self._stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self._stack) - 1, 0, -1):
            if self._stack[i].tag == tag:
                del self._stack[i:]
                break

    def handle_data(self, data: str) -> None:
        self._stack[-1].children.append(_Node(None, parent=self._stack[-1], data=data))


def _clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _slugify(s: str) -> str:
    s = _clean(s).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:40]


def _iter_elements(node: _Node):
    """Every element DESCENDANT of node, depth-first (node itself excluded)."""
    for c in node.children:
        if c.tag is not None:
            yield c
            yield from _iter_elements(c)


def _iter_self_and_elements(node: _Node):
    if node.tag is not None:
        yield node
    yield from _iter_elements(node)


def _text_content(node: _Node) -> str:
    parts: list[str] = []
    for n in _iter_text_nodes(node):
        parts.append(n)
    return "".join(parts)


def _iter_text_nodes(node: _Node):
    if node.tag is None:
        yield node.data or ""
        return
    for c in node.children:
        yield from _iter_text_nodes(c)


def _has_class_token(node: _Node, token: str) -> bool:
    return token in (node.attrs.get("class") or "").split()


_MARKER_WORDS = ("screen", "page", "view", "step")


def _matches_markers(node: _Node) -> bool:
    idv = node.attrs.get("id") or ""
    clv = node.attrs.get("class") or ""
    return any(w in idv or w in clv for w in _MARKER_WORDS)


def _matches_dialog(node: _Node) -> bool:
    if node.tag == "dialog" or node.attrs.get("role") == "dialog":
        return True
    idv = node.attrs.get("id") or ""
    clv = node.attrs.get("class") or ""
    return "modal" in idv or "dialog" in idv or "modal" in clv or "dialog" in clv


_CONTROL_TAGS = {"input", "select", "textarea", "button", "table"}


def _has_control_descendant(node: _Node) -> bool:
    for el in _iter_elements(node):
        if el.tag in _CONTROL_TAGS:
            return True
        if el.tag == "a" and el.attrs.get("href") is not None:
            return True
        if el.attrs.get("role") == "button":
            return True
        if "onclick" in el.attrs:
            return True
    return False


def _looks_hidden(node: _Node) -> bool:
    """ponytail: inline style / attribute only — no CSS cascade, so a class-driven
    `display:none` rule is missed. Real detection needs a browser (the primary
    route); this is only the static fallback's best-effort guess."""
    if "hidden" in node.attrs:
        return True
    style = (node.attrs.get("style") or "").lower().replace(" ", "")
    return "display:none" in style or "visibility:hidden" in style


def _is_visible_static(node: _Node) -> bool:
    return not _looks_hidden(node)


def _collect_candidates(root: _Node) -> list[_Node]:
    main_children: set[int] = set()
    for el in _iter_elements(root):
        if el.tag == "main":
            main_children.update(id(c) for c in el.children if c.tag is not None)

    candidates = []
    for el in _iter_elements(root):
        is_main_child = id(el) in main_children
        if (
            el.tag in ("section", "form")
            or is_main_child
            or _matches_dialog(el)
            or _matches_markers(el)
        ):
            if _has_control_descendant(el):
                candidates.append(el)
    return candidates


def _contains(ancestor: _Node, node: _Node) -> bool:
    n = node.parent
    while n is not None:
        if n is ancestor:
            return True
        n = n.parent
    return False


def _filter_candidates(candidates: list[_Node]) -> list[_Node]:
    def is_wrapper(el: _Node) -> bool:
        return sum(1 for o in candidates if o is not el and _contains(el, o)) >= 2

    kept = [el for el in candidates if not is_wrapper(el)]
    return [
        el for el in kept if not any(o is not el and _contains(o, el) for o in kept)
    ]


def _title_of(node: _Node) -> str:
    aria = node.attrs.get("aria-label")
    if aria:
        return _clean(aria)[:80]
    title_attr = node.attrs.get("title")
    if title_attr:
        return _clean(title_attr)[:80]
    for el in _iter_elements(node):
        if el.tag in ("h1", "h2", "h3", "legend", "caption"):
            t = _clean(_text_content(el))
            if t:
                return t[:80]
    if node.attrs.get("id"):
        return node.attrs["id"][:80]
    return _clean(_text_content(node))[:80]


def _selector_of(node: _Node) -> str:
    if node.attrs.get("id"):
        return "#" + node.attrs["id"]
    parts: list[str] = []
    n: _Node | None = node
    while n is not None and n.tag is not None and n.tag != "body":
        siblings = [
            c for c in (n.parent.children if n.parent else []) if c.tag == n.tag
        ]
        idx = siblings.index(n) + 1 if n in siblings else 1
        parts.insert(0, f"{n.tag}:nth-of-type({idx})")
        if n.parent is not None and n.parent.attrs.get("id"):
            parts.insert(0, "#" + n.parent.attrs["id"])
            break
        n = n.parent
    return " > ".join(parts)


def _finalize_screens(found: list[tuple[_Node, str, str, str | None]]) -> list[dict]:
    seen: dict[str, int] = {}
    screens = []
    for i, (el, kind, show, forced_selector) in enumerate(found):
        raw_id = el.attrs.get("id") or ""
        base_id = _slugify(raw_id) if raw_id else _slugify(_title_of(el))
        if not base_id:
            base_id = f"screen-{i + 1}"
        if base_id in seen:
            seen[base_id] += 1
            sid = f"{base_id}-{seen[base_id]}"
        else:
            seen[base_id] = 1
            sid = base_id
        title = _title_of(el) or sid
        selector = forced_selector if forced_selector else _selector_of(el)
        screens.append(
            {
                "id": sid,
                "title": title,
                "kind": kind,
                "selector": selector,
                "show": show,
                "node": el,
            }
        )
    return screens


def _has_shell_script(root: _Node) -> bool:
    for el in _iter_elements(root):
        if el.tag == "script" and re.search(r"__prototype\s*=", _text_content(el)):
            return True
    return False


def _static_detect(root_body: _Node) -> list[dict]:
    shell = _has_shell_script(root_body)
    found: list[tuple[_Node, str, str, str | None]] = []
    if shell:
        for el in _iter_elements(root_body):
            if el.tag == "section" and _has_class_token(el, "screen"):
                sid = el.attrs.get("id", "")
                found.append((el, "page", f"window.__prototype.show('{sid}')", None))
        for el in _iter_elements(root_body):
            if el.tag == "div" and _has_class_token(el, "dialog"):
                sid = el.attrs.get("id", "")
                found.append(
                    (el, "dialog", f"window.__prototype.openDialog('{sid}')", None)
                )
    else:
        candidates = _collect_candidates(root_body)
        top = _filter_candidates(candidates)
        if top:
            for el in top:
                kind = "dialog" if _matches_dialog(el) else "page"
                show = "force" if _looks_hidden(el) else "visible"
                found.append((el, kind, show, None))
        else:
            headers = [el for el in _iter_elements(root_body) if el.tag in ("h1", "h2")]
            if headers:
                for el in headers:
                    found.append((el, "section", "visible", None))
            else:
                found.append((root_body, "page", "visible", "body"))
    return _finalize_screens(found)


_KEEP_ATTRS_RE = re.compile(
    r"^(id|name|type|required|pattern|min|max|minlength|maxlength|step|placeholder|"
    r"disabled|readonly|multiple|value|checked|selected|href|target|onclick|onchange|"
    r"oninput|onsubmit|role|hidden|title|aria-.+|data-.+)$"
)


def _kept_attrs(el: _Node) -> dict:
    return {k: v for k, v in el.attrs.items() if _KEEP_ATTRS_RE.match(k)}


def _label_of(el: _Node, doc_root: _Node) -> str:
    el_id = el.attrs.get("id")
    if el_id:
        for cand in _iter_elements(doc_root):
            if cand.tag == "label" and cand.attrs.get("for") == el_id:
                return _clean(_text_content(cand))
    n = el.parent
    while n is not None:
        if n.tag == "label":
            return _clean(_text_content(n))
        n = n.parent
    n = el.parent
    while n is not None:
        cls = n.attrs.get("class") or ""
        if any(t in cls for t in ("field", "form-group", "form-field")):
            for cand in _iter_self_and_elements(n):
                if (
                    cand.tag == "label"
                    or "label" in (cand.attrs.get("class") or "").split()
                ):
                    return _clean(_text_content(cand))
            break
        n = n.parent
    return _clean(
        el.attrs.get("aria-label")
        or el.attrs.get("placeholder")
        or el.attrs.get("name")
        or el.attrs.get("id")
        or ""
    )


def _field_of(el: _Node, doc_root: _Node) -> dict:
    if el.tag == "select":
        control = "multi-select" if "multiple" in el.attrs else "dropdown"
    elif el.tag == "textarea":
        control = "textarea"
    else:
        control = el.attrs.get("type") or "text"
    options = None
    if el.tag == "select":
        options = []
        for opt in _iter_elements(el):
            if opt.tag == "option":
                label = _clean(_text_content(opt))
                val = opt.attrs.get("value")
                options.append(
                    f"{label} [value={val}]" if val and val != label else label
                )
    return {
        "label": _label_of(el, doc_root),
        "control": control,
        "attrs": _kept_attrs(el),
        "options": options,
        "visible": _is_visible_static(el),
    }


def _action_of(el: _Node) -> dict:
    text = (
        _clean(_text_content(el))
        or el.attrs.get("aria-label")
        or el.attrs.get("title")
        or ""
    )
    return {
        "text": text,
        "tag": el.tag,
        "attrs": _kept_attrs(el),
        "visible": _is_visible_static(el),
    }


def _table_of(el: _Node) -> dict:
    caption_el = next((c for c in el.children if c.tag == "caption"), None)
    caption = _clean(_text_content(caption_el)) if caption_el else ""

    thead = next((c for c in _iter_elements(el) if c.tag == "thead"), None)
    header_row = (
        next((c for c in _iter_elements(thead) if c.tag == "tr"), None)
        if thead
        else None
    )
    if header_row is None:
        all_rows = [c for c in _iter_elements(el) if c.tag == "tr"]
        header_row = all_rows[0] if all_rows else None
    columns = []
    if header_row is not None:
        columns = [
            _clean(_text_content(th))
            for th in _iter_elements(header_row)
            if th.tag == "th"
        ]

    tbody = next((c for c in _iter_elements(el) if c.tag == "tbody"), None)
    scope = tbody if tbody is not None else el
    body_rows = []
    for tr in _iter_elements(scope):
        if tr.tag == "tr":
            cells = [c for c in _iter_elements(tr) if c.tag in ("td", "th")]
            if cells:
                body_rows.append([_clean(_text_content(c)) for c in cells])

    return {
        "caption": caption,
        "columns": columns,
        "rows": body_rows[:5],
        "row_count": len(body_rows),
    }


_ACTION_TAGS = {"button", "a"}
_ACTION_DATA_ATTRS = (
    "data-goto",
    "data-opens",
    "data-submit",
    "data-closes",
    "data-tab",
    "data-show",
    "data-hide",
)


def _is_action_el(e: _Node) -> bool:
    if e.tag in _ACTION_TAGS or e.attrs.get("role") == "button" or "onclick" in e.attrs:
        return True
    return any(a in e.attrs for a in _ACTION_DATA_ATTRS)


def _is_hidden_candidate(e: _Node) -> bool:
    if "hidden" in e.attrs or e.tag == "dialog":
        return True
    if e.attrs.get("role") in ("alert", "dialog") or "aria-live" in e.attrs:
        return True
    return any(_has_class_token(e, t) for t in ("state", "error", "alert", "toast"))


def _extract_static_screen(node: _Node, doc_root: _Node) -> dict:
    nodes = [node]
    if node.tag in ("h1", "h2") and node.parent is not None:
        siblings = [c for c in node.parent.children if c.tag is not None]
        idx = siblings.index(node)
        for sib in siblings[idx + 1 :]:
            if sib.tag == node.tag or sib.tag == "h1":
                break
            nodes.append(sib)

    def all_matching(pred):
        out = []
        for n in nodes:
            for el in _iter_self_and_elements(n):
                if pred(el):
                    out.append(el)
        return out

    fields = [
        _field_of(el, doc_root)
        for el in all_matching(lambda e: e.tag in ("input", "select", "textarea"))
    ]
    actions = [_action_of(el) for el in all_matching(_is_action_el)]
    tables = [_table_of(el) for el in all_matching(lambda e: e.tag == "table")]

    hidden = []
    for el in all_matching(_is_hidden_candidate):
        if (
            not _is_visible_static(el)
            or _has_class_token(el, "state")
            or el.attrs.get("role") == "alert"
            or "aria-live" in el.attrs
        ):
            hidden.append(
                {
                    "id": el.attrs.get("id", ""),
                    "class": el.attrs.get("class", ""),
                    "text": _clean(_text_content(el))[:500],
                }
            )

    text = " | ".join(_clean(_text_content(n)) for n in nodes)
    return {
        "fields": fields,
        "actions": actions,
        "tables": tables,
        "hidden": hidden,
        "text": text[:40000],
        "text_length": len(text),
    }


def _static_scripts(root: _Node) -> list[dict]:
    scripts = [el for el in _iter_elements(root) if el.tag == "script"]
    records = []
    for i, el in enumerate(scripts):
        src = el.attrs.get("src") or ""
        content = _text_content(el) if not src else ""
        if re.search(r"__prototype\s*=", content):
            records.append(
                {
                    "index": i,
                    "src": src,
                    "length": len(content),
                    "category": "shell_runtime",
                    "content": None,
                }
            )
        elif src:
            records.append(
                {
                    "index": i,
                    "src": src,
                    "length": 0,
                    "category": "library",
                    "content": None,
                }
            )
        else:
            category = "library" if _looks_minified(content) else "own"
            records.append(
                {
                    "index": i,
                    "src": src,
                    "length": len(content),
                    "category": category,
                    "content": content if category == "own" else None,
                }
            )
    return records


_ON_ATTR_RE = re.compile(r"^on")


def _static_handlers(root: _Node) -> list[dict]:
    out = []
    for el in _iter_elements(root):
        for name, val in el.attrs.items():
            if _ON_ATTR_RE.match(name):
                element_name = el.tag + (
                    f"#{el.attrs['id']}" if el.attrs.get("id") else ""
                )
                out.append(
                    {
                        "element": element_name,
                        "text": _clean(_text_content(el))[:60],
                        "event": name,
                        "code": val,
                    }
                )
    return out


def _gather_static(source_bytes: bytes) -> tuple[list[dict], list[dict], list[dict]]:
    text = source_bytes.decode("utf-8", errors="replace")
    builder = _TreeBuilder()
    builder.feed(text)
    builder.close()
    root = builder.root

    screen_defs = _static_detect(root)
    screen_records = []
    for sd in screen_defs:
        data = _extract_static_screen(sd["node"], root)
        screen_records.append(
            {
                "id": sd["id"],
                "title": sd["title"] or sd["id"],
                "kind": sd["kind"],
                "selector": sd["selector"],
                "show": sd["show"],
                "fields": data["fields"],
                "actions": data["actions"],
                "tables": data["tables"],
                "hidden": data["hidden"],
                "text": data["text"],
                "text_length": data["text_length"],
                "screenshot": None,
            }
        )

    script_records = _static_scripts(root)
    handler_records = _static_handlers(root)
    return screen_records, script_records, handler_records


# ---------------------------------------------------------------------------
# Page rendering — shared by both routes (spec §6.1 text.md format)
# ---------------------------------------------------------------------------

_VALIDATION_ATTR_ORDER = (
    "pattern",
    "min",
    "max",
    "minlength",
    "maxlength",
    "step",
    "type",
)
_ACTION_ATTR_ORDER = (
    "data-goto",
    "data-opens",
    "data-submit",
    "data-closes",
    "data-tab",
    "data-show",
    "data-hide",
    "href",
    "onclick",
)


def _validation_of(attrs: dict) -> str:
    return "; ".join(f"{k}={attrs[k]}" for k in _VALIDATION_ATTR_ORDER if attrs.get(k))


def _action_target(attrs: dict) -> str:
    return "; ".join(
        f"{k}={attrs[k]}" for k in _ACTION_ATTR_ORDER if attrs.get(k) not in (None, "")
    )


def _render_screen_md(rec: dict, has_screenshot: bool) -> str:
    lines: list[str] = []
    if has_screenshot:
        lines.append("@[[image-1.png]]")
    lines.append(f"# Screen: {rec['title']}")
    lines.append(
        f"id: {rec['id']} · kind: {rec['kind']} · selector: {rec['selector']} · shown by: {rec['show']}"
    )
    lines.append("")

    lines.append("## Fields")
    lines.append("| Label | Control | Required | Validation | Options or value |")
    lines.append("|---|---|---|---|---|")
    for f in rec.get("fields", []):
        attrs = f.get("attrs") or {}
        required = "yes" if "required" in attrs else "no"
        validation = _validation_of(attrs)
        options = f.get("options")
        opt_val = "; ".join(options) if options else attrs.get("value", "")
        lines.append(
            f"| {f.get('label', '')} | {f.get('control', '')} | {required} | {validation} | {opt_val} |"
        )
    lines.append("")

    lines.append("## Actions")
    lines.append("| Label | Goes to or does |")
    lines.append("|---|---|")
    for a in rec.get("actions", []):
        lines.append(
            f"| {a.get('text', '')} | {_action_target(a.get('attrs') or {})} |"
        )
    lines.append("")

    lines.append("## Tables")
    for t in rec.get("tables", []):
        caption = t.get("caption") or "(untitled table)"
        lines.append(f"**{caption}** ({t.get('row_count', 0)} row(s), up to 5 shown)")
        cols = t.get("columns") or []
        if cols:
            lines.append("| " + " | ".join(cols) + " |")
            lines.append("|" + "---|" * len(cols))
        for row in t.get("rows", []):
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")

    lines.append("## Hidden states and messages")
    for h in rec.get("hidden", []):
        label = h.get("id") or h.get("class") or "(unlabeled)"
        lines.append(f'- {label} (hidden): "{h.get("text", "")}"')
    lines.append("")

    lines.append("## Text")
    text = rec.get("text", "")
    text_length = rec.get("text_length", len(text))
    if text_length > len(text):
        lines.append(f"{text}\n\n(text truncated — {text_length} characters total)")
    else:
        lines.append(text)

    return "\n".join(lines) + "\n"


def _write_screen_page(page_dir: Path, rec: dict) -> dict:
    has_shot = rec.get("screenshot") is not None
    md = _render_screen_md(rec, has_shot)
    (page_dir / "text.md").write_text(md)
    images: list[str] = []
    if has_shot:
        (page_dir / "image-1.png").write_bytes(rec["screenshot"])
        images = ["image-1.png"]
    return {"images": images, "chars": len(md)}


def _render_scripts_index_md(records: list[dict]) -> str:
    lines = [
        "# Scripts index",
        "",
        "| # | Src | Length | Defines window.__prototype | Category |",
        "|---|---|---|---|---|",
    ]
    for r in records:
        defines = "yes" if r["category"] == "shell_runtime" else "no"
        src = r["src"] or "(inline)"
        lines.append(
            f"| {r['index']} | {src} | {r['length']} | {defines} | {r['category']} |"
        )
    return "\n".join(lines) + "\n"


def _render_script_chunk_md(
    index: int, src: str, part: int, total: int, chunk: str
) -> str:
    lines = [f"# Script {index}"]
    if total > 1:
        lines.append(f"part {part} of {total}")
    if src:
        lines.append(f"src: {src}")
    lines.append("")
    lines.append("```javascript")
    lines.append(chunk)
    lines.append("```")
    return "\n".join(lines) + "\n"


def _render_handlers_md(handlers: list[dict]) -> str:
    lines = [
        "# Inline handlers",
        "",
        "| Element | Text | Event | Code |",
        "|---|---|---|---|",
    ]
    for h in handlers:
        lines.append(
            f"| {h.get('element', '')} | {h.get('text', '')} | {h.get('event', '')} | {h.get('code', '')} |"
        )
    return "\n".join(lines) + "\n"
