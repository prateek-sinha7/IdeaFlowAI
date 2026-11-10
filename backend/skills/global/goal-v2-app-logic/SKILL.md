---
name: goal-v2-app-logic
display_name: Goal v2 — Working App Logic
description: "How to put real working logic into prototype.html: one app script that parses files, keeps state, generates output, copy and download. Use in goal_v2 build, integrate and fix for web tools."
category: workflow
isBeta: false
tags:
- javascript
- html
- web-tool
- xml
---

# Real logic in prototype.html

A web tool is still ONE self-contained page, `prototype.html`, styled by the active design system and
template. All behaviour lives in ONE `<script id="app">` at the end of `<body>`. The markup shows the
screens; the app script turns user input into state and output.

## What the app script may do

- Plain browser JavaScript, no libraries, no network: never `fetch`, `XMLHttpRequest`, `eval`, CDN
  scripts or web fonts.
- Browser APIs: `DOMParser`, `XMLSerializer`, `FileReader`, `File`, `Blob`, `URL.createObjectURL`,
  `navigator.clipboard`, `crypto.randomUUID`, `Intl`, `Date`.
- Change the page with `textContent`, attributes, `hidden`, `disabled`, `value` and class toggles that
  the design already defines. Build repeated rows from a `<template>` element with `cloneNode`, never
  from strings with `innerHTML`.
- Never add inline `style=` or colour literals; colours and spacing come from the design tokens.

## Storing nothing

When the requirements say the tool keeps nothing between sessions, do not use `localStorage`,
`sessionStorage` or cookies; everything starts empty on each load.

## Structure the script

1. `const S = {}` — the whole in-memory state (loaded raw text, parsed records, settings).
2. Pure functions, no DOM: `parseX(text) → {records…, errors, warnings}`, `rules(S) → {blocks,
   warnings}`, `generate(S) → string`. Keep them pure so tests can call them.
3. Handlers: input events → update `S` → call `render()`.
4. `render()` — writes computed text, `disabled`, `hidden` and states from `S`. One place, called after
   every change.
5. `window.__app = { state: () => structuredClone(S), parse…, generate… }` — read-only hooks for the
   acceptance tests.

## Loading input (file picker, drag-and-drop, paste)

One function `loadText(text, sourceName)` used by all three. File input: `FileReader.readAsText`. Drop
zone: `dragover` (preventDefault) + `drop` (`e.dataTransfer.files[0]`). Paste: a textarea plus a "Load"
button. Errors show next to the loader, with the parser's own message.

## XML

- Parse: `new DOMParser().parseFromString(text, 'application/xml')`; a `parsererror` element means not
  well-formed — show its text.
- Match by local name so any namespace prefix works: `el.localName`, and a helper
  `kids(el, name) = [...el.children].filter(c => c.localName === name)`; never `querySelector` with
  prefixes.
- Namespaces of generated messages are copied from the sample files (the version the samples use),
  never from memory of another schema version.
- Generate with string building, not DOM: ONE small writer `w.open(name, attrs)`, `w.text(name,
  value)`, `w.close()` that tracks depth and indents (the requirements' indent, e.g. three spaces),
  escapes `& < > " '`, and emits elements in the order the schema/requirements list them. Only the
  writer emits `<?xml version="1.0" encoding="UTF-8"?>` and the root.
- Check your own output: parse the generated string with DOMParser and show "well-formed" or the error.

## Copy and download

Copy: `navigator.clipboard.writeText(text)` and a short confirmation (with a fallback when the
clipboard is unavailable). Download: `URL.createObjectURL(new Blob([text], {type: 'application/xml'}))`
on a temporary `<a download="…">` created with `document.createElement` and never inserted into the
page. File names follow the requirements exactly.

## Determinism

Generated ids (TrxID, CorrelationID) come from one function so tests can stub them
(`window.__app.seed(…)`). Dates use the input's own time zone rules; amounts keep the input's decimals.
