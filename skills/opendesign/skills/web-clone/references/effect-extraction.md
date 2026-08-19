# Evidence Discipline for Effect Extraction + Baseline Gate (WebGL/Canvas Reverse-Engineering Branch)

`reverse-engineering.md` covers "how to read a rendering architecture"; this doc covers **how not to fool yourself when reverse-engineering effects**,
plus the fallback path for when you can't find the real source. Three pieces: **evidence tiering → no-compensation → baseline-first gate**.

> The discipline pattern is inspired by [lixiaolin94/skills · web-shader-extractor](https://github.com/lixiaolin94/skills) (that repo has no LICENSE,
> so all rights are reserved by default — this doc **only borrows the method concept, rewritten entirely in this skill's own words, with no code or original text copied**).
> It shares the same soul as web-clone's #1 iron rule "real source above all," just upgrading "cite the line number" into a systematic evidence regime.

## 1. Evidence Tiering (tag every conclusion)

When writing a TEARDOWN, tag every key fact about the rendering pipeline with a tier, **defaulting to the lowest tier when unsure**:

| Tag | Meaning | Example |
|---|---|---|
| `SOURCE` | Direct, hard evidence tied to the target | Publicly available real source lines, source-map-recovered modules, runtime object dumps, captured shader/WGSL text, frame captures, hash-verified network response bodies |
| `PARTIAL` | A handle for the next probing step, not yet conclusive | Class/function/field names, minified bundle slices, framework objects, a captured shader missing uniforms/pass/input state |
| `GUESS` | A reconstructed value with no direct evidence | Visual fitting, name-based inference, applying defaults, hand-tuned magic numbers, any "looks about right" behavior reconstruction |

- **Untagged = treat as GUESS.** Don't let unproven things slip into "known."
- This codifies the marbles lesson ("AI fabricated ray-marching out of an analytic intersection"): **any GUESS-tier implementation must be upgraded to SOURCE before you copy it as-is.**

## 2. No-Compensation (don't hide ignorance behind knob-tweaking)

> **It is strictly forbidden** to tweak brightness / speed / position / noise values just to make the picture "look right," as a way of papering over real errors in timing, color, FBO, resources, coordinate systems, or state models.

- If a fitted constant makes the output look more similar → **it's still GUESS**, and you must note what evidence would be needed to upgrade it.
- Wiring-level facts (pass order, coordinate transforms, time units, input coupling) **don't become correct just because the picture looks similar** — they must be traced to evidence independently.
- This matches web-clone's existing rule: report what you couldn't verify honestly, **never fake a "drag succeeded."**

## 3. Baseline-First Gate (reproduce first, then refactor)

The easiest mistake when reverse-engineering effects is **extracting, rewriting, and "polishing" all at once**, ending up with something that neither matches the original site nor has a clear record of which step went wrong. Split it into gated stages instead:

```
Locate render surface → Capture minimal ground truth → RAW REPLAY (minimal as-is reproduction) → ✅BASELINE frame-by-frame comparison passes
                                                                                                    ↓ only allowed after passing
                                                                                              PROJECTIZE (refactor into an editable project) → PACKAGE
```

- **RAW REPLAY**: using the real captured draw calls / shaders / uniforms / vertex data, build a runnable reproduction that is **as minimal and as unmodified as possible** — no optimizing, no framework swap, no parameter changes.
- **BASELINE gate**: RAW REPLAY must visually match the original site frame-by-frame (or via multi-frame sampling) to pass. **You may not proceed to refactoring until this gate is passed.**
- After passing the gate, PROJECTIZE: convert to a maintainable form (raw WebGL / Three.js TSL / Babylon, etc.), still tagging every fact's evidence tier.
- Mark the final state honestly with one of three labels: `DONE_BASELINE_VERIFIED` (reproduced and verified) / `DONE_PROJECTIZED` (turned into a proper project) / `DONE_BASELINE_WITH_GAPS` (reproduced but with documented gaps).

## 4. When You Can't Find Real Source — Runtime Capture Fallback

web-clone's first move is always "go find the real source on GitHub / via source-map." But **effect-heavy sites are often sourceless and fully minified**.
In that case, don't fall back to "write it the way it looks" (that's GUESS) — instead, **capture runtime ground truth at the rendering boundary**:

- Intercept the WebGL/WebGPU context: the actual draw calls, the bound program, the compiled shader source, uniform values, FBO/texture sizes, blend/depth state.
- Tooling directions: spector.js-style frame capture, patching the `WebGLRenderingContext` prototype to log calls, using `getShaderSource` to get compiled shader text, injecting hooks via a preload script before page scripts run.
- What you capture this way counts as `SOURCE` tier — it becomes the new "real source," to be fed into the baseline-first pipeline.

## 5. When to Delegate to web-shader-extractor

If you already have `web-shader-extractor` installed (the skill from `npx skills add lixiaolin94/skills`),
**delegate the effects portion directly to it in the following situations, with web-clone acting only as the entry point**:

- The site is WebGL/WebGPU/heavy-Canvas effects, and neither GitHub nor source-map yields real source;
- You need runtime frame capture, frame-by-frame comparison, or shader/uniform-level extraction;
- You want the full gated flow of "reproduce baseline first, then productionize separately."

Once you get back the delegated output (a minimal reproducible baseline + evidence package), **merge it into `$WEB_CLONE_PROJECT/`**,
fill in NOTES/TEARDOWN per web-clone's deliverable conventions, and continue on to Step 5 verification + Step 6 replacement.

Not having it installed doesn't matter — the discipline in the four sections above can be followed as-is; web-shader-extractor just packages section 4's capture machinery into a ready-made tool.

## Integration with Existing Deliverables

- Every item in TEARDOWN.md's "A. Real Technical Breakdown" gets an evidence tag (`SOURCE`/`PARTIAL`/`GUESS`).
- "B. Secondhand Analysis Verification Table" was already about catching GUESS masquerading as SOURCE, so this is consistent with it.
- Baseline reproductions should be kept in `<site-name>-clone/RECON/baseline/`, serving as hard proof of "verified," alongside the original screenshots.
