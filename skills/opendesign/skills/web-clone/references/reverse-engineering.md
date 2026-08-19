# Reverse-Engineering WebGL/Canvas Heavy-Frontend Sites

When recon determines a site is a WebGL/Canvas/Three.js heavy-frontend build (`window.THREE` exists, or multiple `<canvas>` elements, or `<script type="x-shader/*">` present), follow this playbook.

> This doc covers **how to read the rendering architecture**. The **evidence discipline** for reverse-engineering (SOURCE/PARTIAL/GUESS grading, no-compensation, baseline-first gating) and the **runtime-capture fallback for when source isn't available** → `effect-extraction.md`. Use the two together.

## General teardown steps

1. **Get single-file source first.** Many demo sites are fully self-contained in one HTML file (GitHub raw / browser "view source"). Don't rush to spin up Playwright to scrape the site.
2. **Count canvases, read SVG defs, grep for shaders**: How many `<canvas>` elements? Any `<filter>`? Where are the shader scripts? — these three things determine the rendering architecture.
3. **Determine "what the WebGL is computing"** (crucial — decides whether you can trust secondhand analysis):
   - grep `texture2D` / `sampler2D` → sampling a texture / framebuffer
   - grep for `+= dS` / `map(` / `MAX_STEPS` inside a `for` loop → ray-marching (step-based)
   - grep `b*b` / discriminant / `sqrt(` + quadratic equation → **analytic ray intersection** (closed-form solution, commonly used for spheres/planes)
   - Warning: don't assume ray-marching by gut feel — refractive glass demos are often analytic sphere intersection.
4. **Find the GPU↔DOM bridge**: If the WebGL canvas isn't displayed directly, but instead uses `toDataURL` / feeds `<feImage>` / `feDisplacementMap`, it means it's generating a **data map** (displacement/normal/depth) for another layer to consume. This is a hallmark technique of advanced frontends, and the layer most likely to get flipped/misread by secondhand analysis.
5. **Read physics/audio separately**: Usually a pure JS module decoupled from rendering, verifiable on its own.

## Transferable advanced patterns worth keeping

- **Displacement-map DOM refraction**: Offscreen WebGL computes a PNG where RG = displacement, B = auxiliary value; SVG `<feDisplacementMap scale=N>` uses it to distort real HTML. The `scale` on the GPU side and the SVG side must match. This can produce liquid glass, magnifiers, water ripples, or any "lens over a webpage" effect, and crucially **what's being refracted is the live, interactive DOM** — something Three.js's `MeshPhysicalMaterial(transmission)` cannot do (it can only produce a "glass ball appearance," not "refract the entire webpage").
- **One shader + mode uniform, many uses**: Refraction/reflection/shadow/foreground all share the same fragment shader, branching on `u_mode`. Saves code and compile time.
- **Downsample auxiliary data + freeze frames when static**: The eye isn't sensitive to resolution in displacement/reflection/shadow maps → downsample to 1/2 or 1/4. When the object is static → stop rendering entirely (settleFrames). A standard performance trick on heavy-frontend sites.
- **Full-screen triangle instead of a quad**: 3 vertices `[-1,-1, 3,-1, -1,3]` cover the full screen, saving one diagonal edge.

## Cloning-path decision

- **Can achieve 1:1 fidelity + license allows it** → take the real source and modify copy/colors/parameters directly (byte-for-byte preservation of a single-file native site = most faithful).
- **Want an approximate effect, exact match not required** → find a similar open-source template and swap in content (e.g. awesome-threejs). But note: **swapping implementation paths often loses the original site's core mechanism** (e.g., in this case, "refracting the real DOM") — first confirm whether that mechanism is actually the selling point the user wants.
- **Math specific to this site (intersection formulas/magic numbers) needs to be rewritten on migration**: swap the shape in an analytic "sphere" intersection for another shape and you need new formulas (or this is where you genuinely need SDF/ray-marching); refractive index, Fresnel coefficient, absorption, and other hand-tuned magic numbers need retuning when the material changes.

## Verification (hard requirement)
Start a local server → open in browser → check console (must have no JS/WebGL compile errors) → screenshot comparison against the original site.
Honestly record parts that can't be verified: for example, Playwright's synthesized PointerEvents have `isTrusted=false` and won't trigger drag hit-testing logic — **write this into NOTES honestly, don't fake "drag succeeded."** For physics-based sites, "two loads produce different initial states" can serve as indirect proof the engine is running.
