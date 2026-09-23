"use client";

/**
 * useEscapeToClose — the shared Escape-dismiss listener for modal dialogs.
 *
 * ISS-326: `WorkflowDialog` declared `role="dialog" aria-modal="true"` with no
 * keyboard dismiss path at all, because every modal in this codebase re-writes
 * (or omits) its own listener — the shape already inlined in
 * `components/workflow/prototype/TemplateDetailModal.tsx` and file-locally in
 * `library/LibraryPage.tsx`'s `useDetailModalKeyboard`. Lifted here so a modal
 * gets the behaviour by calling one hook instead of copy-pasting an effect.
 *
 * `enabled` mirrors a controlled dialog's own `open` prop: a hidden dialog must
 * not swallow Escape on behalf of whatever is actually on screen.
 */

import { useEffect } from "react";

export function useEscapeToClose(onClose: () => void, enabled = true) {
  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, enabled]);
}
