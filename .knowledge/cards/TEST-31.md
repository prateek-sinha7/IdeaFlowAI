---
id: TEST-31
type: test
status: done
area: [sse, workflow, artifacts]
summary: >-
  TS-P — Generic deliverable & iframe security (custom/unknown mimetype) —
  SECURITY-CRITICAL
source: .planning/TEST-REGISTER.md#ts-p-generic-deliverable-iframe-security-custom
covers: [TS-P-01, TS-P-02, TS-P-03, TS-P-04, TS-P-05, TS-P-06]
---

### TS-P — Generic deliverable & iframe security (custom/unknown mimetype) — **SECURITY-CRITICAL**

`GenericDeliverablePreview` dispatches on **`deliverable_mimetype` (lowercased), never a workflow name (SC-001)**. This is the ISS-021 + Phase 18 custom-deliverable path and the highest-value security assertion in the register.

| ID | Title | Steps | Expected (exact) | Status |
|---|---|---|---|---|
| TS-P-01 | **Custom HTML in sandboxed iframe** | run `custom`/SC-001 workflow producing `text/html` | `iframe[title="Deliverable Preview"]` with **`sandbox="allow-scripts"` EXACTLY — NO `allow-same-origin`**, `srcDoc=<html>`, no `allow=` attr; renders the live HTML | ✅ (V2: live "Habit Tracker") |
| TS-P-02 | Markdown escaped | `text/markdown` deliverable | `MarkdownPreview` (NOT an iframe); raw `<script>`/`<iframe>`/`<img onerror>` in the markdown is **escaped to literal text** (no `rehype-raw`) — assert no live nodes injected | 🟢 (security.test) / 🔴 UI |
| TS-P-03 | Zip → IDE | `application/zip` deliverable | renders `AppBuilderPreview` bundle | 🔴 |
| TS-P-04 | Unknown → download card | any other mimetype | `Deliverable ready` + `This deliverable ({mimetype}) can be downloaded from the Files tab.` + `Download {filename}` button (triggers real browser download); **no iframe** | 🔴 |
| TS-P-05 | **iframe sandbox matrix** | inspect each iframe | generic HTML = `allow-scripts` only; non-od PPT = `allow-scripts` only; **od_ppt** = `allow-scripts allow-same-origin`; **prototype** = `allow-scripts allow-same-origin` (`src=blobUrl`). Assert each exactly | 🟢 (component tests) / 🔴 UI |
| TS-P-06 | XSS payload contained | inject `<script>parent.location=…</script>` into a custom HTML deliverable | script cannot reach parent (no same-origin); no navigation/cookie theft | 🔴 |
