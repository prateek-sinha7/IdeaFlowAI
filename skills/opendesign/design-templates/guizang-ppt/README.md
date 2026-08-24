# Magazine Web PPT · Editorial-Style Web Slide Deck Skill

> 🌏 **English version: [README.en.md](./README.en.md)**

A [Claude Code / Claude Agent Skills](https://agentskills.io/) skill for generating **single-file HTML horizontal-swipe decks**, with a visual tone of "**electronic magazine × electronic ink**" — picture *Monocle* with code stitched in.

> Distilled by [Guizang](https://x.com/op7418) from offline talks like "One-Person Company: Organizations Folded by AI" and "A New Way of Working." Every pitfall hit along the way is logged in `checklist.md`.

![Magazine Web PPT preview](https://github.com/user-attachments/assets/5dc316a2-401c-4e37-9123-ea081b6ae470)

## What you get

- 🖋 **Three-tier type system**: serif for headlines, sans-serif for body, mono for metadata
- 🌊 **WebGL fluid / dispersion backgrounds** — visible on hero pages, restrained on body pages
- 📐 **Horizontal swipe navigation**: keyboard ← → / scroll wheel / touch swipe / bottom dots / ESC for index
- 🎨 **5 curated theme presets**: Ink Classic / Indigo Porcelain / Forest Ink / Kraft Paper / Dune
- 🧩 **10 page layouts**: opening cover, chapter divider, big-number stat page, text-left image-right, image grid, pipeline, suspense question, big quote, before/after comparison, image + text mix
- 📄 **Single HTML file**: no build, no server, opens directly in the browser

## Fits / Doesn't fit

**✅ Fits**: offline talks / industry keynotes / private salons / AI product launches / demo day / presentations with strong personal voice

**❌ Doesn't fit**: data-heavy tables / training decks (information density too low) / multi-user collaborative editing (static HTML)

## Install

### Option 1: Paste this to an AI (recommended)

> Install the `guizang-ppt-skill` Claude Code skill for me. Please follow these steps:
>
> 1. Make sure the `~/.claude/skills/` directory exists (create it if not)
> 2. Run `git clone https://github.com/op7418/guizang-ppt-skill.git ~/.claude/skills/magazine-web-ppt`
> 3. Verify: `ls ~/.claude/skills/magazine-web-ppt/` should show `SKILL.md`, `assets/`, and `references/`
> 4. Let me know when it's installed. Afterward, saying things like "make me a magazine-style deck" will trigger this skill

Paste this block into Claude Code / Cursor / any AI agent with shell access and it will complete the install automatically.

### Option 2: Manual CLI

```bash
git clone https://github.com/op7418/guizang-ppt-skill.git ~/.claude/skills/magazine-web-ppt
```

### How to trigger it

Once installed, Claude Code will automatically discover and invoke the skill during conversation. Trigger keywords:

- "Make me a magazine-style deck"
- "Generate a horizontal swipe deck"
- "editorial magazine style presentation"
- "electronic ink style talk slides"

## Workflow

The skill itself is a structured 6-step workflow; Claude will guide you through it step by step:

1. **Clarify requirements** — a 6-question checklist: audience, duration, source material, images, theme color, hard constraints
2. **Copy the template** — `assets/template.html` → project directory, update `<title>`, swap the theme color
3. **Fill in content** — pick from 10 layout skeletons, paste, edit copy (with class-name pre-check + theme rhythm planning first)
4. **Self-check** — compare against `references/checklist.md`; all P0-level issues must pass
5. **Preview** — open directly in a browser
6. **Iterate** — use inline styles to adjust font size / height / spacing

See [`SKILL.md`](./SKILL.md) for full details.

## Directory structure

```
magazine-web-ppt/
├── SKILL.md              ← main skill file: workflow, principles, common mistakes
├── README.md             ← this file
├── assets/
│   └── template.html     ← fully runnable seed HTML (CSS + WebGL + swipe JS pre-wired)
└── references/
    ├── components.md     ← component catalog (type, color, grid, icons, callout, stat, pipeline)
    ├── layouts.md        ← 10 page layout skeletons (paste-ready)
    ├── themes.md         ← 5 theme presets (pick only, no customizing)
    └── checklist.md      ← quality checklist (P0 / P1 / P2 / P3 tiers)
```

## Theme presets

Pick one from `references/themes.md` — **custom hex values are not allowed**; protecting the aesthetic matters more than giving freedom.

| Theme | Best for |
|------|---------|
| 🖋 Ink Classic | general default, commercial launches, when unsure what to pick |
| 🌊 Indigo Porcelain | tech / research / AI / technical keynotes |
| 🌿 Forest Ink | nature / sustainability / culture / non-fiction |
| 🍂 Kraft Paper | nostalgic / humanist / literary / indie zines |
| 🌙 Dune | art / design / creative / gallery |

Switching themes only requires replacing the 6 variable lines at the top of `template.html`'s `:root{}` block — all other CSS flows through `var(--...)`.

## Core design principles

1. **Restraint over flash** — WebGL backgrounds only bleed through on hero pages
2. **Structure over decoration** — information hierarchy comes from type size + typeface contrast + grid whitespace, not shadows or floating cards
3. **Images are first-class citizens** — crop only from the bottom; top and sides stay intact
4. **Rhythm lives on hero pages** — alternating hero / non-hero pages keeps the eye from fatiguing
5. **Terms stay consistent** — Skills is Skills, no mixing translations

## Visual references

- [*Monocle*](https://monocle.com) magazine layouts
- YC Garry Tan's "Thin Harness, Fat Skills"
- Guizang's offline talk deck series

## Contributing

Bugs, layout issues, new layout requests — Issues and PRs welcome. When making changes, prioritize:

- Adding classes in `template.html` first — don't let `layouts.md` reference undefined classes
- Logging pitfalls into `checklist.md` at the matching P0 / P1 / P2 / P3 tier
- Adding new theme colors to `themes.md` along with a recommended use case

## License

MIT © 2026 [op7418](https://github.com/op7418)
