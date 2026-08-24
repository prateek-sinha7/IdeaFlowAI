"use client";

import type { ReactNode } from "react";

/**
 * Template-specific input as declared in `od.inputs` of the SKILL.md
 * frontmatter. The schema in the wild is loose — most templates use
 * `{id, label, description}` without an explicit type — so we treat
 * everything as a free-text field with an optional hint.
 */
export interface TemplateInput {
  id?: string;
  name?: string;
  label?: string;
  description?: string;
  required?: boolean;
  type?: string;
}

export interface DiscoveryAnswers {
  /** Free-text answers keyed by the template input's id/name. */
  template: Record<string, string>;
  /** The 5 standard style questions, always present. */
  surface: string;
  audience: string;
  tone: string;
  scale: string;
  constraints: string;
}

export const EMPTY_ANSWERS: DiscoveryAnswers = {
  template: {},
  surface: "",
  audience: "",
  tone: "",
  scale: "",
  constraints: "",
};

interface DiscoveryFormProps {
  templateInputs: TemplateInput[];
  answers: DiscoveryAnswers;
  onChange: (next: DiscoveryAnswers) => void;
}

// Standard 5 questions — the "30 seconds of radios" set that primes the
// generation regardless of template. Mirrors what OpenDesign's Discovery
// Form captures: surface / audience / tone / scale / constraints.
const SURFACES = ["Desktop web", "Mobile web", "Tablet", "Native mobile feel"];
const AUDIENCES = ["Developers", "Operators / ops", "End consumers", "Executives", "Mixed"];
const TONES = ["Professional", "Playful", "Editorial", "Brutalist", "Minimal"];
const SCALES = ["Small team (1–20)", "Mid-sized (20–500)", "Enterprise (500+)", "Not applicable"];


export function DiscoveryForm({ templateInputs, answers, onChange }: DiscoveryFormProps) {
  // The free-form template inputs in the wild use either `id` or `name` as
  // the key — fall through and accept either, then label-cased fallback.
  const inputKey = (input: TemplateInput): string =>
    input.id || input.name || (input.label ? input.label.toLowerCase().replace(/\s+/g, "_") : "");

  const updateTemplate = (key: string, value: string) => {
    onChange({ ...answers, template: { ...answers.template, [key]: value } });
  };

  return (
    <div className="flex flex-col gap-8">
      {/* Template-specific inputs (rare — ~9 of 43 templates have these) */}
      {templateInputs.length > 0 && (
        <Section
          title="Template specifics"
          hint="The template asks for these details. Anything you leave blank, the agent will infer from your brief."
        >
          <div className="flex flex-col gap-4">
            {templateInputs.map((input) => {
              const key = inputKey(input);
              if (!key) return null;
              return (
                <FieldText
                  key={key}
                  label={input.label || key}
                  description={input.description}
                  value={answers.template[key] || ""}
                  onChange={(v) => updateTemplate(key, v)}
                />
              );
            })}
          </div>
        </Section>
      )}

      <Section
        title="A few quick details"
        hint="Optional, but they steer the agent significantly. Skip any that don't apply."
      >
        <div className="flex flex-col gap-6">
          <FieldRadio
            label="Surface"
            options={SURFACES}
            value={answers.surface}
            onChange={(v) => onChange({ ...answers, surface: v })}
          />
          <FieldRadio
            label="Audience"
            options={AUDIENCES}
            value={answers.audience}
            onChange={(v) => onChange({ ...answers, audience: v })}
          />
          <FieldRadio
            label="Tone"
            options={TONES}
            value={answers.tone}
            onChange={(v) => onChange({ ...answers, tone: v })}
          />
          <FieldRadio
            label="Scale"
            options={SCALES}
            value={answers.scale}
            onChange={(v) => onChange({ ...answers, scale: v })}
          />
          <FieldText
            label="Anything to avoid?"
            description='e.g. "no animations", "no purple", "no stock photos"'
            value={answers.constraints}
            onChange={(v) => onChange({ ...answers, constraints: v })}
          />
        </div>
      </Section>
    </div>
  );
}

// ---------- Field primitives ----------

function Section({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-gray-200/70 bg-white p-6">
      <h3 className="text-[14px] font-semibold text-gray-900">{title}</h3>
      {hint && <p className="mt-1 text-[12px] text-gray-500">{hint}</p>}
      <div className="mt-5">{children}</div>
    </div>
  );
}

function FieldText({
  label,
  description,
  value,
  onChange,
}: {
  label: string;
  description?: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[12px] font-medium text-gray-800">{label}</span>
      {description && <span className="text-[11px] text-gray-500">{description}</span>}
      <input
        type="text"
        name={label.toLowerCase().replace(/\s+/g, "-")}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-0.5 rounded-lg border border-gray-200 bg-white px-3 py-2 text-[13px] text-gray-900 placeholder:text-gray-400 focus:border-gray-400 focus:outline-none"
      />
    </label>
  );
}

function FieldRadio({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: string[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-[12px] font-medium text-gray-800">{label}</legend>
      <div className="flex flex-wrap gap-2">
        {options.map((opt) => {
          const selected = value === opt;
          return (
            <button
              key={opt}
              type="button"
              // Click an already-selected option to clear it — the field is
              // optional, and there's no other obvious way to un-pick a radio
              // group on the web.
              onClick={() => onChange(selected ? "" : opt)}
              className={`rounded-full border px-3 py-1.5 text-[11px] font-medium transition-colors ${
                selected
                  ? "border-[#1B2A4A] bg-[#1B2A4A] text-white"
                  : "border-gray-200 bg-white text-gray-700 hover:border-gray-300"
              }`}
            >
              {opt}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
