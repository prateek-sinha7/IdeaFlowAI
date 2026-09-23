# DOM evidence: hook cards have no keyboard affordance

Captured via `browser_evaluate` on `http://localhost:3000/library?tab=hooks` (qa-admin session):

```js
document.querySelectorAll('.cursor-pointer.p-4')
```

returned all 8 hook cards, each with:

```json
{ "tabindex": null, "role": null, "onkeydown": false }
```

for every one of: Design Quality Check X, Quality Gate, Config Protection,
GateGuard: Fact Force, Session Context Loader, Console.log Check,
Format + Typecheck on Stop, Session State Persistence.

Separately, `document.querySelectorAll('a,button,input,[tabindex]')` around the card grid
region confirms the grid contributes ZERO entries to that list — only the search input, the
Agents/Skills/Hooks tabs, and the 5 category-filter buttons are keyboard-focusable in that
section. The card grid (the page's only way to reach hook detail) is entirely invisible to
Tab-based keyboard navigation and to assistive tech that relies on focusable/interactive
semantics (no `role="button"`, no `tabindex="0"`, no `onKeyDown` for Enter/Space).

This was reproduced identically across multiple fresh page loads.
