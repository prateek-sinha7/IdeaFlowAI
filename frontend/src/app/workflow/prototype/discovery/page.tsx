"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, SkipForward } from "lucide-react";
import { getToken } from "@/lib/api";
import { getPrototypeTemplate, type PrototypeTemplateDetail } from "@/lib/prototype-api";
import {
  DiscoveryForm,
  EMPTY_ANSWERS,
  type DiscoveryAnswers,
  type TemplateInput,
} from "@/components/workflow/prototype/DiscoveryForm";

/**
 * Discovery — step 3 of the unified Template -> Design System -> Discovery
 * wizard (WizardStepper, plan 37-04). This is the DiscoveryForm's navigation
 * home: the stepper supplies the step ordering, this route hosts the form.
 *
 * Pulls the previously-saved draft from sessionStorage (templateId / dsId /
 * brief — left by /workflow/prototype/templates), fetches the template
 * detail so we know its `od.inputs`, and renders the discovery form.
 *
 * Skipping is fully supported — every field on this page is optional. The
 * brief alone is enough to generate; this page exists to make output more
 * specific cheaply.
 */

const DRAFT_KEY = "prototype.draft";
const DISCOVERY_KEY = "prototype.discovery";

interface Draft {
  templateId?: string;
  designSystemId?: string;
  brief?: string;
}

export default function PrototypeDiscoveryPage() {
  const router = useRouter();

  const [authChecked, setAuthChecked] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [template, setTemplate] = useState<PrototypeTemplateDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [answers, setAnswers] = useState<DiscoveryAnswers>(EMPTY_ANSWERS);

  // Auth gate.
  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/login");
      return;
    }
    setAuthChecked(true);
  }, [router]);

  // Load draft + previous discovery answers from session storage.
  useEffect(() => {
    if (!authChecked) return;
    try {
      const rawDraft = sessionStorage.getItem(DRAFT_KEY);
      if (!rawDraft) {
        // No template was picked — bounce back to the gallery rather than
        // letting the user fill a form that goes nowhere.
        router.replace("/workflow/prototype/templates");
        return;
      }
      const parsed = JSON.parse(rawDraft) as Draft;
      if (!parsed.templateId) {
        router.replace("/workflow/prototype/templates");
        return;
      }
      setDraft(parsed);

      const rawDisc = sessionStorage.getItem(DISCOVERY_KEY);
      if (rawDisc) {
        try {
          setAnswers({ ...EMPTY_ANSWERS, ...(JSON.parse(rawDisc) as DiscoveryAnswers) });
        } catch {
          // ignore — start fresh
        }
      }
    } catch {
      router.replace("/workflow/prototype/templates");
    }
  }, [authChecked, router]);

  // Fetch template detail (gives us od.inputs).
  useEffect(() => {
    if (!draft?.templateId) return;
    const token = getToken();
    if (!token) return;
    let cancelled = false;
    getPrototypeTemplate(token, draft.templateId)
      .then((t) => {
        if (cancelled) return;
        setTemplate(t);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setLoadError(err.message || "Failed to load template");
      });
    return () => {
      cancelled = true;
    };
  }, [draft?.templateId]);

  // `inputs` in the wild is either a list of input dicts or (rarely) absent.
  // Normalise to an array so the form renderer doesn't have to guard.
  const templateInputs: TemplateInput[] = useMemo(() => {
    if (!template) return [];
    const raw = template.inputs;
    if (Array.isArray(raw)) {
      return raw as TemplateInput[];
    }
    return [];
  }, [template]);

  const goToRun = useCallback(
    (saveAnswers: DiscoveryAnswers | null) => {
      if (saveAnswers) {
        sessionStorage.setItem(DISCOVERY_KEY, JSON.stringify(saveAnswers));
      } else {
        sessionStorage.removeItem(DISCOVERY_KEY);
      }
      // Signal the dashboard to auto-trigger the od_prototype pipeline.
      sessionStorage.setItem("od_prototype.pending", "true");
      router.push("/dashboard");
    },
    [router],
  );

  if (!authChecked || !draft) {
    return (
      <div className="flex h-screen items-center justify-center bg-surface-paper">
        <div className="text-sm text-ink-500">Loading…</div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col bg-surface-paper">
      {/* Header */}
      <header className="sticky top-0 z-20 border-b border-line-divider bg-surface-paper/95 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center gap-3 px-6 py-3.5">
          <button
            type="button"
            onClick={() => router.push("/workflow/prototype/templates")}
            className="flex items-center justify-center rounded-[var(--radius-button)] p-1.5 text-ink-500 transition-colors hover:bg-surface-white hover:text-ink-900"
            aria-label="Back to template gallery"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div className="flex flex-col">
            <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-ink-400">
              Step 3 of 3
            </span>
            <h1 className="text-[15px] font-normal italic text-ink-900 font-serif">
              A few details before we generate
            </h1>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="mx-auto w-full max-w-3xl flex-1 px-6 pb-36 pt-8">
        {/* Brief recap */}
        <section className="mb-6 rounded-[var(--radius-card)] border border-line-divider bg-surface-white px-5 py-4">
          <div className="flex flex-col gap-1">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-400">
              Your brief
            </span>
            <p className="text-[13px] italic text-ink-700">
              {draft.brief || <em className="not-italic text-ink-400">(no brief)</em>}
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {template?.name && (
                <span className="rounded-full bg-surface-warm px-2 py-0.5 text-[10px] font-medium text-ink-700">
                  {template.name}
                </span>
              )}
              {draft.designSystemId && (
                <span className="rounded-full bg-surface-warm px-2 py-0.5 text-[10px] font-medium text-ink-700">
                  {draft.designSystemId}
                </span>
              )}
            </div>
          </div>
        </section>

        {loadError ? (
          <div className="rounded-[var(--radius-list-row)] border border-[var(--status-failed-border)] bg-[var(--status-failed-fill)] px-4 py-3 text-[13px] text-status-failed">
            Couldn’t load template detail: {loadError}
          </div>
        ) : !template ? (
          <DiscoverySkeleton />
        ) : (
          <DiscoveryForm
            templateInputs={templateInputs}
            answers={answers}
            onChange={setAnswers}
          />
        )}
      </main>

      {/* Footer */}
      <footer className="fixed bottom-0 left-0 right-0 z-30 border-t border-line-divider bg-surface-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 px-6 py-4">
          <button
            type="button"
            onClick={() => goToRun(null)}
            className="flex items-center gap-1.5 rounded-[var(--radius-button)] px-3 py-2 text-[12px] font-medium text-ink-500 hover:bg-surface-warm hover:text-ink-900"
          >
            <SkipForward className="h-3.5 w-3.5" />
            Skip — brief is enough
          </button>

          <button
            type="button"
            onClick={() => goToRun(answers)}
            className="flex h-[44px] items-center gap-2 rounded-[var(--radius-button)] bg-brand px-5 text-[13px] font-semibold text-white shadow-sm transition-all hover:bg-brand-pressed"
          >
            Generate prototype
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </footer>
    </div>
  );
}

function DiscoverySkeleton() {
  return (
    <div className="flex flex-col gap-8">
      {Array.from({ length: 2 }).map((_, i) => (
        <div key={i} className="rounded-[var(--radius-card)] border border-line-divider bg-surface-white p-6">
          <div className="h-3 w-32 animate-pulse rounded bg-surface-warm" />
          <div className="mt-2 h-2.5 w-3/4 animate-pulse rounded bg-surface-warm" />
          <div className="mt-5 space-y-3">
            {Array.from({ length: 3 }).map((__, j) => (
              <div key={j} className="h-9 w-full animate-pulse rounded-[var(--radius-button)] bg-surface-warm" />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
