# Complexity Grading & Clone Scoring

Used for pre-clone estimation, post-clone acceptance, and explaining to the user "how faithfully can this site be cloned."

## Clone Modes

| Mode | Goal | Applicable Scenarios |
|---|---|---|
| Faithful Clone | Preserve original source code / layout / interactions as much as possible | Legal source found, single-file site, learning complex frontend techniques |
| Visual Clone | Appearance looks close, internal implementation can be replaced | No source code, commercial site, content site, component-based rebuild |
| Content Overhaul | Keep original site's rhythm and visual grammar, swap in the user's business content | Turn a reference site into your own site, brand page, product introduction |
| Technical Teardown | Don't rush to rebuild, first confirm the real implementation | WebGL/Canvas/complex interactions, contradictory AI analyses |

## Complexity Levels L1-L6

| Level | Type | Typical Signals | Usually Achievable Fidelity | Default Boundary |
|---|---|---|---|---|
| L1 | Static HTML/CSS | Minimal JS, no framework, few pages | 90-98% | Can approach pixel-perfect, asset copyright handled separately |
| L2 | CMS/enterprise content site | Multi-page, CMS-generated, forms/news/region sites | 70-90% | Front-end can be reproduced, CMS backend not cloned |
| L3 | React/Vue/Next content frontend | Hydration, chunks, routing, content fetched via API | 65-90% | Data/API can be replaced with a local JSON stand-in |
| L4 | Animated rebrand site | GSAP, Lenis, complex scroll, video masking | 50-80% | Main visuals can be reproduced, micro-interactions often approximated |
| L5 | WebGL/Canvas/Three.js | Shaders, physics, post-processing, GPU resources | 30-95% | High fidelity possible with source code, tear down first if no source |
| L6 | SaaS/e-commerce/login business system | Accounts, payments, orders, permissions, search recommendations | Presentation layer only | Server-side business logic not cloned by default |

## Pre-Clone Estimation Template

```markdown
## Pre-Clone Estimation
- Complexity level:
- Recommended mode: Faithful Clone / Visual Clone / Content Overhaul / Technical Teardown
- Parts that can be high-fidelity:
- Parts that need approximation or substitution:
- Parts that will not be cloned:
- Main risks: licensing / assets / login state / API / performance / WebGL / responsiveness
```

## Post-Clone Scoring

Each item scored 0-5. Only give scores that can be backed by source code, screenshots, or browser runtime results.

| Dimension | 5 points | 3 points | 1 point |
|---|---|---|---|
| Source evidence | Found source code or complete static assets, key conclusions have file/line references | Runtime reconnaissance and asset capture done | Mostly relies on visual inspection and guesswork |
| Structural fidelity | Information architecture, section order, and breakpoints all match | Main sections match, details have merges/omissions | Only keeps a rough style |
| Visual fidelity | Fonts, spacing, colors, image ratios closely match | Main visuals close, some proportions differ locally | Clearly looks like a different design |
| Motion/interaction | Scroll, hover, video, Canvas/WebGL behavior matches closely | Only core interactions preserved | Essentially static |
| Responsiveness | Desktop/tablet/mobile all verified with no layout breaks | 1-2 widths verified | Mobile clearly broken |
| Functional completeness | Navigation, forms, media, external links, local run all work | Main browsing paths work | Multiple dead links or errors |
| Content replacement | Already changed to the user's content, replacement map is clear | Partially adapted, still has original site remnants | Large amounts of original site copy/branding remain |
| Legal/deployment risk | Licensing clear, tracking removed, asset boundaries defined | Risks documented but not fully resolved | Risks unclear |

Recommended output:

```markdown
## Clone Score
- Source evidence: /5
- Structural fidelity: /5
- Visual fidelity: /5
- Motion/interaction: /5
- Responsiveness: /5
- Functional completeness: /5
- Content replacement: /5
- Legal/deployment risk: /5
- Overall assessment:
```

## Original Site vs Clone Comparison Table

```markdown
| Module | Original Site Behavior | Clone Implementation | Differences / Tradeoffs | Evidence |
|---|---|---|---|---|
| Above the fold |  |  |  | screenshot / file:line |
| Navigation |  |  |  |  |
| Core motion |  |  |  |  |
| Content sections |  |  |  |  |
| Mobile |  |  |  |  |
```
