---
name: html-page
display_name: HTML Page
description: How to write a single self-contained HTML page. Use when the task wants one complete page file, not a fragment or a description of one.
category: workflow
isBeta: false
tags:
- html
- css
- page
---

How to write one self-contained HTML page — work in this order:

1. Write the full document: `<!doctype html>` through `</html>`, with a
   `<head>` and a `<body>`.
2. Put all styling in one `<style>` block in the `<head>`. Inline CSS only —
   no external stylesheets, no CSS frameworks, no CDN links.
3. Do not link or load anything external: no scripts, no fonts, no images by
   URL, no JavaScript frameworks. The page must render offline, as-is.
4. Write the file with the file-writing tool — do not describe the page or
   paste it into chat instead of writing it.

- The shape, with placeholders — never copy these words, only the shape:
  `<!doctype html><html><head><style>/* rules */</style></head><body>
  <content></body></html>`
