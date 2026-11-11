"use client";

/**
 * BuilderPanelHeader: title, conversation menu, New conversation and collapse
 * (Req 3.1, 12.1, 12.7, 12.8; design 3.10.1).
 *
 * One compact row, the height of the canvas config rail's header, so the two
 * headers line up across the canvas. The title is the open conversation's title,
 * or "Build with AI" when there is none. The Conversations menu floats over the
 * transcript: the first page of sessions with "Show more" for the next page. It
 * closes on Escape, on a choice and on a click outside it. Delete asks for
 * confirmation first and leaves the session untouched when the prompt is
 * dismissed (Req 12.7, 12.8). New conversation is disabled while a turn runs
 * [pending G-26].
 */

import { History, MessageSquarePlus, PanelLeftClose, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import type { SessionSummary } from "@/types/workflowBuilder";

export interface BuilderPanelHeaderProps {
  title?: string;
  sessions: SessionSummary[];
  currentSessionId: string | null;
  hasMoreSessions: boolean;
  /** Called when the menu opens, so the host can refresh the first page. */
  onMenuOpen?: () => void;
  onShowMore: () => void;
  onSelectSession: (sessionId: string) => void;
  /** Called only after the user confirms. */
  onDeleteSession: (sessionId: string) => void;
  onNewConversation: () => void;
  newConversationDisabled?: boolean;
  onCollapse: () => void;
}

const FOCUS_RING = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand";

const ICON_BUTTON_CLASS = `grid h-7 w-7 flex-none place-items-center rounded-[8px] text-ink-500 transition-colors hover:bg-surface-paper hover:text-ink-900 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-ink-500 aria-expanded:bg-surface-paper aria-expanded:text-ink-900 ${FOCUS_RING}`;

export function BuilderPanelHeader({
  title = "Build with AI",
  sessions,
  currentSessionId,
  hasMoreSessions,
  onMenuOpen,
  onShowMore,
  onSelectSession,
  onDeleteSession,
  onNewConversation,
  newConversationDisabled = false,
  onCollapse,
}: BuilderPanelHeaderProps) {
  const menuId = useId();
  const [menuOpen, setMenuOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<SessionSummary | null>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  // A click outside the menu and its toggle closes the menu.
  useEffect(() => {
    if (!menuOpen) return;
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node | null;
      if (target === null) return;
      if (menuRef.current?.contains(target) || toggleRef.current?.contains(target)) return;
      setMenuOpen(false);
    };
    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [menuOpen]);

  const toggleMenu = () => {
    const next = !menuOpen;
    setMenuOpen(next);
    if (next) onMenuOpen?.();
  };

  const handleMenuKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape" && menuOpen) {
      // Close the menu only; the panel's own Escape handling must not run.
      event.stopPropagation();
      setMenuOpen(false);
      toggleRef.current?.focus();
    }
  };

  const confirmDelete = () => {
    if (pendingDelete) onDeleteSession(pendingDelete.id);
    setPendingDelete(null);
  };

  return (
    <div className="relative flex-none border-b border-line-divider px-[18px] py-2.5">
      <div className="flex min-h-8 items-center gap-1">
        <Sparkles className="mr-1 h-3.5 w-3.5 flex-none text-brand" aria-hidden="true" />
        <h2
          title={title}
          className="min-w-0 flex-1 truncate font-sans text-[13px] font-semibold text-ink-900"
        >
          {title}
        </h2>
        <button
          ref={toggleRef}
          type="button"
          onClick={toggleMenu}
          onKeyDown={handleMenuKeyDown}
          aria-label="Conversations"
          title="Conversations"
          aria-expanded={menuOpen}
          aria-controls={menuOpen ? menuId : undefined}
          className={ICON_BUTTON_CLASS}
        >
          <History className="h-4 w-4" strokeWidth={1.7} aria-hidden="true" />
        </button>
        <button
          type="button"
          onClick={onNewConversation}
          disabled={newConversationDisabled}
          aria-label="New conversation"
          title="New conversation"
          className={ICON_BUTTON_CLASS}
        >
          <MessageSquarePlus className="h-4 w-4" strokeWidth={1.7} aria-hidden="true" />
        </button>
        <button
          type="button"
          onClick={onCollapse}
          aria-label="Collapse builder panel"
          title="Collapse"
          className={ICON_BUTTON_CLASS}
        >
          <PanelLeftClose className="h-4 w-4" strokeWidth={1.7} aria-hidden="true" />
        </button>
      </div>

      {menuOpen ? (
        <div
          ref={menuRef}
          id={menuId}
          onKeyDown={handleMenuKeyDown}
          className="absolute inset-x-3 top-full z-30 mt-1 flex max-h-80 flex-col overflow-hidden rounded-[var(--radius-menu)] border border-line-border bg-surface-card shadow-[var(--elevation-menu)]"
        >
          <p className="flex-none px-3 pb-1.5 pt-2.5 font-sans text-[10px] font-semibold uppercase tracking-[0.13em] text-ink-300">
            Conversations
          </p>
          <div className="min-h-0 overflow-y-auto px-1.5 pb-1.5">
            {sessions.length === 0 ? (
              <p className="px-1.5 py-2 font-sans text-[12px] text-ink-500">No conversations yet.</p>
            ) : (
              <ul className="flex flex-col">
                {sessions.map((session) => (
                  <li key={session.id} className="group flex items-center gap-0.5">
                    <button
                      type="button"
                      onClick={() => {
                        setMenuOpen(false);
                        onSelectSession(session.id);
                      }}
                      aria-current={session.id === currentSessionId ? "true" : undefined}
                      className={`min-w-0 flex-1 truncate rounded-[8px] px-2 py-1.5 text-left font-sans text-[12.5px] text-ink-900 transition-colors hover:bg-surface-warm aria-[current=true]:bg-brand-fill aria-[current=true]:font-semibold aria-[current=true]:text-brand ${FOCUS_RING}`}
                    >
                      {session.title}
                    </button>
                    <button
                      type="button"
                      onClick={() => setPendingDelete(session)}
                      aria-label={`Delete conversation ${session.title}`}
                      title="Delete"
                      className={`grid h-7 w-7 flex-none place-items-center rounded-[8px] text-ink-400 transition-colors hover:bg-status-failed-fill hover:text-status-failed ${FOCUS_RING}`}
                    >
                      <Trash2 className="h-3.5 w-3.5" strokeWidth={1.7} aria-hidden="true" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {hasMoreSessions ? (
            <div className="flex-none border-t border-line-divider p-1.5">
              <Button variant="secondary" size="sm" onClick={onShowMore} className={`w-full ${FOCUS_RING}`}>
                Show more
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}

      {pendingDelete ? (
        <Modal
          title="Delete this conversation?"
          description={`"${pendingDelete.title}" and its messages will be deleted. This cannot be undone.`}
          onClose={() => setPendingDelete(null)}
        >
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setPendingDelete(null)}>
              Cancel
            </Button>
            <Button onClick={confirmDelete}>Delete</Button>
          </div>
        </Modal>
      ) : null}
    </div>
  );
}

export default BuilderPanelHeader;
