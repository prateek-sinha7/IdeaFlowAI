"""agents/capabilities/assemble_step.py — the ``mechanical: assemble_prototype`` step kind.

Code, not a model, turns ``parts/<id>.html`` into ``prototype.html``:

  1. read ``build/screens.json`` (the Architect's inventory, ``screen_inventory``);
  2. for every screen take its part, keep exactly the ``<section class="screen">``,
     strip anything a fragment must not carry (script/style/link), namespace every
     id inside it so twenty-seven builders cannot collide, and wrap dialogs in the
     ONE dialog frame the shell knows how to hide and show;
  3. a screen with no usable part becomes a named stub — the run degrades, it does
     not die;
  4. pour nav + content + overlays into the fixed shell (``assemble_shell.html``),
     whose CSS and runtime are written once and tested once;
  5. validate statically (ids unique, every transition target exists, every
     transition the inventory expects is present) and write ``build/validation.json``;
  6. below the coverage threshold the step FAILS the run, naming what is missing.

Why this exists: across 50 runs the assembly, the hide/show mechanism and the
validation verdict were each produced by a small model reading another small model's
prose, and each was the run-killer at least once (ERROR-REASONS.md). None of those
three jobs needs a model.

Mirrors ``publish_step.py``: the strategy adapter is constructed by the engine per
dispatch for a step declaring ``mechanical: "assemble_prototype"`` — it is never
resolved through ``registry.resolve("strategy", ...)``. The kind IS registered under
``("mechanical", "assemble_prototype")`` (a no-arg stub below) so the capability palette
(``GET /api/capabilities``) and the composer's Capabilities tab can list and select it.
Pure stdlib; reaches the sandbox only through ``ctx.runner.sandbox`` (import-linter).
"""

from __future__ import annotations

import html as _html
import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any, AsyncIterator

from agents.capabilities.registry import register
from agents.capabilities.screen_inventory import (
    spec_fields,
    spec_section,
    Inventory,
    InventoryError,
    Screen,
    attribute_string,
    parse_inventory,
)

SCREENS_PATH = "build/screens.json"
PARTS_DIR = "parts"
VALIDATION_PATH = "build/validation.json"
THEME_PATH = "build/theme.json"
DEFAULT_DELIVERABLE = "prototype.html"
COVERAGE_THRESHOLD = 0.85

_SHELL_PATH = Path(__file__).with_name("assemble_shell.html")

_SECTION_TAG = re.compile(r"<(/?)section\b([^>]*)>", re.IGNORECASE)
_FORBIDDEN = [
    ("script", re.compile(r"<script\b.*?</script\s*>", re.IGNORECASE | re.DOTALL)),
    ("style", re.compile(r"<style\b.*?</style\s*>", re.IGNORECASE | re.DOTALL)),
    ("link", re.compile(r"<link\b[^>]*>", re.IGNORECASE)),
]
_ID_ATTR = re.compile(r"""\bid\s*=\s*(["'])(.*?)\1""", re.IGNORECASE | re.DOTALL)
_REF_ATTRS = (
    "id",
    "for",
    "data-tab",
    "data-show",
    "data-hide",
    "aria-controls",
    "aria-labelledby",
    "aria-describedby",
    "form",
    "list",
)
_REF_ATTR_RE = re.compile(
    r"""\b("""
    + "|".join(re.escape(a) for a in _REF_ATTRS)
    + r""")\s*=\s*(["'])(.*?)\2""",
    re.IGNORECASE | re.DOTALL,
)
_HREF_HASH_RE = re.compile(r"""\bhref\s*=\s*(["'])#([^"']*)\1""", re.IGNORECASE)
_RUNTIME_ATTR_RE = re.compile(
    r"""\b(data-(?:goto|submit|opens|closes|tab|show|hide))\s*=\s*(["'])(.*?)\2""",
    re.IGNORECASE | re.DOTALL,
)


class AssembleStepFailed(Exception):
    """The assembled prototype is below the coverage threshold (or nothing could be
    assembled). ``prototype.html`` and ``build/validation.json`` are still written so
    the failure is inspectable; the message names every missing screen."""


# ── part processing ──────────────────────────────────────────────────────────────


def _attr(tag: str, name: str) -> str | None:
    m = re.search(
        r"""\b%s\s*=\s*(["'])(.*?)\1""" % re.escape(name),
        tag,
        re.IGNORECASE | re.DOTALL,
    )
    return m.group(2) if m else None


def _set_attr(tag: str, name: str, value: str) -> str:
    pat = re.compile(
        r"""\b%s\s*=\s*(["'])(.*?)\1""" % re.escape(name), re.IGNORECASE | re.DOTALL
    )
    if pat.search(tag):
        return pat.sub(lambda _m: f'{name}="{value}"', tag, count=1)
    close = tag.rstrip()
    if close.endswith("/>"):
        return close[:-2].rstrip() + f' {name}="{value}" />'
    return close[:-1] + f' {name}="{value}">'


def _sections(text: str) -> list[tuple[int, int, str]]:
    """Every ``<section …>…</section>`` as (start, end, open_tag), nesting-aware."""
    out: list[tuple[int, int, str]] = []
    stack: list[tuple[int, str]] = []
    for m in _SECTION_TAG.finditer(text):
        if m.group(1) == "":
            stack.append((m.start(), m.group(0)))
        elif stack:
            start, tag = stack.pop()
            out.append((start, m.end(), tag))
    out.sort()
    return out


def extract_section(part: str, sid: str) -> tuple[str | None, list[str]]:
    """The ``<section class="screen" id="<sid>">`` a part must contain, root tag fixed.

    Falls back to the first top-level ``section.screen`` (id corrected), then to the
    first section at all. Returns ``(None, notes)`` when the part has no section.
    """
    notes: list[str] = []
    if not part or not part.strip():
        return None, ["part is empty"]
    secs = _sections(part)
    if not secs:
        return None, ["part has no <section> element"]
    chosen = None
    for start, end, tag in secs:
        if (_attr(tag, "id") or "").strip() == sid:
            chosen = (start, end, tag)
            break
    if chosen is None:
        # top-level sections only: those not contained in an earlier one
        top = [s for s in secs if not any(o[0] < s[0] and s[1] <= o[1] for o in secs)]
        screens = [s for s in top if "screen" in (_attr(s[2], "class") or "").split()]
        chosen = (screens or top)[0]
        notes.append(
            f"no section with id={sid!r}; used the first "
            f"{'screen ' if screens else ''}section and set its id"
        )
    start, end, tag = chosen
    body = part[start:end]
    new_tag = tag
    classes = (_attr(tag, "class") or "").split()
    if "screen" not in classes:
        new_tag = _set_attr(new_tag, "class", " ".join(classes + ["screen"]).strip())
        notes.append("root section was missing class=screen")
    new_tag = _set_attr(new_tag, "id", sid)
    return new_tag + body[len(tag) :], notes


def strip_forbidden(section: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    for name, pat in _FORBIDDEN:
        section, n = pat.subn("", section)
        if n:
            notes.append(
                f"removed {n} <{name}> element(s) — parts carry no style or script"
            )
    return section, notes


def namespace_ids(
    section: str, sid: str, reserved: set[str]
) -> tuple[str, list[str], set[str]]:
    """Prefix every id local to this section with ``<sid>--`` and rewrite the
    attributes that reference ids. Returns (html, duplicate_ids, local_ids_after)."""
    root_end = section.find(">") + 1
    root, rest = section[:root_end], section[root_end:]
    ids = [m.group(2).strip() for m in _ID_ATTR.finditer(rest)]
    counts = Counter(i for i in ids if i)
    duplicates = sorted(i for i, n in counts.items() if n > 1)
    # Every id inside the section is local and gets the prefix — INCLUDING one that
    # happens to equal another screen's id (run d29038b9: a <select id="transaction-type">
    # inside one screen shadowed the screen of that name and broke every route to it).
    # Only the root section keeps its id. ``reserved`` is reported, never exempted.
    # ``rest`` excludes the root tag, so an id equal to ``sid`` here is an INNER element
    # reusing the screen's own id — it is prefixed like any other.
    mapping: dict[str, str] = {}
    for i in counts:
        if i.startswith(f"{sid}--"):
            continue
        mapping[i] = f"{sid}--{i}"
    shadowed = sorted(i for i in counts if i != sid and i in reserved)
    if shadowed:
        duplicates = sorted(
            set(duplicates)
            | {f"{i} (shadowed a screen id, prefixed)" for i in shadowed}
        )

    def _map_tokens(value: str) -> str:
        return " ".join(mapping.get(tok, tok) for tok in value.split())

    def _ref(m: re.Match) -> str:
        name, quote, value = m.group(1), m.group(2), m.group(3)
        if name.lower() in ("aria-labelledby", "aria-describedby"):
            new = _map_tokens(value)
        else:
            new = mapping.get(value.strip(), value)
        return f"{name}={quote}{new}{quote}"

    rest = _REF_ATTR_RE.sub(_ref, rest)
    rest = _HREF_HASH_RE.sub(
        lambda m: f"href={m.group(1)}#{mapping.get(m.group(2), m.group(2))}{m.group(1)}",
        rest,
    )
    local_after = {mapping.get(i, i) for i in counts}
    return root + rest, duplicates, local_after


def _stub_section(screen: Screen, reason: str) -> str:
    summary = (
        _html.escape(screen.summary)
        if screen.summary
        else "See spec.md for this screen."
    )
    return (
        f'<section class="screen stub" id="{screen.id}" data-stub="true">'
        f'<header class="page-header"><h1 class="page-title">{_html.escape(screen.title)}</h1>'
        f'<p class="page-description">Not built in this run</p></header>'
        f'<div class="empty-state"><p><strong>This screen was not built.</strong> {_html.escape(reason)}</p>'
        f'<p class="stub-note">{summary}</p></div></section>'
    )


def _wrap_dialog(screen: Screen, section: str) -> str:
    did = screen.dialog_id
    return (
        f'<div class="dialog" id="{did}" role="dialog" aria-modal="true" aria-labelledby="{did}-title">'
        f'<div class="scrim" data-closes="{did}"></div>'
        f'<div class="dialog-panel">'
        f'<header class="dialog-header"><h2 class="dialog-title" id="{did}-title">{_html.escape(screen.title)}</h2>'
        f'<button type="button" class="btn-close" data-closes="{did}" aria-label="Close">&times;</button></header>'
        f'<div class="dialog-content">{section}</div>'
        f"</div></div>"
    )


def _nav(inv: Inventory, statuses: dict[str, str]) -> str:
    groups: dict[str, list[Screen]] = {}
    for s in inv.pages:
        groups.setdefault(s.nav, []).append(s)
    out: list[str] = []
    for name, screens in groups.items():
        out.append(
            f'<div class="nav-group"><div class="nav-group-title">{_html.escape(name)}</div>'
        )
        for s in screens:
            cls = "nav-link" + (
                " stub-link" if statuses.get(s.id) in ("missing", "invalid") else ""
            )
            out.append(
                f'<a class="{cls}" href="#{s.id}" data-goto="{s.id}">{_html.escape(s.title)}</a>'
            )
        out.append("</div>")
    if inv.dialogs:
        out.append('<div class="nav-group"><div class="nav-group-title">Dialogs</div>')
        for s in inv.dialogs:
            cls = "nav-link" + (
                " stub-link" if statuses.get(s.id) in ("missing", "invalid") else ""
            )
            out.append(
                f'<a class="{cls}" href="#" data-opens="{s.dialog_id}">{_html.escape(s.title)}</a>'
            )
        out.append("</div>")
    return "\n".join(out)


# ── validation ───────────────────────────────────────────────────────────────────


def _validate_screen(
    screen: Screen, section: str, inv: Inventory, local_ids: set[str]
) -> tuple[list[dict], list[str]]:
    """(broken, missing_expected) for one built section."""
    ids = set(inv.by_id())
    dialog_ids = {s.dialog_id for s in inv.dialogs}
    broken: list[dict] = []
    present: set[tuple[str, str]] = set()
    for m in _RUNTIME_ATTR_RE.finditer(section):
        attr, value = m.group(1).lower(), m.group(3).strip()
        present.add((attr, value))
        if attr in ("data-goto", "data-submit"):
            if value not in ids:
                broken.append({"attr": attr, "to": value, "why": "no such screen"})
            elif value in {s.id for s in inv.dialogs}:
                broken.append(
                    {
                        "attr": attr,
                        "to": value,
                        "why": "target is a dialog; use data-opens",
                    }
                )
        elif attr in ("data-opens", "data-closes"):
            if value not in dialog_ids:
                broken.append({"attr": attr, "to": value, "why": "no such dialog"})
        elif attr == "data-tab":
            if value not in local_ids:
                broken.append(
                    {
                        "attr": attr,
                        "to": value,
                        "why": "no panel with that id in this screen",
                    }
                )
        elif attr in ("data-show", "data-hide"):
            if value not in local_ids:
                broken.append(
                    {
                        "attr": attr,
                        "to": value,
                        "why": "no state element with that id in this screen",
                    }
                )
    missing: list[str] = []
    for t in screen.transitions:
        if t.attr == "data-tab":
            want = (t.attr, f"{screen.id}--{t.to}")
            alt = (t.attr, t.to)
            if want not in present and alt not in present:
                missing.append(attribute_string(t))
        else:
            want_attr = attribute_string(t)
            value = want_attr.split("=", 1)[1].strip('"')
            if (t.attr, value) not in present:
                # a page may legitimately use data-submit where the inventory said data-goto
                twin = {"data-goto": "data-submit", "data-submit": "data-goto"}.get(
                    t.attr
                )
                if not (twin and (twin, value) in present):
                    missing.append(want_attr)
    return broken, missing


# ── the step ─────────────────────────────────────────────────────────────────────


def _read_shell() -> str:
    return _SHELL_PATH.read_text(encoding="utf-8")


# ── theme: build/theme.json → :root overrides ────────────────────────────────────
# The Architect maps the attached design system onto the shell's own variables. Code
# accepts ONLY these keys and ONLY well-formed values; anything else is reported in
# validation["theme"] and ignored, so a bad theme can never break the prototype.
THEME_KEYS: dict[str, str] = {
    "primary": "--color-primary",
    "primary_dark": "--color-primary-dark",
    "secondary": "--color-secondary",
    "background": "--color-background",
    "surface": "--color-surface",
    "surface_2": "--color-surface-2",
    "border": "--color-border",
    "text": "--color-text",
    "text_muted": "--color-text-muted",
    "font_family": "--font-family",
    "border_radius": "--border-radius",
}
_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_PX = re.compile(r"^\d{1,2}px$")
_FONT = re.compile(r"^[\w\s,'\"-]{1,160}$")


def load_theme(text: str | None) -> tuple[str, dict]:
    """theme.json text → (css ``:root`` override or "", report). Never raises."""
    if text is None or not text.strip():
        return "", {"status": "default", "applied": [], "rejected": {}}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return "", {
            "status": "invalid",
            "applied": [],
            "rejected": {"_": f"not valid JSON: {exc}"},
        }
    if not isinstance(data, dict):
        return "", {
            "status": "invalid",
            "applied": [],
            "rejected": {"_": "theme.json must be an object"},
        }
    decls: list[str] = []
    applied: list[str] = []
    rejected: dict[str, str] = {}
    for key, value in data.items():
        var = THEME_KEYS.get(key)
        if var is None:
            rejected[key] = "unknown key"
            continue
        v = str(value).strip()
        ok = (
            _FONT.match(v)
            if key == "font_family"
            else _PX.match(v)
            if key == "border_radius"
            else _HEX.match(v)
        )
        if not ok:
            rejected[key] = f"bad value {v[:40]!r}"
            continue
        decls.append(f"{var}:{v}")
        applied.append(key)
    if not decls:
        return "", {
            "status": "invalid" if rejected else "default",
            "applied": [],
            "rejected": rejected,
        }
    return ":root{" + ";".join(decls) + "}", {
        "status": "applied",
        "applied": applied,
        "rejected": rejected,
    }


_NAV_ATTRS = ("data-goto", "data-submit", "data-opens", "data-closes", "data-tab")
_TAG_RE = re.compile(r"<[a-zA-Z][^>]*>")
_STATE_ID_RE = re.compile(
    r"""<[^>]*\bclass\s*=\s*["'][^"']*\bstate\b[^"']*["'][^>]*\bid\s*=\s*["']([^"']+)["']|<[^>]*\bid\s*=\s*["']([^"']+)["'][^>]*\bclass\s*=\s*["'][^"']*\bstate\b[^"']*["']"""
)


def _fix_double_nav_attrs(section: str) -> tuple[str, list[str]]:
    """A control carrying two navigation attributes fires only the first the runtime
    checks, so a tab link with ``data-goto`` is dead. Keep the attribute that moves the
    user (goto/submit/opens/closes), drop ``data-tab``; report every element touched."""
    notes: list[str] = []

    def _one(m: re.Match) -> str:
        tag = m.group(0)
        present = [a for a in _NAV_ATTRS if re.search(rf"\b{a}\s*=", tag)]
        if len(present) < 2:
            return tag
        if "data-tab" in present:
            tag = re.sub(r"""\s+data-tab\s*=\s*(["']).*?\1""", "", tag)
            notes.append(
                f"removed data-tab from a control that also carries {', '.join(a for a in present if a != 'data-tab')}"
            )
        else:
            notes.append(
                f"a control carries {', '.join(present)} at once; only the first fires"
            )
        return tag

    return _TAG_RE.sub(_one, section), notes


def _untriggered_states(section: str) -> list[str]:
    """Ids of ``.state`` elements no ``data-show`` in the section names."""
    states = [a or b for a, b in _STATE_ID_RE.findall(section)]
    shown = {
        m.group(3).strip()
        for m in _RUNTIME_ATTR_RE.finditer(section)
        if m.group(1).lower() == "data-show"
    }
    return [s for s in states if s not in shown]


def assemble(
    inv: Inventory,
    parts: dict[str, str | None],
    *,
    threshold: float = COVERAGE_THRESHOLD,
    theme: str | None = None,
    spec: str = "",
) -> tuple[str, dict]:
    """Pure core: inventory + {screen id: part text or None} (+ theme.json, + spec.md) → (prototype_html, validation)."""
    theme_css, theme_report = load_theme(theme)
    reserved = (
        set(inv.by_id())
        | {s.dialog_id for s in inv.dialogs}
        | {f"{s.dialog_id}-title" for s in inv.dialogs}
    )
    content: list[str] = []
    overlays: list[str] = []
    report: list[dict] = []
    statuses: dict[str, str] = {}
    doc_ids: Counter = Counter()

    for screen in inv.screens:
        issues: list[str] = []
        status = "ok"
        section, notes = extract_section(parts.get(screen.id) or "", screen.id)
        issues += notes
        broken: list[dict] = []
        missing_tr: list[str] = []
        dups: list[str] = []
        expected_fields = spec_fields(spec_section(spec, screen.id)) if spec else []
        found_fields = 0
        untriggered: list[str] = []
        if section is None:
            status = (
                "missing" if not (parts.get(screen.id) or "").strip() else "invalid"
            )
            reason = (
                "No part was written for it."
                if status == "missing"
                else "Its part had no <section> to place."
            )
            section = _stub_section(screen, reason)
        else:
            section, notes = strip_forbidden(section)
            issues += notes
            section, notes = _fix_double_nav_attrs(section)
            issues += notes
            section, dups, local_ids = namespace_ids(section, screen.id, reserved)
            untriggered = _untriggered_states(section)
            if untriggered:
                issues.append(
                    f"{len(untriggered)} state(s) nothing reveals: {', '.join(untriggered)}"
                )
            found_fields = len(
                re.findall(r"""\bclass\s*=\s*["'][^"']*\bform-control\b""", section)
            )
            if expected_fields and found_fields < 0.8 * len(expected_fields):
                issues.append(
                    f"fields: {found_fields} built of {len(expected_fields)} the spec lists"
                )
            if dups:
                issues.append(f"duplicate ids inside the screen: {', '.join(dups)}")
            broken, missing_tr = _validate_screen(screen, section, inv, local_ids)
            if broken:
                issues.append(f"{len(broken)} transition(s) point at nothing")
            if missing_tr:
                issues.append(f"{len(missing_tr)} expected transition(s) not written")
            if (
                broken
                or missing_tr
                or dups
                or untriggered
                or (expected_fields and found_fields < 0.8 * len(expected_fields))
            ):
                status = "degraded"
        for m in _ID_ATTR.finditer(section):
            doc_ids[m.group(2).strip()] += 1
        if screen.is_dialog:
            overlays.append(_wrap_dialog(screen, section))
        else:
            if screen.id == inv.entry:
                cut = section.find(">") + 1
                root = section[:cut]
                root = _set_attr(
                    root,
                    "class",
                    ((_attr(root, "class") or "screen") + " active").strip(),
                )
                section = root + section[cut:]
            content.append(section)
        statuses[screen.id] = status
        report.append(
            {
                "id": screen.id,
                "title": screen.title,
                "kind": screen.kind,
                "status": status,
                "issues": issues,
                "broken_transitions": broken,
                "missing_transitions": missing_tr,
                "duplicate_ids": dups,
                "reqs": screen.reqs,
                "fields": {"expected": len(expected_fields), "found": found_fields},
                "untriggered_states": untriggered,
            }
        )

    totals = Counter(statuses.values())
    total = len(inv.screens)
    built = totals.get("ok", 0) + totals.get("degraded", 0)
    coverage = built / total if total else 0.0
    passed = coverage >= threshold
    missing_ids = [
        s.id for s in inv.screens if statuses[s.id] in ("missing", "invalid")
    ]
    degraded_ids = [s.id for s in inv.screens if statuses[s.id] == "degraded"]
    status_text = (
        f"{built} of {total} screens built"
        + (
            f", {len(missing_ids)} missing: {', '.join(missing_ids)}"
            if missing_ids
            else ""
        )
        + (f", {len(degraded_ids)} with open issues" if degraded_ids else "")
    )

    shell = _read_shell()
    doc = (
        shell.replace("__TITLE__", _html.escape(inv.title))
        .replace("__NAV__", _nav(inv, statuses))
        .replace("__CONTENT__", "\n".join(content))
        .replace("__OVERLAYS__", "\n".join(overlays))
        .replace("__ENTRY__", inv.entry)
        .replace(
            "__STATUS_CLASS__",
            "" if passed and not degraded_ids and not missing_ids else "warn",
        )
        .replace("__STATUS__", _html.escape(status_text))
        .replace("__THEME__", theme_css)
    )

    validation = {
        "version": 1,
        "generated_by": "assemble_prototype",
        "passed": passed,
        "coverage": round(coverage, 3),
        "threshold": threshold,
        "totals": {
            "screens": total,
            "built": built,
            "ok": totals.get("ok", 0),
            "degraded": totals.get("degraded", 0),
            "missing": totals.get("missing", 0),
            "invalid": totals.get("invalid", 0),
        },
        "entry": inv.entry,
        "missing": missing_ids,
        "degraded": degraded_ids,
        "screens": report,
        "document": {
            "duplicate_ids": sorted(i for i, n in doc_ids.items() if n > 1),
            "bytes": len(doc.encode("utf-8")),
        },
        "inventory_notes": inv.notes,
        "theme": theme_report,
        "summary": status_text,
    }
    return doc, validation


def assemble_prototype(ctx: Any) -> str:
    """Engine entry: read from / write to ``ctx.runner.sandbox``; return the reply text."""
    sandbox = ctx.runner.sandbox
    text = sandbox.read(SCREENS_PATH)
    if text is None:
        raise AssembleStepFailed(
            f"assemble_prototype: {SCREENS_PATH} does not exist — the Architect wrote no inventory, nothing to assemble"
        )
    try:
        inv = parse_inventory(text)
    except InventoryError as exc:
        raise AssembleStepFailed(f"assemble_prototype: {exc}") from exc

    parts = {s.id: sandbox.read(f"{PARTS_DIR}/{s.id}.html") for s in inv.screens}
    doc, validation = assemble(
        inv, parts, theme=sandbox.read(THEME_PATH), spec=sandbox.read("spec.md") or ""
    )

    deliverable = getattr(ctx, "deliverable", None)
    name = getattr(deliverable, "name", None) or DEFAULT_DELIVERABLE
    sandbox.write(name, doc)
    sandbox.write(VALIDATION_PATH, json.dumps(validation, indent=2))

    t = validation["totals"]
    summary = (
        f"Assembled {name}: {t['built']}/{t['screens']} screens built "
        f"(coverage {validation['coverage']:.0%}, threshold {COVERAGE_THRESHOLD:.0%}); "
        f"ok {t['ok']}, degraded {t['degraded']}, missing {t['missing']}, invalid {t['invalid']}. "
        f"Details: {VALIDATION_PATH}."
    )
    th = validation["theme"]
    if th["status"] == "applied":
        summary += f" Theme applied from {THEME_PATH}: {', '.join(th['applied'])}."
    if th["rejected"]:
        summary += f" Theme keys ignored: {', '.join(f'{k} ({v})' for k, v in th['rejected'].items())}."
    if validation["missing"]:
        summary += " Missing: " + ", ".join(validation["missing"]) + "."
    if validation["degraded"]:
        summary += " Open issues on: " + ", ".join(validation["degraded"]) + "."
    if not validation["passed"]:
        raise AssembleStepFailed(
            f"Prototype below the coverage threshold — {summary} The files were written; fix the missing screens and rerun the build."
        )
    return summary


@register(
    "mechanical",
    "assemble_prototype",
    user_allowed=True,
    description="Stitches the screen pages the builder agents wrote into one clickable prototype. Pure code, no AI: every screen is included, links between screens work, and a coverage report lists anything missing. Needs an earlier step that lists the screens (build/screens.json) and a builder step that writes one page per screen (parts/).",
)
class _AssembleRegistryStub:
    """Thin stub for registry purposes only (capability palette discovery).

    The actual strategy dispatch uses MechanicalAssembleStrategy per-invocation with
    per-dispatch arguments (spec/index/total/results). This stub is registered for
    the palette and describes the capability; it is never executed.
    """

    name = "assemble_prototype"


class MechanicalAssembleStrategy:
    """``strategy``-shaped adapter for ``mechanical: assemble_prototype`` (see publish_step)."""

    name = "assemble_prototype"

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
        try:
            content = assemble_prototype(ctx)
        except AssembleStepFailed as exc:
            yield {
                "type": "agent_error",
                "data": {"agent_id": spec.id, "error": str(exc), "recoverable": False},
            }
            raise
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
