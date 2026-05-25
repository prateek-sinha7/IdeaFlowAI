"use client";

import { useEffect, useState } from "react";
import { X, Check, AlertCircle } from "lucide-react";

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

- **Primary** (\`#1a1a2e\`): Main brand color — used for CTAs and key interactive elements.
- **Background** (\`#f8f9fa\`): Page background.
- **Surface** (\`#ffffff\`): Card and panel backgrounds.
- **Text** (\`#111827\`): Primary text.
- **Muted** (\`#6b7280\`): Secondary text and labels.
- **Accent** (\`#e63946\`): Highlight color — used sparingly.
- **Border** (\`#e5e7eb\`): Dividers and borders.

## 3. Typography Rules

- **Primary font**: Inter, system-ui, sans-serif
- **Display font**: Georgia, serif (for headings)
- **Mono font**: JetBrains Mono, monospace

## 4. Component Stylings

Describe button styles, card styles, input styles, etc.

## 5. Layout Principles

Describe grid, spacing, max-width, and layout patterns.

## 9. Agent Prompt Guide

Quick reference for the AI agent:
- Primary CTA: \`#1a1a2e\`
- Background: \`#f8f9fa\`
- Accent: \`#e63946\`
- Font: Inter for body, Georgia for display
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
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="Add custom design system"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="relative flex h-[85vh] w-[95vw] max-w-[780px] flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">

        {/* Header */}
        <header className="flex flex-shrink-0 items-center justify-between border-b border-gray-100 px-6 py-4">
          <div>
            <h2 className="text-[15px] font-semibold text-gray-900">
              {existing ? "Edit custom design system" : "Add custom design system"}
            </h2>
            <p className="mt-0.5 text-[12px] text-gray-500">
              Paste your DESIGN.md content — the pipeline will use it as the brand token source.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex items-center justify-center rounded-lg border border-gray-200 p-1.5 text-gray-400 hover:text-gray-700 transition-colors"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </header>

        {/* Body */}
        <div className="flex flex-1 min-h-0 flex-col gap-4 overflow-y-auto px-6 py-5">
          {/* Name */}
          <div className="flex flex-col gap-1.5">
            <label className="text-[12px] font-semibold text-gray-700">
              Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => { setName(e.target.value); setError(null); }}
              placeholder="e.g. Acme Corp, My Startup, Dark Minimal"
              maxLength={60}
              className="rounded-lg border border-gray-200 px-3 py-2 text-[13px] text-gray-900 placeholder:text-gray-400 focus:border-gray-400 focus:outline-none"
            />
          </div>

          {/* DESIGN.md content */}
          <div className="flex flex-1 min-h-0 flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <label className="text-[12px] font-semibold text-gray-700">
                DESIGN.md content <span className="text-red-500">*</span>
              </label>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-gray-400">
                  {body.length.toLocaleString()} / 80,000 chars
                </span>
                {!body && (
                  <button
                    type="button"
                    onClick={() => setBody(PLACEHOLDER)}
                    className="text-[10px] font-medium text-[#1B2A4A] hover:underline"
                  >
                    Load example
                  </button>
                )}
              </div>
            </div>
            <textarea
              value={body}
              onChange={(e) => { setBody(e.target.value); setError(null); }}
              placeholder={`# My Brand\n\n## 2. Color Palette\n- Primary (#1a1a2e): ...\n\n## 3. Typography\n...`}
              className="flex-1 min-h-[280px] resize-none rounded-lg border border-gray-200 bg-gray-50 px-3 py-2.5 font-mono text-[12px] leading-relaxed text-gray-800 placeholder:text-gray-400 focus:border-gray-400 focus:bg-white focus:outline-none"
            />
          </div>

          {/* Format hint */}
          <div className="rounded-lg border border-blue-100 bg-blue-50 px-4 py-3">
            <p className="text-[11px] text-blue-700 leading-relaxed">
              <strong>Format tip:</strong> Follow the 9-section DESIGN.md schema — Visual Theme, Color Palette, Typography, Component Stylings, Layout, Depth, Do's/Don'ts, Responsive, Agent Prompt Guide. The more specific your color tokens and typography rules, the better the output.
            </p>
          </div>

          {/* Error */}
          {error && (
            <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2">
              <AlertCircle className="h-3.5 w-3.5 flex-shrink-0 text-red-500" />
              <p className="text-[12px] text-red-700">{error}</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <footer className="flex flex-shrink-0 items-center justify-end gap-2 border-t border-gray-100 px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-gray-200 px-4 py-2 text-[12px] font-medium text-gray-600 hover:bg-gray-50 transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            className="flex items-center gap-1.5 rounded-lg bg-[#1B2A4A] px-4 py-2 text-[12px] font-semibold text-white hover:bg-[#243660] transition-colors"
          >
            <Check className="h-3 w-3" strokeWidth={3} />
            {existing ? "Save changes" : "Add design system"}
          </button>
        </footer>
      </div>
    </div>
  );
}
