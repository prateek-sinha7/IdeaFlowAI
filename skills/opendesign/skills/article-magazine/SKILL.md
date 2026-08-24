---
name: article-magazine
zh_name: "Magazine Article"
en_name: "Magazine Article"
emoji: "📖"
description: "Huashu / huashu-md-html-inspired magazine article layout for turning Markdown or notes into a polished long-form HTML essay."
category: article
scenario: marketing
aspect_hint: "A4 / long page"
featured: 11
tags: ["blog", "essay", "newsletter", "newsletter platform", "blog post", "article"]
example_id: sample-article-trq212-html
example_name: "Magazine Article · HTML Replaces Markdown"
example_format: markdown
example_tagline: "Inspired by a tweet from @trq212"
example_desc: "An extended commentary on 'HTML > Markdown in the age of AI', with annotations on the original tweet and clickable links"
example_source_url: "https://x.com/trq212/status/2052809885763747935"
example_source_label: "@trq212 / x.com"
od:
  mode: prototype
  surface: web
  platform: desktop
  scenario: marketing
  featured: 0.03
  upstream: "https://github.com/nexu-io/html-anything"
  preview:
    type: html
    entry: index.html
    reload: debounce-100
  design_system:
    requires: false
  example_prompt: "Use the 'Magazine Article' template to turn my content into a 'Huashu / huashu-md-html-inspired magazine article layout for turning Markdown or notes into a polished long-form HTML essay'. Keep the template's visual signature, use real content and data, and avoid lorem ipsum and placeholder images."
---

[Template: Magazine Article]
- Top hero: large title (text-5xl/6xl) + optional subtitle + author / read time / date metadata.
- Body: single column, max width around 700px, centered. Paragraphs use `text-lg leading-relaxed text-neutral-700 dark:text-neutral-300`.
- H2 / H3 headings use a serif font, creating visual contrast with the body text.
- Blockquotes use a bold accent-colored left border + italics.
- Code blocks: rounded corners + dark background + light text, showing a language tag.
- List items use custom bullets (small squares / accent-colored dots).
- Sections are separated by `<hr>`, styled as a small centered ornament.
- End the article with a simple "if you found this useful, please share" call-to-action card.
