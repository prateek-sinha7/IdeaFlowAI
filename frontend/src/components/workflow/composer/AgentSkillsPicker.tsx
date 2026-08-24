"use client";

import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { Check, Info, Plus, Search, X } from "lucide-react";
import { useSkillsCatalog } from "@/hooks/useSkillsCatalog";
import type { AgentDef } from "@/types/index";
import type { SkillDef } from "@/store/api/skills";

/** Walk up from `el` to the nearest ancestor that actually scrolls. The
 *  picker has no scroll region of its own — it's mounted inside whichever
 *  scroll container the embedding surface owns (the rail's tab body, the
 *  Simple-view row's page scroll, the drawer's body) — so scroll-position
 *  preservation has to find that ancestor rather than assume one. */
function nearestScrollable(el: HTMLElement | null): HTMLElement | null {
  let node = el?.parentElement ?? null;
  while (node) {
    const style = getComputedStyle(node);
    if (/(auto|scroll)/.test(style.overflowY) && node.scrollHeight > node.clientHeight) {
      return node;
    }
    node = node.parentElement;
  }
  return null;
}

/**
 * Spec 012/013 (R-01/R-36/R-38) — the per-agent Skills picker. Since ADR-0010
 * retired run-level skill attachment this is the ONLY skill-attachment UI in the
 * app: the Canvas view's `CanvasConfigRail`, the Simple view's `AgentRow`, and
 * the agent inspector drawer (`AgentCapabilitiesModal`) all render this same
 * component, so they cannot drift.
 *
 * Filters the catalog by `compatible_agents`; a custom agent (`agent.isCustom`)
 * accepts any skill (R-34), a built-in is filtered (R-38). Absent/empty
 * `compatible_agents` means compatible with everything (R-33).
 *
 * SEARCH + CATEGORY FILTER are not decoration: the global catalog runs to ~185
 * skills, and a custom agent is compatible with all of them (R-34), so an
 * unfiltered list is an unusable scroll. The retired run-level picker had
 * both; dropping them when skills moved onto the agent made the per-agent
 * surface strictly worse than what it replaced. Selected skills are pinned to
 * the top so a filter can never hide something you already ticked.
 *
 * `readOnly` exists for the mounts with nowhere to write back — the Library
 * page's agent drawer (a catalog agent belonging to no pipeline) and the wizard
 * popup (which persists per-agent config through `onSelectionsChange`, a channel
 * that carries no skills field). Showing the real, correctly-filtered list
 * disabled is honest; showing live checkboxes that silently discard the click
 * is not.
 */
export function AgentSkillsPicker({
  agent,
  onSkillsChange,
  readOnly = false,
}: {
  agent: AgentDef;
  onSkillsChange?: (agentId: string, skills: string[]) => void;
  readOnly?: boolean;
}) {
  const { skills: SKILLS, categories: CATEGORIES } = useSkillsCatalog();
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");

  const selectedSkillIds = useMemo(() => new Set(agent.skills ?? []), [agent.skills]);

  const compatible = useMemo(
    () =>
      agent.isCustom
        ? SKILLS
        : SKILLS.filter(
            (s) => !s.compatible_agents?.length || s.compatible_agents.includes(agent.id),
          ),
    [SKILLS, agent.isCustom, agent.id],
  );

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    const matches = compatible.filter((s) => {
      // A ticked skill always stays visible — otherwise typing a query appears
      // to silently un-attach it, and the only way to untick is to clear the box.
      if (selectedSkillIds.has(s.id)) return true;
      const inCategory = category === "all" || s.category === category;
      const inQuery =
        !q ||
        s.name.toLowerCase().includes(q) ||
        (s.description ?? "").toLowerCase().includes(q);
      return inCategory && inQuery;
    });
    // Selected first, then alphabetical — keeps the ticked set reachable at a
    // glance without scrolling. The row does move on select, but nothing
    // scrolls the container to compensate — whatever ends up under the cursor
    // after the reflow is just normal list reflow, not a jump the picker forces.
    return matches.sort((a, b) => {
      const aSel = selectedSkillIds.has(a.id) ? 0 : 1;
      const bSel = selectedSkillIds.has(b.id) ? 0 : 1;
      return aSel - bSel || a.name.localeCompare(b.name);
    });
  }, [compatible, query, category, selectedSkillIds]);

  // Selected-first sort means ticking a skill near the bottom of a scrolled
  // list reorders it away instantly — the scroll container itself doesn't
  // move, but the row the user's mouse was over does, so the NEXT skill they
  // meant to click is now somewhere else. Capture the scroll offset right
  // before the toggle and restore it after the reorder repaints, so repeated
  // picks from the same scrolled-down spot don't require re-scrolling every time.
  const rootRef = useRef<HTMLDivElement>(null);
  const pendingScrollRestore = useRef<{ el: HTMLElement; top: number } | null>(null);

  const toggleSkill = (skillId: string) => {
    const scrollEl = nearestScrollable(rootRef.current);
    if (scrollEl) pendingScrollRestore.current = { el: scrollEl, top: scrollEl.scrollTop };
    const next = selectedSkillIds.has(skillId)
      ? (agent.skills ?? []).filter((id) => id !== skillId)
      : [...(agent.skills ?? []), skillId];
    onSkillsChange?.(agent.id, next);
  };

  useLayoutEffect(() => {
    if (pendingScrollRestore.current) {
      pendingScrollRestore.current.el.scrollTop = pendingScrollRestore.current.top;
      pendingScrollRestore.current = null;
    }
  });

  const selectedCount = selectedSkillIds.size;
  const [detailSkill, setDetailSkill] = useState<SkillDef | null>(null);

  return (
    <div ref={rootRef} data-testid={`agent-skills-picker-${agent.id}`}>
      <div className="mb-2 flex items-center justify-between">
        <p className="font-sans text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-300">
          Skills
        </p>
        {selectedCount > 0 && (
          <span className="rounded-full bg-brand px-1.5 py-0.5 font-sans text-[9px] font-semibold text-white">
            {selectedCount}
          </span>
        )}
      </div>

      {compatible.length === 0 ? (
        <p className="font-serif text-[11px] text-ink-300">No compatible skills.</p>
      ) : (
        <>
          {/* Search — shown once the list is long enough that scanning it by eye
              stops working. */}
          {compatible.length > 6 && (
            <div className="relative mb-2">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-ink-300" />
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search skills…"
                disabled={readOnly}
                aria-label="Search skills"
                name="skills-search"
                data-testid="agent-skills-search"
                className="w-full rounded-[7px] border border-line-faint-row bg-surface-warm py-1.5 pl-7 pr-2 font-sans text-[11px] text-ink-900 placeholder-ink-300 focus:border-line-control focus:outline-none disabled:opacity-50"
              />
            </div>
          )}

          {/* Category pills — only when the compatible set actually spans more
              than one category, so a two-skill agent gets no useless chrome. */}
          {CATEGORIES.length > 1 && compatible.length > 6 && (
            <div className="mb-2 flex flex-wrap gap-1">
              {CATEGORIES.filter(
                (c) => c.id === "all" || compatible.some((s) => s.category === c.id),
              ).map((c) => (
                <button
                  key={c.id}
                  type="button"
                  disabled={readOnly}
                  onClick={() => setCategory(c.id)}
                  className={`rounded-full px-2 py-0.5 font-sans text-[9px] font-semibold transition-colors disabled:opacity-50 ${
                    category === c.id
                      ? "bg-brand text-white"
                      : "bg-surface-warm text-ink-400 hover:text-ink-700"
                  }`}
                >
                  {c.label}
                </button>
              ))}
            </div>
          )}

          {visible.length === 0 ? (
            <p className="font-serif text-[11px] text-ink-300">No skills match.</p>
          ) : (
            // No max-height / inner scroll here (was `max-h-[240px]
            // overflow-y-auto`) — every mount already scrolls its own outer
            // container (the rail tab body, the row's expanding panel, the
            // drawer body), so a second, SHORTER scroll region nested inside
            // just clipped the list early instead of using the space actually
            // available.
            <div className="flex flex-col gap-1.5">
              {visible.map((s) => {
                const selected = selectedSkillIds.has(s.id);
                return (
                  <div
                    key={s.id}
                    className="flex items-start justify-between gap-2 rounded-[7px] border border-line-faint-row px-2 py-1.5"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1">
                        <span className="truncate font-sans text-[12px] text-ink-900">{s.name}</span>
                        <button
                          type="button"
                          onClick={() => setDetailSkill(s)}
                          aria-label={`View ${s.name} details`}
                          title="View details"
                          className="grid h-4 w-4 flex-none place-items-center rounded-full text-ink-300 hover:text-brand"
                        >
                          <Info className="h-3 w-3" />
                        </button>
                      </div>
                      {s.description && (
                        <p className="mt-0.5 line-clamp-1 font-serif text-[10.5px] text-ink-400">
                          {s.description}
                        </p>
                      )}
                    </div>
                    <button
                      type="button"
                      disabled={readOnly}
                      onClick={() => toggleSkill(s.id)}
                      aria-label={selected ? `Remove ${s.name}` : `Add ${s.name}`}
                      className={`grid h-6 w-6 flex-none place-items-center rounded-full transition-colors disabled:opacity-50 ${
                        selected
                          ? "bg-brand text-surface-white enabled:hover:bg-brand-pressed"
                          : "border border-line-control text-ink-400 enabled:hover:border-brand enabled:hover:text-brand"
                      }`}
                    >
                      {selected ? <Check className="h-3.5 w-3.5" /> : <Plus className="h-3.5 w-3.5" />}
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {readOnly && compatible.length > 0 && (
        <p className="mt-2 font-serif text-[11px] text-ink-300">
          Attach skills to this agent in the workflow composer.
        </p>
      )}

      {detailSkill && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-scrim p-4"
          onClick={() => setDetailSkill(null)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label={`${detailSkill.name} details`}
            onClick={(e) => e.stopPropagation()}
            className="flex max-h-[80vh] w-full max-w-[480px] flex-col overflow-hidden rounded-[14px] border border-line-control bg-surface-card shadow-[var(--elevation-modal)]"
          >
            <div className="flex flex-none items-center justify-between border-b border-line-divider px-4 py-3">
              <p className="font-sans text-[13px] font-semibold text-ink-900">{detailSkill.name}</p>
              <button
                type="button"
                onClick={() => setDetailSkill(null)}
                aria-label="Close"
                className="grid h-6 w-6 place-items-center rounded-md text-ink-400 hover:bg-surface-warm hover:text-ink-700"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
            <div className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
              {detailSkill.description && (
                <p className="font-serif text-[12px] leading-relaxed text-ink-600">
                  {detailSkill.description}
                </p>
              )}
              {detailSkill.content ? (
                <pre className="whitespace-pre-wrap rounded-[8px] border border-line-divider bg-surface-warm p-3 font-mono text-[11px] leading-relaxed text-ink-700">
                  {detailSkill.content}
                </pre>
              ) : (
                <p className="font-serif text-[11px] text-ink-300">No prompt content available.</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
