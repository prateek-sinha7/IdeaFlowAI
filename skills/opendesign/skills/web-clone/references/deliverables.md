# Deliverable Specs & Templates

The standard deliverables for each clone sub-project (`$WEB_CLONE_PROJECT/`).

## NOTES.md (required)

```markdown
# <Site name> · Clone Notes

## Source Info
- Original URL:
- Source repo: (if any)
- Original author:
- License: MIT / Apache / NONE / Proprietary  ← must be verified, see the license table in SKILL.md
- Attribution requirements:

## Tech Stack
- Framework / key libraries / Node version:

## Pre-clone Assessment
- Complexity tier: L1 / L2 / L3 / L4 / L5 / L6 (see references/assessment.md in the web-clone skill)
- Recommended mode: Faithful clone / Visual clone / Content overhaul / Technical teardown
- Parts that can be high-fidelity:
- Parts that need approximation or substitution:
- Parts not being cloned:
- Main risks:

## Getting It Running
\`\`\`bash
cd "$WEB_CLONE_PROJECT"
# Single-file static site: python3 -m http.server 8123
# Framework site: nvm use <ver> && npm install && npm run dev
\`\`\`

## What Changed (vs. the original)
- Removed tracking scripts: ... (GA/gtag line numbers)
- ...

## Original vs. Clone
| Module | Original behavior | Clone implementation | Differences / tradeoffs | Evidence |
|---|---|---|---|---|
| Above the fold |  |  |  | screenshot / file:line |
| Navigation |  |  |  |  |
| Core animation |  |  |  |  |
| Content sections |  |  |  |  |
| Mobile |  |  |  |  |

## Clone Score
- Source evidence: /5
- Structural fidelity: /5
- Visual fidelity: /5
- Animation/interaction: /5
- Responsiveness: /5
- Functional completeness: /5
- Content substitution: /5
- Legal/deployment risk: /5
- Overall:

## Replacement Map (what to swap, where)
- Text → file, line
- Images/media → directory
- Colors → CSS variables / theme
- 3D models / fonts → ...

## Verification
- [ ] Runs locally, 0 console errors
- [ ] Screenshots compared against the original site (RECON/screenshots/)
- [ ] `route-crawl.mjs` output for original/clone route maps (required for multi-page sites)
- [ ] `interaction-probe.mjs` output with hover/click/scroll/canvas state evidence (required for interactive sites)
- [ ] `visual-diff.mjs` output with screenshot diff report (when feasible)
- [ ] `audit-clone.mjs` output with residual-artifact audit report
- Items that couldn't be verified (record honestly, don't fabricate): ...
```

## TEARDOWN.md (add for complex interactive sites)

A technical teardown document; **every conclusion must cite a real source line number**. Structure:
- **0. One-line essence**
- **A. Real technical teardown** (organized by pillar: rendering/compositing/physics/interaction/audio; each item tagged with a line number **+ evidence level `SOURCE`/`PARTIAL`/`GUESS`**, see `effect-extraction.md`)
- **B. Secondary-analysis verification table** (if an AI analysis doc exists: `Claim | Actual source | Accuracy ✅/⚠️/❌ | Notes`, focus on catching substantive errors)
- **C. Transferable methodology** (general patterns / site-specific quirks / clone path)

Example: `./website-clones/marbles-clone/TEARDOWN.md`.

## RECON/ (reconnaissance artifacts)
- `screenshots/original-{1440,768,390}.png` original site at three breakpoints
- `screenshots/clone-1440.png` clone screenshot (for comparison)
- `screenshots/visual-diff-1440.png` screenshot diff image (when feasible)
- `global-recon.json` recon probe output (framework/canvas/scroll library/fonts, etc.)
- `routes/original-route-map.json` / `.md` original site's internal route map with per-route screenshots
- `routes-clone/clone-route-map.json` / `.md` clone site's internal route map with per-route screenshots
- `interactions/original-interactions.json` / `.md` original site's interaction states, network, console, and screenshot evidence
- `interactions-clone/clone-interactions.json` / `.md` clone site's interaction states, network, console, and screenshot evidence
- `asset-manifest.json` original site's asset inventory and download status (when feasible)
- `network/original-network.json` API/XHR capture log (required for SPA/SaaS sites)
- `network/fixtures/` saved JSON/text response fixtures
- `sourcemaps/sourcemap-manifest.json` source map search results (prioritize for complex frontends)
- `visual-diff-1440.json` pixel-diff metrics
- `design-dna.json` structured design identity (produced in visual-clone/content-overhaul modes; scaffolded by `dna-scaffold.mjs` and filled in manually; schema in `design-dna.md`)
- `baseline/` "minimal faithful reproduction" artifacts + evidence package for WebGL/effect reverse-engineering (see the baseline-first gate in `effect-extraction.md`)

## CLONE_REPORT.md (add when reporting externally or evaluating skill effectiveness)

```markdown
# <Site name> · Original vs. Clone Assessment Report

## Conclusion
- Complexity tier:
- Clone mode:
- Overall fidelity:
- Best used for: local learning / further overhaul / deployable demo / technical teardown only

## Comparison
| Dimension | Original | Clone | Conclusion |
|---|---|---|---|
| Information architecture |  |  |  |
| Visual language |  |  |  |
| Animation/interaction |  |  |  |
| Responsiveness |  |  |  |
| Content substitution |  |  |  |
| Functional scope |  |  |  |

## Score
Scored across the 8 dimensions in `references/assessment.md` of the web-clone skill.

## Known Gaps
-

## Suggested Next-Level Upgrades
-
```

## CLONE_AUDIT.md (add before going live)

Generated by `scripts/audit-clone.mjs`. Focus on:
- Whether tracking scripts / analytics pixels have been removed
- Whether the original site's brand name, Japanese text, or TODOs still remain
- Whether external URLs still point to the original site or uncontrolled third-party resources
- Whether asset and license risks have been documented

## Wrap-up
- Update the hub `./website-clones/README.md` index line (status emoji: 🟡 recon / 🟢 running / 🔵 in progress / ✅ live / 🔴 stuck / 🗂️ archived)
- Keep the original source as a read-only baseline `index-original.html`; don't edit it
- Stop the local server process once done
