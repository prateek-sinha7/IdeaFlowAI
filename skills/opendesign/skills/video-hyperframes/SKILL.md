---
name: video-hyperframes
zh_name: "Hyperframes Video Script"
en_name: "Hyperframes Video"
emoji: "🎞️"
description: "Hyperframes / Remotion-compatible continuous frame animation, auto-plays"
category: video
scenario: video
aspect_hint: "1920×1080 (16:9)"
recommended: 5
tags: ["video", "hyperframes", "remotion", "script"]
example_id: sample-hyperframes-workflow
example_name: "Hyperframes · AI workflow video"
example_format: markdown
example_tagline: "8 auto-playing frames, with progress bar + metadata"
example_desc: "Cinematic animation script, ready to feed directly into Remotion to render an mp4"
example_source_url: "https://github.com/heygen-com/hyperframes"
example_source_label: "heygen-com/hyperframes"
od:
  mode: video
  surface: video
  scenario: video
  featured: 0.13
  upstream: "https://github.com/nexu-io/html-anything"
  preview:
    type: html
    entry: index.html
    reload: debounce-100
  design_system:
    requires: false
  example_prompt: "Use the \"Hyperframes Video Script\" template to turn my content into a \"Hyperframes / Remotion-compatible continuous frame animation, auto-plays\" video. Keep the template's visual signature, use real content and data, and avoid lorem ipsum and placeholder images."
---

[Template: Hyperframes Video Frames]
- Output N consecutive `<section class="frame">` elements, each `w-[1920px] h-[1080px]`; N is determined by the information density of [user content] (short scripts start at 6-10 frames, longer scripts should have more; each frame carries only one shot/concept).
- Each frame expresses one shot/concept: text + visual composition (centered composition / golden ratio / rule of thirds).
- Each frame has a hidden marker at the bottom `<!-- frame:N duration:3000 transition:fade -->` for downstream Remotion / Hyperframes rendering scripts to read.
- Add JavaScript at the top for autoplay: advance to the next frame every 3 seconds, also supporting click / arrow-key control; show a progress bar in the corner.
- Frame 1 is the hook (a data point / a counterintuitive fact / a question), frames 2-N build the argument, and the last frame is the conclusion + CTA.
- Type size is huge (text-9xl), one sentence is enough -- don't pile on text.
- Use one unified cinematic color scheme (dark background + 1 neon accent color).
- End the output with a short comment `<!-- HYPERFRAMES_META: ... -->` containing JSON metadata for each frame's duration / transition / sceneSummary, for later conversion to Remotion.
