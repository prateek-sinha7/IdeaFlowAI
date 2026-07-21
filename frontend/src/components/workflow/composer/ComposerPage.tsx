"use client";

import { useCallback, useEffect, useState } from "react";
import { motion } from "motion/react";
import { ArrowLeft, Save, Plus, Shield, GitBranch, LayoutList } from "lucide-react";
import { IdentityCard } from "./IdentityCard";
import { AgentRow } from "./AgentRow";
import { SummaryRail } from "./SummaryRail";
import { CanvasView } from "./CanvasView";
import {
  CapabilityPaletteSection,
  SkillsHooksTab,
  PIPELINE_LABEL,
  getRole,
  type SelectionsMap,
  type StepSelection,
} from "../AgentsPopup";
import { AgentLibrary } from "../AgentLibrary";
import { NameWorkflowModal } from "@/components/catalog/NameWorkflowModal";
import { LIBRARY_AGENTS, ALL_LIBRARY_AGENTS } from "../AgentLibraryData";
import { createUserWorkflow, getToken, getWorkflowDetail } from "@/lib/api";
import type { AgentDef, WorkflowType } from "@/types/index";

interface ComposerPageProps {
  /** base_pipeline_type — fixed at composer entry; the Deliverable-type is read-only (ND-AH). */
  workflowType: WorkflowType;
  onBack: () => void;
  /**
   * 41-06 — Run-once launch (D-05 / D-CMP-RUN). Threads the composed run through
   * the EXISTING owner-scoped onStartPipeline → startPipeline seam (no new
   * contract, no engine edit, SC-001). The parent maps this onto
   * `onStartPipeline(base_pipeline_type, brief, agentIds, attachedSkills,
   * attachedHooks, extraParams)` — the SAME arg convention the revision launch
   * sites use. `base_pipeline_type` is the composer's fixed-at-entry workflowType
   * ("custom" for the compose entry, ND-AH) — the SAME value Save-to-catalogue
   * persists, so Run + Save carry an identical base. Absent ⇒ Run-once stays inert.
   */
  onRun?: (
    base_pipeline_type: WorkflowType,
    brief: string,
    agentIds: string[],
    extraParams?: Record<string, unknown>,
  ) => void;
  /** Edit-from-My-Workflows: pre-load the saved composition (agents + selections + name). */
  initialAgentIds?: string[];
  initialSelections?: SelectionsMap;
  initialName?: string;
  initialDescription?: string;
  /** SURF-03 — a known backend workflow id whose declared per-step caps are surfaced. */
  workflowId?: string;
}

const MAX_OPTIONAL = 8;

/**
 * 41-04 — the full-page Composer surface (mainView='composer'). ADDITIVE: a NEW
 * authoring surface reached from Home's "Compose a custom workflow" card and
 * edit-from-My-Workflows. It REUSES the AgentsPopup shared data model
 * (pipelineAgents order + SelectionsMap + declaredCapabilities) and its exported
 * sub-components (AdvancedExpander / CapabilityPaletteSection / SkillsHooksTab /
 * AgentPromptSection) — the AgentsPopup MODAL wrapper is RETAINED for the
 * wizard/input inline-edit flow, so this is NOT a dual implementation (INV-3).
 *
 * The header carries a Simple ⇄ Canvas toggle (D-03); Simple is active here and
 * renders the mock-fidelity Simple view. The Canvas view mounts in 41-05.
 */
export function ComposerPage({
  workflowType,
  onBack,
  onRun,
  initialAgentIds,
  initialSelections,
  initialName,
  initialDescription,
  workflowId,
}: ComposerPageProps) {
  const [view, setView] = useState<"simple" | "canvas">("simple");
  const [name, setName] = useState(initialName ?? "");
  const [description, setDescription] = useState(initialDescription ?? "");
  const [saveOpen, setSaveOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);

  // Shared data model: the pipeline agent order + the per-agent SelectionsMap.
  const [pipelineAgents, setPipelineAgents] = useState<AgentDef[]>(() =>
    initialAgentIds?.length
      ? (initialAgentIds
          .map((id) => ALL_LIBRARY_AGENTS.find((a) => a.id === id))
          .filter(Boolean) as AgentDef[])
      : LIBRARY_AGENTS.filter((a) => a.pipeline_type === workflowType).sort(
          (a, b) => a.order - b.order,
        ),
  );
  const [selections, setSelections] = useState<SelectionsMap>(initialSelections ?? {});
  const [draggedIdx, setDraggedIdx] = useState<number | null>(null);
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);

  // SURF-03 — the opened workflow's declared per-step capabilities (compiled
  // projection), surfaced in the palette + summary. Skipped for from-scratch.
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
    if (!jwt) return;
    getWorkflowDetail(jwt, workflowId)
      .then((detail) => {
        if (cancelled) return;
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
        if (!cancelled) setDeclaredCapabilities(undefined);
      });
    return () => {
      cancelled = true;
    };
  }, [workflowId]);

  const deliverableLabel = PIPELINE_LABEL[workflowType] ?? workflowType;
  const strategy = "sequential";

  const defaultAgentIds = new Set(
    LIBRARY_AGENTS.filter((a) => a.pipeline_type === workflowType).map((a) => a.id),
  );
  const optionalCount = pipelineAgents.filter((a) => !defaultAgentIds.has(a.id)).length;
  const canAddMore = optionalCount < MAX_OPTIONAL;

  // ── Reorder / add / remove (native drag pattern mirrors AgentsPopup) ──────────
  const moveAgent = useCallback((i: number, dir: -1 | 1) => {
    setPipelineAgents((prev) => {
      const j = i + dir;
      if (j < 0 || j >= prev.length) return prev;
      const next = [...prev];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
  }, []);

  const handleDragStart = useCallback(
    (i: number) => {
      if (getRole(pipelineAgents[i].id, workflowType) === "locked") return;
      setDraggedIdx(i);
    },
    [pipelineAgents, workflowType],
  );
  const handleDragOver = useCallback((e: React.DragEvent, i: number) => {
    e.preventDefault();
    setDragOverIdx(i);
  }, []);
  const handleDrop = useCallback(
    (i: number) => {
      setDraggedIdx((from) => {
        if (from === null || from === i) return null;
        setPipelineAgents((prev) => {
          const next = [...prev];
          const [moved] = next.splice(from, 1);
          next.splice(i, 0, moved);
          return next;
        });
        return null;
      });
      setDragOverIdx(null);
    },
    [],
  );
  const handleDragEnd = useCallback(() => {
    setDraggedIdx(null);
    setDragOverIdx(null);
  }, []);

  const removeAgent = useCallback((id: string) => {
    setPipelineAgents((prev) => prev.filter((a) => a.id !== id));
    setSelections((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
  }, []);

  const addAgent = useCallback(
    (agent: AgentDef) => {
      setPipelineAgents((prev) => {
        if (prev.find((a) => a.id === agent.id)) return prev;
        const currentOptional = prev.filter((a) => !defaultAgentIds.has(a.id)).length;
        if (currentOptional >= MAX_OPTIONAL) return prev;
        return [...prev, { ...agent, order: prev.length + 1 }];
      });
      setAddOpen(false);
    },
    [defaultAgentIds],
  );

  const handleAgentSelection = useCallback(
    (agentId: string, sel: StepSelection | undefined) => {
      setSelections((prev) => {
        const next = { ...prev };
        if (sel && Object.keys(sel).length > 0) next[agentId] = sel;
        else delete next[agentId];
        return next;
      });
    },
    [],
  );

  // ── Derived summary values (live, never fabricated — ND-AG) ───────────────────
  const gateCount = pipelineAgents.filter(
    (a) => (selections[a.id]?.gates?.length ?? 0) > 0 || !!a.gate,
  ).length;
  const totalSec = pipelineAgents.reduce((s, a) => s + a.estimated_duration, 0);
  const estMinutes = Math.max(1, Math.round(totalSec / 60));
  const estDurationLabel = `~${estMinutes}m`;

  const declaredSet = new Set<string>();
  for (const sel of Object.values(selections)) {
    (sel.validators ?? []).forEach((v) => declaredSet.add(v));
    (sel.gates ?? []).forEach((g) => declaredSet.add(g));
  }
  if (declaredCapabilities) {
    for (const d of declaredCapabilities) d.capabilities.forEach((c) => declaredSet.add(c));
  }
  const declaredChips = Array.from(declaredSet);

  // ── Save-to-catalogue (REUSE — owner-scoped createUserWorkflow) ──────────────
  const handleSave = useCallback(
    async (wfName: string, wfDescription: string) => {
      setSaveOpen(false);
      setSaveError(null);
      const token = getToken();
      if (!token) {
        setSaveError("Not authenticated.");
        return;
      }
      setSaving(true);
      try {
        const resp = await createUserWorkflow(token, {
          name: wfName,
          ...(wfDescription ? { description: wfDescription } : {}),
          base_pipeline_type: workflowType,
          agent_ids: pipelineAgents.map((a) => a.id),
          ...(Object.keys(selections).length > 0 ? { selections } : {}),
        });
        setName(wfName);
        setDescription(wfDescription);
        // CWF-001 D1: surface the backend's producer-first pre-sort — reorder the
        // visible rows to the persisted order. The backend is the authoritative
        // source (the FE AgentDef carries no produces/consumes), and it repairs a
        // consumer-before-producer order server-side. Guard on a present, non-empty
        // agent_ids so a response without it (or an older shape) leaves rows
        // untouched. An unsatisfiable composition instead throws below and renders
        // inline via saveError. Selections are keyed by agent_id → reorder-safe.
        if (resp?.agent_ids?.length) {
          setPipelineAgents((prev) =>
            resp.agent_ids
              .map((id) => prev.find((a) => a.id === id))
              .filter((a): a is AgentDef => Boolean(a)),
          );
        }
      } catch (e) {
        setSaveError((e as Error)?.message ?? "Failed to save workflow.");
      } finally {
        setSaving(false);
      }
    },
    [workflowType, pipelineAgents, selections],
  );

  // ── Run-once (D-05 / D-CMP-RUN — through the EXISTING launch seam, ND-AG) ─────
  // Assemble the composed run and fire it through the parent `onRun` (which maps
  // onto the unchanged onStartPipeline → startPipeline seam). The base_pipeline_type
  // is the composer's fixed-at-entry `workflowType` ("custom" for the compose entry,
  // ND-AH) — the SAME value handleSave persists, so Run + Save carry an identical
  // base. The composed agent order → agent ids; the identity brief → the run message;
  // the per-step SelectionsMap + review-gate agents → extraParams (the SAME shared
  // data-model fields the existing launch already accepts — no fabricated cost).
  const handleRunOnce = useCallback(() => {
    if (!onRun) return;
    const brief = description.trim() || name.trim() || "Custom workflow run";
    const gateAgentIds = pipelineAgents
      .filter((a) => (selections[a.id]?.gates?.length ?? 0) > 0 || !!a.gate)
      .map((a) => a.id);
    const extraParams: Record<string, unknown> = {
      ...(Object.keys(selections).length > 0 ? { selections } : {}),
      ...(gateAgentIds.length > 0 ? { gate_agent_ids: gateAgentIds } : {}),
    };
    onRun(
      workflowType,
      brief,
      pipelineAgents.map((a) => a.id),
      Object.keys(extraParams).length > 0 ? extraParams : undefined,
    );
  }, [onRun, description, name, pipelineAgents, selections, workflowType]);

  const segBtn = (id: "simple" | "canvas", label: string, Icon: typeof GitBranch) => (
    <button
      type="button"
      onClick={() => setView(id)}
      className={`inline-flex items-center gap-1.5 rounded-[7px] px-3 py-1.5 font-sans text-[12px] font-semibold transition-colors ${
        view === id
          ? "bg-surface-white text-ink-900 shadow-sm"
          : "text-ink-400 hover:text-ink-700"
      }`}
    >
      <Icon className="h-3.5 w-3.5" />
      {label}
    </button>
  );

  return (
    <div className="flex h-full flex-col overflow-hidden bg-surface-paper text-ink-900">
      {/* Header */}
      <div className="flex flex-none items-center gap-3.5 border-b border-line-divider bg-surface-warm px-[34px] py-[15px]">
        <button
          type="button"
          onClick={onBack}
          aria-label="Back"
          className="grid h-9 w-9 flex-none place-items-center rounded-[9px] border border-line-control bg-surface-card text-ink-700 transition-colors hover:border-line-faint"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <div className="flex-1">
          <p className="mb-0.5 font-sans text-[10px] font-semibold uppercase tracking-[0.15em] text-ink-300">
            Custom workflow · Composer
          </p>
          <h1 className="font-sans text-[22px] font-light leading-none tracking-tight text-ink-900">
            {name || "Untitled workflow"}
          </h1>
        </div>

        {/* Simple ⇄ Canvas toggle (Canvas mounts in 41-05) */}
        <div className="flex items-center gap-1 rounded-[9px] border border-line-control bg-surface-card p-1">
          {segBtn("simple", "Simple", LayoutList)}
          {segBtn("canvas", "Canvas", GitBranch)}
        </div>

        <button
          type="button"
          className="rounded-[10px] border border-line-control bg-surface-card px-3.5 py-2.5 font-sans text-[12.5px] font-semibold text-ink-700 transition-colors hover:border-line-faint"
          onClick={() => setSaveOpen(true)}
        >
          Save draft
        </button>
        <button
          type="button"
          onClick={() => setSaveOpen(true)}
          className="inline-flex items-center gap-2 rounded-[10px] bg-brand px-[18px] py-2.5 font-sans text-[12.5px] font-semibold text-surface-white transition-colors hover:bg-brand-pressed"
        >
          <Save className="h-3.5 w-3.5" />
          Save workflow
        </button>
      </div>

      {/* Body */}
      <div className="min-h-0 flex-1">
        {view === "canvas" ? (
          <CanvasView
            pipelineAgents={pipelineAgents}
            selections={selections}
            pipelineType={workflowType}
            onSelection={handleAgentSelection}
            onRemoveAgent={removeAgent}
            onAddAgent={() => setAddOpen(true)}
            canAddMore={canAddMore}
            gateCount={gateCount}
            strategy={strategy}
            estDurationLabel={estDurationLabel}
            declaredCapabilities={declaredChips}
            onSaveToCatalogue={() => setSaveOpen(true)}
            // 41-06 — Run-once now launches through the EXISTING onStartPipeline seam.
            onRunOnce={onRun ? handleRunOnce : undefined}
          />
        ) : (
          <div className="h-full overflow-y-auto">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.2 }}
            className="mx-auto grid max-w-[1200px] grid-cols-1 items-start gap-[22px] px-[34px] pb-[70px] pt-[30px] lg:grid-cols-[1fr_320px]"
          >
            {/* Main column */}
            <div>
              <IdentityCard
                name={name}
                description={description}
                deliverableLabel={deliverableLabel}
                onNameChange={setName}
                onDescriptionChange={setDescription}
              />

              {/* Agent pipeline header */}
              <div className="mx-0.5 mb-3 flex items-center justify-between">
                <div>
                  <h2 className="font-sans text-[15px] font-semibold text-ink-900">
                    Agent pipeline
                  </h2>
                  <p className="font-serif text-[11.5px] text-ink-300">
                    {pipelineAgents.length} agents · runs {strategy} · drag to reorder
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setAddOpen(true)}
                  disabled={!canAddMore}
                  className="inline-flex items-center gap-1.5 rounded-[9px] border border-line-control bg-surface-card px-3.5 py-2.5 font-sans text-[12px] font-semibold text-ink-700 transition-colors enabled:hover:border-brand enabled:hover:text-brand disabled:opacity-40"
                >
                  <Plus className="h-3.5 w-3.5" />
                  Add agent
                </button>
              </div>

              {/* Agent rows */}
              <div className="flex flex-col gap-2.5">
                {pipelineAgents.length === 0 ? (
                  <div className="rounded-[13px] border border-dashed border-line-control bg-surface-card px-4 py-10 text-center font-serif text-[12.5px] text-ink-300">
                    No agents yet — add one from the catalogue to start composing.
                  </div>
                ) : (
                  pipelineAgents.map((agent, i) => (
                    <AgentRow
                      key={agent.id}
                      agent={agent}
                      index={i}
                      total={pipelineAgents.length}
                      pipelineType={workflowType}
                      selection={selections[agent.id]}
                      onSelection={handleAgentSelection}
                      onMoveUp={() => moveAgent(i, -1)}
                      onMoveDown={() => moveAgent(i, 1)}
                      onRemove={() => removeAgent(agent.id)}
                      isDragOver={dragOverIdx === i}
                      onDragStart={() => handleDragStart(i)}
                      onDragOver={(e) => handleDragOver(e, i)}
                      onDrop={() => handleDrop(i)}
                      onDragEnd={handleDragEnd}
                    />
                  ))
                )}
              </div>

              {/* Capability palette (REUSE CapabilityPaletteSection) */}
              <div className="mt-[22px] rounded-[14px] border border-line-border bg-surface-card px-[22px] py-5">
                <div className="mb-1.5 flex items-center gap-2.5">
                  <Shield className="h-4 w-4 text-ink-700" />
                  <h2 className="font-sans text-[15px] font-semibold text-ink-900">
                    Capability palette
                  </h2>
                </div>
                <p className="mb-4 font-serif text-[12px] leading-relaxed text-ink-400">
                  Only allow-listed capabilities can be enabled. Execution, network and
                  secrets stay off behind the security gate; some capabilities are
                  engineer-only.
                </p>
                <CapabilityPaletteSection declaredCapabilities={declaredCapabilities} />
              </div>

              {/* Skills & hooks (REUSE SkillsHooksTab) */}
              <div className="mt-4 rounded-[14px] border border-line-border bg-surface-card px-[22px] py-5">
                <h2 className="mb-1 font-sans text-[15px] font-semibold text-ink-900">
                  Skills &amp; hooks
                </h2>
                <p className="mb-2 font-serif text-[12px] leading-relaxed text-ink-400">
                  Inject domain instructions and pre/post behaviours across the whole
                  workflow.
                </p>
                <SkillsHooksTab pipelineType={workflowType} />
              </div>
            </div>

            {/* Summary rail */}
            <SummaryRail
              agentCount={pipelineAgents.length}
              gateCount={gateCount}
              strategy={strategy}
              estDurationLabel={estDurationLabel}
              declaredCapabilities={declaredChips}
              onSaveToCatalogue={() => setSaveOpen(true)}
              // 41-06 — Run-once now launches through the EXISTING onStartPipeline seam.
              onRunOnce={onRun ? handleRunOnce : undefined}
            />
          </motion.div>
          </div>
        )}
      </div>

      {saveError && (
        <div className="flex-none px-[34px] pb-3 font-serif text-[11px] text-status-failed">
          {saveError}
        </div>
      )}

      {/* Add agent (REUSE AgentLibrary) */}
      <AgentLibrary
        isOpen={addOpen}
        onClose={() => setAddOpen(false)}
        onAddAgent={addAgent}
        currentPipelineType={workflowType}
        canAddMore={canAddMore}
        existingAgentIds={pipelineAgents.map((a) => a.id)}
      />

      {/* Save to catalogue (REUSE NameWorkflowModal → createUserWorkflow) */}
      {saveOpen && (
        <NameWorkflowModal
          title="Save workflow"
          initialName={name}
          initialDescription={description}
          onSave={handleSave}
          onCancel={() => {
            if (!saving) setSaveOpen(false);
          }}
        />
      )}
    </div>
  );
}
