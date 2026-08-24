"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "motion/react";
import {
  ArrowLeft, ArrowRight, Paperclip, File, X, FileText,
  Presentation, Layout, Settings2, Mic, MicOff, GitBranch,
  Save, Check, Image as ImageIcon, Sparkles, Plus,
} from "lucide-react";
import { AgentsPopup } from "./AgentsPopup";
import { ReviewGatesSection } from "./ReviewGatesSection";
import { useAgentLibrary } from "@/hooks/useAgentLibrary";
import { NameWorkflowModal } from "@/components/catalog/NameWorkflowModal";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";
import { useSkillsHooks } from "@/context/SkillsHooksContext";
import { collectAgentIds, instantiateIfTemplate } from "@/store/api/userWorkflows";
import { createUserWorkflow, getToken, getWorkflowDetail, extractFileText } from "@/lib/api";
import { ATTACH_MAX_CHARS } from "@/lib/constants";
import { resizeImage } from "@/lib/resizeImage";
import { AnimatePresence } from "motion/react";
import type { WorkflowType, AgentDef, AttachedSkill, AttachedHook } from "@/types/index";

// Migration is a meta-pipeline: the home page sends `workflowType="migration"`
// and this page lets the user pick the concrete sub-pipeline before running.
// Defined at module scope so the constant is identity-stable for hook deps.
const MIGRATION_OPTIONS: { type: WorkflowType; label: string; tagline: string }[] = [
  {
    type: "mulesoft_to_springboot",
    label: "Mulesoft → Spring Boot microservices on AWS",
    tagline: "Catalogue the Mule estate, decompose into Spring Boot 3 services, generate the AWS landing zone, and harness the cutover.",
  },
  {
    type: "dotnet_to_azure",
    label: ".NET → Azure (AI-augmented)",
    tagline: "Inventory .NET projects, map each to the right Azure service, modernise to .NET 8, and bolt on Azure AI where it pays off.",
  },
];

// ---------------------------------------------------------------------------
// KAN-112: Smart agent recommendations for custom workflows
// ---------------------------------------------------------------------------

// Companion agent groups: when ANY agent from a group is added, recommend the rest.
// This gives the user the correct full pipeline in the right order.
const COMPANION_GROUPS: { ids: string[]; label: string; description: string }[] = [
  {
    ids: ["prototype-specify", "prototype-plan", "prototype-analyze", "prototype-build", "prototype-validate"],
    label: "Complete Prototype Pipeline",
    description: "Add the full prototype pipeline — Spec Writer → Task Planner → Analyzer → Builder → Validator — to generate a navigable HTML prototype.",
  },
  {
    ids: ["ppt-brief-analyst", "ppt-composer", "ppt-validator"],
    label: "Complete Presentation Pipeline",
    description: "Add all 3 presentation agents — Strategist → Deck Engineer → QA — to generate a full HTML deck.",
  },
  {
    ids: ["domain-analyst", "epic-architect", "story-estimator", "nfr-specialist", "backlog-reviewer", "backlog-compiler"],
    label: "Complete User Stories Pipeline",
    description: "Add the full backlog pipeline — Discovery → Architecture → Estimation → Quality → Review → Compile — to generate Jira-ready user stories.",
  },
];

// ---------------------------------------------------------------------------
// Intent-based recommendation engine (replaces flat keyword matching).
//
// Problems with the old approach:
//   - Generic words like "app", "product", "design" matched the WRONG pipeline.
//     e.g. "user stories for a banking app" fired prototype agents because "app"
//     was in the prototype keyword list.
//   - No priority: if multiple intents were detected, all agents were returned
//     mixed together with no signal about which pipeline the user actually needs.
//   - Substring matching: "product" matched "product management" (user_stories)
//     AND "app" in "application" matched prototype.
//
// New approach:
//   1. Each INTENT has STRONG signals (high-confidence, intent-specific phrases)
//      and WEAK signals (supporting context words that only count if a strong
//      signal is also present from the same group — prevents cross-contamination).
//   2. EXCLUSION terms: if the brief contains any of these for a given intent,
//      that intent is suppressed even if weak signals are present.
//   3. PRIORITY ordering: when multiple intents fire, only the top-priority one
//      drives the agent recommendation chips. Companion banners still show for
//      partially-complete pipelines.
//   4. Word-boundary matching on ambiguous terms to avoid substring false-positives.
// ---------------------------------------------------------------------------

type Intent = {
  id: string;
  priority: number;                // lower = higher priority (1 = most specific)
  strongSignals: string[];         // whole-phrase matches — any one fires the intent
  weakSignals?: string[];          // supporting context — only count with a strong hit
  exclusions?: string[];           // if present, suppress this intent
  agentIds: string[];
};

const INTENT_MAP: Intent[] = [
  // ── User Stories / Backlog ─────────────────────────────────────────────
  // Strong: explicit backlog/story/requirements language
  {
    id: "user_stories",
    priority: 1,
    strongSignals: [
      "user stor", "user-stor",       // "user story", "user stories", "user-story"
      "backlog",
      "epic",
      "acceptance criteria",
      "gherkin",
      "jira",
      "sprint planning",
      "product requirement",
      "prd",                          // Product Requirements Document
      "functional requirement",
      "feature requirement",
      "brd",                          // Business Requirements Document
      "requirements document",
      "requirements doc",
      "agile requirements",
      "story point",
      "definition of done",
      "nfr",                          // Non-functional requirements
    ],
    weakSignals: ["feature", "requirement", "stories", "story"],
    agentIds: ["domain-analyst", "epic-architect", "story-estimator", "nfr-specialist", "backlog-reviewer", "backlog-compiler"],
  },

  // ── Prototype / UI ────────────────────────────────────────────────────
  // Strong: explicit prototype/UI-building language
  {
    id: "prototype",
    priority: 2,
    strongSignals: [
      "prototype",
      "mockup",
      "wireframe",
      "interactive ui",
      "interactive prototype",
      "clickable",
      "navigable",
      "html prototype",
      "ui prototype",
      "low-fidelity",
      "high-fidelity",
      "figma",
      "build a dashboard",
      "build the dashboard",
      "build a portal",
      "build a webapp",
      "build a web app",
      "build an app",
      "saas dashboard",
      "admin panel",
      "admin dashboard",
      "landing page",
      "web interface",
    ],
    weakSignals: ["dashboard", "interface", "screen", "page", "portal", "ui", "ux"],
    exclusions: ["slide", "presentation", "deck", "user stor", "backlog", "epic", "requirements document"],
    agentIds: ["prototype-specify", "prototype-plan", "prototype-analyze", "prototype-build", "prototype-validate"],
  },

  // ── Presentation / Deck ───────────────────────────────────────────────
  {
    id: "presentation",
    priority: 2,
    strongSignals: [
      "presentation",
      "slide deck",
      "slide show",
      "pitch deck",
      "powerpoint",
      "ppt",
      " deck ",          // "a deck for" — note spaces to avoid "deck" in "deckchair"
      "investor deck",
      "executive presentation",
      "board presentation",
      "stakeholder presentation",
    ],
    agentIds: ["ppt-brief-analyst", "ppt-composer", "ppt-validator"],
  },

  // ── Market Research / Competitive Analysis ────────────────────────────
  {
    id: "market_research",
    priority: 3,
    strongSignals: [
      "market research",
      "competitive analysis",
      "competitive landscape",
      "competitor analysis",
      "market analysis",
      "industry analysis",
      "market sizing",
      "tam ",             // Total Addressable Market — space avoids "team"
      "sam ",
      "som ",
      "go-to-market",
      "gtm strategy",
    ],
    agentIds: ["market-research-agent", "swot-analyst"],
  },

  // ── Strategy / SWOT ───────────────────────────────────────────────────
  {
    id: "strategy",
    priority: 3,
    strongSignals: [
      "swot",
      "strategic analysis",
      "strategic plan",
      "business strategy",
      "positioning strategy",
      "market positioning",
      "strengths and weaknesses",
      "opportunities and threats",
    ],
    agentIds: ["swot-analyst", "roadmap-planner"],
  },

  // ── Roadmap / Planning ────────────────────────────────────────────────
  {
    id: "roadmap",
    priority: 3,
    strongSignals: [
      "product roadmap",
      "delivery roadmap",
      "roadmap",
      "release plan",
      "milestone plan",
      "quarterly plan",
      "q1 plan", "q2 plan", "q3 plan", "q4 plan",
      "phased delivery",
      "delivery plan",
    ],
    agentIds: ["roadmap-planner", "market-research-agent"],
  },

  // ── Security ──────────────────────────────────────────────────────────
  {
    id: "security",
    priority: 3,
    strongSignals: [
      "security audit",
      "security review",
      "security assessment",
      "penetration test",
      "pentest",
      "vulnerability assessment",
      "threat model",
      "owasp",
      "security risk",
      "cyber security",
      "cybersecurity",
      "compliance audit",
      "gdpr audit",
      "iso 27001",
    ],
    agentIds: ["security-auditor"],
  },

  // ── Testing / QA ──────────────────────────────────────────────────────
  {
    id: "testing",
    priority: 3,
    strongSignals: [
      "test cases",
      "test scenarios",
      "test plan",
      "test strategy",
      "qa strategy",
      "quality assurance",
      "test coverage",
      "edge cases",
      "regression test",
      "test suite",
      "automated test",
      "unit test",
      "integration test",
    ],
    agentIds: ["test-case-generator"],
  },

  // ── Performance ───────────────────────────────────────────────────────
  {
    id: "performance",
    priority: 3,
    strongSignals: [
      "performance optimiz",
      "performance optimis",
      "performance audit",
      "performance review",
      "latency issue",
      "slow performance",
      "bottleneck",
      "load time",
      "throughput",
      "profiling",
    ],
    agentIds: ["performance-optimizer"],
  },

  // ── Documentation ─────────────────────────────────────────────────────
  {
    id: "documentation",
    priority: 3,
    strongSignals: [
      "documentation",
      "api docs",
      "api documentation",
      "readme",
      "technical guide",
      "developer guide",
      "setup guide",
      "onboarding guide",
      "write docs",
      "document the",
      "runbook",
    ],
    agentIds: ["documentation-agent"],
  },

  // ── Report / Executive Summary ────────────────────────────────────────
  {
    id: "report",
    priority: 3,
    strongSignals: [
      "executive report",
      "executive summary",
      "management report",
      "board report",
      "status report",
      "kpi report",
      "metrics report",
      "business report",
      "insights report",
      "generate a report",
      "write a report",
      "produce a report",
    ],
    agentIds: ["report-generator"],
  },
];

/**
 * Intent-aware recommendation engine.
 *
 * Returns a priority-ranked, deduplicated list of AgentDefs to recommend
 * based on the user's brief. Only fires when brief >= 10 chars.
 *
 * Ranking: higher-priority (lower number) intents come first. Within the
 * same priority tier, the order follows INTENT_MAP definition order.
 * Already-present agents are excluded from the returned list.
 */
function getAgentRecommendations(allAgents: AgentDef[], brief: string, currentAgentIds: Set<string>): AgentDef[] {
  if (!brief || brief.trim().length < 10) return [];
  const lower = brief.toLowerCase();

  // Score each intent
  const matched: { intent: Intent; score: number }[] = [];

  for (const intent of INTENT_MAP) {
    // Check exclusions first — if any exclusion phrase is present, skip
    if (intent.exclusions?.some((exc) => lower.includes(exc))) continue;

    // Check strong signals — any one is enough to fire the intent
    const hasStrong = intent.strongSignals.some((sig) => lower.includes(sig));
    if (!hasStrong) continue;

    // Weak signals count as bonus score (not required to fire)
    const weakScore = intent.weakSignals
      ? intent.weakSignals.filter((w) => lower.includes(w)).length
      : 0;

    matched.push({ intent, score: weakScore });
  }

  if (matched.length === 0) return [];

  // Sort: priority ASC (lower = more specific), then weak score DESC
  matched.sort((a, b) =>
    a.intent.priority !== b.intent.priority
      ? a.intent.priority - b.intent.priority
      : b.score - a.score,
  );

  // Collect agent IDs in priority order, deduplicating
  const recommended = new Set<string>();
  for (const { intent } of matched) {
    intent.agentIds.forEach((id) => recommended.add(id));
  }

  // Remove already-added agents
  currentAgentIds.forEach((id) => recommended.delete(id));
  if (recommended.size === 0) return [];

  // Resolve to AgentDef objects
  return Array.from(recommended)
    .map((id) => allAgents.find((a) => a.id === id))
    .filter(Boolean) as AgentDef[];
}

// Derive the correct pipeline_type and optional deliverable override to dispatch
// based on the chosen agent set.
// KAN-112 Option B: instead of routing to a manifest copy ("custom_prototype"),
// we keep pipeline_type="custom" and inject a __deliverable__ override into the
// selections map.  The engine's _apply_selections reads it and swaps the compiled
// plan's deliverable spec at run entry — no manifest copies, SC-001 compliant.
//
// User stories agents → "user_stories" (streamed_text markdown → UserStoryPreview).
// Prototype agents   → pipeline_type="custom" + __deliverable__={prototype.html}.
// PPT agents         → pipeline_type="custom" (od_ppt requires template_id).
// Everything else    → pipeline_type="custom" (streamed_text default).

// Map: if ANY of these agent ids are present, inject the corresponding deliverable
// override so the engine swaps the compiled plan's deliverable spec at run entry.
// ALL custom-composer runs stay pipeline_type="custom" — consistent labelling in
// logs, history, and the UI regardless of which agents were selected.
const AGENT_DELIVERABLE_MAP: { agents: string[]; deliverable: Record<string, string> }[] = [
  {
    // Prototype agents → single_file HTML output.
    // KAN-121 / FIX-110: all 5 prototype pipeline agents are listed as triggers so
    // the deliverable override fires for ANY prototype agent combination — including
    // compositions that omit prototype-build/specify/plan but include prototype-analyze
    // or prototype-validate (e.g. a user following the COMPANION_GROUPS recommendation).
    agents: ["prototype-build", "prototype-specify", "prototype-plan", "prototype-analyze", "prototype-validate"],
    deliverable: { strategy: "single_file", name: "prototype.html", mimetype: "text/html" },
  },
  {
    // User story agents → streamed_text markdown output
    // Stays pipeline_type="custom" for consistency — no routing to "user_stories".
    // GenericDeliverablePreview renders text/markdown via MarkdownPreview.
    agents: ["epic-architect", "domain-analyst", "backlog-compiler", "story-estimator", "nfr-specialist", "backlog-reviewer"],
    deliverable: { strategy: "streamed_text", name: "user_stories.md", mimetype: "text/markdown" },
  },
  {
    // PPT agents → single_file HTML output (no template — creative free-form).
    // Uses single_file strategy (reads from sandbox file) instead of ppt strategy
    // (reads from last_streamed) to avoid tool-call noise polluting the output.
    // The ppt-brief-analyst/composer AGENT.md handle theme_choice="custom"
    // (no ACTIVE TEMPLATE injected) and build the deck from visual_style in the spec.
    agents: ["ppt-brief-analyst", "ppt-composer", "ppt-validator"],
    deliverable: { strategy: "single_file", name: "presentation.html", mimetype: "text/html" },
  },
];

function resolveDispatchType(
  agents: AgentDef[],
  baseType: WorkflowType,
): { type: WorkflowType; deliverableOverride?: Record<string, string> } {
  if (baseType !== "custom") return { type: baseType };
  const ids = new Set(agents.map((a) => a.id));
  // All custom-composer runs stay pipeline_type="custom".
  // Deliverable override is injected based on the selected agent set so the
  // engine produces the right output type (HTML prototype, markdown stories, etc.)
  // without routing to a different manifest — consistent type in logs + history.
  for (const { agents: keys, deliverable } of AGENT_DELIVERABLE_MAP) {
    if (keys.some((id) => ids.has(id))) {
      return { type: "custom", deliverableOverride: deliverable };
    }
  }
  return { type: "custom", deliverableOverride: { strategy: "streamed_text", name: "output.md", mimetype: "text/markdown" } };
}

/** Export for ComposerPage (INV-12 — single source, no duplication). */
export { getAgentRecommendations, COMPANION_GROUPS, resolveDispatchType, AGENT_DELIVERABLE_MAP };

/**
 * Shared attachment state for the Brief input box (KAN-91 / Image-input Wave 2).
 * Extracted so BOTH IdeaInputPage and ComposerPage's Simple view mount the SAME
 * attach/extract logic (INV-3, no forked implementation) — file/image attach,
 * client-side image downscale (resizeImage), and PDF/docx/pptx text extraction
 * (extractFileText) all live here once.
 */
export function useBriefAttachments() {
  const [attachedFiles, setAttachedFiles] = useState<{ name: string; size: string }[]>([]);
  // KAN-91: file content stored separately so the textarea stays clean —
  // composed into the run message at send time via `fileBlocks` below.
  const [attachedFileContents, setAttachedFileContents] = useState<{ name: string; content: string }[]>([]);
  // Image-input Wave 2: images ride OUT-OF-BAND as the `images` payload field
  // (D3) — NEVER inlined into the brief text (base64 would blow past
  // ATTACH_MAX_CHARS almost immediately).
  const [attachedImages, setAttachedImages] = useState<{ name: string; mime_type: string; data: string }[]>([]);

  const handleFiles = useCallback((files: FileList) => {
    Array.from(files).forEach((f) => {
      const isImageFile =
        ["image/png", "image/jpeg", "image/webp", "image/gif"].includes(f.type) ||
        /\.(png|jpe?g|webp|gif)$/i.test(f.name);
      if (isImageFile) {
        // UPLD-04: downscale oversized images client-side BEFORE base64 —
        // aspect-preserving, no-upscale, degrade-not-block.
        resizeImage(f).then((resized) => {
          setAttachedImages((p) => [
            ...p,
            { name: f.name, mime_type: resized.mime_type, data: resized.data },
          ]);
        });
        return;
      }
      const meta = {
        name: f.name,
        size:
          f.size < 1024
            ? `${f.size}B`
            : f.size < 1048576
              ? `${(f.size / 1024).toFixed(1)}KB`
              : `${(f.size / 1048576).toFixed(1)}MB`,
      };
      setAttachedFiles((p) => [...p, meta]);
      const isTextFile = /\.(txt|md|json|csv)$/i.test(f.name);
      const isBinaryFile = /\.(pdf|docx|pptx)$/i.test(f.name);
      if (isTextFile) {
        const reader = new FileReader();
        reader.onload = (ev) => {
          const content = (ev.target?.result as string) ?? "";
          setAttachedFileContents((p) => [
            ...p,
            { name: f.name, content: content.slice(0, ATTACH_MAX_CHARS) },
          ]);
        };
        reader.readAsText(f);
      } else if (isBinaryFile) {
        const jwt = getToken();
        if (jwt) {
          extractFileText(jwt, f)
            .then((res) => {
              const truncNote = res.truncated
                ? `\n[Content truncated to ${ATTACH_MAX_CHARS.toLocaleString()} chars]`
                : "";
              setAttachedFileContents((p) => [
                ...p,
                { name: res.filename, content: `${res.text}${truncNote}` },
              ]);
            })
            .catch(() => {
              setAttachedFileContents((p) => [
                ...p,
                { name: f.name, content: "[could not extract text]" },
              ]);
            });
        } else {
          setAttachedFileContents((p) => [...p, { name: f.name, content: "" }]);
        }
      }
      // For other file types: chip shows but no content is sent (no text to extract).
    });
  }, []);

  const removeFile = useCallback((idx: number) => {
    setAttachedFiles((p) => {
      const removedName = p[idx]?.name;
      if (removedName) {
        setAttachedFileContents((c) => c.filter((f) => f.name !== removedName));
      }
      return p.filter((_, i) => i !== idx);
    });
  }, []);

  const removeImage = useCallback((idx: number) => {
    setAttachedImages((p) => p.filter((_, i) => i !== idx));
  }, []);

  // KAN-91: the exact block format the run payload has always used — compose
  // at send time, not attach time, so the textarea itself stays clean.
  const fileBlocks = attachedFileContents
    .map((f) => `\n\n=== Attached: ${f.name} ===\n${f.content}\n=== End: ${f.name} ===`)
    .join("");

  return { attachedFiles, attachedFileContents, attachedImages, handleFiles, removeFile, removeImage, fileBlocks };
}

export type BriefAttachments = ReturnType<typeof useBriefAttachments>;

/**
 * Shared Brief textarea + file/image attach UI (KAN-91 / Image-input Wave 2).
 * Reused verbatim by ComposerPage's Simple view (INV-3) — same textarea,
 * attach button, PDF/docx/pptx extraction, and chip list IdeaInputPage has
 * always had. Renders ONLY the inner content (no outer card border) so each
 * page keeps its own surrounding card and can add page-specific siblings
 * (Save/Run, save-error text, a save modal) around it without this component
 * needing to know about them. `leftExtra`/`rightSlot` place page-specific
 * controls (mic, Save/Run) in the same toolbar row without forking it.
 */
export function BriefAttachBox({
  value,
  onChange,
  placeholder,
  attachments,
  textareaRef,
  onSubmitShortcut,
  rows = 5,
  leftExtra,
  rightSlot,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  attachments: BriefAttachments;
  textareaRef?: React.RefObject<HTMLTextAreaElement | null>;
  /** Cmd/Ctrl+Enter while focused in the textarea. */
  onSubmitShortcut?: () => void;
  rows?: number;
  leftExtra?: React.ReactNode;
  rightSlot?: React.ReactNode;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { attachedFiles, attachedImages, handleFiles, removeFile, removeImage } = attachments;

  return (
    <>
      <textarea
        ref={textareaRef}
        name="brief"
        aria-label="Brief description"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full resize-none bg-transparent text-[14px] text-ink-900 placeholder-ink-400 px-5 pt-5 pb-3 focus:outline-none min-h-[130px] max-h-[260px] leading-relaxed"
        rows={rows}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) onSubmitShortcut?.();
        }}
      />

      {attachedFiles.length > 0 && (
        <div className="flex flex-wrap gap-1.5 px-5 pb-2">
          {attachedFiles.map((file, idx) => (
            <span
              key={`${file.name}-${idx}`}
              className="inline-flex items-center gap-1 rounded-lg bg-surface-warm px-2.5 py-1 text-[10px] text-ink-600"
            >
              <File className="h-2.5 w-2.5" /> {file.name}
              <button onClick={() => removeFile(idx)} className="ml-1 text-ink-400 hover:text-status-failed">
                <X className="h-2.5 w-2.5" />
              </button>
            </span>
          ))}
        </div>
      )}

      {attachedImages.length > 0 && (
        <div className="flex flex-wrap gap-1.5 px-5 pb-2">
          {attachedImages.map((img, idx) => (
            <span
              key={`${img.name}-${idx}`}
              className="inline-flex items-center gap-1 rounded-lg bg-surface-warm px-2.5 py-1 text-[10px] text-ink-600"
            >
              <ImageIcon className="h-2.5 w-2.5" /> {img.name}
              <button onClick={() => removeImage(idx)} className="ml-1 text-ink-400 hover:text-status-failed">
                <X className="h-2.5 w-2.5" />
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between px-4 py-3 border-t border-line-divider">
        <div className="flex items-center gap-1">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.doc,.docx,.pptx,.txt,.md,.json,.csv,image/png,image/jpeg,image/webp,image/gif"
            className="hidden"
            onChange={(e) => {
              if (e.target.files) handleFiles(e.target.files);
              e.target.value = "";
            }}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] text-ink-400 hover:text-ink-700 hover:bg-surface-warm transition-all border border-transparent hover:border-line-control"
          >
            <Paperclip className="h-3.5 w-3.5" /> + Attach file
          </button>
          {leftExtra}
        </div>
        {rightSlot && <div className="flex items-center gap-2">{rightSlot}</div>}
      </div>
    </>
  );
}

interface IdeaInputPageProps {
  workflowType: WorkflowType;
  onBack: () => void;
  // `resolvedType` is the concrete pipeline the backend should dispatch.
  // For all standard workflows it equals `workflowType`; for the `migration`
  // meta-pipeline it is the sub-pipeline the user picked in the tile selector.
  // `extraParams` carries the run-level `context` (merged at the top level of the
  // run_pipeline payload by useWorkflow). Currently used only for the per-run
  // `gate_agent_ids` toggle — present only when the user touches the Review-gates
  // section; omitted otherwise so the backend uses its static default.
  onRun: (message: string, agentIds: string[], resolvedType: WorkflowType, extraParams?: Record<string, unknown>) => void;
  // Phase 21 (LAUNCH-EXISTING-PATH §4.6) — saved-workflow launch preload. When a
  // saved row is launched, `DashboardLayout` threads its persisted composition in
  // here so the composer mounts PRE-LOADED instead of re-deriving from the (empty
  // for `custom`) `LIBRARY_AGENTS.filter(type)`. Absent ⇒ behavior is byte-for-byte
  // the existing custom/idea flow (the seed branch is purely additive).
  initialAgentIds?: string[];                       // saved-workflow agent seed
  initialModelOverrides?: Record<string, string>;   // saved-workflow per-agent model seed
  // WR-01 — saved-workflow Advanced-lever seed (the persisted compact selections
  // map from manifest_json). When a saved row is launched, threading this in lets the
  // composer re-load AND re-send the user-composed levers. Absent ⇒ no selections
  // (byte-identical to the existing custom/idea flow — additive only).
  initialSelections?: Record<string, Record<string, unknown>>;
  // SAVE-BRIEF — pre-fill the brief textarea when reopening a saved workflow
  initialInput?: string;
  // SAVE-GATES — pre-fill the review gate selection when reopening a saved workflow
  initialGateIds?: string[];
  // SURF-03 — the known backend workflow id of the launchable/saved workflow being
  // opened in the composer (built-in: the workflow id == the resolved pipeline type;
  // saved: its `base_pipeline_type`). When present, the composer fetches the compiled
  // per-step capability projection (GET /api/workflows/{id}) and surfaces it as the
  // AgentsPopup "Declared by this workflow" strip. Absent (a brand-new from-scratch
  // composition) ⇒ no fetch and the strip does not render (nothing declared yet).
  workflowId?: string;
}

const TYPE_CONFIG: Record<WorkflowType, {
  tag: string;
  heading: string;
  subtitle: string;
  placeholder: string;
  icon: typeof FileText;
}> = {
  user_stories: {
    tag: "Generate product requirements",
    heading: "Provide the brief",
    subtitle: "Turn an idea or brief into a Jira-ready backlog — epics, stories, and Gherkin acceptance criteria.",
    placeholder: "e.g. Generate epics and stories for a refunds workflow with multi-currency support.",
    icon: FileText,
  },
  user_stories_revision: {
    tag: "Refine an existing PRD or story set",
    heading: "What would you like to change?",
    subtitle: "Apply targeted edits to an existing backlog without rewriting what already works.",
    placeholder: "e.g. Add acceptance criteria for the multi-currency refund flow and split epic E2 into two.",
    icon: FileText,
  },
  prototype: {
    tag: "Build an interactive prototype",
    heading: "Describe the product",
    subtitle: "Translate a brief into a multi-page SPA prototype using a selected template and design system.",
    placeholder: "e.g. Build a project management SaaS with login, dashboard, and settings.",
    icon: Layout,
  },
  prototype_revision: {
    tag: "Iterate on an existing prototype",
    heading: "What should change?",
    subtitle: "Surgically refine an existing prototype — preserve the rest of the design exactly as-is.",
    placeholder: "e.g. Swap the side filter for a top tab bar and add a dark-mode toggle.",
    icon: Layout,
  },
  prototype_large_revision: {
    tag: "Major overhaul of an existing prototype",
    heading: "What should change?",
    subtitle: "Perform a substantial rework of an existing prototype — preserve the core logic but modernise the design.",
    placeholder: "e.g. Redesign the entire UI to use a new design system and add mobile responsiveness.",
    icon: Layout,
  },
  prototype_feature_revision: {
    tag: "Add features to an existing prototype",
    heading: "What features should be added?",
    subtitle: "Extend an existing prototype with new functionality while preserving the existing implementation.",
    placeholder: "e.g. Add real-time notifications and user preferences panel to the existing dashboard.",
    icon: Layout,
  },
  ppt: {
    tag: "Build an executive presentation",
    heading: "Specify the topic",
    subtitle: "Shape a topic into an enterprise-grade pitch deck with charts, data tables, and executive-ready visuals.",
    placeholder: "e.g. Blockchain technology — enterprise adoption trends and ROI analysis for 2025.",
    icon: Presentation,
  },
  ppt_revision: {
    tag: "Refine an existing presentation",
    heading: "What should change?",
    subtitle: "Apply precise, scoped edits to an existing deck — every other slide stays untouched.",
    placeholder: "e.g. Tighten the ROI section to 3 slides and add a competitive-landscape slide before the conclusion.",
    icon: Presentation,
  },
  app_builder: {
    tag: "Generate a full-stack application",
    heading: "Describe the application",
    subtitle: "Stand up a complete enterprise application — code, tests, and infrastructure produced by specialist agents.",
    placeholder: "e.g. A SaaS platform for managing freelance invoices with Stripe integration.",
    icon: Layout,
  },
  app_builder_revision: {
    tag: "Extend or refine an existing app",
    heading: "What should change?",
    subtitle: "Extend an existing blueprint with targeted changes — every file you didn't touch stays exactly the same.",
    placeholder: "e.g. Add a webhook receiver for Stripe events and persist invoice status to the existing schema.",
    icon: Layout,
  },
  custom: {
    tag: "AI-driven custom workflow",
    heading: "What do you want to achieve?",
    subtitle: "Describe any business objective — AI will recommend the right agents, ask the right questions, and orchestrate a complete workflow tailored to your goal.",
    placeholder: "e.g. Research the competitive landscape for AI coding assistants, identify gaps, and produce a strategic report with actionable recommendations.",
    icon: Layout,
  },
  migration: {
    tag: "Platform workflows",
    heading: "Modernise a legacy estate",
    subtitle: "Modernise a legacy estate end-to-end with a 13-agent SDLC pipeline — inventory, design, code, tests, and cutover.",
    placeholder: "e.g. Migrate three Mulesoft 4 apps powering our orders + claims platform onto AWS, splitting into Spring Boot microservices with Aurora Postgres and SQS messaging.",
    icon: GitBranch,
  },
  mulesoft_to_springboot: {
    tag: "Mulesoft → Spring Boot microservices on AWS",
    heading: "Modernise off Mulesoft",
    subtitle: "Decompose the Mule estate into Spring Boot 3 services on AWS, with parallel-run validation before cutover.",
    placeholder: "e.g. Migrate three Mulesoft 4 apps powering our orders + claims platform onto AWS, splitting into Spring Boot microservices with Aurora Postgres and SQS messaging.",
    icon: GitBranch,
  },
  dotnet_to_azure: {
    tag: ".NET → Azure (AI-augmented)",
    heading: "Modernise .NET onto Azure",
    subtitle: "Map .NET projects to the right Azure services, modernise to .NET 8, and bolt on Azure AI where it pays off.",
    placeholder: "e.g. Rehost two ASP.NET MVC 4.7 apps and a Windows Service onto Azure App Service + Functions, with Azure SQL and Service Bus. Surface AI document triage where it helps the claims workflow.",
    icon: GitBranch,
  },
};

export function IdeaInputPage({ workflowType, onBack, onRun, initialAgentIds, initialModelOverrides, initialSelections, initialInput, initialGateIds, workflowId }: IdeaInputPageProps) {
  const { libraryAgents: LIBRARY_AGENTS, customAgents: CUSTOM_AGENTS, allAgents: ALL_LIBRARY_AGENTS } = useAgentLibrary();
  const [ideaInput, setIdeaInput] = useState(initialInput ?? "");
  const [showAgents, setShowAgents] = useState(false);
  // KAN-91 / Image-input Wave 2 — shared with ComposerPage's Simple-view Brief
  // card (INV-3, no forked attach/extract logic).
  const briefAttachments = useBriefAttachments();
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const preSpeechTextRef = useRef("");
  const { isListening, transcript, startListening, stopListening, isSupported: speechSupported } = useSpeechRecognition();

  // Strip _wizard key from selections — it's FE-only metadata, not a capability selector
  const cleanSelections = initialSelections
    ? Object.fromEntries(Object.entries(initialSelections).filter(([k]) => k !== "_wizard"))
    : undefined;

  // For the "migration" meta-pipeline, the user must pick a concrete sub-pipeline
  // (Mulesoft→Spring Boot or .NET→Azure) before Run is allowed. Once picked, the
  // chosen sub-type drives config, agents, and the Run dispatch.
  const isMigrationMeta = workflowType === "migration";
  const [migrationChoice, setMigrationChoice] = useState<WorkflowType | null>(null);
  const effectiveType: WorkflowType = isMigrationMeta && migrationChoice ? migrationChoice : workflowType;

  // Phase 21 (LAUNCH-EXISTING-PATH §4.6) — when launching a saved workflow, seed
  // `pipelineAgents` from the persisted `initialAgentIds` instead of the
  // empty-for-custom `LIBRARY_AGENTS.filter(type)`. Resolve each id through
  // ALL_LIBRARY_AGENTS (LIBRARY_AGENTS ∪ CUSTOM_AGENTS) — the SAME superset the
  // composer's AgentLibrary uses — because saved custom workflows reference the
  // CUSTOM_AGENTS, which are NOT in the base LIBRARY_AGENTS list.
  // Absent ⇒ the existing derive is preserved byte-for-byte.
  // KAN-112 (revised): for custom workflow, start with an EMPTY list so the user
  // picks their own agents via recommendations or Browse Agents. The 8 CUSTOM_AGENTS
  // are available in the agent library — not pre-loaded. Saved workflows still
  // restore via initialAgentIds.
  const [pipelineAgents, setPipelineAgents] = useState<AgentDef[]>(() => {
    if (initialAgentIds?.length) {
      return initialAgentIds
        .map((id) => ALL_LIBRARY_AGENTS.find((a) => a.id === id))
        .filter(Boolean) as AgentDef[];
    }
    const type = isMigrationMeta && migrationChoice ? migrationChoice : workflowType;
    // Custom workflow: start blank — user adds agents themselves via recommendations
    // or the Browse Agents library. CUSTOM_AGENTS are available there, not pre-loaded.
    if (type === "custom") return [];
    return LIBRARY_AGENTS.filter((a) => a.pipeline_type === type).sort((a, b) => a.order - b.order);
  });

  const { attachedHooks } = useSkillsHooks();

  // Per-run Human-review gate selection, surfaced by <ReviewGatesSection>.
  // Held in a ref so the section reporting its state doesn't re-render this page
  // and so `handleRun` always reads the latest value. Untouched ⇒ we omit
  // `gate_agent_ids` (backend uses its static default); touched ⇒ we send the
  // explicit array (even when empty = "no gates").
  const gateSelectionRef = useRef<{ ids: string[]; touched: boolean }>({ ids: [], touched: false });
  const handleGatesChange = useCallback((ids: string[], touched: boolean) => {
    gateSelectionRef.current = { ids, touched };
  }, []);

  // ISS-014 (MODEL-03): per-agent model overrides selected in the relocated
  // AgentModelPicker (AgentsPopup Agents tab). Held in a ref so the popup
  // reporting its selection doesn't re-render this page, and so `handleRun`
  // always reads the latest value. An empty map ⇒ we omit `model_overrides`
  // entirely (the run_pipeline payload stays byte-identical to before).
  // Phase 21 (LAUNCH-EXISTING-PATH §4.6) — seed the override ref from the saved
  // workflow's persisted per-agent models; absent ⇒ empty map (existing default).
  const modelOverridesRef = useRef<Record<string, string>>(initialModelOverrides ?? {});
  const handleModelOverridesChange = useCallback((overrides: Record<string, string>) => {
    modelOverridesRef.current = overrides;
  }, []);

  // EMP-01 (D-05) — the per-agent Advanced-expander selections map. Held in a
  // ref (like model_overrides) so the popup reporting a selection doesn't
  // re-render this page, and so `handleSaveWorkflow` always reads the latest.
  // An empty map ⇒ we omit `selections` entirely (the save payload stays
  // byte-identical — INV-3). Threads into the createUserWorkflow payload as the
  // EXACT compact shape 22-04 persists in manifest_json; `onRun`/launch stay
  // pure data (SC-001).
  const selectionsRef = useRef<Record<string, Record<string, unknown>>>(cleanSelections ?? {});
  const handleSelectionsChange = useCallback(
    (selections: Record<string, Record<string, unknown>>) => {
      selectionsRef.current = selections;
    },
    [],
  );

  // SURF-03 — when a launchable/saved workflow is opened with a known backend
  // workflow id, fetch its compiled per-step capability projection
  // (GET /api/workflows/{id}) and surface it as the AgentsPopup "Declared by this
  // workflow" strip. Mirrors the AgentModelPicker / CapabilityPaletteSection fetch
  // idiom (useEffect + cancelled guard); no new fetch shell. When there is no id
  // (a brand-new from-scratch composition) the fetch is skipped, `declaredCapabilities`
  // stays undefined, and the strip does not render (nothing declared yet). The
  // projection is registry/manifest-sourced (SC-001) — no hardcoded capability list.
  const [declaredCapabilities, setDeclaredCapabilities] = useState<
    { step: string; capabilities: string[] }[] | undefined
  >(undefined);
  useEffect(() => {
    if (!workflowId) {
      setDeclaredCapabilities(undefined);
      return;
    }
    let cancelled = false;
    const jwt = getToken();
    if (!jwt) {
      setDeclaredCapabilities(undefined);
      return;
    }
    getWorkflowDetail(jwt, workflowId)
      .then((detail) => {
        if (cancelled) return;
        // Map each compiled step to its declared capabilities, sourced entirely
        // from the projection (strategy + gates + validators + compaction +
        // task_source kind) — no hardcoded names. Steps with zero declared caps
        // are omitted so the strip stays terse.
        const mapped = detail.steps
          .map((s) => {
            const caps: string[] = [];
            if (s.strategy) caps.push(`strategy:${s.strategy}`);
            for (const g of s.gates) caps.push(`gate:${g}`);
            for (const v of s.validators) caps.push(`validator:${v}`);
            if (s.compaction) caps.push(`compaction:${s.compaction}`);
            if (s.task_source?.kind) caps.push(`task_source:${s.task_source.kind}`);
            return { step: s.name || s.agent_id, capabilities: caps };
          })
          .filter((d) => d.capabilities.length > 0);
        setDeclaredCapabilities(mapped.length > 0 ? mapped : undefined);
      })
      .catch(() => {
        // Unknown id (404) or transient error ⇒ treat as "nothing declared":
        // leave it undefined so the strip simply does not render (no noisy UI).
        if (!cancelled) setDeclaredCapabilities(undefined);
      });
    return () => {
      cancelled = true;
    };
  }, [workflowId]);

  useEffect(() => {
    // Phase 21 (gotcha #1) — GUARD: when launching a saved workflow the seed lives
    // in `pipelineAgents` already; the empty-for-custom re-derive would clobber it
    // on the first effect run, so bail out and keep the seed.
    // However, when initialAgentIds is cleared (savedComposition set to null after
    // navigating to a different workflow type), we MUST reset to the correct defaults
    // for the new type — otherwise stale agents from a previous saved workflow bleed in.
    if (initialAgentIds?.length) return;
    // KAN-112: custom workflow starts blank — user picks agents themselves.
    if (effectiveType === "custom") {
      setPipelineAgents([]);
    } else {
      setPipelineAgents(LIBRARY_AGENTS.filter((a) => a.pipeline_type === effectiveType).sort((a, b) => a.order - b.order));
    }
  }, [LIBRARY_AGENTS, effectiveType, initialAgentIds]);

  // Reset the sub-choice when the parent switches us off the migration meta-type.
  useEffect(() => {
    if (!isMigrationMeta) setMigrationChoice(null);
  }, [isMigrationMeta]);

  const config = TYPE_CONFIG[effectiveType];

  useEffect(() => {
    if (isListening && transcript) setIdeaInput(preSpeechTextRef.current ? `${preSpeechTextRef.current} ${transcript}` : transcript);
  }, [transcript, isListening]);

  useEffect(() => { setTimeout(() => inputRef.current?.focus(), 200); }, []);

  const handleRun = () => {
    if (!ideaInput.trim() || pipelineAgents.length === 0) return;
    // For the migration meta-type, Run is gated on a sub-pipeline being chosen.
    if (isMigrationMeta && !migrationChoice) return;
    // KAN-91: compose file content blocks into the message at send time,
    // keeping the textarea clean. ATTACH_MAX_CHARS already applied at attach time.
    const finalMessage = `${ideaInput.trim()}${briefAttachments.fileBlocks}`;
    // Only attach gate_agent_ids when the user actually touched the Review-gates
    // section; otherwise omit it entirely so the backend keeps its static default
    // (the run_pipeline payload is byte-identical to before this feature).
    const { ids, touched } = gateSelectionRef.current;
    // ISS-014 (MODEL-03): include per-agent model_overrides only when the user
    // actually picked a non-default model for ≥1 agent. An unselected picker
    // emits an empty map → omitted → byte-identical payload (preserves INV-3).
    const overrides = modelOverridesRef.current;
    const hasOverrides = Object.keys(overrides).length > 0;
    // WR-01 (EMP-01): include the per-agent Advanced-expander selections so the
    // backend overlay (engine._apply_selections) actually applies the user-composed
    // levers at launch — previously selections only reached SAVE, never a run. Mirror
    // the model_overrides discipline: include ONLY when ≥1 lever is set, so an
    // untouched composer emits a byte-identical payload (INV-3 / SC-001).
    const selections = selectionsRef.current;
    const hasSelections = Object.keys(selections).length > 0;
    // Image-input Wave 2: ship captured images OUT-OF-BAND as `images` (D3 —
    // NEVER inlined into finalMessage). Include only when ≥1 image is attached
    // so an image-less run emits a byte-identical payload (INV-3).
    const hasImages = briefAttachments.attachedImages.length > 0;
    // KAN-112 Option B: for custom pipelines, resolve the actual dispatch type and
    // optional deliverable override from the chosen agent set. Prototype agents inject
    // __deliverable__ into selections so engine._apply_selections swaps the compiled
    // plan's deliverable spec — no manifest copy needed (SC-001 / INV-12).
    const { type: dispatchType, deliverableOverride } = resolveDispatchType(pipelineAgents, effectiveType);

    // Merge deliverableOverride into selections under the reserved __deliverable__ key.
    const mergedSelections = deliverableOverride
      ? { ...selections, __deliverable__: deliverableOverride }
      : selections;
    const hasMergedSelections = Object.keys(mergedSelections).length > 0;

    const finalExtraParams =
      touched || hasOverrides || hasMergedSelections || hasImages
        ? {
            ...(touched ? { gate_agent_ids: ids } : {}),
            ...(hasOverrides ? { model_overrides: overrides } : {}),
            ...(hasMergedSelections ? { selections: mergedSelections } : {}),
            ...(hasImages ? { images: briefAttachments.attachedImages } : {}),
          }
        : undefined;
    onRun(finalMessage, pipelineAgents.map((a) => a.id), dispatchType, finalExtraParams);
  };

  // Phase 21 (SAVE-FROM-BOTH composer entry) — "Save workflow" persists the
  // composer as a named, reusable workflow. The payload is the EXACT triple
  // `onRun` already sends — base_pipeline_type, agent_ids, model_overrides —
  // so saving is pure data: no new pipeline name, no `if saved_workflow:` fork
  // (SC-001). Server re-validates with the launch predicates (save == launch).
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedConfirm, setSavedConfirm] = useState(false);
  const handleSaveWorkflow = async (name: string, description: string) => {
    setShowSaveModal(false);
    setSaveError(null);
    const jwt = getToken();
    if (!jwt) {
      setSaveError("Not authenticated.");
      return;
    }
    const overrides = modelOverridesRef.current;
    const selections = selectionsRef.current;
    const { ids: gateAgentIds, touched: gatesTouched } = gateSelectionRef.current;
    // Store the brief and gate selection in _wizard so the catalogue card
    // can show a clean summary without relying on the user-typed description.
    const wizardConfig: Record<string, unknown> = {
      brief: ideaInput.trim(),
      ...(gatesTouched ? { gateAgentIds } : {}),
    };
    try {
      await createUserWorkflow(jwt, {
        name,
        description: description || undefined,
        base_pipeline_type: effectiveType,
        agent_ids: pipelineAgents.map((a) => a.id),
        model_overrides: Object.keys(overrides).length > 0 ? overrides : undefined,
        // EMP-01/03: the Advanced-expander selections (omitted when empty so the
        // payload stays byte-identical). Server re-compiles trust="user" (22-04).
        selections: {
          ...selections,
          _wizard: wizardConfig,
        },
      });
      setSavedConfirm(true);
      setTimeout(() => setSavedConfirm(false), 2500);
    } catch (e) {
      setSaveError((e as Error)?.message ?? "Failed to save workflow.");
    }
  };

  // KAN-112: for custom, there are no "default" agents — every agent is optional.
  // The optional-agent count and add/remove limits are all relative to an empty baseline.
  const defaultAgentIds = new Set(
    effectiveType === "custom"
      ? [] // custom has no locked defaults — every agent the user adds is optional
      : LIBRARY_AGENTS.filter((a) => a.pipeline_type === effectiveType).map((a) => a.id)
  );
  const optionalAgentCount = pipelineAgents.filter((a) => !defaultAgentIds.has(a.id)).length;
  const maxOptional = effectiveType === "custom" ? 16 : 5; // generous cap for custom
  const canAddMore = optionalAgentCount < maxOptional;

  const handleAddAgent = useCallback((agent: AgentDef) => {
    setPipelineAgents((prev) => {
      // Reusable blank template — mint a fresh instance id per add (R-03).
      const node = instantiateIfTemplate(agent, collectAgentIds(prev));
      if (prev.find((a) => a.id === node.id)) return prev;
      // KAN-112: custom has no locked defaults — every agent counts as optional.
      const currentDefaults = new Set(
        effectiveType === "custom"
          ? []
          : LIBRARY_AGENTS.filter((a) => a.pipeline_type === effectiveType).map((a) => a.id)
      );
      const currentOptional = prev.filter((a) => !currentDefaults.has(a.id)).length;
      const limit = effectiveType === "custom" ? 16 : 5;
      if (currentOptional >= limit) return prev;
      const insertIdx = effectiveType === "custom" ? prev.length : (prev.length > 0 ? prev.length - 1 : 0);
      const updated = [...prev];
      updated.splice(insertIdx, 0, { ...node, order: insertIdx + 1 });
      return updated;
    });
  }, [LIBRARY_AGENTS, effectiveType]);

  const handleRemoveAgent = useCallback((agentId: string) => {
    setPipelineAgents((prev) => prev.filter((a) => a.id !== agentId));
  }, []);

  const handleReorderAgents = useCallback((reordered: AgentDef[]) => {
    setPipelineAgents(reordered);
  }, []);

  // KAN-112: brief-based agent recommendations (for custom workflow only).
  // Shown as a compact suggestion strip below the textarea when the brief
  // has enough content to infer intent (≥15 chars).
  const [dismissedRecommendations, setDismissedRecommendations] = useState<Set<string>>(new Set());
  const recommendations = effectiveType === "custom"
    ? getAgentRecommendations(ALL_LIBRARY_AGENTS, ideaInput, new Set(pipelineAgents.map((a) => a.id)))
        .filter((a) => !dismissedRecommendations.has(a.id))
        .slice(0, 6)
    : [];

  // KAN-112: companion agent suggestion — shown when the agent set implies
  // a full pipeline is being assembled but is incomplete.
  const companionSuggestion = effectiveType === "custom" ? (() => {
    const currentIds = new Set(pipelineAgents.map((a) => a.id));
    for (const group of COMPANION_GROUPS) {
      const hasAny = group.ids.some((id) => currentIds.has(id));
      const hasAll = group.ids.every((id) => currentIds.has(id));
      if (hasAny && !hasAll) {
        const missing = group.ids.filter((id) => !currentIds.has(id));
        return { group, missing };
      }
    }
    return null;
  })() : null;

  const totalEstimatedTime = Math.round(pipelineAgents.reduce((s, a) => s + a.estimated_duration, 0));

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-surface-paper">
      <div className="flex flex-col items-center px-4 sm:px-6 py-10 max-w-2xl mx-auto w-full">

        {/* Back */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="w-full mb-8"
        >
          <button
            onClick={onBack}
            className="flex items-center gap-1.5 text-[12px] text-ink-500 hover:text-ink-900 transition-colors"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> Back
          </button>
        </motion.div>

        {/* Heading */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
          className="w-full mb-6"
        >
          <p className="text-[10px] font-semibold text-ink-400 uppercase tracking-[0.15em] mb-3">
            {config.tag}
          </p>
          <h1
            className="text-[32px] font-normal italic text-ink-900 leading-tight tracking-tight mb-2"
            style={{ fontFamily: "var(--font-fraunces)" }}
          >
            {config.heading}
          </h1>
          <p className="text-[13px] text-ink-500 leading-relaxed max-w-xl">
            {config.subtitle}
          </p>
        </motion.div>

        {/* Input card */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, delay: 0.08 }}
          className="w-full"
        >
          <div className="rounded-2xl bg-surface-white shadow-sm border border-line-control/80 overflow-hidden">
            <BriefAttachBox
              value={ideaInput}
              onChange={setIdeaInput}
              placeholder={isListening ? "Listening... speak your idea" : config.placeholder}
              attachments={briefAttachments}
              textareaRef={inputRef}
              onSubmitShortcut={handleRun}
              leftExtra={
                speechSupported && (
                  <button
                    onClick={() => { if (isListening) stopListening(); else { preSpeechTextRef.current = ideaInput; startListening(); } }}
                    className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] transition-all border border-transparent ${
                      isListening
                        ? "text-status-failed bg-status-failed-fill border-status-failed-border animate-pulse"
                        : "text-ink-400 hover:text-ink-700 hover:bg-surface-warm hover:border-line-control"
                    }`}
                  >
                    {isListening ? <MicOff className="h-3.5 w-3.5" /> : <Mic className="h-3.5 w-3.5" />}
                    {isListening ? "Stop" : "Voice"}
                  </button>
                )
              }
              rightSlot={
                <>
                  {/* Save workflow — SAVE-FROM-BOTH composer entry (Phase 21).
                      Persists the composer triple. */}
                  {savedConfirm ? (
                    <span className="flex items-center gap-1.5 rounded-xl px-3 py-2.5 text-[12px] font-semibold text-status-done bg-status-done-fill border border-status-done-border">
                      <Check className="h-3.5 w-3.5" /> Saved
                    </span>
                  ) : (
                    <button
                      onClick={() => { setSaveError(null); setShowSaveModal(true); }}
                      disabled={pipelineAgents.length === 0 || (isMigrationMeta && !migrationChoice)}
                      className="flex items-center gap-1.5 rounded-xl border border-line-control px-4 py-2.5 text-[12px] font-medium text-ink-600 hover:bg-surface-warm transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                      title="Save this composition as a reusable workflow"
                    >
                      <Save className="h-3.5 w-3.5" /> Save workflow
                    </button>
                  )}

                  {/* Run button */}
                  <button
                    onClick={handleRun}
                    disabled={!ideaInput.trim() || pipelineAgents.length === 0 || (isMigrationMeta && !migrationChoice)}
                    className="flex items-center gap-2 rounded-xl bg-brand text-surface-white px-5 py-2.5 text-[13px] font-semibold hover:bg-brand-pressed transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    {pipelineAgents.length === 0
                      ? "Add agents first"
                      : isMigrationMeta && !migrationChoice
                      ? "Pick a migration path"
                      : "Run workflow"}
                    <ArrowRight className="h-4 w-4" />
                  </button>
                </>
              }
            />

            {saveError && (
              <div className="px-4 pb-3 -mt-1 text-[11px] text-red-600">{saveError}</div>
            )}

            {/* Save modal — reuses NameWorkflowModal (Phase 21). */}
            <AnimatePresence>
              {showSaveModal && (
                <NameWorkflowModal
                  title="Save workflow"
                  onSave={handleSaveWorkflow}
                  onCancel={() => setShowSaveModal(false)}
                />
              )}
            </AnimatePresence>
          </div>
        </motion.div>

        {/* KAN-112: Brief-based agent recommendations — shown only for custom
            workflow when the brief is long enough to infer intent. Compact
            suggestion chips that the user can click to add. */}
        {effectiveType === "custom" && recommendations.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className="w-full mt-3"
          >
            <div className="rounded-xl border border-brand/15 bg-brand/[0.04] px-4 py-3">
              <div className="flex items-center gap-1.5 mb-2.5">
                <Sparkles className="h-3.5 w-3.5 text-brand" />
                <p className="text-[10px] font-semibold text-brand uppercase tracking-wide">
                  Suggested agents for your brief
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {recommendations.map((agent) => (
                  <button
                    key={agent.id}
                    onClick={() => handleAddAgent(agent)}
                    className="flex items-center gap-1.5 rounded-full border border-brand/20 bg-surface-white px-2.5 py-1 text-[11px] font-medium text-brand hover:bg-brand hover:text-surface-white transition-colors group"
                    title={agent.description}
                  >
                    {agent.name.replace(/ Agent$/, "")}
                    <Plus className="h-3 w-3 opacity-50 group-hover:opacity-100" />
                  </button>
                ))}
                <button
                  onClick={() => setDismissedRecommendations(new Set(recommendations.map((a) => a.id)))}
                  className="text-[10px] text-ink-400 hover:text-ink-600 px-1 self-center"
                  title="Dismiss suggestions"
                >
                  Dismiss
                </button>
              </div>
            </div>
          </motion.div>
        )}

        {/* KAN-112: Companion agent suggestion — when user has added some agents
            from a known pipeline but not all, suggest completing it. */}
        {effectiveType === "custom" && companionSuggestion && (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className="w-full mt-2"
          >
            <div className="rounded-xl border border-status-amber-border bg-status-amber-fill px-4 py-3">
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <p className="text-[11px] font-semibold text-status-amber mb-0.5">
                    {companionSuggestion.group.label}
                  </p>
                  <p className="text-[10px] text-status-amber leading-relaxed">
                    {companionSuggestion.group.description}
                  </p>
                </div>
                <button
                  onClick={() => {
                    const missingAgents = companionSuggestion.missing
                      .map((id) => ALL_LIBRARY_AGENTS.find((a) => a.id === id))
                      .filter(Boolean) as AgentDef[];
                    // Replace current agents with the full ordered pipeline group
                    const groupIds = new Set(companionSuggestion.group.ids);
                    const nonGroupAgents = pipelineAgents.filter((a) => !groupIds.has(a.id));
                    const fullGroupAgents = companionSuggestion.group.ids
                      .map((id) => ALL_LIBRARY_AGENTS.find((a) => a.id === id))
                      .filter(Boolean) as AgentDef[];
                    setPipelineAgents([...fullGroupAgents, ...nonGroupAgents]);
                  }}
                  className="flex-shrink-0 flex items-center gap-1 text-[11px] font-semibold text-status-amber bg-status-amber-fill border border-status-amber-border hover:brightness-95 px-2.5 py-1 rounded-lg transition-colors"
                >
                  <Plus className="h-3 w-3" />
                  Add {companionSuggestion.missing.length} missing
                </button>
              </div>
            </div>
          </motion.div>
        )}

        {/* Migration sub-pipeline selector — only when the meta-type was picked.
            Two tiles, always visible (no tap-to-reveal). Tapping a tile drives
            the rest of the page (config copy, agent lineup, Run dispatch). */}
        {isMigrationMeta && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.12 }}
            className="w-full mt-5"
          >
            <p className="text-[10px] font-semibold text-brand uppercase tracking-[0.14em] mb-2.5">
              Choose your migration path
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              {MIGRATION_OPTIONS.map((opt) => {
                const isSelected = migrationChoice === opt.type;
                return (
                  <button
                    key={opt.type}
                    onClick={() => setMigrationChoice(opt.type)}
                    className={`group text-left rounded-2xl border-2 px-4 py-3.5 transition-all ${
                      isSelected
                        ? "border-brand bg-brand shadow-md"
                        : "border-line-control bg-surface-white hover:border-brand/40 hover:bg-brand/[0.04]"
                    }`}
                  >
                    <div className="flex items-start gap-2.5">
                      <GitBranch className={`h-4 w-4 mt-0.5 flex-shrink-0 ${isSelected ? "text-white" : "text-brand"}`} />
                      <div className="min-w-0">
                        <p className={`text-[12px] font-semibold leading-snug ${isSelected ? "text-white" : "text-ink-900"}`}>
                          {opt.label}
                        </p>
                        <p className={`text-[10px] mt-1 leading-relaxed ${isSelected ? "text-white/85" : "text-ink-500"}`}>
                          {opt.tagline}
                        </p>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </motion.div>
        )}

        {/* Advanced / agents info */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
          className="w-full mt-4"
        >
          <button
            onClick={() => setShowAgents(true)}
            className="flex items-center gap-2 text-[12px] text-ink-400 hover:text-ink-700 transition-colors"
          >
            <Settings2 className="h-3.5 w-3.5" />
            <span className="font-medium text-ink-600">Advanced</span>
            <span className="text-ink-400">
              {pipelineAgents.length} agent{pipelineAgents.length !== 1 ? "s" : ""}
              {totalEstimatedTime > 0 && ` · ~${totalEstimatedTime < 60 ? `${totalEstimatedTime}s` : `${Math.round(totalEstimatedTime / 60)}m`}`}
              {attachedHooks.length > 0 && ` · ${attachedHooks.length} hook${attachedHooks.length !== 1 ? "s" : ""}`}
            </span>
          </button>
        </motion.div>

        {/* Review gates — inline expandable, sits beside the Skills/Hooks
            ("Advanced") controls. Self-hides when there are no agents (e.g. the
            migration meta-type before a sub-pipeline is chosen). */}
        {(!isMigrationMeta || migrationChoice) && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.24 }}
            className="w-full mt-3"
          >
            <ReviewGatesSection agents={pipelineAgents} onChange={handleGatesChange} initialGateIds={initialGateIds} />
          </motion.div>
        )}

      </div>

      <AgentsPopup
        isOpen={showAgents}
        onClose={() => setShowAgents(false)}
        agents={pipelineAgents}
        pipelineType={effectiveType}
        onAddAgent={handleAddAgent}
        onRemoveAgent={handleRemoveAgent}
        onReorder={handleReorderAgents}
        canAddMore={canAddMore}
        onModelOverridesChange={handleModelOverridesChange}
        onSelectionsChange={handleSelectionsChange}
        initialModelOverrides={initialModelOverrides}
        initialSelections={cleanSelections}
        declaredCapabilities={declaredCapabilities}
      />
    </div>
  );
}
