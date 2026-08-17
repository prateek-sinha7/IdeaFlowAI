---
name: html-accessibility
display_name: HTML Accessibility
description: "Minimal accessibility fixes for a generated HTML page: lang attribute, one semantic heading, accessible emoji text. Use when writing or reviewing a screen-reader friendly HTML page."
category: specialist
isBeta: false
tags:
- accessibility
- html
- screen-reader
---

Minimal changes that make a page screen-reader friendly:

- `<html>` MUST have `lang="en"`.
- Use exactly one semantic heading (`<h1>`) for the page's main content — never a `<div>`
  or `<p>` standing in for a heading.
- An emoji conveys no meaning to a screen reader by itself. Wrap it with an accessible
  text equivalent, e.g. `<span role="img" aria-label="lighthouse">🗼</span>` — the
  `aria-label` names what the emoji shows, not the raw character.
