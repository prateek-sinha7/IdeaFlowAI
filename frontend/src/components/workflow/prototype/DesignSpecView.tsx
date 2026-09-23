"use client";

import { useMemo } from "react";

interface DesignSpecViewProps {
  source: string | null | undefined;
}

/**
 * Renders a DESIGN.md as a lightly syntax-coloured monospace source view.
 * Hex color tokens get an inline swatch. Bold/italic/code tokens are styled.
 * Mirrors the right-hand panel of open-design's PreviewModal.
 */
export function DesignSpecView({ source }: DesignSpecViewProps) {
  const lines = useMemo(() => (source ? source.split(/\r?\n/) : []), [source]);

  if (source === undefined || source === null) {
    return (
      <div className="flex h-full items-center justify-center text-[12px] text-ink-400">
        Loading spec…
      </div>
    );
  }

  return (
    <pre className="h-full overflow-y-auto bg-[#0f1117] p-4 text-[11.5px] leading-[1.65] font-mono">
      <code>
        {lines.map((line, idx) => (
          <span key={idx} className={`block ${lineClass(line)}`}>
            {renderInline(line)}
            {"\n"}
          </span>
        ))}
      </code>
    </pre>
  );
}

function lineClass(line: string): string {
  if (/^#{1,6}\s+/.test(line)) {
    const hashes = /^(#+)\s/.exec(line)?.[1]?.length ?? 1;
    const sizes = ["text-[15px] font-bold text-white", "text-[13px] font-bold text-white", "text-[12px] font-semibold text-gray-100", "text-[11.5px] font-semibold text-gray-200"];
    return sizes[Math.min(hashes - 1, 3)];
  }
  if (/^>\s/.test(line)) return "text-ink-400 italic border-l-2 border-gray-600 pl-3";
  if (/^[-*+]\s/.test(line.trimStart())) return "text-gray-300";
  if (/^\|.*\|\s*$/.test(line)) return "text-ink-400";
  if (/^\s*```/.test(line)) return "text-ink-500";
  if (/^\s*$/.test(line)) return "h-3";
  return "text-gray-300";
}

// Matches: **bold**, *italic*, `code`, #hexcolor
const TOKEN_RE = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|#[0-9a-fA-F]{3,8}\b)/g;

function renderInline(line: string): React.ReactNode {
  if (!line) return null;
  const out: React.ReactNode[] = [];
  let last = 0;
  let key = 0;

  for (const match of line.matchAll(TOKEN_RE)) {
    const start = match.index ?? 0;
    if (start > last) out.push(line.slice(last, start));
    const token = match[0];

    if (token.startsWith("**")) {
      out.push(
        <span key={key++} className="font-bold text-white">
          {token.slice(2, -2)}
        </span>
      );
    } else if (token.startsWith("*")) {
      out.push(
        <span key={key++} className="italic text-gray-200">
          {token.slice(1, -1)}
        </span>
      );
    } else if (token.startsWith("`")) {
      out.push(
        <span key={key++} className="rounded bg-gray-700/60 px-1 text-[10.5px] text-emerald-300 font-mono">
          {token.slice(1, -1)}
        </span>
      );
    } else if (token.startsWith("#")) {
      // Hex color — show inline swatch
      out.push(
        <span key={key++} className="inline-flex items-center gap-1">
          <span
            className="inline-block h-2.5 w-2.5 rounded-sm border border-white/10 flex-shrink-0"
            style={{ backgroundColor: token }}
            aria-hidden
          />
          <span className="text-amber-300">{token}</span>
        </span>
      );
    } else {
      out.push(token);
    }
    last = start + token.length;
  }

  if (last < line.length) out.push(line.slice(last));
  return out.length > 0 ? <>{out}</> : null;
}
