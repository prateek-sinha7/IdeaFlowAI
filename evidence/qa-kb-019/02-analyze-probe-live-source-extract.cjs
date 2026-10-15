// QA-KB-019 analyzer probe v2 — live-source extraction of BOTH marker readers/strippers, candidate fix table.
const fs = require("fs");
const path = require("path");
const REPO = "/Users/bilala/Developer/Projects/VELOCITY-AI-worktrees/feat-user-stories-v2";
const ts = require(path.join(REPO, "frontend/node_modules/typescript"));

function extract(file, re, name) {
  const src = fs.readFileSync(path.join(REPO, file), "utf8");
  const m = src.match(re);
  if (!m) throw new Error(`${name} not found in ${file}`);
  const line = src.slice(0, m.index).split("\n").length;
  const js = ts.transpileModule(m[0], { compilerOptions: { target: "ES2020" } }).outputText;
  console.log(`# ${name}: ${file}:${line}-${line + m[0].split("\n").length - 2}`);
  return new Function(js + `; return ${name};`)();
}
const current = extract("frontend/src/components/workflow/WorkflowView.tsx", /function stripAttachmentMarker[\s\S]*?\n}\n/, "stripAttachmentMarker");
const cleanBrief = extract("frontend/src/components/savedworkflows/SavedWorkflowsPage.tsx", /function cleanBrief[\s\S]*?\n}\n/, "cleanBrief");

const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// (b) BUGS.md Notes fix, as written (non-greedy + (?=\n\n|$) terminator guard, boundary-aware exact removal)
function agreedFix(text, filename) {
  let removed = false;
  return text.replace(/(\n\n)?\[Attached: (.*?)\](?=\n\n|$)/g, (match, sep, names) => {
    if (removed) return match;
    const re = new RegExp(`(^|, )${esc(filename)}(, |$)`);
    if (!re.test(names)) return match;
    removed = true;
    const rest = names.replace(re, (_a, pre, post) => (pre && post ? ", " : ""));
    return rest ? `${sep ?? ""}[Attached: ${rest}]` : "";
  }).trim();
}

// (c) recommended: literal name, anchored on the marker START only (never tries to find the marker END).
function anchoredLiteral(text, filename) {
  const n = esc(filename);
  return text
    .replace(
      new RegExp(`(\\n\\n)?\\[Attached: ${n}\\]|(\\[Attached: [^\\n]*?), ${n}(?=, |\\])|(\\[Attached: )${n}, `),
      (_m, _sep, keepMid, keepHead) => keepMid ?? keepHead ?? "",
    )
    .trim();
}

// (d) per-file markers + plain literal replace (changes the writer's visible format)
function perFileLiteral(text, filename) {
  return text.replace(`[Attached: ${filename}]`, "").replace(/\n{3,}/g, "\n\n").trim();
}

const cases = [
  ["plain single", "idea\n\n[Attached: a.txt]", "a.txt", "idea"],
  ["name has ]", "idea\n\n[Attached: my].txt]", "my].txt", "idea"],
  ["name has ', '", "idea\n\n[Attached: file, more.txt]", "file, more.txt", "idea"],
  ["name has ', ' and ]", "idea\n\n[Attached: a, b].txt]", "a, b].txt", "idea"],
  ["2 files, remove 1st", "idea\n\n[Attached: a.txt, b.txt]", "a.txt", "idea\n\n[Attached: b.txt]"],
  ["2 files, remove 2nd", "idea\n\n[Attached: a.txt, b.txt]", "b.txt", "idea\n\n[Attached: a.txt]"],
  ["2 files, 1st has ]", "idea\n\n[Attached: my].txt, b.txt]", "my].txt", "idea\n\n[Attached: b.txt]"],
  ["2 files, 2nd has ]", "idea\n\n[Attached: b.txt, my].txt]", "my].txt", "idea\n\n[Attached: b.txt]"],
  ["2 files, 1st has ', '", "idea\n\n[Attached: a, b.txt, c.txt]", "a, b.txt", "idea\n\n[Attached: c.txt]"],
  ["2 files, 2nd has ', '", "idea\n\n[Attached: c.txt, a, b.txt]", "a, b.txt", "idea\n\n[Attached: c.txt]"],
  ["regex metachars", "idea\n\n[Attached: a(1)+$.txt]", "a(1)+$.txt", "idea"],
  ["typed text right after marker (same line)", "idea\n\n[Attached: a.txt] more words", "a.txt", "idea more words"],
  ["typed text after marker (next para)", "idea\n\n[Attached: a.txt]\n\nmore words", "a.txt", "idea\n\nmore words"],
  ["marker first, text after, name has ]", "[Attached: my].txt] more", "my].txt", "more"],
  ["2 batches, remove from 2nd", "idea\n\n[Attached: a.txt]\n\n[Attached: b.txt]", "b.txt", "idea\n\n[Attached: a.txt]"],
  ["2 batches, 2nd name has ]", "idea\n\n[Attached: a.txt]\n\n[Attached: my].txt]", "my].txt", "idea\n\n[Attached: a.txt]"],
  ["marker is whole text", "[Attached: a.txt]", "a.txt", ""],
  ["marker is whole text, name has ]", "[Attached: my].txt]", "my].txt", ""],
  // adversarial: the user's own prose mentions the same filename in a comma list BEFORE the marker
  ["prose has ', a.txt, ' before the marker", "see x, a.txt, y\n\n[Attached: a.txt]", "a.txt", "see x, a.txt, y"],
  ["same name attached twice, remove one", "idea\n\n[Attached: a.txt, a.txt]", "a.txt", "idea\n\n[Attached: a.txt]"],
  ["name is a suffix of another", "idea\n\n[Attached: aa.txt, a.txt]", "a.txt", "idea\n\n[Attached: aa.txt]"],
  ["name is a prefix of another", "idea\n\n[Attached: a.txt, a.txt.bak]", "a.txt", "idea\n\n[Attached: a.txt.bak]"],
];
const fns = { current, agreedFix, anchoredLiteral };
const norm = (s) => s.replace(/\s+/g, " ").trim();
const tally = Object.fromEntries(Object.keys(fns).map((k) => [k, 0]));
for (const [label, text, name, expected] of cases) {
  const bits = [];
  for (const [k, f] of Object.entries(fns)) {
    let out;
    try { out = f(text, name); } catch (e) { out = "THROW " + e.message; }
    const ok = norm(out) === norm(expected);
    if (ok) tally[k]++;
    bits.push(`${k}=${ok ? "PASS" : "FAIL(" + JSON.stringify(out) + ")"}`);
  }
  console.log(`- ${label}\n    ${bits.join("  ")}`);
}
console.log(`\nTALLY of ${cases.length}:`, JSON.stringify(tally));

console.log("\n# per-file-marker variant (writer would emit one marker per file) — sanity on its own cases");
for (const [t, n, e] of [
  ["idea\n\n[Attached: my].txt]", "my].txt", "idea"],
  ["idea\n\n[Attached: a.txt] [Attached: b, c.txt]", "b, c.txt", "idea\n\n[Attached: a.txt]"],
]) console.log(JSON.stringify(n), "=>", JSON.stringify(perFileLiteral(t, n)), norm(perFileLiteral(t, n)) === norm(e) ? "PASS" : "FAIL");

console.log("\n# SIBLING: cleanBrief (SavedWorkflowsPage.tsx) on markers the WorkflowView writer can emit");
for (const raw of [
  "idea\n\n[Attached: a.txt]",
  "idea\n\n[Attached: my].txt]",
  "idea\n\n[Attached: a, b].txt]",
  "idea\n\n[Attached: file, more.txt]",
  "[Attached: my].txt]",
]) console.log(JSON.stringify(raw), "=>", JSON.stringify(cleanBrief(raw)));
