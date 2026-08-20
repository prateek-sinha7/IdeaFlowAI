"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { X, RotateCcw, Check, Sun, Moon, Contrast, Coffee, Sliders, Type, Palette, Code2, ChevronDown, ChevronUp } from "lucide-react";

// ── Token definitions ─────────────────────────────────────────────────────────

export interface TokenMap {
  "--bg": string;
  "--fg": string;
  "--accent": string;
  "--accent-fg": string;
  "--surface": string;
  "--border": string;
  "--muted": string;
  "--font-sans": string;
}

export const DEFAULT_TOKENS: TokenMap = {
  "--bg": "#ffffff",
  "--fg": "#0f172a",
  "--accent": "#2563eb",
  "--accent-fg": "#ffffff",
  "--surface": "#f8fafc",
  "--border": "#e2e8f0",
  "--muted": "#64748b",
  "--font-sans": "ui-sans-serif, system-ui, sans-serif",
};

// ── Theme presets ─────────────────────────────────────────────────────────────

interface ThemePreset {
  id: string;
  label: string;
  icon: React.ReactNode;
  tokens: Partial<TokenMap>;
}

const THEME_PRESETS: ThemePreset[] = [
  {
    id: "light",
    label: "Light",
    icon: <Sun className="h-3.5 w-3.5" />,
    tokens: {
      "--bg": "#ffffff",
      "--fg": "#0f172a",
      "--accent": "#2563eb",
      "--accent-fg": "#ffffff",
      "--surface": "#f8fafc",
      "--border": "#e2e8f0",
      "--muted": "#64748b",
    },
  },
  {
    id: "dark",
    label: "Dark",
    icon: <Moon className="h-3.5 w-3.5" />,
    tokens: {
      "--bg": "#0f172a",
      "--fg": "#f1f5f9",
      "--accent": "#3b82f6",
      "--accent-fg": "#ffffff",
      "--surface": "#1e293b",
      "--border": "#334155",
      "--muted": "#94a3b8",
    },
  },
  {
    id: "sepia",
    label: "Sepia",
    icon: <Coffee className="h-3.5 w-3.5" />,
    tokens: {
      "--bg": "#fdf6e3",
      "--fg": "#3c3836",
      "--accent": "#b57614",
      "--accent-fg": "#ffffff",
      "--surface": "#f5efe0",
      "--border": "#d5c4a1",
      "--muted": "#928374",
    },
  },
  {
    id: "contrast",
    label: "Contrast",
    icon: <Contrast className="h-3.5 w-3.5" />,
    tokens: {
      "--bg": "#000000",
      "--fg": "#ffffff",
      "--accent": "#facc15",
      "--accent-fg": "#000000",
      "--surface": "#111111",
      "--border": "#555555",
      "--muted": "#aaaaaa",
    },
  },
];

// ── Font options ──────────────────────────────────────────────────────────────

export const FONT_OPTIONS: { label: string; value: string; googleFont?: string }[] = [
  { label: "System UI", value: "ui-sans-serif, system-ui, sans-serif" },
  { label: "Inter", value: "'Inter', ui-sans-serif, sans-serif", googleFont: "Inter:wght@400;500;600;700" },
  { label: "DM Sans", value: "'DM Sans', ui-sans-serif, sans-serif", googleFont: "DM+Sans:wght@400;500;600;700" },
  { label: "Roboto", value: "'Roboto', ui-sans-serif, sans-serif", googleFont: "Roboto:wght@400;500;700" },
  { label: "Nunito", value: "'Nunito', ui-sans-serif, sans-serif", googleFont: "Nunito:wght@400;600;700" },
  { label: "Georgia (Serif)", value: "Georgia, 'Times New Roman', serif" },
  { label: "Playfair Display", value: "'Playfair Display', Georgia, serif", googleFont: "Playfair+Display:wght@400;600;700" },
  { label: "JetBrains Mono", value: "'JetBrains Mono', 'Fira Code', monospace", googleFont: "JetBrains+Mono:wght@400;500;700" },
];

// ── Color token rows ──────────────────────────────────────────────────────────

const COLOR_TOKENS: { key: keyof TokenMap; label: string; hint: string }[] = [
  { key: "--bg", label: "Background", hint: "Page background" },
  { key: "--fg", label: "Text", hint: "Primary text color" },
  { key: "--accent", label: "Accent / Primary", hint: "Buttons, links, highlights" },
  { key: "--accent-fg", label: "Accent text", hint: "Text on accent backgrounds" },
  { key: "--surface", label: "Surface / Card", hint: "Cards, panels, inputs" },
  { key: "--border", label: "Border", hint: "Dividers and outlines" },
  { key: "--muted", label: "Muted text", hint: "Secondary / placeholder text" },
];

// ── Props ─────────────────────────────────────────────────────────────────────

interface TweaksPanelProps {
  tokens: TokenMap;
  editHtml: string;
  onTokenChange: (key: keyof TokenMap, value: string) => void;
  onApplyPreset: (tokens: Partial<TokenMap>) => void;
  onApplyHtml: (html: string) => void;
  onReset: () => void;
  onClose: () => void;
}

// ── Section wrapper ───────────────────────────────────────────────────────────

function Section({
  title,
  icon,
  children,
  defaultOpen = true,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b border-gray-100 last:border-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-2.5 text-left hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-center gap-2 text-[11px] font-semibold text-gray-700 uppercase tracking-wider">
          {icon}
          {title}
        </div>
        {open ? (
          <ChevronUp className="h-3.5 w-3.5 text-gray-400" />
        ) : (
          <ChevronDown className="h-3.5 w-3.5 text-gray-400" />
        )}
      </button>
      {open && <div className="px-4 pb-4">{children}</div>}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function TweaksPanel({
  tokens,
  editHtml,
  onTokenChange,
  onApplyPreset,
  onApplyHtml,
  onReset,
  onClose,
}: TweaksPanelProps) {
  const [localHtml, setLocalHtml] = useState(editHtml);
  const [htmlDirty, setHtmlDirty] = useState(false);
  const [activePreset, setActivePreset] = useState<string | null>(null);
  const [appliedHtml, setAppliedHtml] = useState(false);
  const applyTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Sync localHtml when parent content changes (new pipeline run)
  useEffect(() => {
    setLocalHtml(editHtml);
    setHtmlDirty(false);
  }, [editHtml]);

  useEffect(() => {
    return () => {
      if (applyTimeoutRef.current) clearTimeout(applyTimeoutRef.current);
    };
  }, []);

  const handlePreset = useCallback(
    (preset: ThemePreset) => {
      setActivePreset(preset.id);
      onApplyPreset(preset.tokens);
    },
    [onApplyPreset],
  );

  const handleApplyHtml = useCallback(() => {
    onApplyHtml(localHtml);
    setHtmlDirty(false);
    setAppliedHtml(true);
    if (applyTimeoutRef.current) clearTimeout(applyTimeoutRef.current);
    applyTimeoutRef.current = setTimeout(() => setAppliedHtml(false), 2000);
  }, [localHtml, onApplyHtml]);

  const handleReset = useCallback(() => {
    setActivePreset(null);
    setLocalHtml(editHtml);
    setHtmlDirty(false);
    onReset();
  }, [editHtml, onReset]);

  return (
    <div className="flex h-full flex-col bg-white border-l border-gray-200 w-[280px] flex-shrink-0 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 flex-shrink-0 bg-white">
        <div className="flex items-center gap-2">
          <Sliders className="h-4 w-4 text-[#1B2A4A]" />
          <span className="text-[13px] font-semibold text-gray-900">Tweaks</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={handleReset}
            title="Reset all tweaks"
            className="flex h-6 w-6 items-center justify-center rounded text-gray-400 hover:bg-gray-100 hover:text-gray-700 transition-colors"
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={onClose}
            title="Close tweaks"
            className="flex h-6 w-6 items-center justify-center rounded text-gray-400 hover:bg-gray-100 hover:text-gray-700 transition-colors"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Scrollable body */}
      <div className="flex-1 overflow-y-auto">

        {/* ── Theme presets ─────────────────────────────────────────── */}
        <Section title="Theme" icon={<Sun className="h-3.5 w-3.5" />}>
          <div className="grid grid-cols-2 gap-1.5">
            {THEME_PRESETS.map((preset) => (
              <button
                key={preset.id}
                type="button"
                onClick={() => handlePreset(preset)}
                className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-[11px] font-medium transition-all ${
                  activePreset === preset.id
                    ? "border-[#1B2A4A] bg-[#1B2A4A]/5 text-[#1B2A4A]"
                    : "border-gray-200 text-gray-600 hover:border-gray-300 hover:bg-gray-50"
                }`}
              >
                {preset.icon}
                {preset.label}
              </button>
            ))}
          </div>
        </Section>

        {/* ── Colors ────────────────────────────────────────────────── */}
        <Section title="Colors" icon={<Palette className="h-3.5 w-3.5" />}>
          <div className="space-y-2.5">
            {COLOR_TOKENS.map(({ key, label, hint }) => (
              <ColorRow
                key={key}
                label={label}
                hint={hint}
                value={tokens[key]}
                onChange={(v) => {
                  setActivePreset(null);
                  onTokenChange(key, v);
                }}
              />
            ))}
          </div>
        </Section>

        {/* ── Typography ────────────────────────────────────────────── */}
        <Section title="Typography" icon={<Type className="h-3.5 w-3.5" />}>
          <div className="space-y-2">
            <label className="block text-[10px] font-medium text-gray-500 uppercase tracking-wider mb-1">
              Font family
            </label>
            <div className="space-y-1">
              {FONT_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => onTokenChange("--font-sans", opt.value)}
                  className={`w-full flex items-center justify-between rounded-lg border px-3 py-2 text-left transition-all ${
                    tokens["--font-sans"] === opt.value
                      ? "border-[#1B2A4A] bg-[#1B2A4A]/5 text-[#1B2A4A]"
                      : "border-gray-200 text-gray-600 hover:border-gray-300 hover:bg-gray-50"
                  }`}
                >
                  <span
                    className="text-[12px]"
                    style={{ fontFamily: opt.value }}
                  >
                    {opt.label}
                  </span>
                  {tokens["--font-sans"] === opt.value && (
                    <Check className="h-3 w-3 flex-shrink-0" />
                  )}
                </button>
              ))}
            </div>
          </div>
        </Section>

        {/* ── Edit HTML ─────────────────────────────────────────────── */}
        <Section title="Edit HTML" icon={<Code2 className="h-3.5 w-3.5" />} defaultOpen={false}>
          <div className="space-y-2">
            <p className="text-[10px] text-gray-400 leading-relaxed">
              Edit the HTML directly. Click &quot;Apply&quot; to reload the preview with your changes.
              Token tweaks will be baked in automatically.
            </p>
            <textarea
              value={localHtml}
              onChange={(e) => {
                setLocalHtml(e.target.value);
                setHtmlDirty(true);
              }}
              spellCheck={false}
              className="w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2.5 text-[10px] font-mono text-gray-800 focus:border-gray-400 focus:bg-white focus:outline-none transition-colors resize-none leading-relaxed"
              style={{
                fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                minHeight: "200px",
                maxHeight: "320px",
              }}
            />
            <button
              type="button"
              onClick={handleApplyHtml}
              disabled={!htmlDirty && !appliedHtml}
              className={`w-full flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-[11px] font-semibold transition-all ${
                appliedHtml
                  ? "bg-emerald-500 text-white"
                  : htmlDirty
                  ? "bg-[#1B2A4A] text-white hover:bg-[#0F1B33]"
                  : "bg-gray-100 text-gray-400 cursor-not-allowed"
              }`}
            >
              {appliedHtml ? (
                <><Check className="h-3.5 w-3.5" /> Applied</>
              ) : (
                "Apply changes"
              )}
            </button>
          </div>
        </Section>

      </div>
    </div>
  );
}

// ── Color row ─────────────────────────────────────────────────────────────────

function ColorRow({
  label,
  hint,
  value,
  onChange,
}: {
  label: string;
  hint: string;
  value: string;
  onChange: (v: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  // Normalise value to a hex string for the color input
  // (CSS values like "ui-sans-serif..." are not colors — skip)
  const isColor = /^#[0-9a-fA-F]{3,8}$/.test(value.trim());

  return (
    <div className="flex items-center justify-between gap-2">
      <div className="min-w-0">
        <p className="text-[11px] font-medium text-gray-700 truncate">{label}</p>
        <p className="text-[9px] text-gray-400 truncate">{hint}</p>
      </div>
      <div className="flex items-center gap-1.5 flex-shrink-0">
        {/* Color swatch — clicking opens the hidden color input */}
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          title={`Change ${label}`}
          className="h-6 w-6 rounded border border-gray-300 shadow-sm transition-transform hover:scale-110 flex-shrink-0 overflow-hidden"
          style={{ background: isColor ? value : "#cccccc" }}
        />
        {/* Hex value display */}
        <input
          type="text"
          value={isColor ? value : "—"}
          readOnly={!isColor}
          onChange={(e) => {
            const v = e.target.value;
            if (/^#[0-9a-fA-F]{0,8}$/.test(v)) onChange(v);
          }}
          className="w-[68px] rounded border border-gray-200 bg-gray-50 px-1.5 py-0.5 text-[10px] font-mono text-gray-700 focus:border-gray-400 focus:bg-white focus:outline-none"
        />
        {/* Hidden native color picker */}
        <input
          ref={inputRef}
          type="color"
          value={isColor ? value : "#cccccc"}
          onChange={(e) => onChange(e.target.value)}
          className="sr-only"
          tabIndex={-1}
        />
      </div>
    </div>
  );
}
