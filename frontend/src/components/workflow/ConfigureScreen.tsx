"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { getToken, getWorkflowDetail, type WorkflowDetail } from "@/lib/api";
import {
  listDesignSystems,
  listPrototypeTemplates,
  type DesignSystemListItem,
  type PrototypeTemplate,
} from "@/lib/prototype-api";
import { DiscoveryForm, EMPTY_ANSWERS, type DiscoveryAnswers } from "./prototype/DiscoveryForm";
import { TemplateGallery } from "./prototype/TemplateGallery";
import { DesignSystemPicker } from "./prototype/DesignSystemPicker";
import { AdvancedExpander, type SelectionsMap } from "./AgentsPopup";
import { ReviewGatesSection } from "./ReviewGatesSection";
import { Button } from "@/components/ui/Button";
import { saveDraft, readDraft, clearDraft, type ConfigureDraft } from "@/lib/draft";
import type { CustomDesignSystem } from "./prototype/CustomDesignSystemModal";
import type { AgentDef } from "@/types/index";

/**
 * ConfigureScreen — ONE generic per-run setup surface for EVERY deliverable type.
 *
 * The screen lays out per-run setup as accordions: Describe, Templates, Design
 * System, Review Gates, Workflow Settings. It is keyed on DECLARED run inputs
 * (D-15/C): the Templates + Design System accordions render ONLY when the selected
 * deliverable declares `context_providers:[opendesign]` — the SAME signal the
 * Wave-1 backend run-launch seam keys on (SC-001 / INV-1), NEVER a prototype-name
 * branch. Any deliverable that opts into the opendesign context provider GAINS the
 * accordions with zero per-deliverable code.
 *
 * Each accordion body REUSES an existing surface (compose, do not rebuild):
 * Describe→DiscoveryForm, Templates→TemplateGallery, Design System→
 * DesignSystemPicker, Review Gates→ReviewGatesSection, Workflow Settings→
 * AdvancedExpander (preserving its validator→gate coupling + retry-as-int
 * contract). Save-draft persists the composed run-draft CLIENT-SIDE via
 * sessionStorage (ND-1); the screen hydrates from it on mount; launch composes
 * the GENERIC launch inputs (template_id/design_system_id/agent_ids/selections/…)
 * and clears the draft once.
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
  gate_agent_ids?: string[];
}

interface ConfigureScreenProps {
  /** The selected deliverable's workflow id — its compiled definition drives the
   *  declared-signal gating (`context_providers`). */
  workflowId: string;
  /** The launch hand-off seam (live run launch is Phase-34 / live-deferred). Called
   *  with the composed generic command; the screen clears the draft afterwards. */
  onLaunch?: (command: ComposedLaunchCommand) => void;
}

export function ConfigureScreen({ workflowId, onLaunch }: ConfigureScreenProps) {
  const [detail, setDetail] = useState<WorkflowDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [templates, setTemplates] = useState<PrototypeTemplate[]>([]);
  const [systems, setSystems] = useState<DesignSystemListItem[]>([]);

  // Accordion state (superset of the generic launch inputs).
  const [brief, setBrief] = useState("");
  const [discovery, setDiscovery] = useState<DiscoveryAnswers>(EMPTY_ANSWERS);
  const [templateId, setTemplateId] = useState<string | null>(null);
  const [customTemplateBody, setCustomTemplateBody] = useState<string | null>(null);
  const [designSystemId, setDesignSystemId] = useState<string | null>(null);
  const [customDsBody, setCustomDsBody] = useState<string | null>(null);
  const [initialSelections, setInitialSelections] = useState<SelectionsMap>({});
  const [initialGateIds, setInitialGateIds] = useState<string[] | undefined>(undefined);

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
  // carve-out the run-launch seam also excludes: a bare base whose OD flavor is a
  // dedicated `od_` alias (bare `prototype`) declares opendesign but is rejected
  // downstream (od_context=None → 13-06 guard). Mirroring launch_context.py:91
  // keeps the gate aligned with backend eligibility exactly — the primary key is
  // still the declared provider, the exclusion is the seam's documented alias shim.
  const acceptsTemplateDs = useMemo(
    () =>
      (detail?.context_providers ?? []).includes(OPENDESIGN_PROVIDER) &&
      !OD_ALIAS_BASE_PIPELINES.has(workflowId),
    [detail, workflowId],
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

  // Hydrate every accordion from a saved client-side draft on mount (ND-1).
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
  // The compiled-plan step is a PROJECTION, not a full library AgentDef; the two
  // reused controls only read `{id, name, order, gate}`, so we surface that subset
  // and widen to AgentDef (the rest of the library metadata is irrelevant here).
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

  // Compose the persisted draft superset from the current accordion state.
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
      ...(gatesTouched ? { gate_agent_ids: gateAgentIds } : {}),
    };
    onLaunch?.(command);
    clearDraft();
  }, [templateId, designSystemId, customTemplateBody, customDsBody, brief, agentDefs, onLaunch]);

  return (
    <div className="mx-auto max-w-3xl space-y-4 px-6 py-8">
      <header className="space-y-1">
        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-ink-400">
          Configure
        </p>
        <h1 className="font-serif text-[20px] text-ink-900">
          {detail?.name ? `Set up ${detail.name}` : "Set up your run"}
        </h1>
      </header>

      {loadError && (
        <div className="rounded-[var(--radius-card)] border border-line-border bg-surface-white px-4 py-3 text-[12px] text-ink-600">
          Couldn&apos;t load this deliverable&apos;s setup: {loadError}
        </div>
      )}

      {/* Describe — always present. */}
      <Accordion testId="accordion-describe" title="Describe" subtitle="Tell the agents what you're building." defaultOpen>
        <div className="space-y-4">
          <textarea
            data-testid="configure-brief"
            value={brief}
            onChange={(e) => setBrief(e.target.value)}
            rows={4}
            placeholder="e.g. A kanban board for a 5-person growth squad — backlog, doing, review, done."
            className="w-full resize-none rounded-[var(--radius-card)] border border-line-control bg-surface-white px-3.5 py-3 text-[13px] text-ink-900 placeholder:text-ink-400 focus:border-line-border focus:outline-none"
          />
          <DiscoveryForm templateInputs={[]} answers={discovery} onChange={setDiscovery} />
        </div>
      </Accordion>

      {/* Templates + Design System — DECLARED-SIGNAL-GATED (SC-001). */}
      {acceptsTemplateDs && (
        <Accordion testId="accordion-templates" title="Templates" subtitle="Sets the visual DNA — chrome, layout, component style.">
          <TemplateGallery
            templates={templates}
            selectedId={customTemplateBody ? null : templateId}
            onSelect={(id) => { setTemplateId(id); setCustomTemplateBody(null); }}
          />
        </Accordion>
      )}
      {acceptsTemplateDs && (
        <Accordion testId="accordion-designsystem" title="Design System" subtitle="The colour + type tokens the agents build with.">
          <DesignSystemPicker
            systems={systems}
            selectedId={designSystemId}
            onSelect={(id) => { setDesignSystemId(id); setCustomDsBody(null); }}
            onSelectCustom={handleSelectCustomDs}
          />
        </Accordion>
      )}

      {/* Review Gates + Workflow Settings — always present. */}
      <Accordion testId="accordion-gates" title="Review Gates" subtitle="Optionally pause the run for your review after specific steps.">
        <ReviewGatesSection agents={agentDefs} onChange={handleGatesChange} initialGateIds={initialGateIds} />
      </Accordion>
      <Accordion testId="accordion-settings" title="Workflow Settings" subtitle="Per-step validators, gates, model and retry levers.">
        <AdvancedExpander agents={leverAgents} onSelectionsChange={handleSelectionsChange} initialSelections={initialSelections} />
      </Accordion>

      {savedConfirm && (
        <div className="rounded-[var(--radius-card)] border border-line-border bg-surface-white px-3 py-2 text-[11px] font-medium text-ink-700">
          Draft saved to this tab.
        </div>
      )}

      <div className="flex gap-3 pt-2">
        <Button
          type="button"
          variant="secondary"
          data-testid="configure-save-draft"
          onClick={handleSaveDraft}
        >
          Save draft
        </Button>
        <Button
          type="button"
          variant="primary"
          data-testid="configure-launch"
          onClick={handleLaunch}
          className="flex-1"
        >
          Launch run
        </Button>
      </div>
    </div>
  );
}

/** A single token-clean accordion section. */
function Accordion({
  testId,
  title,
  subtitle,
  children,
  defaultOpen = false,
}: {
  testId: string;
  title: string;
  subtitle?: string;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const bodyId = `${testId}-body`;
  return (
    <section
      data-testid={testId}
      className="overflow-hidden rounded-[var(--radius-card)] border border-line-border bg-surface-card"
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={bodyId}
        className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-surface-warm"
      >
        <div className="min-w-0 flex-1">
          <span className="text-[13px] font-semibold text-ink-900">{title}</span>
          {subtitle && <p className="mt-0.5 text-[11px] text-ink-400">{subtitle}</p>}
        </div>
        <ChevronDown
          className={`h-4 w-4 flex-shrink-0 text-ink-400 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <div id={bodyId} className="border-t border-line-divider bg-surface-white px-4 py-4">
          {children}
        </div>
      )}
    </section>
  );
}
