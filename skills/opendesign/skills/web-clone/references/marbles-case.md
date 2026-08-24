# Flagship Case Study · Glass Marbles (Real Architecture vs. AI Fabrication)

Source site https://chiuhans111.github.io/marbles/ · Author Hans Chiu · single file, 1067 lines · License **NONE**.
Full line-by-line teardown at `./website-clones/marbles-clone/TEARDOWN.md`; this is the condensed version for skill use.

## The Real Architecture In One Sentence

A full-screen WebGL fragment shader uses an **analytic method (quadratic equation `b*b-c`)** to find ray-sphere intersections, performing up to 4 refraction/reflection iterations, and encodes the optical result into a **displacement-map PNG** (RG = pixel displacement, B = Fresnel value); then an SVG `<filter>`'s `feDisplacementMap(scale=200)` uses this map to distort the **real, live, interactive page DOM** (background color blocks + heading text).

> The glass marble you drag is essentially a lens, and behind that lens is this page's HTML. WebGL never touches the DOM pixels at any point — the refraction is done entirely by the SVG filter. Both the physics and the audio are hand-written from scratch, with zero libraries.

## The Three Pillars (Key Points of the Real Implementation)

1. **WebGL Optics**: Analytic sphere intersection (not ray-marching); refractive index N=1.3, 4 iterations; Fresnel `0.05+0.95*pow(1-cosθ,2.0)` (exponent 2, not Schlick's 5); interior has 2 bubbles + a paraboloid colored core + Beer-Lambert volumetric absorption; **a single shader reused via `u_mode`** (0=refraction/1=reflection/2=foreground highlight/3=shadow); displacement encoding `DISPLACEMENT_SCALE=200` is kept strictly consistent with the SVG side.
2. **SVG Filter Compositing**: 4 canvases (1 main + 3 offscreen); each frame the offscreen images are fed to `<feImage>` via `toDataURL`. The real chain: shadow `feGaussianBlur(8)` → `feBlend multiply` onto the DOM → refraction `feDisplacementMap` → reflection `feDisplacementMap` → `feGaussianBlur(2)` → the reflection map's B channel (Fresnel) is turned into an alpha mask via `feColorMatrix` → two-step `feComposite` for final compositing. The `SourceGraphic` being refracted is `#container`, which has `filter:url(#marble-filter)` attached.
3. **Physics**: Entirely hand-written — `mass=r³`, gravity 0.8, 3D elastic collisions (restitution 0.8, solved only when close), ground restitution 0.55 + micro-bounce zeroing, quaternion rolling, drag-lift `targetZ=200`; rendering is fully paused during `settleFrames` (at rest).
4. **Audio**: Procedural synthesis via Web Audio (zero files) — base frequency `800+(60-r)*20` plus 5 harmonics, volume scales with collision velocity.

## Where the AI Analysis Document Went Wrong (Cautionary Example — Remember These Failure Patterns)

That `Marbles Site Clone Analysis` document's main text has a **roughly correct conceptual skeleton** (8 steps, and the three-pillar framing is directionally right), but the **accompanying "clone code blocks" are almost entirely fabricated**:

| Fabrication | Reality | Failure Pattern (General Warning) |
|---|---|---|
| ray-marching + SDF + `MAX_STEPS=100` + 6-sample finite-difference normals | Analytic intersection, normal is `normalize(rp-center)` | **Don't assume a refraction demo uses ray-marching just on instinct** — a sphere has a closed-form solution, and many demos use the analytic method because it's faster and more accurate |
| `sampler2D uBackground` samples the DOM as a texture | The shader never reads the background; refraction is handed off to SVG via the displacement map | **This inverts the GPU↔DOM layering** — the single most important architectural idea gets lost |
| `feBlend screen` + a single displacement + `feComposite over` to composite the shadow | Dual displacement + Fresnel mask + multiply shadow | **Don't trust a secondhand analysis's filter chain — always verify node-by-node against the real source** |
| `MARBLE_COUNT=5`, array sized to 10 | Hardcoded at 2 | Even constants get guessed |
| Screen-center NDC coordinates | Top-left pixel origin + Y-flip | Coordinate system conventions are pure speculation |

**Lesson**: Treat AI-written "clone blueprints" as reference for their overall thinking skeleton only — **never copy a single line of the code blocks directly**; you must verify against the real source code. This is the origin of this skill's #1 iron rule.
