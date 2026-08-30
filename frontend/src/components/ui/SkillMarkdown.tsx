"use client";

import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * SkillMarkdown — the ONE renderer every skill-body surface routes through
 * (ISS-359 / ISS-590 / ISS-591).
 *
 * A skill's `content` is its `SKILL.md` body. Two surfaces used to show it and
 * neither rendered it: `AgentSkillsPicker`'s "View details" modal dumped the
 * raw source into a `<pre>` (so `#`/`##` showed as literal characters on all
 * four of its mounts), and `LibraryPage`'s `SkillDetailModal` hand-rolled a
 * line-splitter that only understood `# `/`## ` headings and `-`/`*`/numbered
 * bullets, passing inline `**bold**`/`` `code` ``/`[links]` through verbatim.
 * Both now render the same bytes the same way, so they cannot drift again.
 *
 * SECURITY — carried verbatim from `MarkdownPreview`'s WR-03 invariant: NO
 * `rehype-raw`, and no rehypePlugins of any kind. react-markdown's DEFAULT
 * escapes embedded raw HTML to literal text rather than parsing it into live
 * DOM. Skill bodies render INLINE and unsandboxed here, so adding rehype-raw
 * would execute a skill's `<script>` in the app's own origin. Do not add it.
 */
const COMPONENTS = {
  h1: ({ children }: { children?: ReactNode }) => (
    <h1 className="mb-2 mt-4 font-sans text-[14px] font-bold text-ink-900 first:mt-0">{children}</h1>
  ),
  h2: ({ children }: { children?: ReactNode }) => (
    <h2 className="mb-2 mt-4 border-b border-line-divider pb-1 font-sans text-[13px] font-bold text-ink-900 first:mt-0">
      {children}
    </h2>
  ),
  h3: ({ children }: { children?: ReactNode }) => (
    <h3 className="mb-1 mt-3 font-sans text-[12px] font-semibold text-ink-900">{children}</h3>
  ),
  h4: ({ children }: { children?: ReactNode }) => (
    <h4 className="mb-1 mt-3 font-sans text-[12px] font-semibold text-ink-700">{children}</h4>
  ),
  p: ({ children }: { children?: ReactNode }) => (
    <p className="mb-2 text-[12px] leading-relaxed text-ink-600">{children}</p>
  ),
  ul: ({ children }: { children?: ReactNode }) => (
    <ul className="my-1 list-disc space-y-0.5 pl-4">{children}</ul>
  ),
  ol: ({ children }: { children?: ReactNode }) => (
    <ol className="my-1 list-decimal space-y-0.5 pl-4">{children}</ol>
  ),
  li: ({ children }: { children?: ReactNode }) => (
    <li className="text-[12px] leading-relaxed text-ink-700 marker:text-ink-400">{children}</li>
  ),
  // A fenced block arrives as <pre><code class="language-x">; only that case
  // gets the block treatment, inline `code` stays inline.
  code: ({ className, children }: { className?: string; children?: ReactNode }) => {
    const text = String(children ?? "");
    if (/language-/.test(className ?? "") || text.includes("\n")) {
      return (
        <code className="block overflow-x-auto whitespace-pre rounded-[8px] border border-line-divider bg-surface-warm p-3 font-mono text-[11px] leading-relaxed text-ink-700">
          {text.replace(/\n$/, "")}
        </code>
      );
    }
    return (
      <code className="rounded border border-brand-border bg-brand-fill px-1 py-0.5 font-mono text-[11px] text-brand">
        {children}
      </code>
    );
  },
  // The code branch above already renders its own block container.
  pre: ({ children }: { children?: ReactNode }) => <>{children}</>,
  strong: ({ children }: { children?: ReactNode }) => (
    <strong className="font-semibold text-ink-900">{children}</strong>
  ),
  em: ({ children }: { children?: ReactNode }) => <em className="italic text-ink-600">{children}</em>,
  a: ({ href, children }: { href?: string; children?: ReactNode }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="text-brand underline">
      {children}
    </a>
  ),
  blockquote: ({ children }: { children?: ReactNode }) => (
    <blockquote className="my-2 border-l-[3px] border-line-control pl-3 italic text-ink-500">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-3 border-line-divider" />,
  table: ({ children }: { children?: ReactNode }) => (
    <div className="my-2 overflow-x-auto rounded-[8px] border border-line-divider">
      <table className="w-full border-collapse text-[11.5px]">{children}</table>
    </div>
  ),
  thead: ({ children }: { children?: ReactNode }) => (
    <thead className="bg-surface-warm">{children}</thead>
  ),
  th: ({ children }: { children?: ReactNode }) => (
    <th className="border-b border-line-divider px-2 py-1.5 text-left font-semibold text-ink-900">
      {children}
    </th>
  ),
  td: ({ children }: { children?: ReactNode }) => (
    <td className="border-b border-line-faint-row px-2 py-1.5 text-ink-700">{children}</td>
  ),
};

export function SkillMarkdown({ content }: { content: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={COMPONENTS}>
      {content}
    </ReactMarkdown>
  );
}
