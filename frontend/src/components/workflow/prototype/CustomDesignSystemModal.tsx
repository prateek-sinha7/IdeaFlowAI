"use client";

import { useEffect, useState } from "react";
import { X, Check, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/Button";

export interface CustomDesignSystem {
  id: string;          // always "custom:<name-slug>"
  name: string;
  body: string;        // the raw DESIGN.md content
  createdAt: number;
}

const STORAGE_KEY = "flowin.custom_design_systems";

// ── localStorage helpers ──────────────────────────────────────────────────

export function loadCustomDesignSystems(): CustomDesignSystem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as CustomDesignSystem[]) : [];
  } catch {
    return [];
  }
}

export function saveCustomDesignSystems(systems: CustomDesignSystem[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(systems));
}

function slugify(name: string): string {
  return name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

// ── Modal ─────────────────────────────────────────────────────────────────

interface CustomDesignSystemModalProps {
  /** If provided, we're editing an existing system */
  existing?: CustomDesignSystem;
  onSave: (system: CustomDesignSystem) => void;
  onClose: () => void;
}

const PLACEHOLDER = `# My Brand Design System

> Category: Custom
> A brief description of this design system.

## 1. Visual Theme & Atmosphere

Describe the overall visual mood, key characteristics, and design philosophy.

## 2. Color Palette & Roles

- **Primary** (\`<primary-hex>\`): Main brand color — used for CTAs and key interactive elements.
- **Background** (\`<background-hex>\`): Page background.
- **Surface** (\`<surface-hex>\`): Card and panel backgrounds.
- **Text** (\`<text-hex>\`): Primary text.
- **Muted** (\`<muted-hex>\`): Secondary text and labels.
- **Accent** (\`<accent-hex>\`): Highlight color — used sparingly.
- **Border** (\`<border-hex>\`): Dividers and borders.

## 3. Typography Rules

- **Primary font**: your sans-serif family (e.g. system-ui, sans-serif)
- **Display font**: your display/serif family (for headings)
- **Mono font**: your monospace family (for code)

## 4. Component Stylings

Describe button styles, card styles, input styles, etc.

## 5. Layout Principles

Describe grid, spacing, max-width, and layout patterns.

## 9. Agent Prompt Guide

Quick reference for the AI agent:
- Primary CTA: \`<primary-hex>\`
- Background: \`<background-hex>\`
- Accent: \`<accent-hex>\`
- Font: your body font, plus a display font for headings
`;

export function CustomDesignSystemModal({
  existing,
  onSave,
  onClose,
}: CustomDesignSystemModalProps) {
  const [name, setName] = useState(existing?.name ?? "");
  const [body, setBody] = useState(existing?.body ?? "");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, []);

  const handleSave = () => {
    const trimmedName = name.trim();
    const trimmedBody = body.trim();

    if (!trimmedName) { setError("Give your design system a name."); return; }
    if (trimmedName.length > 60) { setError("Name must be 60 characters or fewer."); return; }
    if (!trimmedBody) { setError("Paste your DESIGN.md content."); return; }
    if (trimmedBody.length < 50) { setError("Content is too short — paste a full DESIGN.md."); return; }
    if (trimmedBody.length > 80_000) { setError("Content is too long (max 80,000 characters)."); return; }

    const slug = slugify(trimmedName);
    const system: CustomDesignSystem = {
      id: `custom:${slug}`,
      name: trimmedName,
      body: trimmedBody,
      createdAt: existing?.createdAt ?? Date.now(),
    };
    onSave(system);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--scrim)] backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="Add custom design system"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="relative flex h-[85vh] w-[95vw] max-w-[780px] flex-col overflow-hidden rounded-[var(--radius-card)] border border-line-border bg-surface-white shadow-[var(--elevation-modal)] font-sans">

        {/* Header */}
        <header className="flex flex-shrink-0 items-center justify-between border-b border-line-divider px-6 py-4">
          <div>
            <h2 className="text-[15px] font-semibold text-ink-900 font-sans">
              {existing ? "Edit custom design system" : "Add custom design system"}
            </h2>
            <p className="mt-0.5 text-[12px] text-ink-500">
              Paste your DESIGN.md content — the pipeline will use it as the brand token source.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex items-center justify-center rounded-[var(--radius-button)] border border-line-control p-1.5 text-ink-400 hover:text-ink-700 transition-colors"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </header>

        {/* Body */}
        <div className="flex flex-1 min-h-0 flex-col gap-4 overflow-y-auto px-6 py-5">
          {/* Name */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="cdsm-name" className="text-[12px] font-semibold text-ink-700">
              Name <span className="text-status-failed">*</span>
            </label>
            <input
              id="cdsm-name"
              type="text"
              value={name}
              onChange={(e) => { setName(e.target.value); setError(null); }}
              placeholder="e.g. Acme Corp, My Startup, Dark Minimal"
              maxLength={60}
              className="rounded-[var(--radius-button)] border border-line-control px-3 py-2 text-[13px] text-ink-900 placeholder:text-ink-400 focus:border-brand-border focus:outline-none"
            />
          </div>

          {/* DESIGN.md content */}
          <div className="flex flex-1 min-h-0 flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <label htmlFor="cdsm-body" className="text-[12px] font-semibold text-ink-700">
                DESIGN.md content <span className="text-status-failed">*</span>
              </label>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-ink-400">
                  {body.length.toLocaleString()} / 80,000 chars
                </span>
                {!body && (
                  <button
                    type="button"
                    onClick={() => setBody(PLACEHOLDER)}
                    className="text-[10px] font-medium text-brand hover:underline"
                  >
                    Load example
                  </button>
                )}
              </div>
            </div>
            <textarea
              id="cdsm-body"
              value={body}
              onChange={(e) => { setBody(e.target.value); setError(null); }}
              placeholder={`# My Brand\n\n## 2. Color Palette\n- Primary (<primary-hex>): ...\n\n## 3. Typography\n...`}
              className="flex-1 min-h-[280px] resize-none rounded-[var(--radius-button)] border border-line-control bg-surface-warm px-3 py-2.5 font-mono text-[12px] leading-relaxed text-ink-800 placeholder:text-ink-400 focus:border-brand-border focus:bg-surface-white focus:outline-none"
            />
          </div>

          {/* Format hint */}
          <div className="rounded-[var(--radius-button)] border border-brand-border bg-brand-fill px-4 py-3">
            <p className="text-[11px] text-ink-600 leading-relaxed">
              <strong className="text-brand">Format tip:</strong> Follow the 9-section DESIGN.md schema — Visual Theme, Color Palette, Typography, Component Stylings, Layout, Depth, Do&apos;s/Don&apos;ts, Responsive, Agent Prompt Guide. The more specific your color tokens and typography rules, the better the output.
            </p>
          </div>

          {/* Error */}
          {error && (
            <div className="flex items-center gap-2 rounded-[var(--radius-button)] border border-[var(--status-failed-border)] bg-[var(--status-failed-fill)] px-3 py-2">
              <AlertCircle className="h-3.5 w-3.5 flex-shrink-0 text-status-failed" />
              <p className="text-[12px] text-status-failed">{error}</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <footer className="flex flex-shrink-0 items-center justify-end gap-2 border-t border-line-divider px-6 py-4">
          <Button variant="secondary" size="md" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" size="md" onClick={handleSave}>
            <Check className="h-3 w-3" strokeWidth={3} />
            {existing ? "Save changes" : "Add design system"}
          </Button>
        </footer>
      </div>
    </div>
  );
}
