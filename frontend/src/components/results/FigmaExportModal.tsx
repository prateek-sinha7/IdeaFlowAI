"use client";

/**
 * FigmaExportModal
 *
 * Step-by-step guide shown before the Figma ZIP download starts.
 * Shell follows the app's modal conventions (UpgradePlanModal / NameWorkflowModal):
 *   - createPortal to <body> so no stacking-context trapping
 *   - bg-surface-white card, border-line-border, rounded-2xl, elevation-modal shadow
 *   - bg-[var(--scrim)] backdrop + backdrop-blur-sm
 *   - motion/react scale-in (opacity 0→1, scale 0.96→1, y 8→0, 150ms)
 *   - brand #3C2CDA, warm ink ramp, Manrope sans, Heebo serif
 */

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { motion } from "motion/react";
import { Download, FolderOpen, Puzzle, FileJson, CheckCircle2, X, ChevronRight } from "lucide-react";

interface FigmaExportModalProps {
  open: boolean;
  onClose: () => void;
  /** Called when user confirms on the last step — parent triggers the ZIP download. */
  onConfirm: () => void;
  loading?: boolean;
}

const STEPS = [
  {
    icon: Download,
    title: "Download the ZIP",
    body: "You'll get a single ZIP with the Figma JSON file for this prototype and the VelocityAI Figma plugin.",
  },
  {
    icon: FolderOpen,
    title: "Unzip the folder",
    body: "Extract the ZIP anywhere. Inside you'll find your JSON file and the plugin folder (velocityai-figma-plugin/).",
  },
  {
    icon: Puzzle,
    title: "Install the plugin (one-time)",
    body: 'Open Figma Desktop → Plugins → Development → "Import plugin from manifest…" → select manifest.json from the plugin folder.',
    note: "Requires Figma Desktop — the browser version cannot run local plugins.",
  },
  {
    icon: FileJson,
    title: "Import your prototype",
    body: 'Run Plugins → Development → "VelocityAI Importer" in any Figma file. Drop the JSON and click Import to Figma.',
  },
  {
    icon: CheckCircle2,
    title: "Done — frames ready to edit",
    body: "Figma creates one frame per screen at 1440 × 900. Colors, text styles, and layout are all editable. Replace placeholder rectangles with real icons and images.",
  },
];

export function FigmaExportModal({ open, onClose, onConfirm, loading = false }: FigmaExportModalProps) {
  const [step, setStep] = useState(0);

  useEffect(() => { if (open) setStep(0); }, [open]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open || typeof document === "undefined") return null;

  const current = STEPS[step];
  const Icon = current.icon;
  const isLast = step === STEPS.length - 1;

  return createPortal(
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-[var(--scrim)] backdrop-blur-sm p-4"
      onClick={onClose}
      role="presentation"
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.15 }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="figma-modal-title"
        onClick={(e) => e.stopPropagation()}
        className="bg-surface-white rounded-2xl border border-line-border shadow-[var(--elevation-modal)] w-full max-w-[440px] overflow-hidden"
      >
        {/* ── Header ── */}
        <div className="flex items-center gap-3 px-5 pt-5 pb-4 border-b border-line-divider">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-fill flex-shrink-0">
            <FileJson className="h-[18px] w-[18px] text-brand" />
          </div>
          <div className="flex-1 min-w-0">
            <h2 id="figma-modal-title" className="font-sans text-[13.5px] font-semibold text-ink-900 leading-tight">
              Export to Figma
            </h2>
            <p className="font-serif text-[11.5px] text-ink-400 mt-0.5">
              One ZIP, five steps — your prototype in Figma
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="flex h-7 w-7 items-center justify-center rounded-lg text-ink-400 hover:text-ink-700 hover:bg-surface-warm transition-colors flex-shrink-0"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* ── Step pills ── */}
        <div className="flex items-center gap-1 px-5 py-3 border-b border-line-divider overflow-x-auto">
          {STEPS.map((s, i) => {
            const done = i < step;
            const active = i === step;
            return (
              <button
                key={i}
                onClick={() => setStep(i)}
                className={[
                  "flex items-center gap-1.5 px-2.5 py-1 rounded-[var(--radius-pill)] text-[11px] font-medium whitespace-nowrap transition-all flex-shrink-0",
                  active
                    ? "bg-brand-fill text-brand border border-brand-border"
                    : done
                    ? "bg-surface-warm text-ink-500 border border-line-divider"
                    : "text-ink-400 border border-transparent",
                ].join(" ")}
              >
                {done
                  ? <CheckCircle2 className="h-3 w-3 text-status-done flex-shrink-0" />
                  : (
                    <span className={[
                      "h-[18px] w-[18px] rounded-full flex items-center justify-center text-[9px] font-bold flex-shrink-0",
                      active ? "bg-brand text-white" : "bg-line-divider text-ink-500",
                    ].join(" ")}>
                      {i + 1}
                    </span>
                  )
                }
                {s.title}
              </button>
            );
          })}
        </div>

        {/* ── Step body ── */}
        <div className="px-5 py-5 min-h-[200px]">
          {/* Icon */}
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-surface-warm border border-line-border mb-4">
            <Icon className="h-5 w-5 text-ink-600" />
          </div>

          {/* Step heading */}
          <p className="font-sans text-[11px] font-semibold uppercase tracking-[0.1em] text-ink-400 mb-1">
            Step {step + 1} of {STEPS.length}
          </p>
          <h3 className="font-sans text-[14px] font-semibold text-ink-900 mb-2">
            {current.title}
          </h3>
          <p className="font-serif text-[13px] text-ink-600 leading-relaxed">
            {current.body}
          </p>

          {/* Note (step 3 — Figma Desktop required) */}
          {current.note && (
            <p className="mt-3 text-[11.5px] text-status-amber bg-[var(--status-amber-fill)] border border-[var(--status-amber-border)] rounded-[var(--radius-node)] px-3 py-2 leading-relaxed">
              {current.note}
            </p>
          )}

          {/* ZIP contents tree — shown on step 0 */}
          {step === 0 && (
            <div className="mt-4 rounded-[var(--radius-card)] border border-line-divider bg-surface-warm divide-y divide-line-divider text-[11.5px]">
              {[
                { name: "prototype-figma.json", desc: "Your prototype screens as Figma nodes", mono: true, highlight: true },
                { name: "velocityai-figma-plugin/", desc: "The importer plugin (install once)", mono: true, highlight: false },
                { name: "  manifest.json", desc: "Plugin descriptor", mono: false, highlight: false },
                { name: "  code.js", desc: "Plugin sandbox code", mono: false, highlight: false },
                { name: "  ui.html", desc: "Plugin UI panel", mono: false, highlight: false },
                { name: "  README.md", desc: "Install instructions", mono: false, highlight: false },
              ].map((f) => (
                <div key={f.name} className="flex items-center gap-3 px-3 py-2">
                  <span className={[
                    "font-mono flex-shrink-0",
                    f.highlight ? "text-brand font-medium" : "text-ink-500",
                  ].join(" ")}>
                    {f.name}
                  </span>
                  <span className="text-ink-400 truncate">{f.desc}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── Footer ── */}
        <div className="flex items-center justify-between gap-2 px-5 pb-5">
          {/* Back */}
          <div>
            {step > 0 && (
              <button
                onClick={() => setStep(s => s - 1)}
                className="rounded-[var(--radius-button)] border border-line-control px-3 py-2 text-[12px] font-medium text-ink-600 hover:bg-surface-warm transition-colors"
              >
                ← Back
              </button>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="rounded-[var(--radius-button)] border border-line-control px-4 py-2 text-[12px] font-medium text-ink-600 hover:bg-surface-warm transition-colors"
            >
              Cancel
            </button>

            {isLast ? (
              <button
                onClick={() => { onConfirm(); onClose(); }}
                disabled={loading}
                className="flex items-center gap-1.5 rounded-[var(--radius-button)] bg-brand px-4 py-2 text-[12px] font-medium text-white hover:bg-brand-pressed transition-colors disabled:opacity-40"
              >
                {loading
                  ? <><span className="h-3 w-3 border-2 border-white/40 border-t-white rounded-full animate-spin" /> Generating…</>
                  : <><Download className="h-3.5 w-3.5" /> Download ZIP</>
                }
              </button>
            ) : (
              <button
                onClick={() => setStep(s => s + 1)}
                className="flex items-center gap-1 rounded-[var(--radius-button)] bg-brand px-4 py-2 text-[12px] font-medium text-white hover:bg-brand-pressed transition-colors"
              >
                Next <ChevronRight className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        </div>
      </motion.div>
    </div>,
    document.body,
  );
}
