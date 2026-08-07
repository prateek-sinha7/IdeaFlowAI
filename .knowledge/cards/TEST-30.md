---
id: TEST-30
type: test
status: done
area: [workflow, artifacts]
summary: >-
  TS-O — Deliverable preview by workflow type (PreviewPanel dispatch)
source: .planning/TEST-REGISTER.md#ts-o-deliverable-preview-by-workflow-type-previe
covers: [TS-O-01, TS-O-02, TS-O-03, TS-O-04, TS-O-05, TS-O-06, TS-O-07, TS-O-08]
---

### TS-O — Deliverable preview by workflow type (PreviewPanel dispatch)

Header `Generating...`/`Results`/`Preview` (state-dependent). Tabs `Preview`/`Files`/`Thinking`. `renderType` normalizes revisions/od-aliases; `KNOWN_RENDER_TYPES=[user_stories,ppt,prototype,app_builder]`; **`custom` is deliberately NOT known → generic channel (TS-P).**

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-O-01 | Empty | before content | `Output will appear here` (exact) | ✅ |
| TS-O-02 | User stories | complete a `user_stories` run | `UserStoryPreview`: sticky `Product Backlog`, stats `Epics/Stories/Points/Sprints`, priority pills `{n} Must-have`/`Should-have`/`Nice-to-have`, epic toggles, stories with bolded `Given`/`When`/`Then`, `Copy MD` | 🔴 |
| TS-O-03 | App builder IDE | complete `app_builder` | `AppBuilderPreview`: file-tree explorer (search `Search files...`, `Collapse/Expand all`), `{n} files` badge, `Full Screen`, `Download ZIP` (→ `Zipping...`), code viewer with line numbers; **121-file tree** rendered in campaign | ✅ (S04) |
| TS-O-04 | PPT deck | complete `od_ppt` | `iframe[title="Slide Deck Preview"]` renders the deck (`<!DOCTYPE html>`, `<section class="slide">×5`) — **NOT** QA narration (ISS-001 fix); `Download` (od → presentation.html / else `/api/runs/export-pptx` → `Exporting…`) + `Full Screen` | ✅ (S03; 18,661-char deck) |
| TS-O-05 | Prototype live app | complete `od_prototype` | `iframe[title="Prototype Preview"]` `src=<blobUrl>` renders the live app; browser-chrome bar `prototype.preview`; zoom controls; `Tweaks`/`Source`/`Open` toggles | ✅ |
| TS-O-06 | Tabs switch | click `Files` / `Thinking` | Files tab (TS-O-07); Thinking tab (TS-J); ~150ms AnimatePresence transition | 🔴 |
| TS-O-07 | Files tab | after a run | empty `No files available` + `Run a workflow to generate downloadable files`; else `{n} file[s] available` + `Download All`; app_builder sections `Project Download`/`Source Code Files`/`Agent Outputs ({n})` | 🔴 |
| TS-O-08 | Copy button | `hasContent` | `title="Copy"` copies `activeContent`, green check for 2000ms | 🔴 |
