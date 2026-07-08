# Third-Party Notices

This product includes mechanisms **derived from** the following third-party
project. Each is a **clean-room reimplementation** written from a behavioral
specification — there is **no build-time dependency on**, and **no bundled copy
of**, the upstream source. Attribution is provided per the upstream license.

---

## nexu-io/open-design

- **Upstream:** https://github.com/nexu-io/open-design
- **License:** Apache License 2.0 (https://www.apache.org/licenses/LICENSE-2.0)
- **Relationship:** derived / clean-room reimplementation (no source copied, no
  build-time dependency). Decision reference: D-09 (no external chat framework —
  revive the in-repo kit and BORROW these mechanisms WITH attribution).

### Borrowed mechanisms (open-design "borrow list" items 1–7)

| # | Mechanism | Upstream reference (file:line) | Local reimplementation |
|---|-----------|--------------------------------|------------------------|
| 1 | `partial-json` repair (`repairJsonPrefix` / `parsePartialJson`) — tolerant repair + parse of a truncated JSON prefix | `runtime/partial-json.ts:16-93` | `frontend/src/components/chat/runtime/partial-json.ts` |
| 2 | `extractStreamingJsonString` — single named-string-field extractor over an open JSON fragment | `AssistantMessage.tsx:2786` | `frontend/src/components/chat/runtime/streaming-json.ts` |
| 3 | Tool-renderer registry — map a generic tool kind to its render component | `AssistantMessage.tsx` (tool renderer dispatch) | `frontend/src/components/chat/runtime/tool-renderers.tsx` |
| 4 | `buildBlocks` events→blocks reducer — coalesce an ordered agent-event array into merged render blocks | `AssistantMessage.tsx:3148` | `frontend/src/components/chat/runtime/buildBlocks.ts` |
| 5 | Scroll/anchor + measured virtualizer (>80 messages) | open-design transcript scroll/virtualizer | `frontend/src/components/chat/runtime/useMeasuredVirtualWindow.ts` |
| 6 | Nonce'd deep-link seam — result cards deep-link into the run tabs | open-design deep-link seam | `frontend/src/hooks/useTabDeepLink.ts` |
| 7 | `ThinkingBlock` / todo / file-ops blocks | open-design block components | `frontend/src/components/chat/blocks/ThinkingBlock.tsx`, `TodoCard.tsx`, `FileOpsSummary.tsx` |

All seven mechanisms have shipped: **#1, #2, #4** in plan 31-01; **#3, #5, #7**
in plan 31-02; **#6** in plan 31-03.

Every local reimplementation module carries the header comment:

```
Adapted from nexu-io/open-design (Apache-2.0) — see /THIRD-PARTY-NOTICES.md
```
