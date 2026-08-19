---
name: ppt-keynote
zh_name: "Keynote-style Slides"
en_name: "Keynote-style Slides"
emoji: "🎬"
description: "Apple Keynote-level slides, one card per screen, arrow-key navigation"
category: slides
scenario: marketing
aspect_hint: "16:9 (1280×720)"
featured: 19
tags: ["slides", "deck", "presentation", "slideshow", "keynote"]
example_id: sample-ppt-html-anything
example_name: "Keynote PPT · Product Introduction"
example_format: markdown
example_tagline: "7 slides that explain a product clearly"
example_desc: "Apple Keynote-style product introduction, switch slides with ←/→"
od:
  mode: deck
  surface: web
  scenario: marketing
  featured: 19
  upstream: "https://github.com/nexu-io/html-anything"
  preview:
    type: html
    entry: index.html
    reload: debounce-100
  design_system:
    requires: false
  example_prompt: "Use the 'Keynote-style Slides' template to turn my content into 'Apple Keynote-level slides, one card per screen, arrow-key navigation'. Keep the template's visual signature, use real content and data, and avoid lorem ipsum and placeholder images."
---

[Template: Keynote-style Slides]
- Each slide is a `<section class="slide">`, 1280 wide by 720 tall overall, centered, with a gradient background.
- Keep each slide minimal: a large heading + 1-3 lines of supporting text; or a single data chart; or one punchy quote.
- Font sizes: heading `text-7xl font-semibold tracking-tight`, subheading `text-2xl text-neutral-500`.
- The first slide is the cover (topic + speaker / date); the last slide is "Thanks." or a call to action.
- Small indicator in the top-right corner: current page / total pages.
- Add a bit of JavaScript that listens for ArrowLeft / ArrowRight / spacebar to switch slides, and keeps the hash in sync (#/3).
- Use a fade-in animation between slides.
- Keep generous whitespace, align data cards with a grid layout, and keep colors restrained.
