"use client";

/**
 * The on/off switch of the Canvas config rail (Tool grants, Tool packs and the
 * Connected Apps list). One implementation so the rail's switches look and
 * behave the same; `label` is the accessible name.
 */
export function Toggle({
  on,
  amber = false,
  label,
  disabled = false,
  onToggle,
}: {
  on: boolean;
  amber?: boolean;
  label: string;
  disabled?: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      disabled={disabled}
      onClick={onToggle}
      className={`relative h-5 w-[34px] flex-none rounded-full transition-colors disabled:opacity-40 ${
        on ? (amber ? "bg-status-amber" : "bg-brand") : "bg-line-faint"
      }`}
    >
      <span
        className={`absolute top-0.5 h-4 w-4 rounded-full bg-surface-white shadow-sm transition-all ${
          on ? "left-[16px]" : "left-0.5"
        }`}
      />
    </button>
  );
}
