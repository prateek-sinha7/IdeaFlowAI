"""agents/capabilities/screen_inventory.py — the ``build/screens.json`` contract.

One small structured file is the ONLY thing the Architect writes, and two pieces of
code read it: the ``screen_plan`` task parser (one builder task per screen) and the
``assemble_prototype`` mechanical step (shell + parts → prototype.html). Both read it
through this module so there is exactly one definition of a screen, a transition and
the attribute string a builder is told to write.

Lenient on purpose (STABILIZATION: degrade, do not die). Anything that can be
defaulted is defaulted and recorded in ``Inventory.notes``; the parse raises only
when there is nothing to build from: not JSON, no ``screens`` list, a screen without
an ``id``, or two screens with the same id.

Shape::

    {
      "title": "Inland Marine Quote System",
      "entry": "search",
      "screens": [
        {"id": "search", "title": "Search", "kind": "page", "nav": "Quote",
         "reqs": ["REQ-035"], "summary": "…",
         "transitions": [{"label": "Search", "attr": "data-goto", "to": "directory"}]}
      ]
    }

``kind`` is ``page`` or ``dialog``. ``attr`` is one of the five runtime attributes;
``to`` is a screen id (``data-goto`` / ``data-submit`` / ``data-opens`` /
``data-closes``) or a panel slug local to the screen (``data-tab``).

Pure stdlib; imports nothing from the kernel or the web layer (import-linter).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

VALID_ATTRS: frozenset[str] = frozenset(
    {"data-goto", "data-submit", "data-opens", "data-closes", "data-tab"}
)

# The class vocabulary the fixed shell (assemble_shell.html) styles. A builder is
# handed this list and told to use nothing else; the shell is the only stylesheet.
COMPONENT_CLASSES: tuple[str, ...] = (
    "page-header",
    "page-title",
    "page-description",
    "section-title",
    "section-content",
    "toolbar",
    "card",
    "form",
    "form-fieldset",
    "form-legend",
    "form-row",
    "form-row-group",
    "form-label",
    "form-control",
    "form-control-group",
    "form-hint",
    "form-actions",
    "required-indicator",
    "radio-group",
    "radio-label",
    "checkbox-group",
    "checkbox-label",
    "btn",
    "btn-primary",
    "btn-secondary",
    "btn-link",
    "btn-icon",
    "table",
    "table-wrap",
    "table-head",
    "table-header",
    "table-body",
    "table-row",
    "table-cell",
    "selected",
    "tabs",
    "tabs-nav",
    "tab-link",
    "tabs-content",
    "tab-panel",
    "active",
    "badge",
    "empty-state",
    "menu",
    "menu-item",
    "status-ok",
    "status-error",
    "status-warning",
)
_DIALOG_KINDS = {"dialog", "overlay", "modal", "popup", "drawer"}
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class InventoryError(ValueError):
    """``screens.json`` cannot be built from. The message names exactly what is wrong."""


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(text).strip().lower()).strip("-")
    return s or "screen"


@dataclass
class Transition:
    label: str
    attr: str
    to: str


@dataclass
class Screen:
    id: str
    title: str
    kind: str = "page"  # "page" | "dialog"
    nav: str = "Screens"
    reqs: list[str] = field(default_factory=list)
    summary: str = ""
    transitions: list[Transition] = field(default_factory=list)
    # The menu section a page belongs to ("" = none given: the flat menu of before),
    # "_auth" for sign-in / register / setup pages that are never in the menu, and the
    # page's label in its section's tab strip ("" = its title).
    section: str = ""
    tab: str = ""

    @property
    def is_dialog(self) -> bool:
        return self.kind == "dialog"

    @property
    def dialog_id(self) -> str:
        return f"dialog-{self.id}"


@dataclass
class Inventory:
    title: str
    entry: str
    screens: list[Screen]
    notes: list[str] = field(default_factory=list)  # every default the parser applied

    def by_id(self) -> dict[str, Screen]:
        return {s.id: s for s in self.screens}

    @property
    def pages(self) -> list[Screen]:
        return [s for s in self.screens if not s.is_dialog]

    @property
    def dialogs(self) -> list[Screen]:
        return [s for s in self.screens if s.is_dialog]


def attribute_string(t: Transition) -> str:
    """The exact ``attr="value"`` a builder writes for this transition.

    ``data-opens`` / ``data-closes`` point at the dialog WRAPPER id (``dialog-<id>``),
    which the assembler creates — the builder never writes the wrapper. ``data-tab``
    points at a panel id local to the screen; the assembler namespaces it later.
    """
    if t.attr in ("data-opens", "data-closes"):
        to = t.to if t.to.startswith("dialog-") else f"dialog-{t.to}"
        return f'{t.attr}="{to}"'
    return f'{t.attr}="{t.to}"'


def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("{") or text.startswith("["):
        return text
    for m in _FENCE_RE.finditer(text):
        body = m.group(1).strip()
        if body.startswith("{"):
            return body
    return text


def parse_inventory(text: str) -> Inventory:
    """Parse the Architect's ``screens.json`` text into an ``Inventory``."""
    if not isinstance(text, str) or not text.strip():
        raise InventoryError("build/screens.json is empty")
    try:
        raw = json.loads(_strip_fence(text))
    except json.JSONDecodeError as exc:
        raise InventoryError(
            f"build/screens.json is not valid JSON: {exc.msg} at line {exc.lineno} column {exc.colno}"
        ) from exc

    notes: list[str] = []
    if isinstance(raw, list):
        raw = {"screens": raw}
        notes.append("top-level array wrapped as {screens: [...]}")
    if not isinstance(raw, dict):
        raise InventoryError(
            "build/screens.json must be a JSON object with a 'screens' list"
        )
    screens_raw = raw.get("screens")
    if not isinstance(screens_raw, list) or not screens_raw:
        raise InventoryError("build/screens.json has no 'screens' list, or it is empty")

    screens: list[Screen] = []
    seen: set[str] = set()
    for i, entry in enumerate(screens_raw):
        if not isinstance(entry, dict):
            raise InventoryError(f"screens[{i}] is not an object")
        sid = entry.get("id")
        if not isinstance(sid, str) or not sid.strip():
            raise InventoryError(f"screens[{i}] has no 'id'")
        norm = slug(sid)
        if norm != sid:
            notes.append(f"screen id {sid!r} normalised to {norm!r}")
        if norm in seen:
            raise InventoryError(f"duplicate screen id {norm!r}")
        seen.add(norm)

        title = entry.get("title") or entry.get("name")
        if not isinstance(title, str) or not title.strip():
            title = norm.replace("-", " ").title()
            notes.append(f"{norm}: title defaulted to {title!r}")
        kind = str(entry.get("kind") or "").strip().lower()
        if kind in _DIALOG_KINDS:
            kind = "dialog"
        elif kind == "page":
            pass
        else:
            kind = (
                "dialog"
                if norm.endswith("-dialog") or norm.endswith("-modal")
                else "page"
            )
            if entry.get("kind"):
                notes.append(
                    f"{norm}: unknown kind {entry.get('kind')!r} treated as {kind!r}"
                )
        nav = entry.get("nav") or entry.get("group") or entry.get("flow") or "Screens"
        reqs = entry.get("reqs") or entry.get("requirements") or []
        if isinstance(reqs, str):
            reqs = [r.strip() for r in re.split(r"[,\s]+", reqs) if r.strip()]
        reqs = [str(r).strip() for r in reqs if str(r).strip()]
        summary = str(entry.get("summary") or entry.get("description") or "").strip()
        screens.append(
            Screen(
                id=norm,
                title=title.strip(),
                kind=kind,
                nav=str(nav).strip(),
                reqs=reqs,
                summary=summary,
                section=str(entry.get("section") or "").strip(),
                tab=str(entry.get("tab") or "").strip(),
            )
        )

    ids = {s.id for s in screens}
    dialog_ids = {s.id for s in screens if s.is_dialog}
    for s, entry in zip(screens, screens_raw, strict=False):
        for j, t in enumerate(entry.get("transitions") or []):
            if not isinstance(t, dict):
                notes.append(f"{s.id}: transitions[{j}] is not an object, dropped")
                continue
            to = t.get("to") or t.get("target") or t.get("screen")
            if not isinstance(to, str) or not to.strip():
                notes.append(f"{s.id}: transitions[{j}] has no 'to', dropped")
                continue
            to = to.strip()
            attr = str(t.get("attr") or t.get("attribute") or "").strip().lower()
            if attr.startswith("data-") is False and attr:
                attr = f"data-{attr}"
            to_slug = slug(to[len("dialog-") :] if to.startswith("dialog-") else to)
            if attr not in VALID_ATTRS:
                # Infer from the target: a dialog is opened, a self-reference is a tab,
                # anything else moves the user.
                if to_slug in dialog_ids and to_slug != s.id:
                    attr = "data-opens"
                elif to_slug == s.id and not s.is_dialog:
                    attr = "data-tab"
                else:
                    attr = "data-goto"
                notes.append(
                    f"{s.id}: transition to {to!r} had attr {t.get('attr')!r}, using {attr}"
                )
            if attr == "data-tab":
                target = slug(to)
            elif attr in ("data-opens", "data-closes"):
                target = to_slug
                if target not in dialog_ids:
                    notes.append(
                        f"{s.id}: {attr} targets {target!r} which is not a dialog screen"
                    )
            else:
                target = to_slug
                if target not in ids:
                    notes.append(f"{s.id}: {attr} targets unknown screen {target!r}")
                elif target in dialog_ids:
                    attr = "data-opens"
                    notes.append(
                        f"{s.id}: goto to dialog {target!r} changed to data-opens"
                    )
            label = str(
                t.get("label") or t.get("control") or target.replace("-", " ").title()
            ).strip()
            s.transitions.append(Transition(label=label, attr=attr, to=target))
        if s.is_dialog and not any(t.attr == "data-closes" for t in s.transitions):
            s.transitions.append(Transition(label="Close", attr="data-closes", to=s.id))
            notes.append(f"{s.id}: dialog had no close transition, one added")

    title = raw.get("title") or raw.get("app") or "Prototype"
    if isinstance(title, dict):
        title = title.get("title") or title.get("name") or "Prototype"
    entry = raw.get("entry") or raw.get("entry_screen")
    pages = [s for s in screens if not s.is_dialog]
    if not isinstance(entry, str) or slug(entry) not in ids:
        fallback = (pages[0] if pages else screens[0]).id
        if entry:
            notes.append(f"entry {entry!r} is not a screen, using {fallback!r}")
        entry = fallback
    else:
        entry = slug(entry)
    return Inventory(
        title=str(title).strip(), entry=entry, screens=screens, notes=notes
    )


# ── spec.md helpers (shared by screen_plan and the assembler) ────────────────────


def spec_section(spec: str, sid: str) -> str:
    """The ``### <sid> — <Name>`` block of spec.md, up to the next ``###``/``##`` heading."""
    if not spec:
        return ""
    m = re.search(rf"^###\s+{re.escape(sid)}\b.*$", spec, re.MULTILINE)
    if not m:
        return ""
    rest = spec[m.start() :]
    nxt = re.search(r"^#{2,3}\s", rest[m.end() - m.start() :], re.MULTILINE)
    return rest[: (m.end() - m.start()) + nxt.start()].strip() if nxt else rest.strip()


_FIELDS_HEAD = re.compile(
    r"^\s*(?:-\s*)?\**Fields\**:?\**\s*$|^\s*-\s*Fields:\s*$", re.MULTILINE
)


def spec_fields(section: str) -> list[str]:
    """The field labels a screen's spec section lists, in either format the Analyst
    has used: a table (``| Field | Control | ... |``, header and rule rows skipped) or
    indented bullets (``  - Label [control: value]``). Empty when the section has none."""
    if not section:
        return []
    lines = section.splitlines()
    start = next((i for i, l in enumerate(lines) if _FIELDS_HEAD.match(l)), None)
    if start is None:
        return []
    out: list[str] = []
    for line in lines[start + 1 :]:
        t = line.strip()
        if not t:
            continue  # blank lines separate sub-sections and tables inside one Fields block
        if t.startswith("#") or re.match(r"^-\s*[A-Z][A-Za-z ]{1,30}:", t):
            break  # next heading, or the next `- Actions:` / `- States:` / `- Data:` bullet
        if t.startswith("|"):
            cells = [c.strip() for c in t.strip("|").split("|")]
            if (
                not cells
                or set(cells[0]) <= set("-: ")
                or cells[0].lower() in ("field", "field label", "label")
            ):
                continue
            out.append(cells[0].strip("*` "))
        elif t.startswith("**") and t.endswith("**"):
            continue  # a sub-section title such as **Basic Information Section:**
        elif line.startswith((" ", "\t")) and t.startswith(("-", "*")):
            out.append(t.lstrip("-* ").split("[", 1)[0].strip())
        elif t.startswith(("-", "*")):
            out.append(t.lstrip("-* ").split("[", 1)[0].strip())
    return [f for f in out if f]


_ID = r"(?:`|\*\*)(?P<{name}>[a-z0-9][a-z0-9-]*)(?:`|\*\*)"
_FLOW_MOVE = re.compile(
    _ID.format(name="src")
    + r"[^\n]*?(?:lands on|returns to|→)\s*"
    + _ID.format(name="dst"),
)
_FLOW_LABEL = re.compile(
    r"(?:clicks|selects|opens|presses|chooses)\s+(?:the\s+)?([A-Z][^→`,;.]{1,40}?)\s*(?:→|,|\.|link|button|icon|tab)"
)


_NAV_HEADS = (
    "navigates to",
    "navigate to",
    "goes to",
    "destination",
    "target screen",
    "target",
)


def _section_of(spec: str, heading: str) -> str:
    """The body of a ``## <heading>`` section, up to the next ``## ``; empty when absent."""
    if f"## {heading}" not in spec:
        return ""
    return re.split(
        r"^## ", spec.split(f"## {heading}", 1)[1], maxsplit=1, flags=re.MULTILINE
    )[0]


def _action_table_moves(spec: str) -> list[tuple[str, str, str]]:
    """Moves the Analyst records per screen: under ``## Screens``, each ``### <id>``
    section's Actions table has a ``Navigates to`` column naming the destination; the
    Control cell is the label. ``stays``, dashes and ``[not evidenced]`` are not moves."""
    moves: list[tuple[str, str, str]] = []
    cur: str | None = None
    col: int | None = None
    for line in _section_of(spec, "Screens").splitlines():
        head = re.match(r"^###\s+[`*]*([a-z0-9][a-z0-9-]*)", line)
        if head:
            cur, col = head.group(1), None
            continue
        t = line.strip()
        if not t.startswith("|"):
            col = None  # a table ends at its first non-table line
            continue
        cells = [c.strip() for c in t.strip("|").split("|")]
        if (
            col is None
        ):  # header row: find the destination column, if this table has one
            col = next(
                (
                    i
                    for i, c in enumerate(cells)
                    if c.strip("*` ").lower() in _NAV_HEADS
                ),
                None,
            )
            if col is None:
                col = -1  # a table without a destination column (Fields): skip its rows
            continue
        if (
            col < 0
            or cur is None
            or len(cells) <= col
            or set("".join(cells)) <= set("-: ")
        ):
            continue
        dst = cells[col].strip("*` ")
        if re.fullmatch(r"[a-z0-9][a-z0-9-]*", dst) and dst not in (cur, "stays"):
            moves.append((cur, dst, cells[0].strip("*` ")))
    return moves


def flow_moves(spec: str) -> list[tuple[str, str, str]]:
    """Every move the spec names → [(source id, destination id, control label or "")].
    Two sources, both as the Analyst writes them: the ``## Flows`` prose, where a line
    names both ends in backticks or bold, and each screen's Actions table under
    ``## Screens``, where the ``Navigates to`` cell names the destination."""
    if not spec:
        return []
    moves: list[tuple[str, str, str]] = []
    for line in _section_of(spec, "Flows").splitlines():
        for m in _FLOW_MOVE.finditer(line):
            src, dst = m.group("src"), m.group("dst")
            if src == dst:
                continue
            lab = _FLOW_LABEL.search(line)
            moves.append((src, dst, lab.group(1).strip() if lab else ""))
    moves.extend(_action_table_moves(spec))
    return moves


def apply_flow_backstop(inv: Inventory, spec: str) -> list[str]:
    """Add a transition for every ``## Flows`` move the Architect left out, so a flow
    the spec describes can never be un-walkable. A page→page move becomes
    ``data-goto``, a page→dialog move ``data-opens``; a move OUT of a dialog is its
    ``data-closes`` (already guaranteed by the parser) and is left alone. Returns the
    notes describing what was added; they are appended to ``inv.notes`` as well."""
    by = inv.by_id()
    notes: list[str] = []
    for src_id, dst_id, label in flow_moves(spec):
        src, dst = by.get(src_id), by.get(dst_id)
        if src is None or dst is None or src.is_dialog:
            continue
        if any(
            t.to == dst_id and t.attr in ("data-goto", "data-submit", "data-opens")
            for t in src.transitions
        ):
            continue
        attr = "data-opens" if dst.is_dialog else "data-goto"
        if not label:
            label = f"Continue to {dst.title}"
        src.transitions.append(Transition(label=label, attr=attr, to=dst_id))
        notes.append(
            f"flow backstop: added {attr}=\"{dst_id}\" ('{label}') on {src_id} — the flow names the move, the inventory did not"
        )
    inv.notes.extend(notes)
    return notes
