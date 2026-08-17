"use client";

// ─────────────────────────────────────────────────────────────────────────────
// ArtifactVersionPicker — ISS-065. The per-artifact version control for the Steps
// L2 agent detail.
//
// `artifact_refs` versions every artifact per run and
// `GET /api/runs/{id}/artifacts` already returns each version (with its body under
// `?include=content`), but nothing surfaced it: the pipeline reducer clears an
// agent's `output` on every `agent_start` (FIX-039), so once the spec agent re-runs
// during an update_specs cycle the earlier text is gone from memory and the panel
// shows the newest version with no way back.
//
// This is a DIFFERENT AXIS from the run-header "Version v1" menu, which walks the
// run FAMILY (`parent_run_id`). Locked decision D2 (IMPLEMENTATION-REGISTER.md:2531)
// defines that control's version as the family chronological index and says in terms
// that it is NOT `artifact_refs.version` — so this axis needs its own control.
// ─────────────────────────────────────────────────────────────────────────────

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronDown, Check } from "lucide-react";
import type { ArtifactNode } from "@/lib/api";

/** One selectable version, after the two artifact-ref series have been collapsed. */
export interface ArtifactVersion {
  /** artifact_refs.id of the row this entry was taken from. */
  id: string;
  /** Display label — the typed kind ("spec", "task_list", "html_file"). */
  kind: string;
  /** artifact_refs.version of that row. Kept for the option's title text. */
  version: number;
  /** 1-based position AFTER dedupe — what "v{n}" shows. */
  index: number;
  contentHash: string;
  /** Body size in characters, when the list call happened to carry content. */
  chars?: number;
}

export interface ArtifactVersionPickerProps {
  /** The run whose artifacts to list. Null/undefined → render nothing. */
  runId: string | null | undefined;
  /** The agent to scope to. Matches `ArtifactNode.producer_agent`. */
  agentId: string;
  /** 1-based index currently displayed; undefined → the latest. */
  selectedIndex?: number;
  /** Fires with the chosen version's CONTENT, or null to return to live output. */
  onSelect: (v: { index: number; content: string } | null) => void;
}

/**
 * Collapse a run's artifact nodes into this agent's distinct versions.
 *
 * Every artifact is written TWICE — once under its typed kind and once under a
 * `produces` alias equal to the agent id (engine.py:4278-4308). Those two series do
 * NOT stay in lockstep: on a real prototype run `html_file` reaches v23 while
 * `prototype-build` reaches v11, because the build task-loop writes one html_file per
 * task iteration. So the only rule that survives both shapes is dedupe by
 * `content_hash`; deduping by `(kind, version)` breaks on the build agent.
 *
 * Consequence, accepted deliberately: a re-run that produces byte-identical output
 * collapses into one entry. That reads as "nothing changed", which is true.
 *
 * Response order is chronological (`created_at ASC, version ASC, id ASC` — authz.py),
 * and the typed-kind row is written before its alias, so first-occurrence-wins
 * normally yields the typed kind. The explicit preference below makes that
 * independent of arrival order rather than relying on it.
 */
export function collapseVersions(nodes: ArtifactNode[], agentId: string): ArtifactVersion[] {
  const byHash = new Map<string, ArtifactVersion>();
  for (const n of nodes) {
    if (n.producer_agent !== agentId) continue;
    const existing = byHash.get(n.content_hash);
    if (!existing) {
      byHash.set(n.content_hash, {
        id: n.id,
        kind: n.kind,
        version: n.version,
        index: 0,
        contentHash: n.content_hash,
        chars: n.content?.length,
      });
    } else if (existing.kind === agentId && n.kind !== agentId) {
      // The typed kind is the better label; take its row wholesale so a later
      // content fetch keyed on `kind` can find this entry by id.
      byHash.set(n.content_hash, { ...existing, id: n.id, kind: n.kind, version: n.version });
    }
  }
  return [...byHash.values()].map((v, i) => ({ ...v, index: i + 1 }));
}

export function ArtifactVersionPicker({
  runId,
  agentId,
  selectedIndex,
  onSelect,
}: ArtifactVersionPickerProps) {
  const [versions, setVersions] = useState<ArtifactVersion[]>([]);
  const [open, setOpen] = useState(false);
  const [highlightIdx, setHighlightIdx] = useState(0);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const optionRefs = useRef<(HTMLButtonElement | null)[]>([]);
  /** Bodies already fetched, keyed by artifact kind — the 2.89 MB guard. */
  const contentCache = useRef<Map<string, ArtifactNode[]>>(new Map());

  // List-only fetch. Copies the tolerant in-component idiom already used for the
  // gate-events strips (AgentThinkingTab.tsx): cancelled guard, dynamic import,
  // silent degrade. This surface must never throw into the Steps panel.
  useEffect(() => {
    contentCache.current.clear();
    if (!runId) {
      setVersions([]);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const { getRunArtifacts, getToken } = await import("@/lib/api");
        const resp = await getRunArtifacts(getToken() || "", runId);
        // The mocked e2e fixture answers every unmatched /api/** with `{}`, so
        // `artifacts` is genuinely absent there — not merely a defensive default.
        if (!cancelled) setVersions(collapseVersions(resp?.artifacts ?? [], agentId));
      } catch {
        if (!cancelled) setVersions([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [runId, agentId]);

  const selected = selectedIndex ?? versions.length;

  const close = useCallback(() => {
    setOpen(false);
    buttonRef.current?.focus();
  }, []);

  const select = useCallback(
    async (v: ArtifactVersion) => {
      setOpen(false);
      buttonRef.current?.focus();
      // The newest entry IS the live output — hand control back rather than
      // pinning a copy that stops updating while the agent streams.
      if (v.index === versions.length) {
        onSelect(null);
        return;
      }
      try {
        const { getRunArtifacts, getToken } = await import("@/lib/api");
        let rows = contentCache.current.get(v.kind);
        if (!rows) {
          const resp = await getRunArtifacts(getToken() || "", runId as string, {
            kind: v.kind,
            includeContent: true,
          });
          rows = resp?.artifacts ?? [];
          contentCache.current.set(v.kind, rows);
        }
        const row = rows.find((r) => r.id === v.id);
        if (row) onSelect({ index: v.index, content: row.content ?? "" });
      } catch {
        /* leave the panel on the live output */
      }
    },
    [onSelect, runId, versions.length],
  );

  useEffect(() => {
    if (open) optionRefs.current[highlightIdx]?.focus();
  }, [open, highlightIdx]);

  // A single version is the normal case — render nothing at all so every run that
  // never revised looks exactly as it did before.
  if (versions.length <= 1) return null;

  const label = versions[0].kind;

  const onListKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      close();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightIdx((i) => Math.min(i + 1, versions.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      const v = versions[highlightIdx];
      if (v) void select(v);
    }
  };

  return (
    <div className="relative flex-none">
      <button
        ref={buttonRef}
        type="button"
        data-testid="artifact-version-picker"
        onClick={() => {
          if (open) {
            setOpen(false);
          } else {
            setHighlightIdx(Math.max(0, selected - 1));
            setOpen(true);
          }
        }}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`${label} version ${selected} of ${versions.length}, choose version`}
        className="inline-flex items-center gap-[7px] rounded-[9px] border border-line-control bg-surface-card px-2.5 py-1.5 transition-colors hover:border-line-faint"
      >
        <span aria-hidden className="h-[6px] w-[6px] rounded-full bg-brand" />
        <span className="font-sans text-[11px] font-semibold leading-none text-ink-900">
          {label} · v{selected} of {versions.length}
        </span>
        <ChevronDown
          aria-hidden
          className={`h-3 w-3 text-ink-400 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <>
          {/* Outside-click catcher. */}
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div
            role="listbox"
            aria-label={`${label} versions`}
            onKeyDown={onListKeyDown}
            className="absolute right-0 top-[38px] z-20 max-h-[280px] w-[210px] overflow-y-auto rounded-[12px] border border-line-border bg-surface-white p-1.5 shadow-[0_12px_32px_rgba(17,17,20,0.12)]"
          >
            {versions.map((v, i) => {
              const isActive = v.index === selected;
              const isHighlighted = i === highlightIdx;
              return (
                <button
                  key={v.id}
                  ref={(el) => {
                    optionRefs.current[i] = el;
                  }}
                  type="button"
                  role="option"
                  aria-selected={isActive}
                  tabIndex={i === highlightIdx ? 0 : -1}
                  onMouseEnter={() => setHighlightIdx(i)}
                  onClick={() => void select(v)}
                  className={`flex w-full items-center gap-2.5 rounded-[8px] px-2.5 py-2 text-left transition-colors ${
                    isHighlighted ? "bg-surface-warm" : "hover:bg-surface-warm"
                  }`}
                >
                  <span
                    aria-hidden
                    className={`h-[6px] w-[6px] flex-none rounded-full ${isActive ? "bg-brand" : "bg-line-faint"}`}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="m-0 font-sans text-[12px] font-semibold leading-[1.2] text-ink-900">
                      v{v.index}
                      {v.index === versions.length ? " · latest" : ""}
                    </p>
                    <p className="m-0 mt-0.5 font-serif text-[11px] font-normal leading-none text-ink-300">
                      {/* No created_at on the node shape (runs.py:907-925), so label by
                          size rather than inventing a time. */}
                      {v.chars !== undefined ? `${v.chars.toLocaleString()} chars` : v.contentHash.slice(0, 8)}
                    </p>
                  </div>
                  {isActive && <Check aria-hidden className="h-[14px] w-[14px] flex-none text-brand" />}
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
