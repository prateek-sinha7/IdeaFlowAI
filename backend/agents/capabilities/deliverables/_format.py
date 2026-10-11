"""agents/capabilities/deliverables/_format.py — DECLARED-format coercion.

QA-SG-014 (ISS-770 / ISS-776): the composer's "Output format" control renames the
deliverable (``DeliverableSpec.name`` → ``output.html``) but nothing downstream
ever produced HTML — both text-backed resolvers return the last agent's raw
markdown verbatim, so a completed run advertised ``.html`` (and, on the
``single_file`` path, ``text/html``) over markdown bytes. This module is the
missing half: when the DECLARED name says HTML and the resolved text is not a
document already, render it AS an HTML document.

Keyed on the DECLARED deliverable name only — never on a pipeline/workflow name
(INV-1 / SC-001), and never on a content sniff of what the bytes "look like"
beyond the one no-op guard (already-a-document → returned untouched, so every
prototype/revision path stays byte-identical).

Stdlib only — no ``app.*``, no kernel import — like ``_artifact.py`` and
``_placeholder.py``, so it composes into the resolver capabilities without
crossing an import-linter boundary.
"""

from __future__ import annotations

import html
import re

_HTML_EXTENSIONS = (".html", ".htm")
_DOCUMENT_START = ("<!doctype", "<html")

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_RULE_RE = re.compile(r"^\s*([-*_])\s*(\1\s*){2,}$")
_UL_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
_OL_RE = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC_RE = re.compile(r"(?<![*\w])\*([^*\n]+)\*(?!\*)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")

# Deliberately tiny: the wrapper is prepended to the agent's own text, and the
# completion gate's narration check (_placeholder._MAX_NARRATION_CHARS) measures
# the FINAL bytes — a fat <style> block would push short narration past that
# bound and silently un-flag it (QA-PS-027 / FIX-612).
_STYLE = (
    "body{max-width:52rem;margin:2rem auto;padding:0 1.25rem;"
    "font:16px/1.6 system-ui,sans-serif}"
    "pre,code{background:#f2f3f5;border-radius:4px}"
    "pre{padding:1rem;overflow:auto}"
)


def declares_html(name: str | None) -> bool:
    """True when the DECLARED deliverable name asks for an HTML document."""
    return bool(name) and name.lower().endswith(_HTML_EXTENSIONS)


def looks_like_html_document(text: str) -> bool:
    """True when the text ALREADY opens an HTML document (converting would corrupt it)."""
    return text.lstrip()[:60].lower().startswith(_DOCUMENT_START)


def coerce_to_declared_format(text: str, name: str | None) -> str:
    """Return ``text`` as an HTML document when the DECLARED ``name`` says HTML.

    No-op — the resolved value is returned untouched — when the declared name is
    not ``.html``/``.htm``, when the text is empty, or when it is already a
    document. So every non-HTML deliverable and every agent-written prototype
    keeps its exact bytes.
    """
    if not text or not text.strip():
        return text
    if not declares_html(name) or looks_like_html_document(text):
        return text
    return _html_document(text, name)


def _inline(raw: str) -> str:
    """Escape one line, then re-introduce the inline markdown spans."""
    out = html.escape(raw, quote=False)
    out = _INLINE_CODE_RE.sub(r"<code>\1</code>", out)
    out = _BOLD_RE.sub(r"<strong>\1</strong>", out)
    out = _ITALIC_RE.sub(r"<em>\1</em>", out)
    out = _LINK_RE.sub(r'<a href="\2">\1</a>', out)
    return out


def _render_body(text: str) -> str:
    """Render markdown block structure as HTML. Everything is escaped first.

    ponytail: headings / fences / lists / rules / paragraphs only — a markdown
    TABLE renders as paragraph text. Add a table branch when a workflow actually
    declares an HTML deliverable whose agents emit tables.
    """
    out: list[str] = []
    para: list[str] = []
    code: list[str] = []
    list_tag: str | None = None
    in_code = False

    def flush_para() -> None:
        if para:
            out.append("<p>" + "<br />".join(_inline(p) for p in para) + "</p>")
            para.clear()

    def close_list() -> None:
        nonlocal list_tag
        if list_tag:
            out.append(f"</{list_tag}>")
            list_tag = None

    def open_list(tag: str) -> None:
        nonlocal list_tag
        if list_tag != tag:
            close_list()
            out.append(f"<{tag}>")
            list_tag = tag

    for line in text.replace("\r\n", "\n").split("\n"):
        if line.lstrip().startswith("```"):
            if in_code:
                out.append(
                    "<pre><code>" + html.escape("\n".join(code)) + "</code></pre>"
                )
                code.clear()
            else:
                flush_para()
                close_list()
            in_code = not in_code
            continue
        if in_code:
            code.append(line)
            continue
        if not line.strip():
            flush_para()
            close_list()
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            flush_para()
            close_list()
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(heading.group(2).strip())}</h{level}>")
            continue
        if _RULE_RE.match(line):
            flush_para()
            close_list()
            out.append("<hr />")
            continue
        item = _UL_RE.match(line)
        if item:
            flush_para()
            open_list("ul")
            out.append(f"<li>{_inline(item.group(1).strip())}</li>")
            continue
        item = _OL_RE.match(line)
        if item:
            flush_para()
            open_list("ol")
            out.append(f"<li>{_inline(item.group(1).strip())}</li>")
            continue
        para.append(line.strip())

    if in_code and code:  # an unterminated fence still carries real content
        out.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
    flush_para()
    close_list()
    return "\n".join(out)


def _html_document(text: str, name: str | None) -> str:
    """Wrap the rendered body in a minimal, self-contained HTML document."""
    heading = _HEADING_RE.match(next((ln for ln in text.split("\n") if ln.strip()), ""))
    title = heading.group(2).strip() if heading else (name or "Deliverable")
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8" />\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1" />\n'
        f"<title>{html.escape(title, quote=False)}</title>\n"
        f"<style>{_STYLE}</style>\n"
        "</head>\n"
        "<body>\n"
        f"{_render_body(text)}\n"
        "</body>\n"
        "</html>\n"
    )
