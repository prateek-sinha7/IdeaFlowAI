"use client";

import { useEffect, useMemo, useState } from "react";
import { X, Check, Layout, Palette } from "lucide-react";
import { getToken } from "@/lib/api";
import {
  listPrototypeTemplates,
  listDesignSystems,
  type PrototypeTemplate,
  type DesignSystemListItem,
} from "@/lib/prototype-api";
import { listPPTTemplates, type PPTTemplate } from "@/lib/ppt-api";
import { TemplateGallery } from "@/components/workflow/prototype/TemplateGallery";
import { DesignSystemPicker } from "@/components/workflow/prototype/DesignSystemPicker";
import { PPTTemplateGallery } from "@/components/workflow/ppt/PPTTemplateGallery";
import type { CustomDesignSystem } from "@/components/workflow/prototype/CustomDesignSystemModal";
import type { CustomTemplate } from "@/components/workflow/prototype/CustomTemplateModal";
import type { DesignMode } from "@/types/index";

/**
 * DesignPickerModal — the ONE design-selection surface for a composed workflow.
 *
 * Opened from both the Canvas Brief node and the Simple view's Design card, so
 * the two surfaces edit the SAME selection rather than each growing their own
 * picker.
 *
 * The two tab bodies are the SHIPPED wizard surfaces, used unmodified —
 * `TemplateGallery` / `PPTTemplateGallery` / `DesignSystemPicker`. They already
 * carry the thumbnails, search, category filters, custom upload, and the
 * click-through detail modal with the live example preview, so the composer
 * gets the same behaviour as the prototype wizard for free and there is no
 * second copy to keep in sync (INV-12).
 *
 * Which catalog the Template tab lists is the workflow's declared `designMode`
 * — the server filters, one family per endpoint, both reading the same
 * `design-templates/` directory:
 *   web  -> GET /api/prototype/templates   (mode == "prototype")
 *   deck -> GET /api/ppt/templates         (mode in {"deck","slides"})
 *
 * The stored mode drives THIS list only. The launch boundary derives the loader
 * profile from the chosen template's own `mode`, so a stale mode here can never
 * mis-route a run — it can only show the wrong shelf.
 */

/** The picked design. `null` on an id means "not chosen".
 *
 *  The `*Name` fields are DISPLAY ONLY — they let the Brief-node button and the
 *  Simple card label the selection without every caller refetching the catalog.
 *  The `custom*Body` fields carry a user-uploaded template / design system,
 *  which the launch payload already accepts as `custom_template_body` /
 *  `custom_ds_body`. Only ids and bodies are ever sent to the backend. */
export interface DesignSelection {
  templateId: string | null;
  designSystemId: string | null;
  templateName?: string | null;
  designSystemName?: string | null;
  customTemplateBody?: string | null;
  customDsBody?: string | null;
}

export interface DesignPickerModalProps {
  open: boolean;
  onClose: () => void;
  /** Which catalog to show — the workflow's declared design mode. */
  designMode: DesignMode;
  value: DesignSelection;
  /** A React-style UPDATER, not a plain value.
   *
   *  Load-bearing: the shipped pickers fire TWO callbacks for one click —
   *  `DesignSystemPicker.handleSelectBuiltIn` calls `onSelect(id)` AND
   *  `onSelectCustom(null)`, and `TemplateGallery` does the same pair. With a
   *  plain `(next) => void` both handlers close over the SAME stale `value`, so
   *  the second call overwrites the first and the selection silently reverts to
   *  null — the click appears to do nothing. Composing off `prev` makes the two
   *  updates stack instead of racing. */
  onChange: (update: (prev: DesignSelection) => DesignSelection) => void;
}

export function DesignPickerModal({
  open,
  onClose,
  designMode,
  value,
  onChange,
}: DesignPickerModalProps) {
  const [webTemplates, setWebTemplates] = useState<PrototypeTemplate[]>([]);
  const [deckTemplates, setDeckTemplates] = useState<PPTTemplate[]>([]);
  const [systems, setSystems] = useState<DesignSystemListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Two tabs rather than one long scroll: each gallery brings its own search
  // and category bar, so stacking them buried the second one entirely.
  const [tab, setTab] = useState<"template" | "system">("template");

  // Fetch on open, and refetch when the family changes. The design-system
  // catalog is shared by both families, so it is always loaded.
  useEffect(() => {
    if (!open) return;
    const token = getToken();
    if (!token) {
      setError("Not authenticated.");
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([
      designMode === "deck" ? listPPTTemplates(token) : listPrototypeTemplates(token),
      listDesignSystems(token),
    ])
      .then(([ts, ds]) => {
        if (cancelled) return;
        if (designMode === "deck") setDeckTemplates(ts as PPTTemplate[]);
        else setWebTemplates(ts as PrototypeTemplate[]);
        setSystems(ds);
      })
      .catch((e) => {
        if (cancelled) return;
        setError((e as Error)?.message ?? "Could not load the design catalog.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, designMode]);

  // Escape closes, matching every other dismissible surface in the composer.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const selectedDeckTemplate = useMemo(
    () => deckTemplates.find((t) => t.id === value.templateId) ?? null,
    [deckTemplates, value.templateId],
  );

  // Web: a design system is ALWAYS required — `load_prototype_context` raises
  // LookupError without one, even on the no-template blank-canvas path.
  // Deck: only when the chosen template opts in, the same `design_system.requires`
  // rule LaunchWizard applies (LaunchWizard.tsx:524), which is what drives
  // od_context's `is_design_system_required`.
  const dsRequired =
    designMode === "web" ? true : selectedDeckTemplate?.design_system?.requires === true;

  const nameForTemplate = (id: string | null) => {
    if (!id) return null;
    const pool: { id: string; name: string }[] =
      designMode === "deck" ? deckTemplates : webTemplates;
    return pool.find((t) => t.id === id)?.name ?? id;
  };

  const handleSelectTemplate = (id: string | null) => {
    onChange((prev) => ({
      ...prev,
      templateId: id,
      templateName: nameForTemplate(id),
      // Picking a catalog template retires any uploaded one.
      customTemplateBody: null,
    }));
  };

  // `null` here means "no custom template", which the gallery sends ALONGSIDE a
  // built-in `onSelect(id)`. It must therefore clear only the uploaded body and
  // leave the id alone, or it would undo the selection that just arrived.
  const handleSelectCustomTemplate = (ct: CustomTemplate | null) => {
    onChange((prev) =>
      ct
        ? { ...prev, templateId: ct.id, templateName: ct.name, customTemplateBody: ct.body }
        : { ...prev, customTemplateBody: null },
    );
  };

  const handleSelectSystem = (id: string | null) => {
    onChange((prev) => ({
      ...prev,
      designSystemId: id,
      designSystemName: id ? (systems.find((s) => s.id === id)?.name ?? id) : null,
      customDsBody: null,
    }));
  };

  // Same rule as handleSelectCustomTemplate — `null` clears the uploaded body
  // only; the built-in id arrives on its own `onSelect` call.
  const handleSelectCustomSystem = (ds: CustomDesignSystem | null) => {
    onChange((prev) =>
      ds
        ? { ...prev, designSystemId: ds.id, designSystemName: ds.name, customDsBody: ds.body }
        : { ...prev, customDsBody: null },
    );
  };

  if (!open) return null;

  const tabs = [
    {
      id: "template" as const,
      label: "Template",
      Icon: Layout,
      picked: !!value.templateId,
    },
    {
      id: "system" as const,
      label: "Design system",
      Icon: Palette,
      picked: !!value.designSystemId,
    },
  ];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 p-6"
      role="dialog"
      aria-modal="true"
      aria-label="Choose a design"
      onClick={onClose}
    >
      <div
        className="flex max-h-[88vh] w-full max-w-[1080px] flex-col overflow-hidden rounded-[16px] border border-line-border bg-surface-paper shadow-[0_18px_50px_rgba(17,17,20,0.22)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex flex-none items-center justify-between border-b border-line-border px-6 py-4">
          <div>
            <p className="font-sans text-[10px] font-semibold uppercase tracking-[0.18em] text-ink-400">
              {designMode === "deck" ? "Slide templates" : "Page templates"}
            </p>
            <h2 className="font-serif text-[16px] font-normal italic text-ink-900">
              Choose a design
            </h2>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1 rounded-[9px] border border-line-control bg-surface-card p-1">
              {tabs.map(({ id, label, Icon, picked }) => (
                <button
                  key={id}
                  type="button"
                  aria-label={label}
                  aria-pressed={tab === id}
                  onClick={() => setTab(id)}
                  className={`flex items-center gap-1.5 rounded-[7px] px-2.5 py-1.5 font-sans text-[12px] font-semibold transition-colors ${
                    tab === id
                      ? "bg-surface-white text-ink-900 shadow-[0_1px_2px_rgba(17,17,20,0.06)]"
                      : "text-ink-500 hover:text-ink-900"
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {label}
                  {picked && <Check className="h-3 w-3 text-brand" />}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="rounded-[8px] p-1.5 text-ink-500 transition-colors hover:bg-surface-white hover:text-ink-900"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          {error && (
            <p className="mb-4 rounded-[10px] border border-status-error/30 bg-status-error/5 px-3 py-2 font-sans text-[12px] text-status-error">
              {error}
            </p>
          )}
          {loading && (
            <p className="font-sans text-[12.5px] text-ink-500">Loading the catalog…</p>
          )}

          {!loading && tab === "template" && (
            <>
              <p className="mb-3 font-serif text-[11.5px] text-ink-400">
                {designMode === "web"
                  ? "Optional — leave it unpicked to build on a blank canvas."
                  : "Required for a deck."}
              </p>
              {designMode === "deck" ? (
                <PPTTemplateGallery
                  templates={deckTemplates}
                  selectedId={value.templateId}
                  onSelect={handleSelectTemplate}
                  onSelectCustomTemplate={handleSelectCustomTemplate}
                  selectedCustomTemplateId={value.customTemplateBody ? value.templateId : null}
                />
              ) : (
                <TemplateGallery
                  templates={webTemplates}
                  selectedId={value.templateId}
                  onSelect={handleSelectTemplate}
                  onSelectCustomTemplate={handleSelectCustomTemplate}
                  selectedCustomTemplateId={value.customTemplateBody ? value.templateId : null}
                />
              )}
            </>
          )}

          {!loading && tab === "system" && (
            <>
              <p className="mb-3 font-serif text-[11.5px] text-ink-400">
                {dsRequired
                  ? "Required — supplies the colour, type and spacing tokens."
                  : "Optional — this template brings its own styling."}
              </p>
              <DesignSystemPicker
                systems={systems}
                selectedId={value.designSystemId}
                onSelect={handleSelectSystem}
                onSelectCustom={handleSelectCustomSystem}
              />
            </>
          )}
        </div>

        <div className="flex flex-none items-center justify-end gap-2 border-t border-line-border px-6 py-3.5">
          <button
            type="button"
            onClick={onClose}
            className="rounded-[10px] bg-brand px-[18px] py-2.5 font-sans text-[12.5px] font-semibold text-surface-white transition-colors hover:bg-brand-pressed"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}

export default DesignPickerModal;
