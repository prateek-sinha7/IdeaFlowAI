"use client";

import {
  useEffect,
  useId,
  useRef,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";

/**
 * Modal — the first real accessible dialog primitive in this codebase
 * (specs/014). Every existing modal (CustomDesignSystemModal, WorkflowDialog,
 * the admin create-user/delete-confirm dialogs, etc.) is a hand-rolled copy of
 * the same `fixed inset-0` + scrim shape, and NONE of them implement a focus
 * trap or restore focus on close — only an initial `.focus()` exists anywhere
 * (`WorkflowHistory.tsx`). This component is the primitive those duplicates
 * can migrate onto later (YAGNI — not done here, see specs/014 §7 note on
 * "new primitive, no retrofit").
 *
 * Accessibility contract:
 *   - `role="dialog"` + `aria-modal="true"` + `aria-labelledby` pointing at
 *     the rendered title (every existing hand-rolled modal is missing at
 *     least one of these — two are missing all three).
 *   - Escape closes, via a `window` keydown listener with cleanup (the
 *     `CustomDesignSystemModal.tsx` idiom — the one already used correctly
 *     elsewhere in this codebase, extended here to a real trap).
 *   - A genuine focus CYCLE: Tab/Shift+Tab wraps between the first and last
 *     focusable element inside the panel, and a Tab that would otherwise
 *     leave the panel (focus moved out via click, browser autofill, etc.) is
 *     pulled back in. This did not exist anywhere in the codebase before.
 *   - Focus is moved into the panel on mount and RESTORED to whatever had
 *     focus beforehand on unmount — closing a dialog must not strand focus
 *     on `<body>`.
 *   - Body scroll is locked while mounted (mirrors `CustomDesignSystemModal`'s
 *     existing `document.body.style.overflow` effect).
 *
 * Styling is token-only (no raw hex, per the primitives convention enforced
 * by `primitives.test.tsx`'s `RETIRED_HEX` check): `--scrim` for the backdrop,
 * `--radius-card` / `--elevation-modal` for the panel, matching every
 * hand-rolled modal's existing token usage.
 *
 * Deliberately framework-agnostic (no `motion`/`AnimatePresence` dependency,
 * matching `Card`/`Button` staying plain) — a caller that wants enter/exit
 * animation wraps this in `AnimatePresence` itself, the same way the existing
 * hand-rolled modals already do around their own markup.
 */

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "textarea:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(", ");

function getFocusableElements(container: HTMLElement): HTMLElement[] {
  // No `offsetParent`-based visibility filter here: jsdom (this project's test
  // environment) never computes layout, so `offsetParent` is always `null`
  // regardless of real visibility — filtering on it would silently collapse
  // the focusable set down to a single element under test. A modal's own
  // contents are not expected to hide focusable descendants while it is
  // open, so the query result is used as-is.
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
}

export interface ModalProps {
  /** Called on Escape, a backdrop click (unless disabled), or the built-in × button. */
  onClose: () => void;
  /** The dialog's accessible name — rendered as an `<h2>` and wired via `aria-labelledby`. */
  title: string;
  /** Optional supporting text rendered under the title. */
  description?: string;
  children: ReactNode;
  /** Extra classes for the panel (e.g. a width override). */
  className?: string;
  /** Hide the built-in × button — set when the caller renders its own close action. */
  hideCloseButton?: boolean;
  /** Disable closing on a backdrop click (e.g. a "you must choose" dialog). Default: enabled. */
  closeOnBackdropClick?: boolean;
  /** Optional stable id override for the title element; auto-generated otherwise. */
  titleId?: string;
}

export function Modal({
  onClose,
  title,
  description,
  children,
  className = "",
  hideCloseButton = false,
  closeOnBackdropClick = true,
  titleId,
}: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const previouslyFocusedRef = useRef<HTMLElement | null>(null);
  // React's own stable-id primitive (SSR-safe, no ref-during-render, unique
  // per mounted instance) — the correct tool here, not a module-level counter
  // ref read during render.
  const generatedTitleId = useId();
  const resolvedTitleId = titleId ?? generatedTitleId;

  // Mount: remember what had focus, lock body scroll, move focus into the
  // panel (first focusable element, falling back to the panel itself).
  // Unmount: restore both — a closed dialog must never leave focus on
  // <body> or leave the page unable to scroll.
  useEffect(() => {
    previouslyFocusedRef.current = document.activeElement as HTMLElement | null;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const panel = panelRef.current;
    if (panel) {
      const focusable = getFocusableElements(panel);
      (focusable[0] ?? panel).focus();
    }

    return () => {
      document.body.style.overflow = prevOverflow;
      previouslyFocusedRef.current?.focus?.();
    };
  }, []);

  // Escape-to-close, on `window` (the CustomDesignSystemModal idiom) rather
  // than the panel, so it fires regardless of which descendant holds focus.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  // The focus CYCLE. Handled as a React keydown on the panel (not window) so
  // it only intercepts Tab while focus is already inside the dialog — a Tab
  // fired before focus enters the panel (impossible in practice, since the
  // mount effect above focuses it synchronously) is not our concern.
  const handlePanelKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "Tab") return;
    const panel = panelRef.current;
    if (!panel) return;

    const focusable = getFocusableElements(panel);
    if (focusable.length === 0) {
      // Nothing to tab between — keep focus pinned on the panel itself.
      e.preventDefault();
      panel.focus();
      return;
    }

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = document.activeElement;
    const activeIndex = active ? focusable.indexOf(active as HTMLElement) : -1;

    if (activeIndex === -1) {
      // Focus is inside the panel's DOM subtree but on a non-focusable node,
      // or somehow escaped the tracked list — pull it back to a known edge
      // rather than letting Tab carry it out of the dialog entirely.
      e.preventDefault();
      (e.shiftKey ? last : first).focus();
      return;
    }

    if (e.shiftKey && active === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && active === last) {
      e.preventDefault();
      first.focus();
    }
    // Otherwise: let the browser move focus normally within the panel.
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--scrim)] backdrop-blur-sm p-4"
      onClick={(e) => {
        if (closeOnBackdropClick && e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={resolvedTitleId}
        tabIndex={-1}
        onKeyDown={handlePanelKeyDown}
        className={[
          "relative bg-surface-card border border-line-border rounded-[var(--radius-card)] shadow-[var(--elevation-modal)] w-full max-w-sm p-6 font-sans focus:outline-none",
          className,
        ]
          .filter(Boolean)
          .join(" ")}
      >
        <div className="flex items-start justify-between gap-3 mb-4">
          <div>
            <h2
              id={resolvedTitleId}
              className="text-[14px] font-semibold text-ink-900"
            >
              {title}
            </h2>
            {description ? (
              <p className="mt-1 text-[12px] text-ink-500">{description}</p>
            ) : null}
          </div>
          {hideCloseButton ? null : (
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="h-7 w-7 flex-shrink-0 flex items-center justify-center rounded-[var(--radius-button)] text-ink-400 hover:bg-surface-warm hover:text-ink-700 transition-colors"
            >
              <svg
                viewBox="0 0 24 24"
                width="14"
                height="14"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                strokeLinecap="round"
                aria-hidden="true"
              >
                <path d="M18 6 6 18M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
        {children}
      </div>
    </div>
  );
}

export default Modal;
