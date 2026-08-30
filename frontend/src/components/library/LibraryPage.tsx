"use client";

import { useRef, useState, useEffect, useCallback, type HTMLAttributes } from "react";
import { useRouter, useSearchParams, useParams, notFound } from "next/navigation";
import { motion, AnimatePresence } from "motion/react";
import {
  Search, Clock, Puzzle, Webhook, X, Copy, Check,
  Tag, Zap, BookOpen, ChevronRight,
} from "lucide-react";
import { AgentCapabilitiesModal, type SelectionsMap } from "@/components/workflow/AgentsPopup";
import type { HookDef } from "@/store/api/hooks";
import type { SkillDef } from "@/store/api/skills";
import { useAgentLibrary } from "@/hooks/useAgentLibrary";
import { useSkillsCatalog } from "@/hooks/useSkillsCatalog";
import { useHooksCatalog } from "@/hooks/useHooksCatalog";
import { useClipboardCopy } from "@/hooks/useClipboardCopy";
import { useAppSelector } from "@/store/hooks";
import { routes, parseViewPath } from "@/lib/routes";
import { getSkillCategoryIcon } from "@/lib/skillIcons";
import { getWorkflowTypeIcon, getPrimaryPipelineType, agentMatchesPipelineType } from "@/lib/workflowIcons";
import { Tabs, type TabItem } from "@/components/ui/Tabs";
import { Card } from "@/components/ui/Card";
import { Pill } from "@/components/ui/Pill";
import { SkillMarkdown } from "@/components/ui/SkillMarkdown";
import type { AgentDef } from "@/types/index";

type CategoryEntry = { id: string; label: string; section?: boolean };

const BETA_WORKFLOWS = new Set(["user_stories_revision", "ppt_revision", "prototype_revision", "app_builder_revision", "mulesoft_to_springboot", "dotnet_to_azure", "sample_brownfield", "sample_fanout", "sample_wave", "reverse_engineer"]);

// Token-based avatar tints (was a retired-hex array) — cycle brand/warm
// surfaces + ink/brand text so every agent chip stays on the Phase-32 palette.
const ICON_TINTS = [
  "bg-brand-fill text-brand",
  "bg-surface-warm text-ink-700",
  "bg-brand-fill text-ink-700",
  "bg-surface-warm text-brand",
  "bg-surface-paper text-ink-600",
  "bg-brand-fill text-ink-600",
];

function getInitials(name: string): string {
  const words = name.replace(/\s+agent$/i, "").split(" ");
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

// ISS-222/270/271 — `Card` renders a plain <div>, so every grid card that
// carries an onClick has to supply its own keyboard affordance: focusable,
// announced as a button, activated by Enter/Space. Enter/Space forward to the
// element's own click handler so activation stays defined in exactly one place.
// Cards with no working onClick (beta agents, beta skills) deliberately do NOT
// get this — a focus stop that does nothing is worse than none.
const CARD_KEYBOARD_PROPS: HTMLAttributes<HTMLDivElement> = {
  role: "button",
  tabIndex: 0,
  onKeyDown: (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      e.currentTarget.click();
    }
  },
};

// ISS-272 — both in-file detail modals are the same scrim+panel shell and
// neither had a keyboard dismiss path or any focus management. One shared hook
// gives them the modal contract the prototype detail modals already use
// (TemplateDetailModal): Escape closes, and focus moves onto the panel on open
// so a keyboard user lands inside the dialog instead of behind it. No Tab trap,
// same as those modals.
function useDetailModalKeyboard(onClose: () => void) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    panelRef.current?.focus();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return panelRef;
}

// ─── Loading Skeletons ───────────────────────────────────────────────────────

function AgentCardSkeleton() {
  return (
    <Card className="flex flex-col p-[17px] min-h-[180px] shimmer-effect">
      <div className="relative overflow-hidden">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-[10px] bg-surface-warm" />
          <div className="flex-1 space-y-2">
            <div className="h-4 bg-surface-warm rounded w-3/4" />
            <div className="h-3 bg-surface-warm rounded w-1/2" />
          </div>
        </div>
        <div className="space-y-2 mb-4">
          <div className="h-3 bg-surface-warm rounded w-full" />
          <div className="h-3 bg-surface-warm rounded w-5/6" />
          <div className="h-3 bg-surface-warm rounded w-4/6" />
        </div>
        <div className="h-[1px] bg-line-divider my-3" />
        <div className="flex items-center gap-2">
          <div className="h-3 bg-surface-warm rounded w-16" />
          <div className="flex-1" />
          <div className="h-3 bg-surface-warm rounded w-20" />
        </div>
      </div>
    </Card>
  );
}

function SkillCardSkeleton() {
  return (
    <Card className="p-4 shimmer-effect">
      <div className="relative overflow-hidden">
        <div className="flex items-center gap-2.5 mb-2.5">
          <div className="w-[30px] h-[30px] flex-shrink-0 rounded-lg bg-surface-warm" />
          <div className="flex-1 space-y-2">
            <div className="h-3 bg-surface-warm rounded w-3/4" />
            <div className="h-2.5 bg-surface-warm rounded w-1/2" />
          </div>
        </div>
        <div className="space-y-2 mb-2.5">
          <div className="h-3 bg-surface-warm rounded w-full" />
          <div className="h-3 bg-surface-warm rounded w-5/6" />
        </div>
        <div className="flex items-center gap-1.5">
          <div className="h-5 bg-surface-warm rounded w-12" />
          <div className="h-5 bg-surface-warm rounded w-16" />
          <div className="flex-1" />
          <div className="h-3 bg-surface-warm rounded w-12" />
        </div>
      </div>
    </Card>
  );
}

function HookCardSkeleton() {
  return (
    <Card className="p-4 shimmer-effect">
      <div className="relative overflow-hidden">
        <div className="flex items-center gap-2.5 mb-2">
          <div className="flex-1 space-y-2">
            <div className="h-3 bg-surface-warm rounded w-3/4" />
            <div className="h-2.5 bg-surface-warm rounded w-1/3" />
          </div>
          <div className="h-5 bg-surface-warm rounded w-16 flex-shrink-0" />
        </div>
        <div className="h-3 bg-surface-warm rounded w-1/2 mb-2 italic" />
        <div className="space-y-2 mb-2.5">
          <div className="h-3 bg-surface-warm rounded w-full" />
          <div className="h-3 bg-surface-warm rounded w-5/6" />
        </div>
        <div className="flex items-center gap-1.5">
          <div className="h-5 bg-surface-warm rounded w-12" />
          <div className="h-5 bg-surface-warm rounded w-16" />
          <div className="flex-1" />
          <div className="h-3 bg-surface-warm rounded w-12" />
        </div>
      </div>
    </Card>
  );
}

function CategoryChipSkeleton() {
  return (
    <div className="relative overflow-hidden inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-line-border bg-surface-card shimmer-effect">
      <div className="h-3.5 bg-surface-warm rounded w-20" />
    </div>
  );
}

// ISS-231 — all three grids below render `list.map(...)` straight into the DOM,
// so an empty list left the whole content area blank with no markup at all. One
// shared empty state, rendered on the array's LENGTH rather than on whether the
// search box has text, so a category/event filter that matches nothing lands
// here too instead of on the same blank grid.
function EmptyGridState({ noun, query, onClear }: { noun: string; query: string; onClear: () => void }) {
  return (
    <div className="col-span-full flex flex-col items-center gap-2 py-14">
      <p className="text-[13px] text-ink-400">
        {query ? `No ${noun} match “${query}”` : `No ${noun} found`}
      </p>
      {query && (
        <button onClick={onClear} className="text-[12px] font-medium text-brand hover:opacity-80 transition-opacity">
          Clear search
        </button>
      )}
    </div>
  );
}

// ─── Skill Detail Modal ───────────────────────────────────────────────────────

function SkillDetailModal({ skill, onClose }: { skill: SkillDef; onClose: () => void }) {
  const { copied, failed, copy } = useClipboardCopy();
  const panelRef = useDetailModalKeyboard(onClose);

  const handleCopy = () => void copy(skill.content);

  return (
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-[80] flex items-center justify-center p-6 bg-[var(--scrim)] backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={`${skill.name} skill`}
      onClick={onClose}
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        onClick={e => e.stopPropagation()}
        className="bg-surface-white rounded-2xl shadow-2xl border border-line-border w-full max-w-2xl overflow-hidden flex flex-col"
        style={{ maxHeight: "88vh" }}
      >
        {/* Header */}
        <div className="px-6 pt-6 pb-4 border-b border-line-divider flex-shrink-0">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-brand-fill border border-brand-border flex items-center justify-center flex-shrink-0">
                <Puzzle className="h-5 w-5 text-brand" />
              </div>
              <div>
                <h2 className="font-sans text-[16px] font-bold text-ink-900 leading-tight">{skill.name}</h2>
                <div className="flex items-center gap-2 mt-1">
                  <Pill className="capitalize text-ink-600">{skill.category}</Pill>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              {failed && (
                <span className="text-[11px] font-semibold text-status-failed">Copy failed</span>
              )}
              <button
                onClick={handleCopy}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold transition-all border ${
                  copied
                    ? "bg-status-done text-white border-status-done"
                    : "bg-surface-white text-ink-600 border-line-control hover:bg-surface-warm hover:border-ink-300"
                }`}
              >
                {copied ? <><Check className="h-3 w-3" /> Copied!</> : <><Copy className="h-3 w-3" /> Copy content</>}
              </button>
              <button onClick={onClose} className="h-8 w-8 flex items-center justify-center rounded-lg text-ink-400 hover:text-ink-700 hover:bg-surface-warm transition-all">
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>
          <p className="text-[12px] text-ink-600 leading-relaxed mt-3">{skill.description}</p>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          {/* Formatted content — ISS-591: this used to be a hand-rolled
              line-splitter that only recognized `# `/`## ` headings and
              `-`/`*`/numbered bullets, so inline **bold**, `code` and [links]
              rendered as literal markup. Routed through the same
              react-markdown + remark-gfm renderer the composer's skill modal
              uses, so both surfaces parse the same SKILL.md identically. */}
          <div className="px-6 py-4">
            <SkillMarkdown content={skill.content} />
          </div>

          {/* Raw content block */}
          <div className="mx-6 mb-4 rounded-xl border border-line-border overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2.5 bg-surface-warm border-b border-line-border">
              <div className="flex items-center gap-2">
                <BookOpen className="h-3.5 w-3.5 text-ink-400" />
                <span className="text-[10px] font-semibold text-ink-500 uppercase tracking-wide">SKILL.md content</span>
              </div>
              <button
                onClick={handleCopy}
                className="flex items-center gap-1 text-[10px] text-ink-400 hover:text-ink-700 transition-colors"
              >
                {copied ? <><Check className="h-3 w-3" /> Copied</> : <><Copy className="h-3 w-3" /> Copy</>}
              </button>
            </div>
            <pre className="px-4 py-3 text-[11px] text-ink-600 leading-relaxed overflow-x-auto whitespace-pre-wrap font-mono bg-surface-white">
              {skill.content}
            </pre>
          </div>

          {/* Footer meta */}
          <div className="px-6 pb-5 space-y-3">
            {/* Tags */}
            <div className="flex items-center gap-2 flex-wrap">
              <Tag className="h-3 w-3 text-ink-400 flex-shrink-0" />
              {skill.tags.map(tag => (
                <Pill key={tag} className="text-ink-500">{tag}</Pill>
              ))}
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}


// ─── Hook Detail Modal ────────────────────────────────────────────────────────

function HookDetailModal({ hook, onClose }: { hook: HookDef; onClose: () => void }) {
  const { copied, failed, copy } = useClipboardCopy();
  const panelRef = useDetailModalKeyboard(onClose);

  const copyText = `Hook: ${hook.name}\nEvent: ${hook.event}\nTrigger: ${hook.trigger}\n\n${hook.description}\n\nTags: ${hook.tags.join(", ")}`;

  const handleCopy = () => void copy(copyText);

  const EVENT_DESCRIPTION: Record<string, string> = {
    PreToolUse: "Runs before a tool is executed. Can inspect or block the operation.",
    PostToolUse: "Runs after a tool completes. Can validate output or trigger follow-up actions.",
    Stop: "Runs at the end of each agent response. Good for batch operations and cleanup.",
    SessionStart: "Runs when a new session begins. Used for context loading and setup.",
    SessionEnd: "Runs when a session ends. Used for state persistence and cleanup.",
  };

  return (
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-[80] flex items-center justify-center p-6 bg-[var(--scrim)] backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={`${hook.name} hook`}
      onClick={onClose}
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        onClick={e => e.stopPropagation()}
        className="bg-surface-white rounded-2xl shadow-2xl border border-line-border w-full max-w-xl overflow-hidden flex flex-col"
        style={{ maxHeight: "88vh" }}
      >
        {/* Header */}
        <div className="px-6 pt-6 pb-4 border-b border-line-divider flex-shrink-0">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-brand-fill border border-brand-border flex items-center justify-center flex-shrink-0">
                <Webhook className="h-5 w-5 text-brand" />
              </div>
              <div>
                <h2 className="font-sans text-[16px] font-bold text-ink-900 leading-tight">{hook.name}</h2>
                <div className="flex items-center gap-2 mt-1">
                  <Pill className="bg-brand text-white border-transparent">{hook.event}</Pill>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              {failed && (
                <span className="text-[11px] font-semibold text-status-failed">Copy failed</span>
              )}
              <button
                onClick={handleCopy}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold transition-all border ${
                  copied
                    ? "bg-status-done text-white border-status-done"
                    : "bg-surface-white text-ink-600 border-line-control hover:bg-surface-warm hover:border-ink-300"
                }`}
              >
                {copied ? <><Check className="h-3 w-3" /> Copied!</> : <><Copy className="h-3 w-3" /> Copy</>}
              </button>
              <button onClick={onClose} className="h-8 w-8 flex items-center justify-center rounded-lg text-ink-400 hover:text-ink-700 hover:bg-surface-warm transition-all">
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>
          <p className="text-[12px] text-ink-600 leading-relaxed mt-3">{hook.description}</p>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {/* Event type explanation */}
          <div className="rounded-xl border border-line-divider bg-surface-warm px-4 py-3">
            <div className="flex items-center gap-2 mb-1.5">
              <Zap className="h-3.5 w-3.5 text-ink-400" />
              <p className="text-[10px] font-semibold text-ink-500 uppercase tracking-wide">Event: {hook.event}</p>
            </div>
            <p className="text-[12px] text-ink-600 leading-relaxed">{EVENT_DESCRIPTION[hook.event] ?? "Triggered by the specified event."}</p>
          </div>

          {/* Trigger */}
          <div className="rounded-xl border border-line-divider bg-surface-warm px-4 py-3">
            <p className="text-[10px] font-semibold text-ink-400 uppercase tracking-wide mb-1.5">When it fires</p>
            <p className="text-[12px] text-ink-700 font-medium">{hook.trigger}</p>
          </div>

          {/* How to use */}
          <div>
            <div className="flex items-center gap-2 mb-2.5">
              <BookOpen className="h-3.5 w-3.5 text-ink-400" />
              <p className="text-[10px] font-semibold text-ink-500 uppercase tracking-wide">How to use</p>
            </div>
            <div className="space-y-2">
              {[
                "Attach this hook to agents in the Advanced → Skills & Hooks panel before running a pipeline.",
                "The hook's behaviour will be injected as a guideline into the agent's execution context.",
                `Best suited for: ${hook.compatible_agents.slice(0, 3).join(", ")}${hook.compatible_agents.length > 3 ? " and more" : ""}.`,
              ].map((step, i) => (
                <div key={i} className="flex items-start gap-2.5">
                  <div className="w-5 h-5 rounded-full bg-brand-fill border border-brand-border flex items-center justify-center flex-shrink-0 text-[9px] font-bold text-brand mt-0.5">{i + 1}</div>
                  <p className="text-[12px] text-ink-600 leading-relaxed">{step}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Compatible agents */}
          <div>
            <p className="text-[10px] font-semibold text-ink-400 uppercase tracking-wide mb-2">Compatible agents</p>
            <div className="flex flex-wrap gap-1.5">
              {hook.compatible_agents.map(id => (
                <div key={id} className="flex items-center gap-1 text-[10px] px-2 py-1 rounded-lg bg-surface-warm border border-line-border text-ink-600">
                  <ChevronRight className="h-2.5 w-2.5 text-ink-400" />
                  {id}
                </div>
              ))}
            </div>
          </div>

          {/* Tags */}
          <div className="flex items-center gap-2 flex-wrap pt-1">
            <Tag className="h-3 w-3 text-ink-400 flex-shrink-0" />
            {hook.tags.map(tag => (
              <Pill key={tag} className="text-ink-500">{tag}</Pill>
            ))}
          </div>

        </div>
      </div>
    </motion.div>
  );
}


// ─── LibraryPage ─────────────────────────────────────────────────────────────

export function LibraryPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // T15 (015-frontend-routing, FR-006): parse the catch-all's segments so a
  // cold mount of /library/{type}/{slug} can seed the matching detail modal
  // below — read directly here (same useParams()/parseViewPath() pair
  // `[...view]/page.tsx` uses) rather than threaded through DashboardLayout,
  // since LibraryPage takes no props from it today.
  const viewParams = useParams<{ view?: string[] }>();
  const parsedView = parseViewPath(viewParams?.view);
  const librarySlug =
    parsedView.screen === "library-agent" ? { type: "agents" as const, slug: parsedView.slug } :
    parsedView.screen === "library-skill" ? { type: "skills" as const, slug: parsedView.slug } :
    parsedView.screen === "library-hook" ? { type: "hooks" as const, slug: parsedView.slug } :
    null;

  const { allAgents: ALL_AGENTS_COMBINED } = useAgentLibrary();
  const { skills: SKILLS, categories: SKILL_CATEGORIES } = useSkillsCatalog();
  const { hooks: HOOKS, events: HOOK_EVENTS } = useHooksCatalog();

  // Load status from Redux for skeleton rendering
  const agentsStatus = useAppSelector((state) => state.agents.status);
  const skillsStatus = useAppSelector((state) => state.skills.status);
  const hooksStatus = useAppSelector((state) => state.hooks.status);

  // Build agent categories from user_launchable, non-beta workflows in Redux
  const workflows = useAppSelector((state) => state.global.workflows);
  const CATEGORIES: CategoryEntry[] = [
    { id: "all", label: "All" },
    ...workflows
      .filter((w) => w.user_launchable && !w.is_beta && !["custom"].includes(w.id))
      .map((w) => ({
        id: w.id,
        label: w.name || w.display_name || w.id,
      })),
    { id: "custom", label: "Custom" },
  ];

  // Read category param from URL on mount, default to "all"
  const urlCategory = searchParams.get("category") || "all";
  // ISS-360/592/593/594: search text gets the SAME one-shot URL seed the three
  // category states already get. Opening an item-detail view remounts this
  // component (routes.libraryAgent/Skill/Hook change the [...view] catch-all's
  // segments — see `[...view]/page.tsx`'s T6 comment), so the URL is the only
  // thing that survives the round trip, whether the user comes back via the
  // detail view's X or the browser's own Back button.
  const urlSearch = searchParams.get("search") || "";
  const [activeCategory, setActiveCategory] = useState(urlCategory);
  const [searchQuery, setSearchQuery] = useState(urlSearch);
  // Carries the persisted selections SNAPSHOT taken when the drawer was
  // opened. Reading `savedSelectionsRef` inline in the drawer's
  // JSX instead would be a render-time ref read (react-hooks/refs): React does
  // not re-render on a ref write, so that read only ever reflected whatever the
  // ref held during some arbitrary earlier render. Snapshotting at open time —
  // inside a click handler, where ref reads are legal — captures exactly the same
  // value the drawer used to receive, deterministically.
  const [selectedAgent, setSelectedAgent] = useState<{
    agent: AgentDef;
    index: number;
    savedSelections?: SelectionsMap;
  } | null>(null);
  const [mainTab, setMainTab] = useState<"agents" | "skills" | "hooks">("agents");
  const [skillCategory, setSkillCategory] = useState(urlCategory);
  const [skillSearch, setSkillSearch] = useState(urlSearch);
  const [hookEvent, setHookEvent] = useState(urlCategory);
  const [hookSearch, setHookSearch] = useState(urlSearch);
  const [selectedSkill, setSelectedSkill] = useState<SkillDef | null>(null);
  const [selectedHook, setSelectedHook] = useState<HookDef | null>(null);

  // T13 (post-close amendment, 2026-08-21): seed mainTab from the URL's
  // ?tab= query param on mount. parseViewPath only sees path segments, not
  // query params (the unified /library route carries tab/category as query
  // params now) — same established convention as urlCategory above — so the
  // tab is read directly via useSearchParams here, not through parsedView.
  const mainTabSeededRef = useRef(false);
  useEffect(() => {
    if (mainTabSeededRef.current) return;
    const urlTab = searchParams.get("tab");
    if (urlTab === "skills") {
      setMainTab("skills");
    } else if (urlTab === "hooks") {
      setMainTab("hooks");
    }
    mainTabSeededRef.current = true;
  }, [searchParams]);

  // T13: category state is seeded directly from the URL via the useState
  // initializers above — no separate mount-read effect. (Fix, 015-frontend-
  // routing SC-003 regression #1: a mount-read effect setting state AND a
  // shared "initialized" ref, checked by the write effects below, raced —
  // all three effects fire in the SAME initial commit, in declaration order,
  // so the read effect's ref write was already visible by the time a write
  // effect's guard checked it, and every fresh mount replaced the URL
  // unconditionally, silently clobbering the previous history entry.)

  // T13 redo: the URL write is no longer a mount-observing effect at all —
  // it fires only from the category-chip onClick handlers below, alongside
  // setActiveCategory/setSkillCategory, matching AnalyticsPage's pattern
  // (router.replace called inline in the filter's own event handler, T14).
  // (Fix, SC-003 regression #2: the previous "skip my own first invocation"
  // private-ref guard broke under React Strict Mode's dev-mode double-invoke
  // of mount effects — the effect body runs twice in the same mount with no
  // cleanup between them, so the ref was already flipped true by the second
  // invocation and the guard fell through to a real router.replace() on
  // every mount, not just on a genuine user-driven category change. An
  // event-handler write can't mount-fire at all, so it can't race this way.)

  // T15 (015-frontend-routing, FR-006): cold-mounting /library/{type}/{slug}
  // opens the SAME detail modal a click opens (reused, not forked) — it
  // already renders as a full-viewport overlay (`fixed inset-0`), so seeding
  // it from the URL satisfies "renders full-page" with no new UI. Applied
  // once the matching catalog has finished loading, and only once — closing
  // the modal afterward must not immediately reopen it.
  const librarySlugAppliedRef = useRef(false);
  useEffect(() => {
    if (!librarySlug || librarySlugAppliedRef.current) return;
    if (librarySlug.type === "agents" && agentsStatus === "succeeded") {
      const agent = ALL_AGENTS_COMBINED.find(a => a.id === librarySlug.slug);
      if (agent) {
        setMainTab("agents");
        // ISS-303: a "Coming Soon" (BETA_WORKFLOWS) agent has no click path
        // into the drawer — the grid card's own onClick refuses it — so a
        // direct URL must not be one either. Redirect to the listing rather
        // than leaving the URL on a detail path nothing renders.
        if (BETA_WORKFLOWS.has(getPrimaryPipelineType(agent.pipeline_type))) {
          router.replace(routes.library({ tab: "agents" }));
        } else {
          setSelectedAgent({ agent, index: ALL_AGENTS_COMBINED.indexOf(agent) });
        }
        librarySlugAppliedRef.current = true;
      }
    } else if (librarySlug.type === "skills" && skillsStatus === "succeeded") {
      const skill = SKILLS.find(s => s.id === librarySlug.slug);
      if (skill) {
        setMainTab("skills");
        // ISS-416: same gate for a beta skill — the "Coming Soon" skills grid
        // renders those cards with no onClick at all.
        if (skill.isBeta) {
          router.replace(routes.library({ tab: "skills" }));
        } else {
          setSelectedSkill(skill);
        }
        librarySlugAppliedRef.current = true;
      }
    } else if (librarySlug.type === "hooks" && hooksStatus === "succeeded") {
      const hook = HOOKS.find(h => h.id === librarySlug.slug);
      if (hook) {
        setMainTab("hooks");
        setSelectedHook(hook);
        librarySlugAppliedRef.current = true;
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [librarySlug?.type, librarySlug?.slug, agentsStatus, skillsStatus, hooksStatus, ALL_AGENTS_COMBINED, SKILLS, HOOKS]);

  // ISS-360/592/593/594: the one place the active tab's search text is written,
  // so it always reaches the URL alongside the tab's category — the category
  // chips below already do this, and search needs it for the same reason: the
  // URL is what a detail-view round trip (or a browser Back out of one) reads
  // the filters back from. An event-handler write, never an effect — see T13.
  const applySearch = (value: string) => {
    if (mainTab === "agents") setSearchQuery(value);
    else if (mainTab === "skills") setSkillSearch(value);
    else setHookSearch(value);
    router.replace(routes.library({
      tab: mainTab,
      category: mainTab === "skills" ? skillCategory : mainTab === "hooks" ? hookEvent : activeCategory,
      search: value,
    }));
  };

  // Closes whichever detail modal is open via the URL, not local state directly
  // — mirrors what browser Back already does, so the T16 effect below is the
  // ONE place that clears selectedAgent/Skill/Hook, and the URL never goes
  // stale the way it did when this only called setSelectedX(null) (a refresh
  // right after closing via the X button would reopen the modal, since the
  // URL still pointed at /library/{type}/{slug}).
  const closeDetailModal = useCallback(() => {
    const category =
      mainTab === "skills" ? skillCategory :
      mainTab === "hooks" ? hookEvent :
      activeCategory;
    const search =
      mainTab === "skills" ? skillSearch :
      mainTab === "hooks" ? hookSearch :
      searchQuery;
    router.push(routes.library({ tab: mainTab, category: category === "all" ? undefined : category, search }));
  }, [router, mainTab, activeCategory, skillCategory, hookEvent, searchQuery, skillSearch, hookSearch]);

  // T16 (015-frontend-routing, FR-006): when the URL changes (e.g., via browser back),
  // close any modal that no longer matches the current URL. This allows the browser
  // back button to close the modal and return to the list view.
  useEffect(() => {
    if (!librarySlug) {
      // No item slug in URL — close all modals
      setSelectedAgent(null);
      setSelectedSkill(null);
      setSelectedHook(null);
    } else if (librarySlug.type === "agents" && (!selectedAgent || selectedAgent.agent.id !== librarySlug.slug)) {
      // URL has an agent, but modal is for a different item — close non-agent modals
      setSelectedSkill(null);
      setSelectedHook(null);
    } else if (librarySlug.type === "skills" && (!selectedSkill || selectedSkill.id !== librarySlug.slug)) {
      // URL has a skill, but modal is for a different item — close non-skill modals
      setSelectedAgent(null);
      setSelectedHook(null);
    } else if (librarySlug.type === "hooks" && (!selectedHook || selectedHook.id !== librarySlug.slug)) {
      // URL has a hook, but modal is for a different item — close non-hook modals
      setSelectedAgent(null);
      setSelectedSkill(null);
    }
  }, [librarySlug?.type, librarySlug?.slug, selectedAgent?.agent.id, selectedSkill?.id, selectedHook?.id]);

  // Persist per-agent Config-tab selections across drawer open/close cycles.
  // Keyed by agent.id → the SelectionsMap for that agent. A useRef keeps the
  // map stable (no re-render on save) while surviving the drawer unmount.
  const savedSelectionsRef = useRef<Record<string, SelectionsMap>>({});

  const MAIN_TABS: TabItem[] = [
    { id: "agents", label: `Agents  ${ALL_AGENTS_COMBINED.length}`, icon: <Zap className="h-3.5 w-3.5" /> },
    { id: "skills", label: `Skills  ${SKILLS.length}`, icon: <Puzzle className="h-3.5 w-3.5" /> },
    { id: "hooks", label: `Hooks  ${HOOKS.length}`, icon: <Webhook className="h-3.5 w-3.5" /> },
  ];

  const filteredAgents = ALL_AGENTS_COMBINED.filter(agent => {
    const matchesCategory =
      activeCategory === "all" ||
      agentMatchesPipelineType(agent.pipeline_type, activeCategory);
    const matchesSearch = !searchQuery ||
      agent.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.role.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesCategory && matchesSearch;
  }).sort((a, b) => {
    // Sort beta workflows to the end
    const aPt = getPrimaryPipelineType(a.pipeline_type);
    const bPt = getPrimaryPipelineType(b.pipeline_type);
    const aBeta = BETA_WORKFLOWS.has(aPt) ? 1 : 0;
    const bBeta = BETA_WORKFLOWS.has(bPt) ? 1 : 0;
    if (aBeta !== bBeta) return aBeta - bBeta;
    return aPt.localeCompare(bPt) || a.order - b.order;
  });

  const filteredSkills = SKILLS.filter(s => {
    const matchCat = skillCategory === "all" || s.category === skillCategory;
    const matchSearch = !skillSearch ||
      s.name.toLowerCase().includes(skillSearch.toLowerCase()) ||
      s.description.toLowerCase().includes(skillSearch.toLowerCase());
    return matchCat && matchSearch;
  });

  const activeSkills = filteredSkills.filter(s => !s.isBeta);
  const betaSkills = filteredSkills.filter(s => s.isBeta);

  const filteredHooks = HOOKS.filter(h => {
    const matchEvent = hookEvent === "all" || h.event === hookEvent;
    const matchSearch = !hookSearch ||
      h.name.toLowerCase().includes(hookSearch.toLowerCase()) ||
      h.description.toLowerCase().includes(hookSearch.toLowerCase());
    return matchEvent && matchSearch;
  });

  const chipBase =
    "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-[12px] transition-colors";
  const chipActive = "bg-surface-near-black border-transparent text-white font-medium";
  const chipIdle =
    "bg-surface-card border-line-border text-ink-500 hover:border-line-control hover:text-ink-700";

  const countLine = `${ALL_AGENTS_COMBINED.length} agents · ${SKILLS.length} skills · ${HOOKS.length} hooks · tap any item to see its capabilities`;

  // T15: once the matching catalog has loaded and the slug isn't in it,
  // render Next's branded not-found (T19) instead of a blank panel. Placed
  // after every hook above so hook order stays consistent on every render
  // that leads up to this throw — the same pattern `[...view]/page.tsx`
  // already uses for its own `screen === "unknown"` case.
  if (
    librarySlug &&
    ((librarySlug.type === "agents" && agentsStatus === "succeeded" && !ALL_AGENTS_COMBINED.some(a => a.id === librarySlug.slug)) ||
      (librarySlug.type === "skills" && skillsStatus === "succeeded" && !SKILLS.some(s => s.id === librarySlug.slug)) ||
      (librarySlug.type === "hooks" && hooksStatus === "succeeded" && !HOOKS.some(h => h.id === librarySlug.slug)))
  ) {
    notFound();
  }

  return (
    <div className="h-full overflow-y-auto bg-surface-paper">
      <div className="max-w-[1320px] w-full mx-auto px-8 pt-6 pb-16">
        {/* ── Header — h1 + count + search (leads above the tabs, per the mock) ── */}
        <div className="flex items-end justify-between gap-5 mb-4">
          <div>
            <h1 className="font-sans text-[26px] font-light text-ink-900 tracking-[-0.01em] leading-none mb-1.5">Library</h1>
            <p className="text-[13px] text-ink-400 leading-none">{countLine}</p>
          </div>
          <div className="relative w-[280px] flex-shrink-0">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-[15px] w-[15px] text-ink-200" />
            <input type="text"
              aria-label={`Search ${mainTab}`}
              name="library-search"
              value={mainTab === "agents" ? searchQuery : mainTab === "skills" ? skillSearch : hookSearch}
              onChange={e => applySearch(e.target.value)}
              placeholder={`Search ${mainTab}...`}
              className="w-full pl-10 pr-4 py-[9px] text-[13px] text-ink-800 bg-surface-card border border-line-control rounded-[10px] focus:outline-none focus:border-brand transition-colors placeholder:text-ink-200"
            />
          </div>
        </div>

        {/* ── Tab chrome — Tabs primitive, ND-C purple underline (kept) ── */}
        <Tabs
          tabs={MAIN_TABS}
          active={mainTab}
          onChange={(id) => {
            // Post-close amendment (2026-08-21): switching tabs used to be
            // pure local state with no URL update — the URL and the visibly
            // active tab could go out of sync, and sharing the URL after
            // switching tabs shared the wrong tab. Each tab keeps its OWN
            // category state (hooks has no category param), so the URL's
            // category reflects the NEWLY active tab's own state, never the
            // previous tab's.
            const tab = id as "agents" | "skills" | "hooks";
            setMainTab(tab);
            router.replace(routes.library({
              tab,
              category: tab === "agents" ? activeCategory : tab === "skills" ? skillCategory : undefined,
            }));
          }}
          className="mb-5"
        />

        {/* ── AGENTS ── */}
        {mainTab === "agents" && (
          <>
            <div className="flex flex-wrap gap-[7px] mb-5">
              {CATEGORIES.map(cat => {
                const count = cat.id === "all" ? ALL_AGENTS_COMBINED.length
                  : ALL_AGENTS_COMBINED.filter(a => agentMatchesPipelineType(a.pipeline_type, cat.id)).length;
                const isActive = activeCategory === cat.id;
                const showIcon = cat.id !== "all" && cat.id !== "custom";
                const IconComponent = showIcon ? getWorkflowTypeIcon(cat.id) : null;
                return (
                  <button key={cat.id} onClick={() => {
                    setActiveCategory(cat.id);
                    router.replace(routes.library({ tab: "agents", category: cat.id === "all" ? undefined : cat.id, search: searchQuery }));
                  }}
                    className={`${chipBase} ${isActive ? chipActive : chipIdle} flex items-center gap-1.5`}>
                    {IconComponent && <IconComponent className="h-3.5 w-3.5" />}
                    {cat.label}<span className="opacity-50">{count}</span>
                  </button>
                );
              })}
            </div>
            <div className="grid grid-cols-[repeat(auto-fill,minmax(288px,1fr))] gap-[13px]">
              {agentsStatus === "loading" ? (
                Array.from({ length: 6 }).map((_, i) => <AgentCardSkeleton key={i} />)
              ) : filteredAgents.length === 0 ? (
                <EmptyGridState noun="agents" query={searchQuery} onClear={() => applySearch("")} />
              ) : (
                filteredAgents.map((agent) => {
                  const WorkflowIconComponent = getWorkflowTypeIcon(getPrimaryPipelineType(agent.pipeline_type));
                  const workflow = workflows.find(w => w.id === getPrimaryPipelineType(agent.pipeline_type));
                  const workflowLabel = workflow?.name || workflow?.display_name || getPrimaryPipelineType(agent.pipeline_type);
                  return (
                    <Card key={`${getPrimaryPipelineType(agent.pipeline_type)}-${agent.id}`}
                      onClick={() => {
                        if (!BETA_WORKFLOWS.has(getPrimaryPipelineType(agent.pipeline_type))) {
                          setSelectedAgent({
                            agent,
                            index: filteredAgents.indexOf(agent),
                            // Snapshot the persisted drawer state at OPEN time.
                            savedSelections: savedSelectionsRef.current[agent.id],
                          });
                          router.push(routes.libraryAgent(agent.id, { tab: "agents", category: activeCategory, search: searchQuery }));
                        }
                      }}
                      {...(BETA_WORKFLOWS.has(getPrimaryPipelineType(agent.pipeline_type)) ? {} : CARD_KEYBOARD_PROPS)}
                      className={`flex flex-col p-[17px] min-h-[180px] transition-colors group ${
                        BETA_WORKFLOWS.has(getPrimaryPipelineType(agent.pipeline_type))
                          ? "opacity-60 cursor-not-allowed"
                          : "hover:border-line-control cursor-pointer"
                      }`}
                    >
                      <div className="flex items-center gap-3 mb-3">
                        <div className="w-10 h-10 rounded-[10px] flex items-center justify-center flex-shrink-0 bg-brand-fill text-brand">
                          <WorkflowIconComponent className="h-5 w-5" />
                        </div>
                        <div className="min-w-0">
                          <p className="font-sans text-[14px] font-semibold text-ink-900 leading-tight group-hover:text-brand transition-colors">{agent.name}</p>
                          <p className="text-[9px] text-ink-200 mt-1 uppercase tracking-[0.11em] font-semibold">{workflowLabel}</p>
                        </div>
                      </div>
                    <p className={`text-[12px] font-semibold mb-1.5 ${BETA_WORKFLOWS.has(getPrimaryPipelineType(agent.pipeline_type)) ? 'text-ink-400' : 'text-ink-700'}`}>{agent.role}</p>
                    <p className={`text-[12px] leading-relaxed line-clamp-3 ${BETA_WORKFLOWS.has(getPrimaryPipelineType(agent.pipeline_type)) ? 'text-ink-300' : 'text-ink-400'}`}>{agent.description}</p>
                    <span className="flex-1" />
                    <div className="flex items-center gap-2 mt-3.5 pt-3 border-t border-line-divider">
                      <Clock className="h-[13px] w-[13px] text-ink-200" />
                      <span className="text-[11.5px] text-ink-300">~{agent.estimated_duration}s</span>
                      <span className="flex-1" />
                      {BETA_WORKFLOWS.has(getPrimaryPipelineType(agent.pipeline_type)) ? (
                        <span className="text-[11.5px] font-medium text-ink-400">Coming Soon</span>
                      ) : (
                        <span className="text-[11.5px] font-medium text-brand">Configure →</span>
                      )}
                    </div>
                  </Card>
                  );
                })
              )}
            </div>
          </>
        )}

        {/* ── SKILLS ── */}
        {mainTab === "skills" && (
          <>
            <div className="flex flex-wrap gap-[7px] mb-5">
              {skillsStatus === "loading" ? (
                Array.from({ length: 6 }).map((_, i) => <CategoryChipSkeleton key={i} />)
              ) : (
                SKILL_CATEGORIES.map(cat => {
                  const isActive = skillCategory === cat.id;
                  const IconComponent = cat.icon ? getSkillCategoryIcon(cat.id) : null;
                  return (
                    <button key={cat.id} onClick={() => {
                      setSkillCategory(cat.id);
                      router.replace(routes.library({ tab: "skills", category: cat.id === "all" ? undefined : cat.id, search: skillSearch }));
                    }}
                      className={`${chipBase} ${isActive ? chipActive : chipIdle} flex items-center gap-1.5`}>
                      {IconComponent && <IconComponent className="h-3.5 w-3.5" />}
                      {cat.label}
                    </button>
                  );
                })
              )}
            </div>

            {/* Active skills grid */}
            <div className="grid grid-cols-[repeat(auto-fill,minmax(360px,1fr))] gap-3">
              {skillsStatus === "loading" ? (
                Array.from({ length: 6 }).map((_, i) => <SkillCardSkeleton key={i} />)
              ) : filteredSkills.length === 0 ? (
                // filteredSkills, not activeSkills: when only beta skills match,
                // the Coming Soon grid below still renders them, so the area is
                // not blank and "no skills match" would contradict it.
                <EmptyGridState noun="skills" query={skillSearch} onClear={() => applySearch("")} />
              ) : (
              activeSkills.map((skill) => {
                const IconComponent = getSkillCategoryIcon(skill.category);
                return (
                  <Card key={skill.id}
                    onClick={() => {
                      setSelectedSkill(skill);
                      router.push(routes.librarySkill(skill.id, { tab: "skills", category: skillCategory, search: skillSearch }));
                    }}
                    {...CARD_KEYBOARD_PROPS}
                    className="p-4 hover:border-line-control transition-colors cursor-pointer group"
                  >
                    <div className="flex items-center gap-2.5 mb-2.5">
                      <span className="w-[30px] h-[30px] flex-shrink-0 rounded-lg bg-brand-fill grid place-items-center text-brand">
                        <IconComponent className="h-[15px] w-[15px]" />
                      </span>
                      <div className="min-w-0">
                        <p className="font-sans text-[13.5px] font-semibold text-ink-900 leading-tight group-hover:text-brand transition-colors">{skill.name}</p>
                        <p className="text-[8.5px] text-ink-200 mt-0.5 uppercase tracking-[0.1em] font-semibold capitalize">{skill.category}</p>
                      </div>
                    </div>
                    <p className="text-[12px] text-ink-400 leading-relaxed mb-2.5 line-clamp-2">{skill.description}</p>
                    <div className="flex items-center flex-wrap gap-1.5">
                      {skill.tags.slice(0, 3).map(tag => (
                        <span key={tag} className="text-[10px] px-2 py-1 rounded-[5px] bg-surface-paper border border-line-border text-ink-500 font-medium">{tag}</span>
                      ))}
                      <span className="flex-1" />
                      <span className="text-[11px] font-medium text-brand self-center group-hover:opacity-80 transition-opacity">View →</span>
                    </div>
                  </Card>
                );
              })
              )}
            </div>

            {/* Coming Soon section */}
            {skillsStatus !== "loading" && betaSkills.length > 0 && (
              <>
                <div className="mt-10 mb-3.5 flex items-center gap-2">
                  <h3 className="text-[13px] font-semibold text-ink-500">Coming Soon</h3>
                  <span className="text-[11px] text-ink-400">Beta skills not yet available</span>
                </div>
                <div className="grid grid-cols-[repeat(auto-fill,minmax(360px,1fr))] gap-3">
                  {betaSkills.map((skill) => {
                    const IconComponent = getSkillCategoryIcon(skill.category);
                    return (
                      <Card key={skill.id}
                        className="p-4 opacity-60 cursor-not-allowed"
                      >
                        <div className="flex items-center gap-2.5 mb-2.5">
                          <span className="w-[30px] h-[30px] flex-shrink-0 rounded-lg bg-surface-warm grid place-items-center text-ink-400">
                            <IconComponent className="h-[15px] w-[15px]" />
                          </span>
                          <div className="min-w-0">
                            <p className="font-sans text-[13.5px] font-semibold text-ink-400 leading-tight">{skill.name}</p>
                            <p className="text-[8.5px] text-ink-200 mt-0.5 uppercase tracking-[0.1em] font-semibold capitalize">{skill.category}</p>
                          </div>
                        </div>
                        <p className="text-[12px] text-ink-400 leading-relaxed mb-2.5 line-clamp-2">{skill.description}</p>
                        <div className="flex items-center flex-wrap gap-1.5">
                          <span className="text-[10px] px-2 py-1 rounded-[5px] bg-surface-paper border border-line-border text-ink-500 font-medium">
                            Coming Soon
                          </span>
                        </div>
                      </Card>
                    );
                  })}
                </div>
              </>
            )}
          </>
        )}

        {/* ── HOOKS ── */}
        {mainTab === "hooks" && (
          <>
            <div className="flex flex-wrap gap-[7px] mb-5">
              {hooksStatus === "loading" ? (
                Array.from({ length: 5 }).map((_, i) => <CategoryChipSkeleton key={i} />)
              ) : (
                HOOK_EVENTS.map(ev => {
                  const isActive = hookEvent === ev.id;
                  return (
                    <button key={ev.id} onClick={() => {
                      setHookEvent(ev.id);
                      router.replace(routes.library({ tab: "hooks", category: ev.id === "all" ? undefined : ev.id, search: hookSearch }));
                    }}
                      className={`${chipBase} ${isActive ? chipActive : chipIdle}`}>
                      {ev.label}
                    </button>
                  );
                })
              )}
            </div>
            <div className="grid grid-cols-[repeat(auto-fill,minmax(360px,1fr))] gap-3">
              {hooksStatus === "loading" ? (
                Array.from({ length: 6 }).map((_, i) => <HookCardSkeleton key={i} />)
              ) : filteredHooks.length === 0 ? (
                <EmptyGridState noun="hooks" query={hookSearch} onClear={() => applySearch("")} />
              ) : (
              filteredHooks.map((hook) => (
                <Card key={hook.id}
                  onClick={() => {
                    setSelectedHook(hook);
                    router.push(routes.libraryHook(hook.id, { tab: "hooks", category: hookEvent, search: hookSearch }));
                  }}
                  {...CARD_KEYBOARD_PROPS}
                  className="p-4 hover:border-line-control transition-colors cursor-pointer group"
                >
                  <div className="flex items-center gap-2.5 mb-2">
                    <p className="font-sans text-[13.5px] font-semibold text-ink-900 leading-tight group-hover:text-brand transition-colors">{hook.name}</p>
                    <span className="flex-1" />
                    <span className="text-[9px] font-semibold px-2 py-1 rounded-[5px] bg-surface-near-black text-white flex-shrink-0">{hook.event}</span>
                  </div>
                  <p className="text-[11.5px] text-ink-200 italic mb-2">{hook.trigger}</p>
                  <p className="text-[12px] text-ink-400 leading-relaxed mb-2.5 line-clamp-2">{hook.description}</p>
                  <div className="flex items-center flex-wrap gap-1.5">
                    {hook.tags.slice(0, 3).map(tag => (
                      <span key={tag} className="text-[10px] px-2 py-1 rounded-[5px] bg-surface-paper border border-line-border text-ink-500 font-medium">{tag}</span>
                    ))}
                    <span className="flex-1" />
                    <span className="text-[11px] font-medium text-brand self-center group-hover:opacity-80 transition-opacity">View →</span>
                  </div>
                </Card>
              ))
              )}
            </div>
          </>
        )}
      </div>

      {/* Modals */}
      <AnimatePresence>
        {selectedAgent && (
          <AgentCapabilitiesModal
            agent={selectedAgent.agent}
            agentIndex={selectedAgent.index}
            onClose={closeDetailModal}
            asDrawer
            initialSelections={selectedAgent.savedSelections ?? {}}
            onSelectionsChange={(next) => {
              // Persist the selections for this agent so reopening restores them.
              savedSelectionsRef.current[selectedAgent.agent.id] = next;
            }}
            // ISS-318 — NO onSkillsChange: a catalog agent belongs to no
            // pipeline, so there is no step to write skills to and no backend
            // that stores them (ADR-0010). Omitting it is what makes
            // AgentSkillsPicker render readOnly, per its own documented
            // contract for this exact mount — an honest disabled list instead
            // of checkmarks and a count badge for a click nothing persists.
          />
        )}
      </AnimatePresence>
      <AnimatePresence>
        {selectedSkill && <SkillDetailModal skill={selectedSkill} onClose={closeDetailModal} />}
      </AnimatePresence>
      <AnimatePresence>
        {selectedHook && <HookDetailModal hook={selectedHook} onClose={closeDetailModal} />}
      </AnimatePresence>
    </div>
  );
}
