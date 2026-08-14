"use client";

/**
 * PreviewChrome — the mock's browser-chrome frame around the deliverable preview
 * (Phase 39, RUNUI-06/07). Reproduces `Hexaware Run.dc.html:184-206` (settled) and
 * `Hexaware Run - Live.dc.html:177-197` (streaming build):
 *   • a card with a top bar — three traffic-light dots, a centered URL/file bar
 *     (lock icon + the REAL deliverable filename + a version chip), and a right
 *     "100%" zoom label + open-in-new affordance;
 *   • a "Renders as" segmented deliverable-type switch row beneath it (settled);
 *   • a scrollable content surface into which the CHILDREN — the REUSED deliverable
 *     renderer output — are slotted.
 *
 * SCOPE FENCES:
 *   • ND-G: this is a PASSIVE FRAME. It WRAPS the existing renderers (children)
 *     UNCHANGED — it renders no deliverable content itself and injects no raw HTML
 *     (the sandboxed-iframe contract stays with the renderers). The filename is
 *     rendered as escaped text (T-39-06-02).
 *   • ND-D: the caller feeds the REAL live filename + version + the genuinely
 *     available typed renderers (`rendererOptions`) — never the mock's fixed 5-way
 *     list or its hardcoded "index.html".
 *   • ND-F: the mock's streaming "drop a screenshot" placeholder is NOT reproduced;
 *     the streaming surface shows the live renderer output (or a calm building
 *     state) under an indeterminate progress bar.
 */
import { type ReactNode } from "react";
import { ExternalLink, Lock } from "lucide-react";

export interface RendererOption {
  value: string;
  label: string;
}

// ─── RendersAsSwitch — the mock's "Renders as" segmented deliverable-type row ──
// ONE switch implementation with TWO mount points (INV-12 — not cloned markup):
//   • inside PreviewChrome (beneath the browser top bar) for PLAIN deliverables;
//   • standalone above a SELF-CHROMED renderer (prototype / app_builder) that
//     brings its own frame (ND-V, Option B ruling 2026-07-11).
// The pills reuse the caller's existing rendererOptions/rendererOverride dispatch.
export function RendersAsSwitch({
  rendererOptions,
  rendererValue = "auto",
  onRendererChange,
  className,
}: {
  rendererOptions: RendererOption[];
  rendererValue?: string;
  onRendererChange?: (value: string | null) => void;
  className?: string;
}) {
  return (
    <div
      data-testid="renders-as-switch"
      className={`flex flex-none items-center gap-[6px] border-b border-line-faint-row bg-surface-warm px-[14px] py-[9px] ${
        className ?? ""
      }`}
    >
      <span className="mr-[3px] font-sans text-[9px] font-semibold uppercase leading-none tracking-[0.09em] text-ink-300">
        Renders as
      </span>
      {rendererOptions.map((o) => {
        const active = (rendererValue ?? "auto") === o.value;
        return (
          <button
            key={o.value}
            type="button"
            data-testid="renderer-pill"
            aria-pressed={active}
            onClick={() => onRendererChange?.(o.value === "auto" ? null : o.value)}
            className={`rounded-[7px] px-[10px] py-[5px] font-sans text-[11px] font-semibold leading-none transition-colors ${
              active
                ? "bg-brand text-white"
                : "border border-line-control bg-surface-white text-ink-500 hover:border-line-faint"
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

export interface PreviewChromeProps {
  /** The REAL deliverable filename shown in the URL bar (ND-D live, never fixed). */
  filename: string;
  /** The live version label (e.g. "v1") for the URL-bar chip. */
  versionLabel?: string;
  /** Streaming build variant: "building …" URL + top progress bar, no switch row. */
  streaming?: boolean;
  /** The genuinely-available typed renderers for THIS deliverable (Auto + typed).
   *  The switch row renders only when there is more than one (ND-D). */
  rendererOptions?: RendererOption[];
  /** The active renderer value ("auto" or a renderType/mimetype token). */
  rendererValue?: string;
  /** Called with the picked token, or null when "Auto" is chosen (clears override). */
  onRendererChange?: (value: string | null) => void;
  /** Optional open-in-new affordance (client-only). Decorative when omitted. */
  onOpen?: () => void;
  /** The REUSED deliverable renderer output — slotted unchanged (ND-G). */
  children?: ReactNode;
}

// Component-scoped sweep keyframes (globals.css is out of this plan's scope).
// Unique name to avoid colliding with any global `bar` animation.
const BAR_KEYFRAMES =
  "@keyframes preview-chrome-bar{0%{transform:translateX(-100%)}100%{transform:translateX(320%)}}";

export function PreviewChrome({
  filename,
  versionLabel,
  streaming = false,
  rendererOptions,
  rendererValue = "auto",
  onRendererChange,
  onOpen,
  children,
}: PreviewChromeProps) {
  const showSwitch = !streaming && !!rendererOptions && rendererOptions.length > 1;

  return (
    <div className="h-full px-6 py-5">
      <div
        data-testid="preview-chrome"
        data-streaming={streaming || undefined}
        className="flex h-full flex-col overflow-hidden rounded-[14px] border border-line-divider bg-surface-white"
      >
        {/* Browser top bar — traffic-light dots · URL/file bar · zoom + open. */}
        <div className="flex h-[46px] flex-none items-center gap-[14px] border-b border-line-faint-row bg-surface-warm px-[14px]">
          <div className="flex gap-[7px]">
            <span className="h-[11px] w-[11px] rounded-full bg-line-control" />
            <span className="h-[11px] w-[11px] rounded-full bg-line-control" />
            <span className="h-[11px] w-[11px] rounded-full bg-line-control" />
          </div>

          <div className="flex flex-1 justify-center">
            <div className="flex h-[29px] w-full max-w-[520px] items-center gap-2 rounded-[8px] border border-line-control bg-surface-paper px-3">
              {!streaming && (
                <Lock aria-hidden className="h-3 w-3 flex-none text-ink-200" strokeWidth={1.7} />
              )}
              <span
                data-testid="preview-url"
                className={`flex-1 truncate font-serif text-[12px] leading-none ${
                  streaming ? "text-ink-300" : "text-ink-500"
                }`}
              >
                {streaming ? `building ${filename}…` : filename}
              </span>
              {versionLabel && (
                <span className="flex-none rounded-[5px] bg-brand-fill px-[6px] py-[3px] font-sans text-[10px] font-medium leading-none text-brand">
                  {versionLabel}
                </span>
              )}
            </div>
          </div>

          {streaming ? (
            <div className="w-9 flex-none" />
          ) : (
            <div className="flex items-center gap-2 text-ink-200">
              <span className="tabular-nums font-serif text-[12px] leading-none text-ink-300">100%</span>
              {onOpen ? (
                <button
                  type="button"
                  onClick={onOpen}
                  aria-label="Open the deliverable in a new tab"
                  className="inline-flex text-ink-200 transition-colors hover:text-ink-500"
                >
                  <ExternalLink aria-hidden className="h-4 w-4" strokeWidth={1.7} />
                </button>
              ) : (
                <ExternalLink aria-hidden className="h-4 w-4" strokeWidth={1.7} />
              )}
            </div>
          )}
        </div>

        {/* "Renders as" segmented deliverable-type switch (settled only). The
            options are the genuinely-available typed renderers for THIS deliverable
            (ND-D) — reskinned from the existing renderer switcher, same dispatch.
            Extracted to RendersAsSwitch so a self-chromed renderer can mount the
            SAME strip standalone above its own frame (ND-V). */}
        {showSwitch && (
          <RendersAsSwitch
            rendererOptions={rendererOptions!}
            rendererValue={rendererValue}
            onRendererChange={onRendererChange}
          />
        )}

        {/* Content surface — the reused renderer floats on the mock's #EEECE5 bg.
            Streaming adds the indeterminate progress bar at the top (ND-F: no
            screenshot placeholder — the live renderer output or a calm building
            state fills the surface). */}
        <div className="relative min-h-0 flex-1 overflow-auto bg-surface-warm p-[22px]">
          {streaming && (
            <>
              <style>{BAR_KEYFRAMES}</style>
              <div
                data-testid="preview-progress"
                className="absolute inset-x-0 top-0 z-10 h-[3px] overflow-hidden bg-brand-border"
              >
                <div
                  className="h-full w-[30%] bg-brand"
                  style={{ animation: "preview-chrome-bar 1.6s ease-in-out infinite" }}
                />
              </div>
            </>
          )}
          {children}
        </div>
      </div>
    </div>
  );
}

export default PreviewChrome;
