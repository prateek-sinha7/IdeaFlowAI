"""agents/capabilities/task_parsers/screen_plan.py — ``screen_plan`` TaskParser.

Expands the Architect's ``build/screens.json`` (``screen_inventory``) into ONE builder
task per screen. No model writes the plan: the task count, the targets, the exact
transition attribute strings and the acceptance list are all derived by code, so none
of them can be dropped, miscounted or mistyped (ERROR-REASONS.md C6, C7).

Each task body is self-sufficient. It carries the fixed part contract, the screen's
row from the inventory, the exact ``attr="value"`` strings to write, the screen's own
section of ``spec.md`` verbatim, and the EARS requirement lines it serves — so a
builder never has to open another file to know what to build.

Every task targets a distinct ``parts/<id>.html`` and depends on nothing, so the wave
scheduler runs the whole plan as one wave.

Pure stdlib; imports only ``agents.workflows.plan`` (typed data) and the sibling
``screen_inventory`` module (import-linter).
"""

from __future__ import annotations

import json
import re
from typing import Any, Sequence

from agents.capabilities.registry import register
from agents.capabilities.template_kit import (
    RUNTIME_CLASSES,
    TemplateKit,
    load_template_kit,
)
from agents.capabilities.screen_inventory import (
    COMPONENT_CLASSES,
    Inventory,
    InventoryError,
    Screen,
    apply_flow_backstop,
    attribute_string,
    parse_inventory,
    spec_fields,
    spec_section,
)
from agents.workflows.plan import Task

DEFAULT_TARGET = "build/screens.json"
SPEC_PATH = "spec.md"

_REQ_LINE = re.compile(r"^(REQ-\d+)\s*\|", re.MULTILINE)


_spec_section = spec_section  # kept for callers/tests that import the private name


def _req_lines(spec: str, screen: Screen) -> list[str]:
    if not spec:
        return []
    wanted = set(screen.reqs)
    out: list[str] = []
    for line in spec.splitlines():
        m = _REQ_LINE.match(line)
        if not m:
            continue
        rid = m.group(1)
        screens_field = re.search(r"screens:\s*([^|]*)", line)
        named = (
            {s.strip() for s in screens_field.group(1).split(",")}
            if screens_field
            else set()
        )
        if rid in wanted or screen.id in named:
            out.append(line.strip())
    return out


def _template_rules(screen: Screen, kit: TemplateKit) -> str:
    """The look rules when a design template is attached: the template decides, and
    only the hooks the runtime needs are fixed. Replaces the shell's class rules."""
    files = " and ".join(f"`{p}`" for p in reversed(kit.paths))
    classes = ", ".join(c for c in kit.classes if c not in RUNTIME_CLASSES)
    return (
        f"- The DESIGN TEMPLATE decides how this screen looks. Before writing, read_file {files}, each to its end. "
        "Find the part that is the same kind of screen as this one — a list or register, a record detail, a form, "
        "a wizard step, a dashboard — and build this screen with the same markup and the same classes.\n"
        f"- Use the template's classes: {classes}. Colours, fonts and sizes come from those classes and the design "
        "system, which code applies to them: never write a colour, a font or a size yourself.\n"
        "- Keep the hooks the prototype's runtime needs, whatever the template calls things: the root "
        f'`<section class="screen" id="{screen.id}">`; tabs as `<div class="tabs"><nav class="tabs-nav">'
        '<a class="tab-link active" data-tab="PANEL">Tab</a>...</nav><div class="tabs-content">'
        '<div class="tab-panel active" id="PANEL">...</div>...</div></div>` with the template\'s own tab classes '
        "added beside those; states as elements with class `state` (below). The first tab link and panel carry "
        "`active`; every panel holds its real content.\n"
        "- Every field is a real `<input>`, `<select>` or `<textarea>` with the template's field class and a "
        "`<label for=...>`. Ids are local to this screen; the assembler prefixes them, so keep them short.\n"
        "- A control with no transition listed below and no state to show does nothing, and carries no "
        '`href="#"`, no `onclick`, no data-* attribute.\n'
    )


def render_body(
    screen: Screen, inv: Inventory, spec: str, kit: TemplateKit | None = None
) -> str:
    attrs = [attribute_string(t) for t in screen.transitions]
    transitions = (
        "\n".join(
            f"- {t.label}: write `{attribute_string(t)}` on that control"
            + (
                "  (this moves to another screen)"
                if t.attr in ("data-goto", "data-submit")
                else "  (opens a dialog)"
                if t.attr == "data-opens"
                else "  (closes this dialog)"
                if t.attr == "data-closes"
                else "  (switches a tab panel inside this screen)"
            )
            for t in screen.transitions
        )
        or "- none. No control on this screen moves the user anywhere."
    )
    section = _spec_section(spec, screen.id)
    spec_block = (
        section
        or f"(spec.md has no `### {screen.id}` section; build from the summary: {screen.summary or screen.title})"
    )
    n_fields = len(spec_fields(section))
    reqs = "\n".join(_req_lines(spec, screen)) or "(none listed)"
    kind_rules = (
        "- This screen is a DIALOG. The shell draws the frame, the title bar and the close button around your section. "
        "Write only the dialog's content: no page-header, no close button of your own, no scrim.\n"
        if screen.is_dialog
        else f'- Start the section with `<header class="page-header"><h1 class="page-title">{screen.title}</h1></header>`.\n'
        if kit is None
        else f"- Start the section with the page heading the template uses, titled `{screen.title}`.\n"
    )
    classes = ", ".join(COMPONENT_CLASSES)
    supplier = (
        "The shell supplies"
        if kit is None
        else "The template's CSS and the shell's runtime supply"
    )
    required_rule = (
        '- A field the SPEC marks required, or that a requirement says is highlighted as required, gets `class="form-control required"`; the shell paints it yellow.'
        if kit is None
        else "- A field the SPEC marks required, or that a requirement says is highlighted as required, "
        "gets the class `required` beside the template's field class."
    )
    look_rules = (
        _template_rules(screen, kit)
        if kit is not None
        else (
            f"- Use ONLY these classes (the shell styles exactly these): {classes}.\n"
            '- Form fields: `<div class="form-row"><label class="form-label" for="ID">Label</label><input class="form-control" id="ID" ...></div>`. Ids are local to this screen; the assembler prefixes them, so keep them short.\n'
            '- Tables: `<div class="table-wrap"><table class="table"><thead class="table-head"><tr><th class="table-header">Col</th></tr></thead><tbody class="table-body"><tr class="table-row"><td class="table-cell">Value</td></tr></tbody></table></div>`, with the example rows the SPEC gives.\n'
            '- Tabs inside this screen: `<div class="tabs"><nav class="tabs-nav"><a class="tab-link active" data-tab="PANEL">Tab</a>...</nav><div class="tabs-content"><div class="tab-panel active" id="PANEL">...</div>...</div></div>`. The first link and the first panel both carry `active`. Every panel holds its real content; an empty panel is a defect.\n'
            '- Buttons and links: `<button type="button" class="btn btn-primary">Label</button>`. A control with no transition listed below and no state to show does nothing, and carries no `href="#"`, no `onclick`, no data-* attribute.\n'
        )
    )
    done = "\n".join(
        [
            f'- `parts/{screen.id}.html` exists and its only root element is `<section class="screen" id="{screen.id}">`',
            "- every field, action, table column and state listed in the SPEC below is present, with the real values the spec shows",
            *[
                f"- the exact string `{a}` appears on exactly one control"
                for a in attrs
            ],
            "- no `<script>`, `<style>`, `<link>`, `<html>`, `<head>` or `<body>` anywhere in the file",
            "- every `<label for=...>` matches an `id` in this file; no id is used twice in this file",
            "- every `data-show`/`data-hide` value is the id of an element with class `state` in this file, and every state the SPEC describes has one",
            "- every element with class `state` is named by a `data-show` on a control in this file; a state nothing reveals is a defect",
            "- no element carries two of data-goto / data-submit / data-opens / data-closes / data-tab; a tab link never carries data-goto",
            *(
                [
                    f'- at least {n_fields} form controls (`class="form-control"`) are present: the SPEC lists {n_fields} fields, and code counts them'
                ]
                if n_fields and kit is None
                else [
                    f"- at least {n_fields} fields (`<input>`, `<select>` or `<textarea>`) are present: the SPEC lists {n_fields} fields, and code counts them"
                ]
                if n_fields
                else []
            ),
            "- every control marked `[not evidenced]` in the SPEC is rendered disabled; every icon-only control has visible content and an aria-label",
            "- the reply is ONE line: the path written, then anything in the SPEC you could not build",
        ]
    )
    return f"""CURRENT TASK: screen-{screen.id}

Build ONE screen of the prototype as an HTML FRAGMENT and write it to `parts/{screen.id}.html`.

Screen: {screen.title}
id: {screen.id}    kind: {screen.kind}    nav group: {screen.nav}
Serves: {", ".join(screen.reqs) or "see SPEC"}
Summary: {screen.summary or "(see SPEC)"}

THE PART CONTRACT
- Exactly one root element: `<section class="screen" id="{screen.id}">` ... `</section>`. Nothing outside it.
- No `<!DOCTYPE>`, `<html>`, `<head>`, `<body>`, `<script>`, `<style>`, `<link>`. {supplier} every style and all behaviour; anything you add here is removed by the assembler.
{kind_rules}- Build EVERY field, action, table column and state the SPEC lists, with the real example values it shows. Never lorem ipsum, never "example value", never a placeholder sentence in place of content.
- A control the SPEC marks `[not evidenced]` is rendered, disabled, with `title="Not evidenced in the source documents"`.
{look_rules}- STATES the SPEC lists for this screen (a confirmation, an error message, a success banner, an expanded row, a highlighted selection) are built as elements with class `state`, hidden at rest: `<div class="state" id="confirm-finalize">...</div>`. The control that triggers the state carries `data-show="confirm-finalize"`; a control inside it that dismisses carries `data-hide="confirm-finalize"`. Every state the SPEC describes gets one. These two attributes are only ever used for states on THIS screen.
{required_rule}
- An icon-only control (folder, clone, print, close, edit...) has visible content — text or a Unicode glyph such as ⎘ 🖨 ✎ ✕ — AND an `aria-label` and `title` naming the action. A button with nothing visible inside it is a defect.

TRANSITIONS — write these EXACT attribute strings on the control the SPEC names. The attribute IS the behaviour; the shell's runtime handles every one of them.
{transitions}
Do not invent transitions that are not listed. Do not change the attribute name or its value.

SPEC (verbatim from spec.md — this is what you build)
{spec_block}

REQUIREMENTS this screen serves (EARS)
{reqs}

Write: parts/{screen.id}.html
Done when:
{done}
"""


def build_tasks(
    inv: Inventory, spec: str = "", kit: TemplateKit | None = None
) -> list[Task]:
    tasks: list[Task] = []
    for screen in inv.screens:
        attrs = [attribute_string(t) for t in screen.transitions]
        tasks.append(
            Task(
                id=f"screen-{screen.id}",
                title=f"Build {screen.title} ({screen.kind})",
                body=render_body(screen, inv, spec, kit),
                targets=[f"parts/{screen.id}.html"],
                depends_on=[],
                conflict_keys=[f"parts/{screen.id}.html"],
                done_when=[f"section.screen#{screen.id}", *attrs],
            )
        )
    return tasks


@register(
    "task_parser",
    "screen_plan",
    user_allowed=True,
    description="Reads the screen list an earlier step produced and creates exactly one build task per screen. No AI decides the list, so no screen is skipped or counted twice. Each task already carries that screen's spec and the exact links to write.",
    config_schema={
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "The file this parser reads the screen list from.",
                "default": DEFAULT_TARGET,
            },
        },
    },
)
class ScreenPlanParser:
    """``screens.json`` → one ``Task`` per screen. Satisfies the ``TaskParser`` port."""

    name = "screen_plan"

    def parse(self, text: str) -> list[Task]:
        """From the inventory text alone (no spec.md available): bodies carry the
        inventory row and the transitions, and say the spec section is missing."""
        try:
            inv = parse_inventory(text)
        except InventoryError as exc:
            raise ValueError(f"screen_plan: {exc}") from exc
        return build_tasks(inv, "")

    def parse_preferring_target(
        self,
        reply_text: str,
        *,
        sandbox: Any = None,
        target: str | None = None,
        fallback_targets: Sequence[str] = (DEFAULT_TARGET,),
    ) -> list[Task]:
        """Prefer the file on disk (``build/screens.json``) over the Architect's reply,
        and inline ``spec.md`` into every task body when it is present."""
        text: str | None = None
        errors: list[str] = []
        if sandbox is not None:
            for path in [target, *fallback_targets]:
                if not path:
                    continue
                try:
                    candidate = sandbox.read(path)
                except Exception as exc:  # noqa: BLE001 — a bad path is a diagnosis, not a crash
                    errors.append(f"{path}: {exc}")
                    continue
                if candidate and candidate.strip():
                    text = candidate
                    break
                errors.append(f"{path}: absent or empty")
        if text is None:
            if reply_text and reply_text.strip():
                text = reply_text
            else:
                raise ValueError(
                    "screen_plan: no inventory to plan from — "
                    + "; ".join(errors or ["no sandbox and an empty reply"])
                )
        try:
            inv = parse_inventory(text)
        except InventoryError as exc:
            raise ValueError(f"screen_plan: {exc}") from exc
        spec = ""
        if sandbox is not None:
            try:
                spec = sandbox.read(SPEC_PATH) or ""
            except Exception:  # noqa: BLE001 — the spec is an enrichment, not a requirement
                spec = ""
        if spec:
            # Code-owned safety net: a flow the spec describes always has its control,
            # whatever the Architect wrote. The added transitions are recorded in the
            # inventory notes and written back so the assembler validates the same list.
            added = apply_flow_backstop(inv, spec)
            if added and sandbox is not None and text is not None:
                try:
                    data = json.loads(text)
                    by = {
                        s["id"]: s
                        for s in data.get("screens", [])
                        if isinstance(s, dict)
                    }
                    for scr in inv.screens:
                        if scr.id not in by:
                            continue
                        # keep any extra keys the Architect put on an existing transition
                        orig = {
                            (t.get("label"), t.get("attr"), t.get("to")): t
                            for t in by[scr.id].get("transitions") or []
                            if isinstance(t, dict)
                        }
                        by[scr.id]["transitions"] = [
                            {
                                **orig.get((t.label, t.attr, t.to), {}),
                                "label": t.label,
                                "attr": t.attr,
                                "to": t.to,
                            }
                            for t in scr.transitions
                        ]
                    data.setdefault("notes", [])
                    data["notes"] = list(data["notes"]) + added
                    sandbox.write(target or DEFAULT_TARGET, json.dumps(data, indent=2))
                except Exception:  # noqa: BLE001 — writing back is best effort; the tasks already carry the moves
                    pass
        # The design template, when the launch seeded one: its classes and files replace
        # the shell's vocabulary in every task (template_kit).
        kit = load_template_kit(sandbox.read) if sandbox is not None else None
        return build_tasks(inv, spec, kit)
