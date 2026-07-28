"use client";

import { useState, type ReactNode } from "react";
import { ArrowLeft, ArrowRight, Globe, Presentation } from "lucide-react";
import { TemplateGallery } from "@/components/workflow/prototype/TemplateGallery";
import { PPTTemplateGallery } from "@/components/workflow/ppt/PPTTemplateGallery";
import { Tabs, type TabItem } from "@/components/ui/Tabs";
import type { PrototypeTemplate } from "@/lib/prototype-api";
import type { PPTTemplate } from "@/lib/ppt-api";
import type { CustomTemplate } from "@/components/workflow/prototype/CustomTemplateModal";

/**
 * WizardStepper (plan 37-04) — the unified Template -> Design System ->
 * Discovery stepper. Today the flow is route-split (prototype/templates vs
 * ppt/templates) with no stepper; this consolidates the chrome into ONE
 * component.
 *
 * The stepper is CHROME ONLY. Its step bodies REUSE the shipped surfaces:
 *   - Web  -> <TemplateGallery>    (live GET /api/prototype/templates)
 *   - Deck -> <PPTTemplateGallery> (live GET /api/ppt/templates)
 * plus render slots (dsSlot, discoverySlot) that plan 37-05 injects WITHOUT
 * editing this file.
 *
 * SC-001 / INV-1: the stepper is keyed on a GENERIC `mode` toggle value
 * ("web" | "deck") — never a workflow-name branch on the pipeline type.
 * The deliverable family is a data value, not a code path.
 *
 * All colours route through the plan-01 @theme token layer; NO retired palette.
 */

export type WizardMode = "web" | "deck";

export interface WizardStepperProps {
  /** Generic deliverable toggle — the template family to show. NOT a workflow name. */
  mode: WizardMode;
  onModeChange: (mode: WizardMode) => void;

  /**
   * Whether to render the Web/Deck toggle control (default false — hidden).
   * Pass `true` only when cross-family switching is explicitly desired.
   * When false the gallery is fixed to the `mode` prop value.
   */
  showToggle?: boolean;

  // ── Web template step — props forwarded verbatim to the reused TemplateGallery ──
  webTemplates: PrototypeTemplate[];
  webSelectedId: string | null;
  onWebSelect: (id: string | null) => void;
  onWebSelectCustomTemplate?: (ct: CustomTemplate | null) => void;
  webSelectedCustomTemplateId?: string | null;

  // ── Deck template step — props forwarded verbatim to the reused PPTTemplateGallery ──
  deckTemplates: PPTTemplate[];
  deckSelectedId: string | null;
  onDeckSelect: (id: string) => void;
  onDeckSelectCustomTemplate?: (ct: CustomTemplate | null) => void;
  deckSelectedCustomTemplateId?: string | null;

  /**
   * Step 2 (Design System) render slot. Plan 37-05 injects the DS band-cards
   * here without editing the stepper. When omitted a neutral placeholder shows.
   */
  dsSlot?: ReactNode;
  /**
   * Step 3 (Discovery) render slot. Plan 37-05 injects the Discovery form here
   * without editing the stepper. When omitted a neutral placeholder shows.
   */
  discoverySlot?: ReactNode;

  /** Optional controlled step index (0..2). Uncontrolled (internal state) by default. */
  step?: number;
  onStepChange?: (step: number) => void;

  /**
   * Which steps to show as tabs (default: all three).
   * Pass ["template"] for PPT/deck mode where DS + Discovery are not needed.
   */
  steps?: StepId[];

  className?: string;
}

const ALL_STEP_IDS = ["template", "design-system", "discovery"] as const;
type StepId = (typeof ALL_STEP_IDS)[number];

const STEP_TAB_LABELS: Record<StepId, string> = {
  "template": "Template",
  "design-system": "Design System",
  "discovery": "Discovery",
};

export function WizardStepper({
  mode,
  onModeChange,
  showToggle = false,
  webTemplates,
  webSelectedId,
  onWebSelect,
  onWebSelectCustomTemplate,
  webSelectedCustomTemplateId,
  deckTemplates,
  deckSelectedId,
  onDeckSelect,
  onDeckSelectCustomTemplate,
  deckSelectedCustomTemplateId,
  dsSlot,
  discoverySlot,
  step,
  onStepChange,
  steps = ["template", "design-system", "discovery"],
  className = "",
}: WizardStepperProps) {
  const [stepState, setStepState] = useState(0);
  const activeStep = step ?? stepState;

  // Derive the visible tab list and last step index from the `steps` prop.
  const stepIds = steps;
  const stepTabs: TabItem[] = steps.map((id) => ({ id, label: STEP_TAB_LABELS[id] }));
  const lastStep = steps.length - 1;

  const goToStep = (next: number) => {
    const clamped = Math.max(0, Math.min(lastStep, next));
    setStepState(clamped);
    onStepChange?.(clamped);
  };

  // Resolve the actual step kind at the current index.
  const activeStepId = stepIds[activeStep] ?? "template";

  return (
    <div className={["flex flex-col gap-6", className].filter(Boolean).join(" ")}>
      {/* ── Step header (reuses the shared underline-Tabs primitive) ─────────── */}
      <Tabs
        tabs={stepTabs}
        active={stepIds[activeStep]}
        onChange={(id) => goToStep(stepIds.indexOf(id as StepId))}
      />

      {/* ── Step body ───────────────────────────────────────────────────────── */}
      <div>
        {activeStepId === "template" && (
          <div className="flex flex-col gap-4">
            {/* Web/Deck toggle — hidden by default (showToggle=false); shown only
                when the caller explicitly opts in to cross-family switching. */}
            {showToggle && (
              <div
                role="group"
                aria-label="Deliverable family"
                className="inline-flex items-center gap-0.5 self-start rounded-[var(--radius-button)] border border-line-border bg-surface-warm p-0.5"
              >
                <ModeButton
                  active={mode === "web"}
                  onClick={() => onModeChange("web")}
                  icon={<Globe className="h-3.5 w-3.5" />}
                  label="Web"
                />
                <ModeButton
                  active={mode === "deck"}
                  onClick={() => onModeChange("deck")}
                  icon={<Presentation className="h-3.5 w-3.5" />}
                  label="Deck"
                />
              </div>
            )}

            {/* Reused template body — swapped by the toggle, never rebuilt. */}
            {mode === "web" ? (
              <TemplateGallery
                templates={webTemplates}
                selectedId={webSelectedId}
                onSelect={onWebSelect}
                onSelectCustomTemplate={onWebSelectCustomTemplate}
                selectedCustomTemplateId={webSelectedCustomTemplateId}
              />
            ) : (
              <PPTTemplateGallery
                templates={deckTemplates}
                selectedId={deckSelectedId}
                onSelect={onDeckSelect}
                onSelectCustomTemplate={onDeckSelectCustomTemplate}
                selectedCustomTemplateId={deckSelectedCustomTemplateId}
              />
            )}
          </div>
        )}

        {activeStepId === "design-system" && (dsSlot ?? <StepPlaceholder label="Design system step" />)}

        {activeStepId === "discovery" && (discoverySlot ?? <StepPlaceholder label="Discovery step" />)}
      </div>

      {/* ── Back / Next navigation — only shown when there are multiple steps ── */}
      {steps.length > 1 && (
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => goToStep(activeStep - 1)}
          disabled={activeStep === 0}
          className="inline-flex items-center gap-2 rounded-[var(--radius-button)] border border-line-border bg-surface-white px-4 py-2 text-[13px] font-medium text-ink-700 transition-colors hover:bg-surface-warm disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </button>
        <button
          type="button"
          onClick={() => goToStep(activeStep + 1)}
          disabled={activeStep === lastStep}
          className="inline-flex items-center gap-2 rounded-[var(--radius-button)] bg-brand px-5 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-brand-pressed disabled:cursor-not-allowed disabled:opacity-40"
        >
          Next
          <ArrowRight className="h-4 w-4" />
        </button>
      </div>
      )}
    </div>
  );
}

function ModeButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: ReactNode;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={[
        "inline-flex items-center gap-1.5 rounded-[var(--radius-tag)] px-3 py-1.5 text-[12.5px] font-medium transition-colors",
        active
          ? "bg-surface-white text-ink-900 shadow-[var(--elevation-raised)]"
          : "text-ink-500 hover:text-ink-800",
      ].join(" ")}
    >
      {icon}
      {label}
    </button>
  );
}

function StepPlaceholder({ label }: { label: string }) {
  return (
    <div className="flex h-40 items-center justify-center rounded-[var(--radius-card)] border border-dashed border-line-control bg-surface-warm text-[12px] text-ink-400">
      {label}
    </div>
  );
}

export default WizardStepper;
