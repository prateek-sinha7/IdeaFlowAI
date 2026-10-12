"""agents/capabilities/template_kit.py — what a prototype takes from its design template.

The launch seeds the chosen template's files into ``.context/design/template/``
(``assets/template.html`` when the template ships one, ``example.html`` for most).
Two pieces of code read them through this module, so both see the same template:

  * the ``screen_plan`` task parser hands every builder the template's class list and
    the paths to open, instead of the shell's own vocabulary;
  * ``assemble_prototype`` emits the template's CSS and, when the template's markup
    has a recognisable frame (a content area plus repeated nav items), builds the page
    frame from it — the template's own top bar or side bar, with the prototype's
    screens as its nav items. Otherwise the shell's frame stays, styled by the
    template's CSS.

With neither file the kit is ``None`` and both callers behave exactly as before.

Pure stdlib; reads the sandbox only through the ``read`` callable it is given.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

TEMPLATE_DIR = ".context/design/template"
# CSS is taken from both, template.html first: example.html carries the fuller vocabulary.
SOURCES = ("assets/template.html", "example.html")

_STYLE_RE = re.compile(r"<style\b[^>]*>(.*?)</style\s*>", re.IGNORECASE | re.DOTALL)
_SCRIPT_RE = re.compile(r"<script\b.*?</script\s*>", re.IGNORECASE | re.DOTALL)
_BODY_RE = re.compile(r"<body\b[^>]*>(.*)</body\s*>", re.IGNORECASE | re.DOTALL)
_HEAD_RE = re.compile(r"<head\b[^>]*>(.*?)</head\s*>", re.IGNORECASE | re.DOTALL)
_LINK_RE = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_STRING_URL_RE = re.compile(r"""url\([^)]*\)|"[^"]*"|'[^']*'""")
_CLASS_SEL_RE = re.compile(r"\.(-?[_a-zA-Z][\w-]*)")
_VAR_RE = re.compile(r"(--[\w-]+)\s*:")
_OPEN_TAG_RE = re.compile(r"<([a-zA-Z][\w-]*)\b([^>]*)>")
_CLASS_ATTR_RE = re.compile(r"""\bclass\s*=\s*(["'])(.*?)\1""", re.IGNORECASE | re.DOTALL)
_ID_ATTR_RE = re.compile(r"""\s\bid\s*=\s*(["']).*?\1""", re.IGNORECASE | re.DOTALL)
_DATA_ATTR_RE = re.compile(r"""\s(?:data-[\w-]+|on[a-z]+)\s*=\s*(["']).*?\1""", re.IGNORECASE | re.DOTALL)

# Class tokens that mark the content area and a nav item, across the catalogue's
# templates (main / div.main / .content; a.nav-item / div.nav-item / .menu-item …).
_CONTENT_TOKENS = {"main", "main-content", "content", "app-main", "workspace", "page-content"}
_ITEM_TOKENS = {"nav-item", "nav-link", "menu-item", "sidebar-item", "side-item", "nav-btn", "navlink"}
# An element after the content area with one of these is an example overlay, not frame.
_OVERLAY_TOKENS = {"overlay", "modal", "dialog", "toast", "drawer", "popover", "scrim", "backdrop"}
_ACTIVE_TOKENS = ("is-active", "active", "current", "is-current", "selected", "on")
# The container the example's pages put their content in, so every screen gets the same column.
_COLUMN_TOKENS = ("wrap", "container", "page-inner", "content-inner", "page-body", "main-inner")
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

# The classes the shell's runtime and the assembler depend on, whatever the template
# names things: the screen root, tabs, states and the active marker.
RUNTIME_CLASSES = ("screen", "active", "state", "tabs", "tabs-nav", "tab-link", "tabs-content", "tab-panel")


@dataclass
class Frame:
    """The template's page frame with the content area and the nav items cut out."""
    before: str            # markup up to the content area, the nav already rebuilt around NAV_SLOT
    content_tag: str       # the content element's tag and its classes, for the new content area
    content_classes: str
    after: str             # the closing markup after the content area
    item_tag: str          # a nav item's tag and classes, for the prototype's screens
    item_classes: str
    active_class: str
    chrome_classes: list[str] = field(default_factory=list)   # the frame elements before the nav items
    column_class: str = ""   # the example's page column (its .wrap / .container), "" when it has none


@dataclass
class TemplateKit:
    sources: list[str]
    css_blocks: list[str]   # each <style> on its own, so an @import stays first in its sheet
    classes: list[str]
    variables: set[str]
    head_links: list[str] = field(default_factory=list)
    frame: Frame | None = None
    # Variables the frame's dark bar and the primary button paint their background with,
    # so the design system reaches them too (a template's own --navy, not just --accent).
    chrome_vars: list[str] = field(default_factory=list)
    button_vars: list[str] = field(default_factory=list)

    @property
    def css(self) -> str:
        return "\n".join(self.css_blocks)

    @property
    def paths(self) -> list[str]:
        return [f"{TEMPLATE_DIR}/{s}" for s in self.sources]


NAV_SLOT = "\x00NAV\x00"


def _classes_of(attrs: str) -> list[str]:
    m = _CLASS_ATTR_RE.search(attrs)
    return m.group(2).split() if m else []


def _element_end(html: str, start: int, tag: str) -> int | None:
    """End offset of the element whose open tag starts at ``start`` (nesting-aware)."""
    if tag.lower() in _VOID:
        close = html.find(">", start)
        return close + 1 if close >= 0 else None
    pat = re.compile(rf"<(/?){re.escape(tag)}\b[^>]*>", re.IGNORECASE)
    depth = 0
    for m in pat.finditer(html, start):
        if m.group(1):
            depth -= 1
            if depth == 0:
                return m.end()
        elif not m.group(0).endswith("/>"):
            depth += 1
    return None


def css_classes(css: str) -> list[str]:
    clean = _STRING_URL_RE.sub("", _COMMENT_RE.sub("", css))
    return sorted(set(_CLASS_SEL_RE.findall(clean)))


def _find_frame(body: str) -> Frame | None:
    """The content area and the nav items, or ``None`` when the markup has no
    recognisable frame (no content area, or fewer than two nav items outside it)."""
    content = None
    for m in _OPEN_TAG_RE.finditer(body):
        tag, attrs = m.group(1).lower(), m.group(2)
        if tag == "main" or set(_classes_of(attrs)) & _CONTENT_TOKENS:
            end = _element_end(body, m.start(), tag)
            if end is not None:
                content = (m.start(), end, tag, " ".join(_classes_of(attrs)))
            break
    if content is None:
        return None
    c_start, c_end, c_tag, c_classes = content
    outside = body[:c_start]
    items = []
    for m in _OPEN_TAG_RE.finditer(outside):
        classes = _classes_of(m.group(2))
        if set(classes) & _ITEM_TOKENS:
            end = _element_end(outside, m.start(), m.group(1))
            if end is not None:
                items.append((m.start(), end, m.group(1).lower(), classes))
    # Items nested in another item (an icon span with the same class) are not items.
    items = [it for it in items if not any(o[0] < it[0] and it[1] <= o[1] for o in items)]
    if len(items) < 2:
        return None
    common = [c for c in items[0][3] if all(c in it[3] for it in items)]
    active = next((t for t in _ACTIVE_TOKENS if any(t in it[3] for it in items) and t not in common), "active")
    first, last = items[0][0], items[-1][1]
    chrome_classes = [c for m in _OPEN_TAG_RE.finditer(outside[:first]) for c in _classes_of(m.group(2))]
    inside = [c for m in _OPEN_TAG_RE.finditer(body[c_start:c_end]) for c in _classes_of(m.group(2))]
    column = next((c for c in inside if c in _COLUMN_TOKENS), "")
    before = _neutralise(outside[:first]) + NAV_SLOT + _neutralise(outside[last:])
    after = _drop_overlays(_neutralise(body[c_end:]))
    return Frame(before=before, content_tag=c_tag, content_classes=c_classes, after=after,
                 item_tag=items[0][2], item_classes=" ".join(common or items[0][3]),
                 active_class=active, chrome_classes=chrome_classes, column_class=column)


def _neutralise(html: str) -> str:
    """The template's frame keeps its look and loses its behaviour: no ids (one could
    shadow a screen id and break every route to it), no data-* and no inline handlers,
    and no seed placeholder markers."""
    return _DATA_ATTR_RE.sub("", _ID_ATTR_RE.sub("", html)).replace("[REPLACE] ", "").replace("[REPLACE]", "")


def _drop_overlays(html: str) -> str:
    out, pos = [], 0
    for m in _OPEN_TAG_RE.finditer(html):
        if m.start() < pos:
            continue
        if set(_classes_of(m.group(2))) & _OVERLAY_TOKENS:
            end = _element_end(html, m.start(), m.group(1))
            if end is not None:
                out.append(html[pos:m.start()])
                pos = end
    out.append(html[pos:])
    return "".join(out)


_RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_HEX_RE = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")


def _bg_vars(css: str, classes: list[str]) -> list[str]:
    """The custom properties a rule for one of ``classes`` (alone, maybe with a tag)
    paints its background with, in rule order."""
    out: list[str] = []
    for m in _RULE_RE.finditer(_COMMENT_RE.sub("", css)):
        selectors = [x.strip() for x in m.group(1).split(",")]
        if any(re.fullmatch(rf"[a-z]*\.{re.escape(c)}", x) for x in selectors for c in classes):
            for decl in re.findall(r"background(?:-color)?\s*:([^;]*)", m.group(2)):
                out += [v for v in re.findall(r"var\((--[\w-]+)", decl) if v not in out]
    return out


def _is_dark(css: str, var: str) -> bool:
    m = re.search(rf"{re.escape(var)}\s*:\s*([^;}}]*)", css)
    hexm = _HEX_RE.search(m.group(1)) if m else None
    if not hexm:
        return False
    h = hexm.group(1)
    h = "".join(c * 2 for c in h) if len(h) == 3 else h
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.35


# The frame's example content, dropped: a subtitle, status badges and pills, an
# environment tag. Matched on class tokens, the way the catalogue's templates name them.
_DEMO_TOKENS = {"brand-sub", "brand-subtitle", "subtitle", "tagline", "badge", "pill", "env-pill", "env", "chip"}
_AVATAR_TOKENS = {"avatar", "user-avatar", "user-chip", "user", "user-menu", "profile"}


def _drop_elements(html: str, wanted: Callable[[set[str]], bool]) -> str:
    out, pos = [], 0
    for m in _OPEN_TAG_RE.finditer(html):
        if m.start() < pos or not wanted(set(_classes_of(m.group(2)))):
            continue
        end = _element_end(html, m.start(), m.group(1))
        if end is not None:
            out.append(html[pos:m.start()])
            pos = end
    out.append(html[pos:])
    return "".join(out)


_SEARCH_TOKENS = {"search", "searchbar", "search-box", "global-search", "search-bar"}
_TEXT_NODE_RE = re.compile(r">(\s*)([^<\s][^<]*?)(\s*)<")


def strip_demo_chrome(html: str) -> str:
    """The template's frame without its example content: no subtitle, badge or pill,
    and a plain search box ("Search…"), marked ``proto-search`` so the sign-in screen
    can hide it."""
    html = _drop_elements(html, lambda cls: bool(cls & _DEMO_TOKENS)
                          or any(c.endswith(("-badge", "-pill")) for c in cls))
    html = re.sub(r"""\bplaceholder\s*=\s*(["']).*?\1""", 'placeholder="Search…"', html)
    out, pos = [], 0
    for m in _OPEN_TAG_RE.finditer(html):
        if m.start() < pos or not set(_classes_of(m.group(2))) & _SEARCH_TOKENS:
            continue
        end = _element_end(html, m.start(), m.group(1))
        if end is None:
            continue
        inner = html[m.end():end]
        seen = []
        inner = _TEXT_NODE_RE.sub(lambda t, seen=seen: f">{t.group(1)}{'' if seen else seen.append(1) or 'Search…'}{t.group(3)}<", inner)
        tag = m.group(0)
        tag = (re.sub(r"""\bclass\s*=\s*(["'])(.*?)\1""", lambda c: f'class="{c.group(2)} proto-search"', tag, count=1))
        out.append(html[pos:m.start()] + tag + inner)
        pos = end
    out.append(html[pos:])
    return "".join(out)


def find_avatar(html: str) -> tuple[int, int] | None:
    """Where the frame's user avatar is, to put the prototype's account menu there."""
    for m in _OPEN_TAG_RE.finditer(html):
        if set(_classes_of(m.group(2))) & _AVATAR_TOKENS:
            end = _element_end(html, m.start(), m.group(1))
            if end is not None:
                return m.start(), end
    return None


def load_template_kit(read: Callable[[str], str | None]) -> TemplateKit | None:
    """The template's CSS, class list, variables, font links and frame, or ``None``
    when neither file is in the run (a run with no template)."""
    texts: dict[str, str] = {}
    for src in SOURCES:
        try:
            text = read(f"{TEMPLATE_DIR}/{src}")
        except Exception:  # noqa: BLE001 — an unreadable file is an absent one
            text = None
        if text and text.strip():
            texts[src] = text
    if not texts:
        return None
    blocks = [block for text in texts.values() for block in _STYLE_RE.findall(text) if block.strip()]
    css = "\n".join(blocks)
    head_links: list[str] = []
    for text in texts.values():
        head = _HEAD_RE.search(text)
        for link in _LINK_RE.findall(head.group(1) if head else ""):
            if re.search(r"""href\s*=\s*["']https?://""", link, re.IGNORECASE) and link not in head_links:
                head_links.append(link)
    frame = None
    # The frame comes from the finished example first — the seed is a skeleton of
    # `[REPLACE]` placeholders — and from the seed when the example has none.
    for src in reversed(SOURCES):
        body = _BODY_RE.search(texts.get(src, ""))
        if body and (frame := _find_frame(_SCRIPT_RE.sub("", body.group(1)))):
            break
    chrome_vars = ([v for v in _bg_vars(css, frame.chrome_classes) if _is_dark(css, v)]
                   if frame else [])
    return TemplateKit(sources=list(texts), css_blocks=blocks, classes=css_classes(css),
                       variables=set(_VAR_RE.findall(_COMMENT_RE.sub("", css))),
                       head_links=head_links, frame=frame, chrome_vars=chrome_vars,
                       button_vars=_bg_vars(css, ["btn-primary"]))
