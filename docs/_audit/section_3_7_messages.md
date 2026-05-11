# Phase B Audit — §3.7 Messages (W50–W53)

**Scope:** `frontend/src/components/chat/MessageBubble.tsx`, `frontend/src/components/chat/ChatPanel.tsx`, `frontend/src/hooks/useTextToSpeech.ts`, `backend/app/api/chats.py` (PUT `/chats/{id}/messages` only), `backend/app/models/chat.py` (`Message` model).
**Branch:** `infra-agent-integration`
**Status verdict:** **Dead code in the live shell.** Every issue below is reported against the file regardless of mount status — but the practical blast radius is near-zero today because nothing renders these components in the deployed dashboard. Severities are scored "as-if-wired"; the live-impact column qualifies that.

---

## Mount / Wiring Reality Check (foundational, applies to all findings)

| Artefact | Live consumption today |
|---|---|
| `MessageBubble` | Imported only by `ChatPanel.tsx:7`. No external importer. |
| `ChatPanel` | Zero importers across `frontend/src/`. Verified by `grep -rn "ChatPanel\|MessageBubble"`. |
| `onRegenerateMessage` / `onEditMessage` | Declared on `ChatPanelProps` (`ChatPanel.tsx:20-21`) but **not declared on `DashboardLayoutProps`** (`DashboardLayout.tsx:20-46`); `dashboard/page.tsx` never supplies them. |
| `messages: ChatMessage[]` on `DashboardLayout` | Prop is accepted (`DashboardLayout.tsx:22, :52`) but **never read or rendered** inside the layout (count = 2 occurrences only: the type declaration and destructure). |
| `useTextToSpeech` | Only consumer is `MessageBubble.tsx:85` — dies with the bubble. |
| Backend message mutations | `chats.py` exposes only POST/GET/DELETE on sessions plus PUT append at `chats.py:162-196`. No `PATCH /messages/{id}`, no `DELETE /messages/{id}`, no regenerate endpoint. |
| `Message` model audit columns | `chat.py:34-49` defines only `id, chat_session_id, role, content, created_at`. No `edited_at`, `deleted_at`, version, `parent_id`. Migration `0001_initial_schema.py:117-125` matches. |
| Frontend API client | `lib/api.ts` exposes `addMessage` (PUT append) only — no edit/regenerate methods. |

**Roadmap signal:** `docs/WORKFLOWS.md` §3.7 lists W50–W53 as planned workflows and already contains the Phase A note that "**The bubble UI and all four W50-W53 interactions therefore exist as built-but-unmounted code in the current app shell.**" There is no other roadmap document.

**Deletion cost estimate (informational, not a recommendation):**
- `MessageBubble.tsx` (392 LOC) + `ChatPanel.tsx` (291 LOC) + `useTextToSpeech.ts` (113 LOC) = ~796 LOC of unreachable UI logic.
- Removing them also lets `messages: ChatMessage[]` drop from `DashboardLayoutProps` and the dashboard's `messages` state slice — but that state is currently wired into `addMessage` calls and WebSocket stream accumulation in `dashboard/page.tsx`, so removal needs care to not break workflow-run history persistence.
- **Conservative path:** mark dead code with TODO and keep until §3.6/§3.7 of the UX roadmap finalises whether the chat bubble UI returns.

---

## CRITICAL

_(none — every issue below is gated by the dead-code reality. If the components are mounted later, several findings here promote.)_

---

## HIGH

### H1. Backend completely lacks edit / delete / regenerate endpoints (planned features blocked)
- **Files:** `backend/app/api/chats.py:162-196` (only PUT append exists), `backend/app/models/chat.py:34-49`, `backend/alembic/versions/0001_initial_schema.py:117-125`.
- **Issue:** Even if `onEditMessage`/`onRegenerateMessage` were wired in the UI, the backend has nowhere to send the call. There is no `PATCH /api/chats/{chat_id}/messages/{message_id}`, no `DELETE`, and the `Message` table has no soft-delete or edit-history columns (`id, chat_session_id, role, content, created_at` only).
- **Live impact:** None today (UI unmounted). On wiring, edits will silently mutate via re-send (`addMessage` PUT) creating a *new* row, which loses the original — there is no immutability or audit trail.
- **Severity reasoning:** HIGH (as-if-wired) because correct edit/regenerate semantics require schema + endpoint work *before* the FE can be safely re-mounted. LOW today.

### H2. Edit path has no concurrency / re-streaming guard
- **Files:** `MessageBubble.tsx:103-108`.
- **Issue:** `handleEditSubmit` fires `onEdit?.(message.id, editContent.trim())` unconditionally on Enter, with no check that the original assistant turn has finished streaming, and no rule that editing a *user* turn must invalidate the assistant response after it. `isStreaming` is checked only for hiding the assistant action bar (`:338`), not for blocking edit submits on the prior user bubble.
- **Live impact:** None today. On wiring, a user can press Enter on an edit textarea while the assistant for that exchange is still streaming, producing a race between the in-flight stream and the edit-driven resend.
- **Severity reasoning:** HIGH (as-if-wired) because state model is unspecified. LOW today.

### H3. Conditional `useTextToSpeech` hook usage (call vs. render gate)
- **Files:** `MessageBubble.tsx:85` (call), `:360-372` (render gate).
- **Issue:** The hook is always called (good — no conditional hook violation), but `isSupported` is initialised `false` and flipped to `true` only inside a post-mount `useEffect` (`useTextToSpeech.ts:21-25`). This is fine, but combined with `getVoices()` returning `[]` on first call in some browsers (`useTextToSpeech.ts:30`, no `voiceschanged` listener wired), the first `speak()` invocation right after mount will fall through to "no voice" and use the engine default — which on Linux/Chromium can be an unintelligible robot voice. There is **no `voiceschanged` event subscription** to refresh the voice list.
- **Live impact:** None today. On wiring, first-use TTS will frequently get the wrong voice on macOS Chrome (voices populate async). Accessibility regression.
- **Severity reasoning:** HIGH (accessibility) as-if-wired. LOW today.

---

## MEDIUM

### M1. Clipboard copy includes `<thinking>...</thinking>` blocks (information disclosure / UX)
- **Files:** `MessageBubble.tsx:121-129` (`handleCopy`), `:55` (stripping done only for display in `parseThinkingBlocks`), `:90-93` (`displayContent` = raw content).
- **Issue:** `displayContent` is the *raw* `message.content`, which for assistant turns in "thinking" mode (`backend/app/agents/modes.py:9-11`) contains chain-of-thought wrapped in `<thinking>` tags. The UI hides them in a collapsible panel (`:286-318`) but the clipboard write copies the unmodified string. A user expecting to copy "the answer" pastes the CoT blob with XML tags.
- **Live impact:** None today (UI unmounted). On wiring: not a security vulnerability per se — the user generated the content, and CoT is shown in the UI panel anyway — but is **leakage when forwarded** (pasted into another chat, ticket, doc). Trivial to address by copying `mainContent` instead of `displayContent`.
- **Severity reasoning:** MEDIUM (as-if-wired) confidentiality / UX. LOW today.

### M2. Clipboard write fails silently — no user feedback on permission denial
- **Files:** `MessageBubble.tsx:121-129`.
- **Issue:** `try { await navigator.clipboard.writeText(...) } catch (err) { console.error("Failed to copy:", err) }`. No toast, no fallback (e.g. `document.execCommand("copy")` on legacy `textarea`), no `setCopied(false)` state mutation differentiating "not copied" from "copied". The icon stays a `<Copy>` glyph and the user has no idea the click failed. Browsers reject `navigator.clipboard.writeText` in insecure contexts and on permission denial.
- **Live impact:** None today. On wiring: silent failure on Safari iOS / Firefox-strict / insecure-origin previews.
- **Severity reasoning:** MEDIUM (as-if-wired) UX. LOW today.

### M3. TTS markdown-stripping regex chain is incomplete and lossy
- **File:** `useTextToSpeech.ts:60-70`.
- **Issues with each step:**
  - `.replace(/#{1,6}\s/g, "")` — strips heading marker but leaves the text. OK. However, list markers (`- `, `1. `) and blockquotes (`> `) survive; the synth reads "dash dash dash item".
  - `.replace(/\*\*(.*?)\*\*/g, "$1")` and `.replace(/\*(.*?)\*/g, "$1")` — non-greedy. For nested or unmatched `**a*b**` patterns these mis-strip. Works for typical content; brittle.
  - `.replace(/`{1,3}[^`]*`{1,3}/g, "")` — **destroys** all inline code AND fenced code blocks (replaces with empty string, so a message "Use `npm install` to install" reads "Use to install"). Semantically lossy. Also fails on fenced blocks that contain backticks themselves, and on triple backticks with a language hint like ` ```python ` because `[^`]*` will match across newlines and consume hint+code.
  - `.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")` — link `[text](url)` → `text`. OK.
  - `.replace(/<thinking>[\s\S]*?<\/thinking>/g, "")` — strips CoT. OK.
  - `.replace(/<[^>]+>/g, "")` — strips remaining HTML. Works but greedy across attribute values that contain `>` is rare; acceptable.
  - `.replace(/\n{2,}/g, ". ")` then `.replace(/\n/g, " ")` — paragraph→sentence separation. Reasonable.
- **Live impact:** None today. On wiring: code blocks are *silently dropped* — users with screen-reader needs hearing code-heavy assistant messages will miss content entirely.
- **Severity reasoning:** MEDIUM (accessibility) as-if-wired. LOW today.

### M4. Voice preference list is hard-coded with no user override
- **File:** `useTextToSpeech.ts:34-50`.
- **Issue:** `preferredNames = ["Google US English", "Samantha", "Alex", "Microsoft Zira", "Microsoft David"]` — Anglo-American only, no user setting, no locale awareness (e.g. ignores `navigator.language`). A French/German/Hindi/RTL user with appropriate platform voices gets either an `en-*` fallback or `voices[0]` (`useTextToSpeech.ts:48-49`).
- **Live impact:** None today. On wiring: i18n / accessibility gap; no UI surface exists to expose voice selection.
- **Severity reasoning:** MEDIUM (i18n + a11y) as-if-wired. LOW today.

### M5. Backend PUT append accepts arbitrary `role` from client
- **File:** `chats.py:28-33` (`AddMessageRequest`), `chats.py:162-196` (`add_message`).
- **Issue:** `AddMessageRequest.role: str = "user"`. There is no enum validation; the client can persist a message with `role="system"`, `role="admin"`, `role="anything"`. The DB column accepts any string (`chat.py:43`). Phase A scope is "PUT /chats/{id}/messages only", and this is the only mutation path — but it's open to role spoofing.
- **Live impact:** Modest. A malicious authenticated user can poison their own chat history with fake system / assistant turns, which then become input to subsequent LLM calls (prompt-injection vector if those turns are replayed as context). The blast radius is per-user (the chat is gated by `user_id`), but the injection scenario is real.
- **Severity reasoning:** MEDIUM (per-user prompt injection / data integrity). This is the only finding that has live impact today, because the endpoint is wired (`lib/api.ts:214-225`).

---

## LOW

### L1. Dead-code surface: `MessageBubble` + `ChatPanel` + `useTextToSpeech` (~796 LOC)
- **Files:** `MessageBubble.tsx:1-392`, `ChatPanel.tsx:1-291`, `useTextToSpeech.ts:1-113`.
- **Issue:** Confirmed unreferenced by any live page. Maintenance / mental-model tax; bundle cost (next.js may tree-shake — verify).
- **Mitigation options:** delete; or mount; or annotate with a `@deprecated`/`// DEAD CODE — unmount of W50-W53` banner at the top.

### L2. `DashboardLayout` accepts `messages` prop it never reads
- **Files:** `DashboardLayout.tsx:22, :52`. `grep -c "messages"` = 2 (the type + the destructure, nothing else).
- **Issue:** Dead prop. The actual `messages` state lives in `dashboard/page.tsx:25` and is fed into `addMessage` API calls + WebSocket accumulation only; never consumed for rendering.
- **Severity:** LOW (waste, not a bug).

### L3. Regenerate has no documented semantics
- **Files:** `MessageBubble.tsx:374-382`, `ChatPanel.tsx:261`.
- **Issue:** `onRegenerate(message.id)` fires the message ID — but the dashboard would need to: (a) walk backwards to find the preceding user turn, (b) re-invoke WebSocket send with same context, (c) decide whether to keep, replace, or version the original assistant turn. None of this is specified. The closest existing pattern is `ChatPanel.tsx:235-248` (error-retry resends last user message) — but that's a *retry on error*, not a regenerate.
- **Token cost:** Re-sending the full conversation history adds N×tokens per regenerate click. No throttle, no confirmation.
- **Severity:** LOW (dead code) / MEDIUM (as-if-wired ambiguity).

### L4. Edit submit ignores empty-trim equivalence vs. whitespace-only change
- **Files:** `MessageBubble.tsx:103-108`.
- **Issue:** `editContent.trim() && editContent !== message.content` — uses *un-trimmed* comparison on the right side. If the user adds a trailing space and presses Enter, `editContent.trim()` is truthy and `editContent !== message.content` is also true (string differs by whitespace), so a no-op resend fires. Minor.

### L5. Edit textarea resets to original content on Esc but not on outside click
- **Files:** `MessageBubble.tsx:114-118`.
- **Issue:** Esc → reset + close. Click-outside / blur → no handler. The `motion.div` parent has `onMouseLeave={() => setShowActions(false)}` (`:152-153`) but the textarea stays editable until Enter or Esc, even if the user mouses-away. Acceptable; flagged only because it can confuse users.

### L6. `parseThinkingBlocks` regex is greedy across multiple `<thinking>` blocks (intended)
- **Files:** `MessageBubble.tsx:43-61`.
- **Issue:** `/<thinking>([\s\S]*?)<\/thinking>/g` non-greedy across blocks. OK. But the join uses `"\n\n"` between matches (`:58`), losing block boundaries / order metadata. Cosmetic.

### L7. `setTimeout(() => setCopied(false), 2000)` not cleared on unmount
- **Files:** `MessageBubble.tsx:125`.
- **Issue:** If the bubble unmounts within 2 s of a copy, React will log a `setState on unmounted component` warning (React 18 has softened this, but the leak is real). No `useRef` to store the timer, no `clearTimeout` in any cleanup.
- **Severity:** LOW (cosmetic warning + transient leak).

### L8. TTS `useEffect` cleanup cancels speech but does not clear `utteranceRef`
- **Files:** `useTextToSpeech.ts:98-105`.
- **Issue:** On unmount, `window.speechSynthesis.cancel()` is called, but `utteranceRef.current` is not nulled. Not a leak in practice (the ref dies with the hook instance) but a noted style miss.

### L9. `setIsSpeaking(false)` on `utterance.onerror` swallows error info
- **Files:** `useTextToSpeech.ts:83`.
- **Issue:** No `console.error` / no user feedback when speech synthesis fails (network voice fetch error, OOM, etc.). User clicks Volume2 → nothing happens → no diagnostic.

### L10. ChatPanel error-message regex is permissive
- **Files:** `ChatPanel.tsx:217-228`.
- **Issue:** Regex `\[code:(\w+)\]` matches the *first* occurrence anywhere; a user-typed message containing `[code:foo]` would be mis-parsed. Only relevant if assistant prefixes "Error:" — low likelihood — but no `^` anchor.

### L11. ChatPanel auto-scroll runs on every `messages`/`streamingContent` change
- **Files:** `ChatPanel.tsx:68-70`.
- **Issue:** `scrollIntoView({ behavior: "smooth" })` on every stream chunk fights user-initiated scroll. No "user-has-scrolled-up" detection. Minor UX.

---

## TF / Infra Concerns

_(none in this section — this audit is FE + REST endpoint scope. No Terraform, Docker, IAM, or networking surfaces in scope.)_

---

## Code-Quality Notes (non-defect)

- **No `useState`-as-effect anti-patterns** observed (referenced in §3.4 SkillManager). The `useEffect`s here have legitimate side-effect bodies (`scrollIntoView`, `setIsSupported` from a guarded `typeof window`).
- **No conditional hook calls.** `useTextToSpeech` is invoked at the top of `MessageBubble` unconditionally. `useMemo` and `useState` calls are unconditional.
- **`useCallback` dependencies on `useTextToSpeech.ts:88, :96`** are correct (`isSupported`, `getPreferredVoice`).
- **`displayContent` selection (`MessageBubble.tsx:90-93`)** uses `isStreaming && streamingContent !== undefined`. The empty-string case (`streamingContent === ""`) correctly resolves to streaming mode — intentional.
- The `WORKFLOWS.md` Phase A section already flags two of the dead-code / wiring findings (M1-style and the dashboard prop wiring) — those items are mirrored here for completeness.

---

## Cross-references for fix-planning (no fixes applied — audit-only)

- If the W50-W53 surface is **kept and to be wired**: needs (a) `PATCH /api/chats/{chat_id}/messages/{message_id}` + soft-delete or version columns on `messages`; (b) `DashboardLayoutProps` extension with `onRegenerateMessage` / `onEditMessage`; (c) `useTextToSpeech` enhancement for `voiceschanged` + user voice preference; (d) clipboard sanitiser that uses `mainContent`; (e) role-enum validation on `AddMessageRequest.role`.
- If the W50-W53 surface is **to be deleted**: drop `MessageBubble.tsx`, `ChatPanel.tsx`, `useTextToSpeech.ts`, the `onRegenerate*` callbacks on `ChatPanelProps`, and the unused `messages` prop on `DashboardLayoutProps`. The `messages` state in `dashboard/page.tsx` itself must remain (it persists WS-streamed turns via `addMessage`).
