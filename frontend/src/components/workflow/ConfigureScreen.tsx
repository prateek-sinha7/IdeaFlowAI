"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { getToken, getWorkflowDetail, type WorkflowDetail } from "@/lib/api";

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
 * SCAFFOLD (37-02 Task 1): the accordion structure + the declared-signal gating.
 * The bodies are wired to the reused surfaces (DiscoveryForm/TemplateGallery/
 * DesignSystemPicker/AdvancedExpander) in Task 2.
 */

/** The declared context provider that turns on the Templates + Design System
 *  accordions — the SAME signal the backend run-launch seam keys on (SC-001). */
const OPENDESIGN_PROVIDER = "opendesign";

interface ConfigureScreenProps {
  /** The selected deliverable's workflow id — its compiled definition drives the
   *  declared-signal gating (`context_providers`). */
  workflowId: string;
}

export function ConfigureScreen({ workflowId }: ConfigureScreenProps) {
  const [detail, setDetail] = useState<WorkflowDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

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

  // The declared signal — never a prototype-name branch (SC-001 / INV-1).
  const acceptsTemplateDs = useMemo(
    () => (detail?.context_providers ?? []).includes(OPENDESIGN_PROVIDER),
    [detail],
  );

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
      <Accordion testId="accordion-describe" title="Describe" subtitle="Tell the agents what you're building.">
        <PlaceholderBody label="Describe" />
      </Accordion>

      {/* Templates + Design System — DECLARED-SIGNAL-GATED (SC-001). */}
      {acceptsTemplateDs && (
        <Accordion testId="accordion-templates" title="Templates" subtitle="Sets the visual DNA — chrome, layout, component style.">
          <PlaceholderBody label="Templates" />
        </Accordion>
      )}
      {acceptsTemplateDs && (
        <Accordion testId="accordion-designsystem" title="Design System" subtitle="The colour + type tokens the agents build with.">
          <PlaceholderBody label="Design System" />
        </Accordion>
      )}

      {/* Review Gates + Workflow Settings — always present. */}
      <Accordion testId="accordion-gates" title="Review Gates" subtitle="Optionally pause the run for your review after specific steps.">
        <PlaceholderBody label="Review Gates" />
      </Accordion>
      <Accordion testId="accordion-settings" title="Workflow Settings" subtitle="Per-step validators, gates, model and retry levers.">
        <PlaceholderBody label="Workflow Settings" />
      </Accordion>
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

function PlaceholderBody({ label }: { label: string }) {
  return <p className="text-[12px] text-ink-400">{label} setup loads here.</p>;
}
