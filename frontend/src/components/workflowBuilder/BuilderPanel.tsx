"use client";

/**
 * BuilderPanel: the chat column of the AI Workflow Builder (Req 3.1, 3.3, 14.1).
 *
 * At 1280 px and wider it is a 360 px column docked under the Composer header,
 * left of the canvas, the same width as the run chat lane. Below that it is an
 * overlay with a backdrop, a focus trap and Escape to collapse, and it does not
 * shrink the canvas. Opening it puts the cursor in the message box. When it
 * closes, focus returns to the AI button (`returnFocusRef`). A collapsed panel
 * leaves a 40 px rail at the left edge with an icon that reopens it; the host
 * keeps the session stream and state, so a running turn continues (Req 3.2).
 *
 * The body (transcript, picker, input) comes in as `children`.
 */

import { PanelLeftOpen } from "lucide-react";
import {
  useEffect,
  useRef,
  useSyncExternalStore,
  type KeyboardEvent,
  type ReactNode,
  type RefObject,
} from "react";

import { BuilderPanelHeader, type BuilderPanelHeaderProps } from "./BuilderPanelHeader";

/** Viewport width from which the panel docks instead of overlaying (Req 3.1, 3.3). */
export const DOCK_MIN_WIDTH_PX = 1280;
const DOCK_QUERY = `(min-width: ${DOCK_MIN_WIDTH_PX}px)`;

/** The panel's element id; the Composer's AI button names it in `aria-controls`. */
export const BUILDER_PANEL_ID = "ai-workflow-builder-panel";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "textarea:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(", ");

export interface BuilderPanelProps {
  collapsed: boolean;
  header: Omit<BuilderPanelHeaderProps, "onCollapse">;
  onCollapse: () => void;
  /** Reopens the panel from the collapsed rail's icon. */
  onExpand: () => void;
  /** The AI button; it gets focus back when the panel closes. */
  returnFocusRef?: RefObject<HTMLElement | null>;
  children: ReactNode;
}

function subscribeDock(onChange: () => void): () => void {
  const query = window.matchMedia(DOCK_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

function useIsDocked(): boolean {
  return useSyncExternalStore(
    subscribeDock,
    () => window.matchMedia(DOCK_QUERY).matches,
    () => true,
  );
}

export function BuilderPanel({
  collapsed,
  header,
  onCollapse,
  onExpand,
  returnFocusRef,
  children,
}: BuilderPanelProps) {
  if (collapsed) return <CollapsedRail onExpand={onExpand} />;
  return (
    <OpenPanel header={header} onCollapse={onCollapse} returnFocusRef={returnFocusRef}>
      {children}
    </OpenPanel>
  );
}

/** The slim left-edge strip left behind when the panel is collapsed; its icon reopens the panel. */
function CollapsedRail({ onExpand }: { onExpand: () => void }) {
  return (
    <div
      data-testid="builder-collapsed-rail"
      className="flex h-full w-10 flex-none flex-col items-center border-r border-line-divider bg-surface-warm pt-2.5"
    >
      <button
        type="button"
        onClick={onExpand}
        aria-label="Open builder panel"
        title="Open builder panel"
        aria-expanded={false}
        className="grid h-7 w-7 place-items-center rounded-[8px] text-ink-500 transition-colors hover:bg-surface-paper hover:text-ink-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
      >
        <PanelLeftOpen className="h-4 w-4" strokeWidth={1.7} aria-hidden="true" />
      </button>
    </div>
  );
}

function OpenPanel({
  header,
  onCollapse,
  returnFocusRef,
  children,
}: Omit<BuilderPanelProps, "collapsed" | "onExpand">) {
  const docked = useIsDocked();
  const panelRef = useRef<HTMLElement>(null);
  // Closing (unmount) hands focus back to the AI button (design 3.10.9).
  useEffect(() => {
    // The AI button lives outside the panel, so its node is stable while the panel is open.
    const target = returnFocusRef?.current ?? null;
    return () => {
      target?.focus?.();
    };
  }, [returnFocusRef]);

  // Opening puts the cursor in the message box. The overlay falls back to its first
  // control (or itself) so focus is always inside the trap; the docked column only
  // moves focus when it has a box to move it to.
  useEffect(() => {
    const panel = panelRef.current;
    if (!panel) return;
    const box = panel.querySelector<HTMLTextAreaElement>("textarea:not([disabled])");
    if (box) {
      box.focus();
      return;
    }
    if (!docked) (panel.querySelector<HTMLElement>(FOCUSABLE_SELECTOR) ?? panel).focus();
  }, [docked]);

  const handleKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (docked || event.defaultPrevented) return;
    const panel = panelRef.current;
    if (!panel) return;

    if (event.key === "Escape") {
      // A nested dialog (delete confirmation) handles its own Escape.
      if (panel.querySelector('[role="dialog"]')) return;
      onCollapse();
      return;
    }
    if (event.key !== "Tab") return;

    const focusable = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
    if (focusable.length === 0) {
      event.preventDefault();
      panel.focus();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = document.activeElement;
    if (event.shiftKey && (active === first || active === panel)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  };

  const panel = (
    <aside
      ref={panelRef}
      id={BUILDER_PANEL_ID}
      aria-label="AI workflow builder"
      role={docked ? "complementary" : "dialog"}
      aria-modal={docked ? undefined : true}
      tabIndex={-1}
      onKeyDown={handleKeyDown}
      className={[
        "flex h-full w-[360px] max-w-full flex-col bg-surface-warm font-sans focus:outline-none",
        docked
          ? "flex-shrink-0 border-r border-line-divider"
          : "relative z-50 border-r border-line-divider shadow-[var(--elevation-modal)]",
      ].join(" ")}
    >
      <BuilderPanelHeader {...header} onCollapse={onCollapse} />
      <div className="flex min-h-0 flex-1 flex-col">{children}</div>
    </aside>
  );

  if (docked) return panel;

  return (
    <div className="fixed inset-0 z-40 flex">
      <div
        data-testid="builder-backdrop"
        className="absolute inset-0 bg-[var(--scrim)]"
        onClick={onCollapse}
        aria-hidden="true"
      />
      {panel}
    </div>
  );
}

export default BuilderPanel;
