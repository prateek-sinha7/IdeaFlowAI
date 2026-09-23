/**
 * contentKind — what KIND of thing is this, so it can be rendered as itself.
 *
 * Everywhere the product asks a person to read something before deciding on
 * it, it had one renderer and used it regardless. That produced two failures
 * in opposite directions on the same screen:
 *
 *   Markdown shown as text  — a spec arrived at its review gate as
 *                             "### Screen 1" and "**Primary action**" in
 *                             monospace. The one place asking for a careful
 *                             read was the one place showing markup.
 *
 *   Markup shown as prose   — react-markdown DROPS raw tags and reflows the
 *                             newlines that were their only structure, so a
 *                             task list quoting a page of HTML arrived as one
 *                             run-together 300-word paragraph.
 *
 * A two-way markup/markdown guard fixed the second and not the first: it could
 * not tell a spec from the HTML the spec quoted, so every spec containing a
 * fenced <!DOCTYPE collapsed behind "An HTML artifact — open the Preview tab",
 * which had nothing on the other end.
 *
 * Three kinds, because there are three renderings:
 *
 *   code      — scrolls sideways, keeps every character, drops nothing
 *   markdown  — headings, lists, tables
 *   plain     — prose, wrapped, newlines kept
 *
 * The distinction that matters most is wrap vs. no-wrap: prose is rewrapped to
 * the column, code is not, and there is no single setting that is right for
 * both.
 *
 * SC-001: every rule keys on the TEXT'S OWN SHAPE. Nothing here may branch on
 * a workflow name, a pipeline type, or an agent id.
 */

export type ContentKind = "code" | "markdown" | "plain";

export interface ContentClass {
  kind: ContentKind;
  /** Fence- or tag-derived language for a code body: "html", "json", "ts", … */
  language?: string;
  /** The content with the product's own artifact envelope removed. */
  body: string;
}

/** The product's own wrappers. They carry markdown; they are not markup. */
const ENVELOPE = /^\s*<(spec|tasks|analysis)>([\s\S]*?)<\/\1>\s*$/i;

/** Any opening tag at the very start of the body. */
const LEADING_TAG = /^<([a-z][a-z0-9-]*)[\s>/]/i;

/** Loose tag counter — how much raw markup is in here at all. */
const ANY_TAG = /<\/?[a-z][a-z0-9-]*[\s>/]/gi;

/** A fenced block, with its info string. */
const FENCE = /```([a-z0-9+#.-]*)\n([\s\S]*?)```/gi;

/**
 * Inline code is the one signal that counts on its own.
 *
 * The two-signal rule below exists to stop an ordinary answer with one
 * hyphenated line being treated as a document. Backticks are different: they
 * never occur by accident in prose, and a lone pair is nearly always someone
 * naming a path, a flag or an endpoint. Left under the two-signal rule, a
 * clarify question reading "Should the delete endpoint stay `DELETE
 * /accounts/:id`?" rendered its backticks literally, which is the exact
 * complaint that started this work — markup shown as text.
 */
const INLINE_CODE = /`[^`\n]+`/;

/**
 * Distinct markdown signals. Two DIFFERENT kinds are required to call
 * something markdown — one hyphenated line in a plain answer is not a
 * document, and rendering it as one eats the hyphen and reflows the line.
 */
const MARKDOWN_SIGNALS: RegExp[] = [
  /^#{1,6}\s/m,                    // ATX heading
  /^\s*[-*+]\s/m,                  // unordered list
  /^\s*\d+[.)]\s/m,                // ordered list
  /^\s*\|.*\|\s*$/m,               // table row
  /```/,                           // fenced block
  /\*\*[^*\n]+\*\*|__[^_\n]+__/,   // bold
  /\[[^\]\n]+\]\([^)\n]+\)/,       // link
  /^\s*>\s/m,                      // blockquote
];

function nonWhitespaceLength(s: string): number {
  return s.replace(/\s/g, "").length;
}

/**
 * How much of the body is inside fenced code blocks, 0..1.
 *
 * A "spec" that is one ```html block with a sentence above it is code with a
 * caption, and rendering it as markdown buries the part you need to read
 * inside a collapsed dark slab.
 */
function fencedShare(body: string): { share: number; language?: string } {
  const total = nonWhitespaceLength(body);
  if (total === 0) return { share: 0 };

  let fenced = 0;
  let language: string | undefined;
  let longest = 0;

  FENCE.lastIndex = 0;
  for (let m = FENCE.exec(body); m !== null; m = FENCE.exec(body)) {
    const len = nonWhitespaceLength(m[2]);
    fenced += len;
    if (len > longest) {
      longest = len;
      language = m[1] || undefined;
    }
  }
  return { share: fenced / total, language };
}

/**
 * Close a fence the writer has not closed yet.
 *
 * A live reply is read while it is still being written, so it is routinely
 * observed mid-fence. react-markdown treats an unterminated ``` as a code block
 * that runs to the end of the document, which swallows every heading and list
 * after it — the reply appears to stop being a document halfway down. Adding
 * the closing fence renders exactly what the writer is in the middle of saying,
 * and once the real fence arrives this is a no-op.
 */
function closeDanglingFence(body: string): string {
  const fences = body.match(/```/g)?.length ?? 0;
  return fences % 2 === 0 ? body : `${body}\n\`\`\``;
}

export function classifyContent(raw: string): ContentClass {
  const text = raw ?? "";

  // 0. Unwrap the product's own envelope first, so every rule below sees what
  //    the agent actually wrote rather than the tag the kernel put around it.
  const envelope = text.match(ENVELOPE);
  const body = (envelope ? envelope[2] : text).trim();
  const head = body.slice(0, 2000);

  if (!body) return { kind: "plain", body };

  // 1. A built artifact.
  if (/^<(!DOCTYPE|html|artifact)[\s>]/i.test(head)) {
    return { kind: "code", language: "html", body };
  }

  // 2. A JSON payload. Parsed, not guessed — a sentence starting with "{" is
  //    not JSON, and a gate's choice envelope genuinely is.
  if (/^[{[]/.test(head)) {
    try {
      JSON.parse(body);
      return { kind: "code", language: "json", body };
    } catch {
      // fall through — it only looked like JSON
    }
  }

  // 3. Anything else that opens with a tag.
  const lead = head.match(LEADING_TAG);
  if (lead) return { kind: "code", language: "html", body };

  // 4. Mostly one fenced block, and that fence NAMED its language: the fence is
  //    the content, so show it as that language rather than as a document.
  //
  //    The language is not decoration here, it is the whole condition. An agent
  //    that writes a long ``` block with no info string has written a document
  //    with a quoted passage in it — a ledger, a tree, a sample — and the reply
  //    around it is markdown. Treating that as code labelled "text" turned an
  //    entire streamed reply into a monospace slab with its headings, bold and
  //    numbering shown as asterisks. Markdown renders the fence as a code block
  //    anyway, so nothing is lost by staying on the markdown side.
  const { share, language } = fencedShare(body);
  if (share >= 0.6 && language) return { kind: "code", language, body };

  // 5. Prose carrying a wall of raw markup. It opens as prose, so rules 1-3
  //    miss it, and the markdown renderer would eat every tag and reflow the
  //    rest into one paragraph. This is the rule that caught the live case.
  const tagCount = head.match(ANY_TAG)?.length ?? 0;
  if (tagCount >= 6) return { kind: "code", language: "html", body };

  // 6. Two distinct markdown signals or more — or one pair of backticks.
  if (INLINE_CODE.test(body)) return { kind: "markdown", body: closeDanglingFence(body) };
  const signals = MARKDOWN_SIGNALS.reduce((n, re) => n + (re.test(body) ? 1 : 0), 0);
  if (signals >= 2) return { kind: "markdown", body: closeDanglingFence(body) };

  // 7. A sentence is a sentence.
  return { kind: "plain", body };
}
