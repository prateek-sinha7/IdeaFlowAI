"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ArrowRight, ArrowUp, ChevronLeft, Paperclip, X } from "lucide-react";
import { getToken, getWorkflowDetail, type WorkflowDetail } from "@/lib/api";
import {
  listDesignSystems,
  listPrototypeTemplates,
  type DesignSystemListItem,
  type PrototypeTemplate,
} from "@/lib/prototype-api";
import { EMPTY_ANSWERS, type DiscoveryAnswers } from "./prototype/DiscoveryForm";
import type { SelectionsMap } from "./AgentsPopup";
import { saveDraft, readDraft, clearDraft, type ConfigureDraft } from "@/lib/draft";
import type { CustomDesignSystem } from "./prototype/CustomDesignSystemModal";
import type { AgentDef } from "@/types/index";
import { TemplatesAccordion } from "./configure/TemplatesAccordion";
import { DesignSystemAccordion } from "./configure/DesignSystemAccordion";
import { ReviewGatesAccordion } from "./configure/ReviewGatesAccordion";
import { WorkflowSettingsAccordion } from "./configure/WorkflowSettingsAccordion";

/**
 * ConfigureScreen — the mock's ONE "Configure your run" screen (D-01 / CFGUI-01).
 *
 * Composition (Phase-41 rebuild):
 *   - a top HEADER bar (back · eyebrow · "Configure your run" · Save draft · Start run →)
 *   - an always-open STEP-1 brief card ("① Describe what you're building" — textarea
 *     + Attach, NO Voice [ND-AI], ⌘Enter send)
 *   - four "ADVANCED CONFIGURATION" summary-line accordion cards (Templates ·
 *     Design System · Review Gates · Workflow Settings), each with a live
 *     "Currently using: X" summary + a Browse/Open control that opens its overlay.
 *
 * The screen is keyed on DECLARED run inputs (D-15/C): the Templates + Design
 * System accordions render ONLY when the selected deliverable declares
 * `context_providers:[opendesign]` (ND-AE) — the SAME signal the Wave-1 backend
 * run-launch seam keys on (SC-001 / INV-1), NEVER a prototype-name branch.
 *
 * Each accordion's overlay REUSES a shipped body verbatim (compose, do not
 * rebuild): Templates→TemplateGallery, Design System→DesignSystemPicker, Review
 * Gates→ReviewGatesSection, Workflow Settings→AdvancedExpander (preserving its
 * validator→gate coupling + retry-as-int contract). Selections bind to the LIVE
 * registries and read "None selected" until picked (ND-AF). Save-draft persists
 * the composed run-draft CLIENT-SIDE via sessionStorage (ND-1); the screen
 * hydrates from it on mount; Start-run composes the GENERIC launch inputs and
 * clears the draft once. The `onLaunch` / `ComposedLaunchCommand` contract is
 * UNCHANGED here — it is wired live in 41-03.
 */

/** The declared context provider that turns on the Templates + Design System
 *  accordions — the SAME signal the backend run-launch seam keys on (SC-001). */
const OPENDESIGN_PROVIDER = "opendesign";

/** Base pipeline types whose OpenDesign flavor is requested via a dedicated
 *  `od_` alias (`prototype` → `od_prototype`). Such a base DECLARES `opendesign`
 *  but is NOT self-OD-eligible: a bare-base launch returns `od_context=None` and
 *  the backend 13-06 `missing_template_context` guard rejects it. This mirrors
 *  the run-launch seam's `pipeline_type in _OD_ALIAS_BASE.values()` exclusion
 *  (backend/app/api/launch_context.py:91) so the Configure gate never offers
 *  template/DS for a deliverable the seam would reject. Single source of truth =
 *  the backend `agents.registry._OD_ALIAS_BASE`; keep this FE mirror in sync. */
const OD_ALIAS_BASE_PIPELINES = new Set<string>(["prototype"]);

/** The generic run-launch command the Configure screen composes at launch — the
 *  SAME declared fields the backend launch seam accepts for ANY deliverable
 *  (D-15/C), never a prototype-specific shape. */
export interface ComposedLaunchCommand {
  template_id: string | null;
  design_system_id: string | null;
  custom_template_body: string | null;
  custom_ds_body: string | null;
  brief: string;
  agent_ids: string[];
  selections: SelectionsMap;
  /** Discovery answers captured for the run (IN-01) — threaded into the launch
   *  hand-off instead of being silently dropped. Defaults to EMPTY_ANSWERS. */
  discovery: DiscoveryAnswers;
  gate_agent_ids?: string[];
}

interface ConfigureScreenProps {
  /** The selected deliverable's workflow id — its compiled definition drives the
   *  declared-signal gating (`context_providers`). */
  workflowId: string;
  /** The launch hand-off seam (wired live in 41-03). Called with the composed
   *  generic command; the screen clears the draft afterwards. */
  onLaunch?: (command: ComposedLaunchCommand) => void;
  /** Optional back affordance for the header bar (mock's ‹ button). */
  onBack?: () => void;
}

export function ConfigureScreen({ workflowId, onLaunch, onBack }: ConfigureScreenProps) {
  const [detail, setDetail] = useState<WorkflowDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [templates, setTemplates] = useState<PrototypeTemplate[]>([]);
  const [systems, setSystems] = useState<DesignSystemListItem[]>([]);

  // Composed run inputs (superset of the generic launch command).
  const [brief, setBrief] = useState("");
  const [discovery, setDiscovery] = useState<DiscoveryAnswers>(EMPTY_ANSWERS);
  const [templateId, setTemplateId] = useState<string | null>(null);
  const [customTemplateBody, setCustomTemplateBody] = useState<string | null>(null);
  const [designSystemId, setDesignSystemId] = useState<string | null>(null);
  const [customDsBody, setCustomDsBody] = useState<string | null>(null);
  const [initialSelections, setInitialSelections] = useState<SelectionsMap>({});
  const [initialGateIds, setInitialGateIds] = useState<string[] | undefined>(undefined);
  const [attachedFiles, setAttachedFiles] = useState<string[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Levers reported upward by the reused surfaces, held in refs so their reporting
  // doesn't re-render the screen (mirrors the prototype wizard idiom).
  const selectionsRef = useRef<SelectionsMap>({});
  const gateSelectionRef = useRef<{ ids: string[]; touched: boolean }>({ ids: [], touched: false });
  const [savedConfirm, setSavedConfirm] = useState(false);

  // Fetch the compiled definition for the selected deliverable. The declared
  // `context_providers` list gates the Templates/DS accordions (SC-001).
  useEffect(() => {
    let cancelled = false;
    const token = getToken();
    if (!token) return;
    getWorkflowDetail(token, workflowId)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch((e: Error) => {
        if (!cancelled) setLoadError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [workflowId]);

  // Gate on the DECLARED opendesign signal (SC-001), minus the ONE legacy
  // carve-out the run-launch seam also excludes: a base whose OD flavor is a
  // dedicated `od_` alias (`prototype`) declares opendesign but is rejected
  // downstream (od_context=None → 13-06 guard). The seam keys on the RESOLVED base
  // pipeline_type (`pipeline_type in _OD_ALIAS_BASE.values()`, launch_context.py:91),
  // so mirror it on the resolved base — `detail.id` is `compiled.id` from
  // getWorkflowDetail — NOT the input workflow id (IN-06). Primary key is still the
  // declared provider.
  const acceptsTemplateDs = useMemo(
    () =>
      (detail?.context_providers ?? []).includes(OPENDESIGN_PROVIDER) &&
      !OD_ALIAS_BASE_PIPELINES.has(detail?.id ?? ""),
    [detail],
  );

  // Load the live template/DS registries only when this deliverable declares the
  // opendesign context provider (no needless fetch for non-opendesign runs).
  useEffect(() => {
    if (!acceptsTemplateDs) return;
    let cancelled = false;
    const token = getToken();
    if (!token) return;
    listPrototypeTemplates(token)
      .then((t) => { if (!cancelled) setTemplates(t); })
      .catch(() => { /* picker stays empty on failure */ });
    listDesignSystems(token)
      .then((s) => { if (!cancelled) setSystems(s); })
      .catch(() => { /* non-fatal */ });
    return () => { cancelled = true; };
  }, [acceptsTemplateDs]);

  // Hydrate every input from a saved client-side draft on mount (ND-1).
  useEffect(() => {
    const d = readDraft();
    if (!d) return;
    if (d.brief) setBrief(d.brief);
    if (d.discovery) setDiscovery(d.discovery as DiscoveryAnswers);
    if (d.templateId !== undefined) setTemplateId(d.templateId ?? null);
    if (d.customTemplateBody !== undefined) setCustomTemplateBody(d.customTemplateBody ?? null);
    if (d.designSystemId !== undefined) setDesignSystemId(d.designSystemId ?? null);
    if (d.customDsBody !== undefined) setCustomDsBody(d.customDsBody ?? null);
    if (d.selections) {
      selectionsRef.current = d.selections as SelectionsMap;
      setInitialSelections(d.selections as SelectionsMap);
    }
    if (d.gateAgentIds !== undefined) {
      gateSelectionRef.current = { ids: d.gateAgentIds, touched: true };
      setInitialGateIds(d.gateAgentIds);
    }
  }, []);

  // The deliverable's steps ARE the run's agents — build the shape each reused
  // control needs (SC-001: sourced from the compiled plan, not a hardcoded list).
  const agentDefs: AgentDef[] = useMemo(
    () =>
      (detail?.steps ?? []).map(
        (s) =>
          ({
            id: s.agent_id,
            name: s.name,
            role: s.role,
            order: s.order,
            gate: s.declared_gate ?? null,
          }) as unknown as AgentDef,
      ),
    [detail],
  );
  const leverAgents = useMemo(
    () => agentDefs.map((a) => ({ id: a.id, name: a.name })),
    [agentDefs],
  );

  const handleSelectionsChange = useCallback((s: SelectionsMap) => {
    selectionsRef.current = s;
  }, []);
  const handleGatesChange = useCallback((ids: string[], touched: boolean) => {
    gateSelectionRef.current = { ids, touched };
  }, []);
  const handleSelectCustomDs = useCallback((ds: CustomDesignSystem | null) => {
    if (ds) {
      setDesignSystemId(ds.id);
      setCustomDsBody(ds.body);
    } else {
      setCustomDsBody(null);
    }
  }, []);
  const handleSelectTemplate = useCallback((id: string | null) => {
    setTemplateId(id);
    setCustomTemplateBody(null);
  }, []);
  const handleSelectDesignSystem = useCallback((id: string | null) => {
    setDesignSystemId(id);
    setCustomDsBody(null);
  }, []);

  const handleFilesPicked = useCallback((files: FileList | null) => {
    if (!files) return;
    setAttachedFiles((prev) => [...prev, ...Array.from(files).map((f) => f.name)]);
  }, []);

  // Compose the persisted draft superset from the current input state.
  const composeDraft = useCallback((): ConfigureDraft => {
    const { ids: gateAgentIds, touched: gatesTouched } = gateSelectionRef.current;
    return {
      templateId,
      designSystemId,
      brief,
      agentIds: agentDefs.map((a) => a.id),
      discovery,
      ...(Object.keys(selectionsRef.current).length > 0 ? { selections: selectionsRef.current } : {}),
      ...(customDsBody ? { customDsBody } : {}),
      ...(customTemplateBody ? { customTemplateBody } : {}),
      ...(gatesTouched ? { gateAgentIds } : {}),
    };
  }, [templateId, designSystemId, brief, agentDefs, discovery, customDsBody, customTemplateBody]);

  const handleSaveDraft = useCallback(() => {
    saveDraft(composeDraft());
    setSavedConfirm(true);
    setTimeout(() => setSavedConfirm(false), 2000);
  }, [composeDraft]);

  // Compose the GENERIC launch command (the same declared fields the backend seam
  // accepts for any deliverable) and clear the draft once after hand-off.
  const handleLaunch = useCallback(() => {
    const { ids: gateAgentIds, touched: gatesTouched } = gateSelectionRef.current;
    const command: ComposedLaunchCommand = {
      template_id: templateId,
      design_system_id: designSystemId,
      custom_template_body: customTemplateBody,
      custom_ds_body: customDsBody,
      brief,
      agent_ids: agentDefs.map((a) => a.id),
      selections: selectionsRef.current,
      discovery,
      ...(gatesTouched ? { gate_agent_ids: gateAgentIds } : {}),
    };
    onLaunch?.(command);
    clearDraft();
  }, [templateId, designSystemId, customTemplateBody, customDsBody, brief, discovery, agentDefs, onLaunch]);

  const eyebrow = detail?.name ? `${detail.name} · Quick start` : "New run · Quick start";

  return (
    <div className="flex h-full min-h-0 flex-col bg-surface-paper">
      {/* HEADER BAR — back · eyebrow · title · Save draft · Start run → */}
      <header className="flex flex-none items-center gap-4 border-b border-line-border px-8 py-3.5">
        {onBack && (
          <button
            type="button"
            onClick={onBack}
            aria-label="Back"
            data-testid="configure-back"
            className="grid h-9 w-9 flex-none place-items-center rounded-[9px] border border-line-border bg-surface-card text-ink-700 transition-colors hover:border-line-control"
          >
            <ChevronLeft className="h-[17px] w-[17px]" />
          </button>
        )}
        <div className="min-w-0 flex-1">
          <p className="mb-0.5 text-[10px] font-semibold uppercase tracking-[0.15em] text-ink-400">
            {eyebrow}
          </p>
          <h1 className="truncate text-[20px] font-light tracking-tight text-ink-900">
            Configure your run
          </h1>
        </div>
        <button
          type="button"
          data-testid="configure-save-draft"
          onClick={handleSaveDraft}
          className="rounded-[10px] border border-line-border bg-surface-card px-4 py-2.5 text-[12.5px] font-semibold text-ink-700 transition-colors hover:border-line-control"
        >
          {savedConfirm ? "Saved" : "Save draft"}
        </button>
        <button
          type="button"
          data-testid="configure-launch"
          onClick={handleLaunch}
          className="inline-flex items-center gap-2 rounded-[10px] bg-brand px-5 py-2.5 text-[12.5px] font-semibold text-white transition-colors hover:bg-brand-pressed"
        >
          Start run
          <ArrowRight className="h-[15px] w-[15px]" />
        </button>
      </header>

      {/* BODY */}
      <div className="min-h-0 flex-1 overflow-y-auto px-8 py-10 pb-16">
        <div className="mx-auto max-w-[720px]">
          {loadError && (
            <div className="mb-6 rounded-[var(--radius-card)] border border-line-border bg-surface-white px-4 py-3 text-[12px] text-ink-600">
              Couldn&apos;t load this deliverable&apos;s setup: {loadError}
            </div>
          )}

          {/* STEP 1 — DESCRIBE (always open) */}
          <div className="mb-4 flex items-center gap-3">
            <span className="grid h-[26px] w-[26px] flex-none place-items-center rounded-full bg-ink-900 text-[12px] font-semibold text-white">
              1
            </span>
            <h2 className="text-[24px] font-light tracking-tight text-ink-900">
              Describe what you&apos;re building
            </h2>
          </div>
          <div className="overflow-hidden rounded-2xl border border-line-border bg-surface-white shadow-[0_6px_24px_rgba(17,17,20,0.05)]">
            <textarea
              data-testid="configure-brief"
              value={brief}
              onChange={(e) => setBrief(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleLaunch();
              }}
              rows={4}
              placeholder="e.g. A kanban board for a 5-person growth squad — backlog, doing, review, done. Show real ticket titles and assignee avatars."
              className="min-h-[132px] w-full resize-none bg-transparent px-[18px] pb-1.5 pt-[18px] text-[15px] leading-relaxed text-ink-700 placeholder:text-ink-400 focus:outline-none"
            />
            {attachedFiles.length > 0 && (
              <div className="flex flex-wrap gap-1.5 px-[18px] pb-2">
                {attachedFiles.map((name, idx) => (
                  <span
                    key={`${name}-${idx}`}
                    className="inline-flex items-center gap-1 rounded-lg bg-surface-warm px-2.5 py-1 text-[10px] text-ink-600"
                  >
                    {name}
                    <button
                      type="button"
                      aria-label={`Remove ${name}`}
                      onClick={() => setAttachedFiles((p) => p.filter((_, i) => i !== idx))}
                      className="ml-1 text-ink-400 hover:text-ink-900"
                    >
                      <X className="h-2.5 w-2.5" />
                    </button>
                  </span>
                ))}
              </div>
            )}
            <div className="flex items-center gap-[18px] border-t border-surface-paper px-3 py-[11px] pl-[18px]">
              <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                onChange={(e) => {
                  handleFilesPicked(e.target.files);
                  e.target.value = "";
                }}
              />
              <button
                type="button"
                data-testid="configure-attach"
                onClick={() => fileInputRef.current?.click()}
                className="inline-flex items-center gap-[7px] text-[12.5px] font-medium text-ink-500 transition-colors hover:text-brand"
              >
                <Paperclip className="h-[15px] w-[15px]" />
                Attach file
              </button>
              <span className="flex-1" />
              <span className="text-[12px] text-ink-400">Press ⌘Enter to start</span>
              <button
                type="button"
                aria-label="Start run"
                data-testid="configure-brief-send"
                onClick={handleLaunch}
                className="grid h-[34px] w-[34px] flex-none place-items-center rounded-[10px] bg-brand text-white transition-colors hover:bg-brand-pressed"
              >
                <ArrowUp className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* ADVANCED CONFIGURATION — four summary-line accordions */}
          <p className="mb-4 mt-[52px] text-[10.5px] font-semibold uppercase tracking-[0.15em] text-ink-400">
            Advanced configuration
          </p>
          <div className="flex flex-col gap-3.5">
            {/* Templates + Design System — DECLARED-SIGNAL-GATED (ND-AE). */}
            {acceptsTemplateDs && (
              <TemplatesAccordion
                templates={templates}
                selectedId={templateId}
                customBody={customTemplateBody}
                onSelect={handleSelectTemplate}
              />
            )}
            {acceptsTemplateDs && (
              <DesignSystemAccordion
                systems={systems}
                selectedId={designSystemId}
                customBody={customDsBody}
                onSelect={handleSelectDesignSystem}
                onSelectCustom={handleSelectCustomDs}
              />
            )}
            {/* Review Gates + Workflow Settings — always present. */}
            <ReviewGatesAccordion
              agents={agentDefs}
              initialGateIds={initialGateIds}
              onChange={handleGatesChange}
            />
            <WorkflowSettingsAccordion
              agents={leverAgents}
              agentCount={agentDefs.length}
              onSelectionsChange={handleSelectionsChange}
              initialSelections={initialSelections}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * ConfigureCard — the shared Configure summary card chrome (icon · title · live
 * "Currently using: X" summary line · Browse/Open action). Reused by all four
 * accordion wrappers so the mock's card composition lives in ONE place.
 */
export function ConfigureCard({
  testId,
  icon,
  title,
  summaryLabel,
  summaryValue,
  action,
}: {
  testId: string;
  icon: ReactNode;
  title: string;
  summaryLabel?: string;
  summaryValue: string;
  action: ReactNode;
}) {
  return (
    <section
      data-testid={testId}
      className="rounded-[14px] border border-line-border bg-surface-card"
    >
      <div className="flex items-center gap-3.5 px-5 py-[18px]">
        <span className="grid h-9 w-9 flex-none place-items-center rounded-[9px] bg-surface-warm text-ink-700">
          {icon}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[14px] font-semibold text-ink-900">{title}</p>
          <p className="mt-[3px] truncate text-[12.5px] text-ink-400">
            {summaryLabel && <span>{summaryLabel} </span>}
            <span className="font-semibold text-ink-700">{summaryValue}</span>
          </p>
        </div>
        {action}
      </div>
    </section>
  );
}

/**
 * ConfigureOverlay — the shared Configure overlay/modal shell (mock's
 * `overlayTemplate` / `overlayDs` / `overlayGates` / `modalWorkflow`). Hosts a
 * reused body as its scrollable content, with a scrim, a titled header, and a
 * Cancel / confirm footer. Reused by all four accordion wrappers.
 */
export function ConfigureOverlay({
  open,
  onClose,
  eyebrow,
  title,
  subtitle,
  confirmLabel,
  children,
}: {
  open: boolean;
  onClose: () => void;
  eyebrow?: string;
  title: string;
  subtitle?: string;
  confirmLabel: string;
  children: ReactNode;
}) {
  if (!open) return null;
  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/50 p-8 backdrop-blur-sm"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[80vh] w-full max-w-2xl flex-col overflow-hidden rounded-[20px] bg-surface-white shadow-2xl"
      >
        <div className="flex flex-none items-start justify-between border-b border-line-divider px-6 py-[18px]">
          <div className="min-w-0">
            {eyebrow && (
              <p className="mb-[3px] text-[10px] font-semibold uppercase tracking-[0.15em] text-ink-400">
                {eyebrow}
              </p>
            )}
            <h2 className="text-[16px] font-semibold text-ink-900">{title}</h2>
            {subtitle && <p className="mt-0.5 text-[11.5px] text-ink-400">{subtitle}</p>}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="grid h-8 w-8 flex-none place-items-center rounded-lg text-ink-400 transition-colors hover:bg-surface-warm hover:text-ink-900"
          >
            <X className="h-[18px] w-[18px]" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">{children}</div>
        <div className="flex flex-none justify-end gap-3 border-t border-line-divider px-6 py-3.5">
          <button
            type="button"
            onClick={onClose}
            className="rounded-[10px] border border-line-border bg-surface-card px-4 py-2.5 text-[12.5px] font-semibold text-ink-700 transition-colors hover:border-line-control"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded-[10px] bg-brand px-5 py-2.5 text-[12.5px] font-semibold text-white transition-colors hover:bg-brand-pressed"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
