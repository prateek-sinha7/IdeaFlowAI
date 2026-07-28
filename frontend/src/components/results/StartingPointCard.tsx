"use client";

import { useState } from "react";
import { FileText, ChevronDown, Pencil, File, ImageOff } from "lucide-react";
import { parseRunInput } from "@/lib/runInput";

// ─────────────────────────────────────────────────────────────────────────────
// Workstream C2 (POR §5 D3) — StartingPointCard: the true beginning of the run's
// timeline, inserted BEFORE PlannerCard. CONSUMES C1's parseRunInput (no marker
// regex here — the legacy RevisionInstructionCard inline regex is superseded,
// INV-12). Variant is chosen by the PARSED shape (revisionInstruction / chain-
// Context), NEVER by a workflow-name string (SC-001). Renders on BOTH the live
// mount and the reopen mount from props alone (never reads pipelineState).
//
// Every visual node clones an existing analog (WORKSTREAM-C-UI-SPEC.md Surface 1):
//   card shell + timeline dot .......... PlannerCard AgentThinkingTab.tsx:108-177
//   revision emphasis block ............ RevisionInstructionCard :182-195
//   Show-more / Original-brief expander  InputPromptSection :371-405
//   attachment chip .................... IdeaInputPage.tsx:506-511
//   "revision of v{n-1}" micro chip .... AgentThinkingTab.tsx:324
// ─────────────────────────────────────────────────────────────────────────────

/** ND-10 (LOCK-E) — a payload-transient attachment ref. The backend stamps
 *  chat-turn image attachments `{kind:"image", retained:false}` with NO bytes
 *  (run_commands._persist_chat_message); image persistence for reopen/replay is
 *  DEFERRED. The honest reopen surface is a "not retained" placeholder derived
 *  SOLELY from this ref — never a fetch, never durable image storage. */
export interface AttachmentRef {
  kind: string;
  retained: boolean;
}

interface StartingPointCardProps {
  /** The run's raw input string; parsed via C1 parseRunInput. */
  input?: string;
  /** Family ROOT run id — enables the lazy "Original brief (v1)" expander
   *  (revision variant only). Absent → the expander is omitted (graceful). */
  originalBriefRootRunId?: string;
  /** The immediately-prior version number, for the "revision of v{n-1}" chip. */
  revisionParentVersion?: number;
  /** ND-10: payload-transient attachment refs for a reopened run. A
   *  `{kind:"image", retained:false}` ref renders the "image not retained"
   *  placeholder. Absent/empty → no placeholder, no layout change. */
  attachmentRefs?: AttachmentRef[];
}

export function StartingPointCard({ input, originalBriefRootRunId, revisionParentVersion, attachmentRefs }: StartingPointCardProps) {
  const parsed = parseRunInput(input ?? "");
  const isRevision = parsed.revisionInstruction !== undefined;
  const isChained = !isRevision && parsed.chainContext !== undefined;

  // ND-10: not-retained image refs → the honest "image not retained" placeholder.
  // Derived SOLELY from the retained:false ref — we render NO <img>, fetch no
  // bytes, and build no durable storage. A run with no such ref is unchanged.
  const notRetainedImageCount = (attachmentRefs ?? []).filter(
    (a) => a.kind === "image" && a.retained === false,
  ).length;

  const hasContent =
    !!parsed.brief ||
    parsed.revisionInstruction !== undefined ||
    parsed.attachments.length > 0 ||
    parsed.chainContext !== undefined ||
    notRetainedImageCount > 0;

  // Card body is open by default — the run's inputs are short and high-value.
  const [expanded, setExpanded] = useState(true);
  const [briefExpanded, setBriefExpanded] = useState(false);
  const [openAttachment, setOpenAttachment] = useState<number | null>(null);
  const [chainOpen, setChainOpen] = useState(false);

  // "Original brief (v1)" lazy fetch state (revision variant).
  const [originalOpen, setOriginalOpen] = useState(false);
  const [originalLoading, setOriginalLoading] = useState(false);
  const [originalBrief, setOriginalBrief] = useState<string | null>(null);
  const [originalFetched, setOriginalFetched] = useState(false);

  if (!hasContent) return null;

  const title = isRevision ? "Revision request" : "Starting point";
  const subtitle = isRevision
    ? parsed.revisionInstruction || ""
    : parsed.brief || (parsed.attachments.length > 0 ? `${parsed.attachments.length} attachment(s)` : "");

  const toggleOriginal = async () => {
    const next = !originalOpen;
    setOriginalOpen(next);
    if (next && !originalFetched && originalBriefRootRunId) {
      setOriginalFetched(true);
      setOriginalLoading(true);
      try {
        // B3 dynamic-import idiom — keeps AgentThinkingTab/PreviewPanel/Dashboard
        // suites from needing a getWorkflow mock (no static @/lib/api import here).
        const { getWorkflow, getToken } = await import("@/lib/api");
        const rootRun = await getWorkflow(getToken() || "", originalBriefRootRunId);
        setOriginalBrief(parseRunInput(rootRun.output ?? "").brief);
      } catch {
        setOriginalBrief("");
      } finally {
        setOriginalLoading(false);
      }
    }
  };

  return (
    <div className="rounded-xl border overflow-hidden border-gray-100">
      <button
          onClick={() => setExpanded(v => !v)}
          aria-expanded={expanded}
          aria-label={expanded ? `Collapse ${title.toLowerCase()}` : `Expand ${title.toLowerCase()}`}
          className="w-full flex items-center gap-3 px-4 py-3 bg-white hover:bg-gray-50/50 transition-colors text-left"
        >
          <div className="w-7 h-7 rounded-lg bg-[#E8EDF5] flex items-center justify-center flex-shrink-0">
            <FileText aria-hidden className="h-3.5 w-3.5 text-[#1B2A4A]" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <p className="text-[12px] font-semibold text-gray-900">{title}</p>
              {isRevision && revisionParentVersion != null && (
                <span className="text-[9px] bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded-full font-medium">
                  revision of v{revisionParentVersion}
                </span>
              )}
            </div>
            <p className="text-[10px] text-gray-400 truncate">{subtitle}</p>
          </div>
          <ChevronDown aria-hidden className={`h-3.5 w-3.5 text-gray-400 flex-shrink-0 transition-transform ${expanded ? "rotate-180" : ""}`} />
        </button>

        {expanded && (
          <div className="border-t border-gray-100 px-4 py-3 bg-white space-y-3">
            {/* REVISION variant — the instruction is the PRIMARY content */}
            {isRevision && (
              <>
                <div className="rounded-xl border-2 border-[#1B2A4A]/30 bg-[#1B2A4A]/5 px-3 py-2.5">
                  <div className="flex items-center gap-1.5 mb-1.5">
                    <Pencil aria-hidden className="h-3 w-3 text-[#1B2A4A]" />
                    <span className="text-[9px] font-bold text-[#1B2A4A] uppercase tracking-widest">Revision Request</span>
                  </div>
                  <p className="text-[11px] text-[#1B2A4A] font-medium leading-relaxed">{parsed.revisionInstruction}</p>
                </div>

                {/* Original brief (v1) — lazy fetch on first expand only */}
                {originalBriefRootRunId && (
                  <div aria-busy={originalLoading}>
                    <button
                      onClick={toggleOriginal}
                      aria-expanded={originalOpen}
                      aria-label="Show original brief version 1"
                      className="flex items-center gap-1.5 text-[9px] font-bold text-gray-400 uppercase tracking-widest hover:text-gray-600 transition-colors"
                    >
                      <FileText aria-hidden className="h-3 w-3" />
                      Original brief (v1)
                      <ChevronDown aria-hidden className={`h-3 w-3 transition-transform ${originalOpen ? "rotate-180" : ""}`} />
                    </button>
                    {originalOpen && (
                      <div className="mt-2">
                        {originalLoading ? (
                          <div className="flex items-center gap-2">
                            <span className="h-3.5 w-3.5 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
                            <span className="text-[10px] text-gray-400">Loading original brief…</span>
                          </div>
                        ) : (
                          <pre className="text-[9px] text-gray-600 whitespace-pre-wrap leading-relaxed p-3 rounded-lg border border-gray-100 bg-white max-h-[500px] overflow-y-auto font-mono">
                            {originalBrief && originalBrief.length > 0 ? originalBrief : "No original brief available."}
                          </pre>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </>
            )}

            {/* NORMAL / CHAINED variant — brief as line-clamped body w/ Show more */}
            {!isRevision && parsed.brief && (
              <div>
                <p className={`text-[11px] text-gray-700 leading-relaxed ${briefExpanded ? "whitespace-pre-wrap max-h-[500px] overflow-y-auto" : "line-clamp-2"}`}>
                  {parsed.brief}
                </p>
                <button
                  onClick={() => setBriefExpanded(v => !v)}
                  aria-expanded={briefExpanded}
                  aria-label={briefExpanded ? "Show less of the brief" : "Show more of the brief"}
                  className="mt-1 flex items-center gap-1 text-[9px] font-bold text-gray-400 uppercase tracking-widest hover:text-gray-600 transition-colors"
                >
                  {briefExpanded ? "Show less" : "Show more"}
                  <ChevronDown aria-hidden className={`h-3 w-3 transition-transform ${briefExpanded ? "rotate-180" : ""}`} />
                </button>
              </div>
            )}

            {!isRevision && !parsed.brief && parsed.attachments.length > 0 && (
              <p className="text-[10px] text-gray-400">No typed brief — see attachments below.</p>
            )}

            {/* CHAINED — "From previous workflow" collapsed chip */}
            {isChained && parsed.chainContext && (
              <div>
                <button
                  onClick={() => setChainOpen(v => !v)}
                  aria-expanded={chainOpen}
                  aria-label="Show context from previous workflow"
                  className="inline-flex items-center gap-1 rounded-lg bg-gray-100 px-2.5 py-1 text-[10px] text-gray-600 hover:bg-gray-200 transition-colors"
                >
                  <File aria-hidden className="h-2.5 w-2.5" />
                  From previous workflow
                  <ChevronDown aria-hidden className={`h-3 w-3 transition-transform ${chainOpen ? "rotate-180" : ""}`} />
                </button>
                {chainOpen && (
                  <pre className="mt-2 text-[9px] text-gray-600 whitespace-pre-wrap leading-relaxed p-3 rounded-lg border border-gray-100 bg-white max-h-[500px] overflow-y-auto font-mono">
                    {parsed.chainContext}
                  </pre>
                )}
              </div>
            )}

            {/* Attachment chips — each an expander revealing content inline */}
            {parsed.attachments.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {parsed.attachments.map((att, i) => (
                  <div key={`${att.name}-${i}`} className="w-full">
                    <button
                      onClick={() => setOpenAttachment(prev => (prev === i ? null : i))}
                      aria-expanded={openAttachment === i}
                      aria-label={`${openAttachment === i ? "Collapse" : "Expand"} attachment ${att.name}`}
                      className="inline-flex items-center gap-1 rounded-lg bg-gray-100 px-2.5 py-1 text-[10px] text-gray-600 hover:bg-gray-200 transition-colors"
                    >
                      <File aria-hidden className="h-2.5 w-2.5" />
                      {att.name} — {att.content.length} chars
                      <ChevronDown aria-hidden className={`h-3 w-3 transition-transform ${openAttachment === i ? "rotate-180" : ""}`} />
                    </button>
                    {openAttachment === i && (
                      <pre className="mt-1.5 text-[9px] text-gray-600 whitespace-pre-wrap leading-relaxed p-3 rounded-lg border border-gray-100 bg-white max-h-[500px] overflow-y-auto font-mono">
                        {att.content}
                      </pre>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* ND-10 (LOCK-E) — "image not retained" placeholder. Derived SOLELY
                from a retained:false image ref: no <img>, no byte fetch, no
                durable storage (image persistence for reopen is deferred). */}
            {notRetainedImageCount > 0 && (
              <div className="flex items-center gap-2 rounded-lg border border-dashed border-gray-200 bg-gray-50 px-3 py-2">
                <ImageOff aria-hidden className="h-3.5 w-3.5 text-gray-400 flex-shrink-0" />
                <p className="text-[10px] text-gray-500 leading-relaxed">
                  {notRetainedImageCount === 1 ? "Image not retained" : `${notRetainedImageCount} images not retained`}
                  {" — images are not stored after the run."}
                </p>
              </div>
            )}
          </div>
        )}
    </div>
  );
}
