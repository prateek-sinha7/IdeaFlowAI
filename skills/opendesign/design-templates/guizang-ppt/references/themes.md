# Theme Color Presets (Themes)

5 carefully tuned color palettes that keep the "digital magazine × e-ink" aesthetic from falling apart. **Users are not allowed to customize colors — a wrong color pairing makes the layout look ugly instantly.** Only pick from the presets below.

---

## How to use

1. Ask the user which set to pick (or recommend one based on the content)
2. Open the `<style>` block in `assets/template.html`
3. Find the `:root{` block at the top
4. **Fully replace** the lines marked with the "theme color" comment: `--ink` / `--ink-rgb` / `--paper` / `--paper-rgb` / `--paper-tint` / `--ink-tint`
5. All other CSS goes through `var(--...)` — no other changes needed

---

## 🖋 Classic Ink (Monocle Default)

**Best for**: general sharing, business releases, tech products — the safe default choice for any scenario.
**Tone**: pure ink black + warm off-white, the strongest magazine feel, in the style of Monocle / Apricot / A Book Apart.

```css
--ink:#0a0a0b;
--ink-rgb:10,10,11;
--paper:#f1efea;
--paper-rgb:241,239,234;
--paper-tint:#e8e5de;
--ink-tint:#18181a;
```

---

## 🌊 Indigo Porcelain

**Best for**: tech/research/data sharing, engineering culture, in-depth content, technical launch events.
**Tone**: deep indigo + porcelain white, calm, rational, with depth — like an academic journal or blue-and-white porcelain.

```css
--ink:#0a1f3d;
--ink-rgb:10,31,61;
--paper:#f1f3f5;
--paper-rgb:241,243,245;
--paper-tint:#e4e8ec;
--ink-tint:#152a4a;
```

---

## 🌿 Forest Ink

**Best for**: nature/sustainability/culture/nonfiction content, outdoor brands, environmental themes.
**Tone**: deep forest green + ivory, composed and breathable, like an old issue of National Geographic.

```css
--ink:#1a2e1f;
--ink-rgb:26,46,31;
--paper:#f5f1e8;
--paper-rgb:245,241,232;
--paper-tint:#ece7da;
--ink-tint:#253d2c;
```

---

## 🍂 Kraft Paper

**Best for**: nostalgic/humanities/reading/history/literary sharing, indie magazines, handmade brands.
**Tone**: deep brown + warm beige, like a kraft paper envelope or an old notebook — warm, with a sense of era.

```css
--ink:#2a1e13;
--ink-rgb:42,30,19;
--paper:#eedfc7;
--paper-rgb:238,223,199;
--paper-tint:#e0d0b6;
--ink-tint:#3a2a1d;
```

---

## 🌙 Dune

**Best for**: art/design/creative/fashion sharing, gallery booklets, aesthetics-first private gatherings.
**Tone**: charcoal gray + sand, restrained, refined, neutral — like a desert dusk or an architecture design portfolio.

```css
--ink:#1f1a14;
--ink-rgb:31,26,20;
--paper:#f0e6d2;
--paper-rgb:240,230,210;
--paper-tint:#e3d7bf;
--ink-tint:#2d2620;
```

---

## Recommendation reference

| If it's... | Recommended theme |
|---|---|
| Not sure what to pick / first time using this | 🖋 Classic Ink |
| AI / tech / product launch | 🌊 Indigo Porcelain |
| Content / industry commentary / culture | 🌿 Forest Ink |
| Book review / lifestyle / humanities | 🍂 Kraft Paper |
| Design / art / branding | 🌙 Dune |

---

## Switching principles

- **Use only one theme per deck** — don't switch colors partway through
- The WebGL shader's default primary colors (titanium dispersion / silver flow) work with all 5 sets (tested and acceptable)
- Borders/icons driven by `currentColor` automatically adapt to the section's text color — no extra adjustment needed
- Once a theme is chosen, the `<title>` text and `chrome` copy can reinforce that theme's meaning (e.g. pairing Kraft Paper with something like "Vol.03 · Autumn")

## ❌ Things not to do

- ❌ **Don't mix and match** (e.g. taking `ink` from Classic Ink and `paper` from Dune) — it will clash completely
- ❌ **Don't let the user just hand you an arbitrary hex value** — politely decline and show the 5 presets for them to choose from
- ❌ **Don't directly modify colors elsewhere in template.html** — every scattered rgba value goes through `var`; changing `:root` in one place is enough

Once a theme is chosen, tell the user in the skill conversation: "Using 🖋 Classic Ink / 🌊 Indigo Porcelain ..." and note it in the deck project record, so future iterations stay consistent.
