"use client";

/**
 * WorkflowPickerModal — the target picker for a `trigger: "workflow"` conditional
 * outcome (spec 014 / R-22).
 *
 * Replaces a native `<select>`, which could only ever render a bare name. This
 * choice is the one place in the composer where getting it wrong does not merely
 * misconfigure a step — it STOPS the run and hands off to a different
 * `WorkflowRun` — so the author gets the description, the step count and the
 * group each candidate belongs to before committing.
 *
 * REUSE-MANDATE (UI-SPEC §1/§4 — no new visual language): backdrop + scale-in
 * `motion.div` + header + footer are the same shape as `NameWorkflowModal`
 * (itself a clone of WorkflowHistory's DeleteModal); the tab strip reuses the
 * group chips are LibraryPage's agent-category chips. Nothing new is invented
 * here beyond the row cards.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { motion } from "motion/react";
import { Search, Check, X, LayoutGrid, Boxes, RotateCcw, User, ExternalLink } from "lucide-react";
import { getWorkflowIcon } from "@/lib/workflowIcons";
import type { WorkflowPickerOption } from "./CanvasNode";

type GroupId = "all" | "system" | "revision" | "user";

/** Chip styling lifted verbatim from LibraryPage's agent-category chips
 *  (LibraryPage.tsx:623-627) so this picker reads as the same control, not a
 *  second filter language. Those consts are module-local there; the three
 *  class strings are copied rather than exported to avoid reaching into an
 *  unrelated page for styling. */
const CHIP_BASE =
  "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-[12px] transition-colors";
const CHIP_ACTIVE = "bg-surface-near-black border-transparent text-white font-medium";
const CHIP_IDLE =
  "bg-surface-card border-line-border text-ink-500 hover:border-line-control hover:text-ink-700";

const GROUP_CHIPS: { id: GroupId; label: string; Icon: typeof LayoutGrid }[] = [
  { id: "all", label: "All", Icon: LayoutGrid },
  { id: "system", label: "System", Icon: Boxes },
  { id: "revision", label: "Revision", Icon: RotateCcw },
  { id: "user", label: "Yours", Icon: User },
];

export function WorkflowPickerModal({
  value,
  workflows,
  onSelect,
  onCancel,
}: {
  /** Currently-selected target id, so the open modal shows what is already set. */
  value: string;
  workflows: WorkflowPickerOption[] | null;
  onSelect: (id: string) => void;
  onCancel: () => void;
}) {
  const [query, setQuery] = useState("");
  // Clicking a row HIGHLIGHTS it; nothing commits until "Pick workflow". Picking
  // a target diverts the whole run, so a single stray click should not be able
  // to change it.
  const [draft, setDraft] = useState(value);
  const selectedRowRef = useRef<HTMLButtonElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);
  const didMount = useRef(false);

  // Same three groups the dropdown offered, same rules — see
  // `WorkflowTargetPicker`'s comment for why revisions are included despite
  // `user_launchable: false` and why beta is excluded.
  const groups = useMemo(() => {
    const all = workflows ?? [];
    const isRevision = (w: WorkflowPickerOption) => w.id.endsWith("_revision");
    const system = all.filter((w) => w.kind === "system" && w.launchable && !w.isBeta);
    const revision = all.filter((w) => w.kind === "system" && isRevision(w));
    const user = all.filter((w) => w.kind === "user");
    return {
      all: [...system, ...revision, ...user],
      system,
      revision,
      user,
    } satisfies Record<GroupId, WorkflowPickerOption[]>;
  }, [workflows]);

  // Open on the tab the CURRENT target lives in, not always System — reopening
  // a configured outcome should show you what is set, not make you hunt for it.
  const initialTab: GroupId = useMemo(() => {
    if (!value) return "all";
    if (groups.revision.some((w) => w.id === value)) return "revision";
    if (groups.user.some((w) => w.id === value)) return "user";
    return "system";
    // Deliberately mount-only: recomputing would yank the tab out from under
    // someone who has since browsed elsewhere.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const [tab, setTab] = useState<GroupId>(initialTab);

  // …and scroll that row into view, for a group long enough to need it.
  useEffect(() => {
    selectedRowRef.current?.scrollIntoView({ block: "nearest" });
    // Mount-only: this is "show me where I am on open", not a scroll that should
    // fight the user every time they click another row.
  }, []);


  // Search filters WITHIN each group rather than flattening them, so the tab
  // strip always means something and can stay pinned. The counts below become
  // per-tab match counts while searching — which is what tells you to look in
  // another tab, the thing a flattened all-groups search used to do implicitly.
  const q = query.trim().toLowerCase();

  // Switching tabs (or changing the query) starts at the top. Without this the
  // scroll offset carries over, so moving from a long list to a short one can
  // land you below its last row looking at nothing.
  useEffect(() => {
    if (!didMount.current) {
      didMount.current = true;
      return; // don't undo the scroll-to-selected above
    }
    if (listRef.current) listRef.current.scrollTop = 0;
  }, [tab, q]);

  const matches = useMemo(() => {
    const hit = (w: WorkflowPickerOption) =>
      !q ||
      w.name.toLowerCase().includes(q) ||
      w.id.toLowerCase().includes(q) ||
      (w.description ?? "").toLowerCase().includes(q);
    return {
      all: groups.all.filter(hit),
      system: groups.system.filter(hit),
      revision: groups.revision.filter(hit),
      user: groups.user.filter(hit),
    } satisfies Record<GroupId, WorkflowPickerOption[]>;
  }, [q, groups]);

  const visible = matches[tab];

  const row = (w: WorkflowPickerOption) => {
    const selected = w.id === draft;
    // The manifest's `icon` is a LUCIDE COMPONENT NAME ("Presentation",
    // "Rocket"), not an emoji — rendering it as text printed the literal word
    // across the card. `getWorkflowIcon` is the shared resolver HomeLaunchGrid
    // and RunChatLane already use, and it falls back to Sparkles rather than
    // leaving a blank, so a user workflow (which authors no icon) still gets one.
    const RowIcon = getWorkflowIcon(w.icon);
    return (
      <button
        key={w.id}
        type="button"
        ref={selected ? selectedRowRef : undefined}
        data-testid={`workflow-picker-row-${w.id}`}
        onClick={() => setDraft(w.id)}
        onDoubleClick={() => onSelect(w.id)}
        className={`flex w-full items-start gap-2.5 rounded-[10px] border px-3 py-2.5 text-left transition-colors ${
          selected
            ? "border-brand bg-brand-fill"
            : "border-line-faint-row bg-surface-white hover:border-line-control"
        }`}
      >
        <span
          className={`mt-0.5 grid h-7 w-7 flex-none place-items-center rounded-[8px] ${
            selected ? "bg-brand text-surface-white" : "bg-brand-fill text-brand"
          }`}
        >
          <RowIcon className="h-[15px] w-[15px]" strokeWidth={1.8} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-1.5">
            <span className="truncate font-sans text-[12.5px] font-semibold text-ink-900">
              {w.name}
            </span>
            {w.shortName && (
              <span className="flex-none rounded-full border border-line-control px-1.5 py-0.5 font-sans text-[8px] font-bold uppercase tracking-[0.05em] text-ink-400">
                {w.shortName}
              </span>
            )}
          </span>
          {w.description && (
            <span className="mt-0.5 line-clamp-2 block font-serif text-[11px] leading-relaxed text-ink-400">
              {w.description}
            </span>
          )}
          {typeof w.stepCount === "number" && (
            <span className="mt-0.5 block font-sans text-[10px] text-ink-300">
              {w.stepCount} step{w.stepCount === 1 ? "" : "s"}
            </span>
          )}
        </span>
        {selected && <Check className="mt-1 h-4 w-4 flex-none text-brand" />}
      </button>
    );
  };

  // Escape closes. This has to be a WINDOW listener: the backdrop is a plain
  // div, so it never takes focus and an `onKeyDown` on it could not fire.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  if (typeof document === "undefined") return null;

  // PORTALLED to <body>. The picker button lives inside the config rail's
  // `<label>`, and a click anywhere inside a label is forwarded to the control
  // that label wraps — so a backdrop click closed the modal and then instantly
  // re-triggered the button that opens it, which read as "clicking away does
  // nothing". Rendering outside that subtree also frees the overlay from the
  // rail's stacking context.
  return createPortal(
    <div
      className="fixed inset-0 z-[80] grid place-items-center bg-ink-900/30 p-4"
      onClick={onCancel}
      role="presentation"
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.97 }}
        animate={{ opacity: 1, scale: 1 }}
        role="dialog"
        aria-label="Pick a workflow"
        data-testid="workflow-picker-modal"
        onClick={(e) => e.stopPropagation()}
        className="flex w-full max-w-[520px] flex-col overflow-hidden rounded-[16px] border border-line-border bg-surface-card shadow-2xl"
      >
        <div className="flex-none border-b border-line-faint-row px-4 pb-3 pt-3.5">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="font-sans text-[14px] font-semibold text-ink-900">Pick a workflow</p>
              <p className="mt-0.5 font-serif text-[11.5px] leading-relaxed text-ink-400">
                This outcome stops the current run and hands off to the workflow you choose.
              </p>
            </div>
            <button
              type="button"
              aria-label="Close"
              onClick={onCancel}
              className="-mr-1 -mt-1 flex-none rounded-[8px] p-1.5 text-ink-400 transition-colors hover:bg-surface-warm hover:text-ink-900"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="relative mt-2.5">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-300" />
            <input
              autoFocus
              aria-label="Search workflows"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search all workflows…"
              className="w-full rounded-[9px] border border-line-control bg-surface-white py-2 pl-8 pr-2.5 font-sans text-[12.5px] text-ink-900 focus:border-brand focus:outline-none"
            />
          </div>
        </div>

        {/* Pinned: OUTSIDE the scroll box, so the chips stay put instead of
            sliding away with the rows. Always rendered, never hidden while
            searching — conditionally removing it would change the modal's
            height the moment you typed, which is the jumping we just fixed. */}
        <div className="flex flex-none flex-wrap gap-1.5 px-4 pt-2.5">
          {GROUP_CHIPS.map(({ id, label, Icon }) => (
            <button
              key={id}
              type="button"
              data-testid={`workflow-picker-chip-${id}`}
              onClick={() => setTab(id)}
              className={`${CHIP_BASE} ${tab === id ? CHIP_ACTIVE : CHIP_IDLE}`}
            >
              <Icon className="h-3.5 w-3.5" />
              {label}
              <span className="opacity-50">{matches[id].length}</span>
            </button>
          ))}
        </div>
        {/* FIXED height, not flex-1: the modal must not resize when you switch
            between a 5-row tab and a 14-row one — a dialog that jumps around
            under the cursor is hard to aim at, and the footer button moves with
            it. Long lists scroll inside this box instead. The vh cap only ever
            engages on a viewport too short for the fixed height, and is still
            tab-independent, so the box stays stable wherever it lands. */}
        <div
          ref={listRef}
          className="h-[520px] max-h-[calc(100vh-260px)] overflow-y-auto px-4 py-3"
        >
          <div className="space-y-1.5">
            {workflows === null ? (
              <p className="py-6 text-center font-serif text-[12px] text-ink-300">
                Loading workflows…
              </p>
            ) : visible.length === 0 ? (
              <p className="py-6 text-center font-serif text-[12px] text-ink-300">
                {q
                  ? `No match for “${query.trim()}” in this group.`
                  : "Nothing in this group yet."}
              </p>
            ) : (
              visible.map(row)
            )}
          </div>
        </div>

        <div className="flex flex-none items-center justify-between gap-3 border-t border-line-faint-row px-4 py-2.5">
          {/* Mirrors the rail's selected-target chip (WorkflowTargetPicker's
              button): same ExternalLink glyph, same font-sans 11px ink-900, so
              what you are about to commit looks like what you will see once it
              is committed. */}
          {draft ? (
            <span className="flex min-w-0 items-center gap-1.5">
              <ExternalLink className="h-3 w-3 flex-none text-brand" />
              <span className="min-w-0 truncate font-sans text-[11px] text-ink-900">
                {groups.all.find((w) => w.id === draft)?.name ?? draft}
              </span>
            </span>
          ) : (
            <span className="min-w-0 truncate font-sans text-[11px] italic text-ink-400">
              Nothing selected yet.
            </span>
          )}
          <button
            type="button"
            data-testid="workflow-picker-confirm"
            disabled={!draft}
            onClick={() => draft && onSelect(draft)}
            // Verbatim NameWorkflowModal's primary "Save" pill (its footer is
            // the shape this modal already clones) — same radius, fill, weight,
            // hover and disabled treatment. Only `flex-1` is dropped: that
            // footer splits two equal buttons, this one is right-aligned beside
            // the selection label.
            className="flex-none rounded-xl bg-brand px-4 py-2.5 text-[12px] font-medium text-surface-white transition-colors hover:bg-brand-pressed disabled:cursor-not-allowed disabled:opacity-30"
          >
            Pick workflow
          </button>
        </div>
      </motion.div>
    </div>,
    document.body,
  );
}
