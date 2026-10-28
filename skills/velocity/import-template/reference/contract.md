# Template contract (what VelocityAI reads)

All paths are repo-relative. A template folder is `skills/opendesign/design-templates/<id>/`.
The loader is `backend/app/services/od_loader.py`. It is cached for the process
lifetime (`:181`), so a backend restart is needed after any change.

## Files

| File | Status | What reads it | If missing |
|---|---|---|---|
| folder name | required | it is the template id (`od_loader.py:171`) | n/a |
| `SKILL.md` | required | catalog gate. The body is injected as ACTIVE TEMPLATE and seeded to `.context/design/template/SKILL.md` (`od_context_sandbox.py:73-75`) | the folder is skipped |
| `example.html` | required for the gallery | gallery card, preview route, TEMPLATE EXAMPLE prompt block (`opendesign.py:140-154`), `template_kit` frame (`template_kit.py:28,395-445`) | hidden from both galleries (`TemplateGallery.tsx:59`, `PPTTemplateGallery.tsx:58`) |
| `assets/*` | optional | seeded to runs. For prototypes it is also served at `/api/prototype/templates/<id>/assets/<path>` (`prototype_templates.py:170-190`) | nothing |
| `assets/template.html` | optional seed | read by `template_kit` before `example.html` | nothing |
| `references/*.md` | optional | seeded to runs. The legacy path also injects them (4,000 chars each) | nothing |
| `thumbnail.jpg` | build artifact | generated at image build (`Dockerfile:308`) and gitignored | live iframe fallback |
| `template.json`, `LICENSE`, `README*`, `scripts/` | not read by the app | — | — |

Seeding copies only `example.html`, `template.json` and the folders `assets`,
`references`, `templates`, `palettes` and `examples`. Only these extensions are
copied: `.html .htm .css .js .md .json .svg .txt` (`od_loader.py:296-330`).

## SKILL.md frontmatter

| Field | Read | Values |
|---|---|---|
| `name` | gallery title. For decks it also decides the tab | Title Case display name |
| `description` | card blurb and search | block scalar is fine |
| `triggers` | gallery search | list of 5-10 phrases |
| `od.mode` | gallery membership (`od_loader.py:198-219`) | `prototype` or `deck` |
| `od.shape` | not read by the app. Read by `validate_template.py` and `preview_check.cjs` | `thin` = frame plus one finished screen (prototype only, standard in `TEMPLATE-DESIGN.md` §9); omit for full templates |
| `od.platform` | badge (`TemplateCard.tsx:153`) | `desktop` / `mobile` |
| `od.scenario` | prototype tab (`TemplateGallery.tsx:24-32`) | `operations product engineering design marketing finance hr` |
| `od.preview` | not read (always `example.html`) | `{type: html, entry: example.html}` |
| `od.design_system.requires` | deck: shows the design-system picker. Prototype: always needs one (`od_context.py:197, 299`) | `true` (recommended) |
| `od.design_system.sections` | not read | `[color, typography, layout, components]` |
| `od.craft.requires` | prototype legacy path only; unknown names silently dropped | stems of `skills/opendesign/craft/*.md` |
| `od.example_prompt` | prefills the brief (`LaunchWizard.tsx:768`) | one sentence |
| `od.inputs` | detail payload | list of what the user must supply |
| `od.outputs.primary` | detail payload | `prototype.html` / `presentation.html` |

## Prototype example.html

- **Frame** (`template_kit._find_frame`, `template_kit.py:195-256`):
  - A content element: `<main>`, or a class in `main main-content content app-main workspace page-content`.
  - At least two nav items BEFORE the content element, with a class in `nav-item nav-link menu-item sidebar-item side-item nav-btn navlink`.
  - An active class from `is-active active current is-current selected on` on one item.
- **Frame neutralising**: the frame keeps its CSS. Its `id`, `data-*` and `on*` attributes and its scripts are stripped (`template_kit.py:259-267, 429`). The assembled prototype rebuilds nav items with `data-goto`. Scripts in `example.html` therefore only drive the gallery preview.
- **Theme**: the design system overrides only variables the template declares (`assemble_step.py:813-910`, `TEMPLATE_THEME_VARS`).
  - Declare at least `--bg --surface --fg --muted --border --accent`.
  - Also declare `--accent-on --font-body --font-display --radius` where the design uses them.
- **Size**: the prompt copy is cut at 120,000 chars (`od_context.py:37`). The sandbox copy is full.
- **Patterns**: `<section class="pattern" data-pattern="<id>">` with a `<!-- PATTERN <id> - purpose -->` comment. This is the convention of the shipped airline templates, so builders can find each screen.

- **Thin shape** (`od.shape: thin`): exactly one pattern, no `<script>`, no `style=`, 2+ `.nav-item` where only the finished screen has `data-go`. The folder is `SKILL.md` + `example.html` only. Reference: `airline-disruption-light`.

## Deck example.html

- No assets route exists for decks (`ppt_templates.py:56-125`), so everything must be inline.
- The composer copies the template's navigation script verbatim and keeps one `<section class="slide">` per slide (`prompts/ppt-composer/AGENT.md`). It follows the SKILL.md **Workflow** section step by step.
- Slides are 1920x1080. The PPTX exporter renders at authored size.

## Design system binding

- The template never names a design system.
- For prototypes, the run's design system re-themes the `:root` variables.
- For decks, the picker shows only when `od.design_system.requires: true`. Then DESIGN.md, `tokens.css` and `components.html` are seeded to `.context/design/`.
