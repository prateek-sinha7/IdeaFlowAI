# Magazine Directions

5 **preset directions**, each bundling together "which theme color / which layouts / how many slides / how to write the chrome copy" so you don't end up offering 5 unrelated options during the 6-question clarification.

> Inspiration: [alchaincyf/huashu-design](https://github.com/alchaincyf/huashu-design)'s "20 design philosophies × 5 streams" — we've compressed it down to 5 magazine-flavored directions, each mapped to a specific set in `themes.md` plus certain combinations from `layouts.md`.

---

## When to use this document

At the start of `Step 1 · Requirements Clarification` in SKILL.md: **first let the user pick one of these 5 directions**, then ask about theme color / duration / audience / outline. The flow is:

```
1. The user says one line like "I want to make a talk deck"
2. You (the agent) introduce the 5 directions (copy the 1-line summaries below)
3. The user picks a direction (or says "I don't know, you recommend one")
4. Having answered the "theme color" and "slide count" questions based on the chosen direction, you ask the remaining 4 questions
```

**Hard rule**: the direction must be chosen from the 5 below — no mixing and matching. Mixing = walking the failure path already proven by huashu-design (Brand Asset Protocol v1). If the user isn't satisfied with any of the 5, gently persuade them to pick the closest match, then you may lightly customize the tone in `chrome` / `kicker` — **never the color palette**.

---

## 1. Monocle Editorial · International Magazine Style ✦ Default Recommendation

**Keywords**: restrained, intellectual, cosmopolitan, has *taste*

| Recipe | Choice |
|---|---|
| Theme color | 🖋 Ink Classic |
| Recommended slide count | 18–24 pages (60% non-hero / 40% hero) |
| Primary layouts | **1 Cover / 2 Chapter Break / 4 Text-Left-Image-Right / 8 Big Quote / 10 Mixed Text-Image** |
| Chrome copy | `Vol.04 · Spring 2026` / `Act II · 12 / 24` / `lukew.com · 2026.04` |
| Kicker style | Short English words + middle dot: `THE TWIST` / `BUT` / `DEC.` |
| Footer copy | `Page 12 · A new way of working` |

**Suited for**: business launches, industry keynotes, product announcements, personal brand recaps. **Default choice** — hard to go badly wrong with this one.

**Anti-examples**: technically deep reports (too low-density), ops retrospectives full of tables (no suitable layout for that).

**Visual anchors**: *Monocle* / *Apricot Magazine* / *A Book Apart* / *Apartamento*.

---

## 2. WIRED Tech · Data + Engineering

**Keywords**: hard data, pipelines, comparisons, futuristic

| Recipe | Choice |
|---|---|
| Theme color | 🌊 Indigo Porcelain |
| Recommended slide count | 14–18 pages (light, data-dense) |
| Primary layouts | **1 Cover / 3 Big Stat Card / 6 Pipeline / 7 Problem Page / 9 Before/After** |
| Chrome copy | `Q2 / 2026 · Field Report` / `Data · 03` / `Eng Notes` |
| Kicker style | All caps + numbers: `38× FASTER` / `RUNTIME 04` / `CASE 02` |
| Footer copy | `Page 03 · benchmark` / `methodology footnote` |

**Suited for**: tech launches, research talks, benchmark reports, internal engineering-team communication, AI product demo days.

**Anti-examples**: humanities-flavored quote decks (too cold), art brands (not warm enough).

**Visual anchors**: *WIRED* longform edition / *MIT Technology Review* / *The Pudding* / *Stripe Press*.

**Special guidance**: use an English monospace font for each stat-card's `stat-label` (this is the core of the WIRED look); skip thousands separators on numbers (not engineering-flavored enough) — use `K` / `M` / `×` shorthand instead.

---

## 3. Kinfolk Slow · Slow Living / Humanities

**Keywords**: whitespace, serif, warmth, intimate gathering

| Recipe | Choice |
|---|---|
| Theme color | 🍂 Kraft Paper |
| Recommended slide count | 9–12 pages (slow, spacious, low density) |
| Primary layouts | **1 Cover / 4 Text-Left-Image-Right / 8 Big Quote / 10 Mixed Text-Image / 2 Chapter Break** |
| Chrome copy | `Vol.07 · Autumn` / `A Letter · 03` / `Notes from Kyoto` |
| Kicker style | Short phrases + punctuation: "For a friend." / "Late autumn." / "Letter Three" |
| Footer copy | `Page 03 · Letter Three` / `2026 · Spring Issue` |

**Suited for**: intimate gatherings, book-club talks, profile/interview recaps, lifestyle brands, personal essays.

**Anti-examples**: product launches (too slow), tech talks (too soft), heavy data reports (not information-dense enough).

**Visual anchors**: *Kinfolk* / *The Gentlewoman* / *Cereal* / *Drift Magazine*.

**Special guidance**:
- **Deliberately keep the slide count under 10** — Kinfolk's core principle is "less is more"; don't overfill
- Lean heavily on Layout 8 (Big Quote) and Layout 10 (Mixed Text-Image)
- Avoid Layout 3 (Big Stat Card) — it clashes with the mood
- Use serif type and short phrases throughout for the `<title>` text, chapter names, and kicker

---

## 4. Domus Architectural · Architecture / Spatial Feel

**Keywords**: scale, geometry, asymmetry, restrained flair

| Recipe | Choice |
|---|---|
| Theme color | 🌙 Dune |
| Recommended slide count | 12–18 pages (medium density, strong visuals) |
| Primary layouts | **1 Cover / 2 Chapter Break / 5 Image Grid / 9 Before/After / 10 Mixed Text-Image** |
| Chrome copy | `Spazio 09 · Project File` / `Plan · 03` / `Fig.4` |
| Kicker style | Number + category: `PROJECT 04` / `SECTION B` / `FIGURE 12` |
| Footer copy | `Page 09 · West Wing` / `1:200 scale` |

**Suited for**: design / architecture case studies, product design reviews, brand visual launches, gallery-style portfolio showcases.

**Anti-examples**: quote decks (too rigid), deep technical dives (this direction isn't built for pipelines).

**Visual anchors**: *Domus* / *Apartamento* / *Mark Magazine* / *Pin-Up*.

**Special guidance**:
- **Leave 60% negative space on every hero page** — don't overfill; the architectural feel comes from breathing room
- Lean on Layout 5 (Image Grid) but **use only 4 large images**, not 6 small ones
- Keep `chrome` copy cool and detached — all English + numbers

---

## 5. Lab / Reference · Academic + Technical Manual

**Keywords**: restrained, image-and-table-rich, reproducible, engineer-approved

| Recipe | Choice |
|---|---|
| Theme color | 🌿 Forest Ink |
| Recommended slide count | 16–24 pages (high density, chart-heavy) |
| Primary layouts | **1 Cover / 2 Chapter Break / 3 Big Stat Card / 6 Pipeline / 9 Before/After** |
| Chrome copy | `Field Notes · Vol.II` / `Section 3.2 · Method` / `Reference 04` |
| Kicker style | Numbered: `§ 3.2` / `Ref. 04` / `Method 01` |
| Footer copy | `Page 12 · 3.2 Calibration` / `appendix A` |

**Suited for**: academic talks, internal research reviews, sustainability / nature-themed topics, long-term product retrospectives, methodology-driven craft talks (coffee / perfume / tea).

**Anti-examples**: business launches (too clinical), marketing campaigns (not catchy enough).

**Visual anchors**: *National Geographic* (vintage) / *Hand-Eye Magazine* / *Nautilus* / *MIT Press* book layouts.

**Special guidance**:
- Use `meta-row` extensively to annotate sources, methods, and citations
- Use `<figcaption class="img-cap">` **more frequently than other directions** to number every image
- Use § section numbering for `kicker`, not exclamatory phrases

---

## Quick lookup (which direction to recommend based on what the user describes)

| What the user says | Recommended direction |
|---|---|
| "A general-purpose talk" / "I don't know what to pick" | **1. Monocle** |
| "Solo founder / AI product / startup demo day" | **1. Monocle** (default) or **2. WIRED** (if more technical) |
| "AI / benchmark / model evaluation" | **2. WIRED** |
| "Product launch / engineering team talk" | **2. WIRED** |
| "Book talk / profile interview / one person's story" | **3. Kinfolk** |
| "Intimate gathering / talk among friends / casual weekend chat" | **3. Kinfolk** |
| "Design case study / brand launch / portfolio showcase" | **4. Domus** |
| "Architecture / space / installation" | **4. Domus** |
| "Academic / research / methodology / tutorial" | **5. Lab** |
| "Sustainability / environment / nature theme" | **5. Lab** |

---

## Decision record (required before generating)

After picking a direction, **create or update `project-record.md`** (or `outline-v1.md`) in the project directory, with the first lines reading:

```markdown
# [Talk Title] · Project Record

- Direction: **Monocle Editorial** (from `references/styles.md`)
- Theme color: 🖋 Ink Classic
- Audience: internal team (product + design)
- Duration: 25 min · ~18 slides
- Chrome style: Vol.04 / Act II / 12 of 18
- Kicker style: short English words + middle dot
```

Update this section every time the direction is adjusted in later iterations. **Don't switch directions mid-project** — the "tone" gap between the 5 directions is bigger than it looks, and mixing them will tear the deck apart.

---

## ❌ Things not to do

- ❌ Mix layout choices across the 5 directions (e.g. Monocle with multiple Layout 6 Pipeline pages + Kinfolk-style chrome) — messy
- ❌ Invent a 6th direction yourself ("I want a 'tech + literary' vibe") — gently persuade them to pick the closest match; the failure rate of mixing directions is proven to be very high
- ❌ Switch direction mid-way — e.g. deciding on page 8 that "Kinfolk would actually be better" — the first 7 pages are wasted; either start over completely or commit to the original direction
- ❌ Spend time on layouts that don't belong to the chosen direction (e.g. writing 4 pages of Layout 6 Pipeline in Kinfolk) — that's a sign you picked the wrong direction

## ✅ Things to do

- ✅ Only choose from the 5 directions, then use that choice to answer the other 5 clarification questions
- ✅ State the direction clearly on the first line of `project-record.md`, and keep it unchanged throughout
- ✅ Let the chrome / kicker / footer text carry the direction's identity — they account for half of a direction's recognizability
- ✅ When in doubt, **default to Monocle Editorial** — it's the safest fallback among the 5 directions, with the lowest failure rate
