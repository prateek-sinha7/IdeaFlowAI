#!/usr/bin/env node
/**
 * One-shot generator: reads /skills/{superpowers,ecc}/*\/SKILL.md and emits a new
 * frontend/src/data/skills.ts with all entries. Preserves curated metadata
 * (category, compatible_agents, tags) from the existing skills.ts by matching
 * on the human-readable display name.
 */

const fs = require("fs");
const path = require("path");

const ROOT = "/Users/1000060523/Documents/Work/UKI/Flowin/flowin";
const SKILLS_DIR = path.join(ROOT, "skills");
const SKILLS_TS = path.join(ROOT, "frontend/src/data/skills.ts");

// ──────────────────────────────────────────────────────────────────────────
// 1. Parse existing skills.ts to capture curated metadata
// ──────────────────────────────────────────────────────────────────────────
const existing = fs.readFileSync(SKILLS_TS, "utf8");

// Match each object literal inside SKILLS = [...] capturing id and the curated fields.
const objectRegex =
  /\{\s*id:\s*"([^"]+)",\s*name:\s*"([^"]+)",[\s\S]*?source:\s*"([^"]+)",[\s\S]*?category:\s*"([^"]+)",[\s\S]*?compatible_agents:\s*\[([^\]]*)\],\s*tags:\s*\[([^\]]*)\],/g;

// Map old curated id → new generated id (so we can keep curated metadata across the rename).
const OLD_TO_NEW_ID = {
  // Superpowers
  "sp-brainstorming": "superpowers-brainstorming",
  "sp-tdd": "superpowers-test-driven-development",
  "sp-writing-plans": "superpowers-writing-plans",
  "sp-subagent-driven-dev": "superpowers-subagent-driven-development",
  "sp-systematic-debugging": "superpowers-systematic-debugging",
  "sp-code-review": "superpowers-requesting-code-review",
  "sp-finishing-branch": "superpowers-finishing-a-development-branch",
  // ECC — old ids drop the `-workflow`/`-patterns` suffix on some, but the
  // folder-name side preserved them. Verified all targets exist.
  "ecc-tdd-workflow": "ecc-tdd-workflow",
  "ecc-security-review": "ecc-security-review",
  "ecc-backend-patterns": "ecc-backend-patterns",
  "ecc-frontend-patterns": "ecc-frontend-patterns",
  "ecc-api-design": "ecc-api-design",
  "ecc-deployment-patterns": "ecc-deployment-patterns",
  "ecc-e2e-testing": "ecc-e2e-testing",
  "ecc-search-first": "ecc-search-first",
  "ecc-springboot-patterns": "ecc-springboot-patterns",
  "ecc-continuous-learning": "ecc-continuous-learning",
};

const curatedByNewId = new Map();
let m;
while ((m = objectRegex.exec(existing)) !== null) {
  const [, oldId, , source, category, agentsRaw, tagsRaw] = m;
  if (source === "gsd") continue; // discarding GSD curation per user direction
  const newId = OLD_TO_NEW_ID[oldId];
  if (!newId) {
    console.warn(`[curated] no mapping for ${oldId} — skipping`);
    continue;
  }
  const parseList = (s) =>
    s
      .split(",")
      .map((x) => x.trim().replace(/^"|"$/g, ""))
      .filter(Boolean);
  curatedByNewId.set(newId, {
    category,
    compatible_agents: parseList(agentsRaw),
    tags: parseList(tagsRaw),
  });
}
console.log(`[curated] parsed ${curatedByNewId.size} non-GSD curated entries`);

// ──────────────────────────────────────────────────────────────────────────
// 2. Read each SKILL.md, parse frontmatter, derive display name from H1
// ──────────────────────────────────────────────────────────────────────────
function parseSkill(filepath) {
  const raw = fs.readFileSync(filepath, "utf8");
  const fmMatch = raw.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$/);
  if (!fmMatch) return null;
  const [, fmRaw, body] = fmMatch;
  const fm = {};
  for (const line of fmRaw.split(/\r?\n/)) {
    const kv = line.match(/^([A-Za-z_]+):\s*(.*)$/);
    if (!kv) continue;
    fm[kv[1]] = kv[2].trim().replace(/^["']|["']$/g, "");
  }
  // First H1 of body, if any
  const h1 = body.match(/^#\s+(.+)$/m);
  return {
    slug: fm.name || path.basename(path.dirname(filepath)),
    description: fm.description || "",
    h1: h1 ? h1[1].trim() : null,
    body: body.replace(/^\s+/, ""), // trim leading whitespace only
  };
}

function titleCase(slug) {
  return slug
    .split("-")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function inferCategory(name, body) {
  const text = (name + " " + body.slice(0, 800)).toLowerCase();
  if (/\btest|tdd\b|\bqa\b|red.{0,5}green|coverage|jest|vitest|playwright|cypress/.test(text))
    return "testing";
  if (/\bdebug|stack trace|breakpoint|root cause|reproduce/.test(text))
    return "debugging";
  if (/\bsecurity|vulnerab|owasp|cve|csrf|xss|sql.{0,5}inject|authentication|authoriz|secrets?/.test(text))
    return "security";
  if (/\bplan(ning)?|spec(s|ification)?|brainstorm|requirement|design|roadmap|epic/.test(text))
    return "planning";
  if (/\breview|collab|pair[ -]?program|feedback/.test(text))
    return "collaboration";
  if (/\bskill[s]? writing|meta|introspection|self[ -]?review|continuous learning/.test(text))
    return "meta";
  return "workflow";
}

function inferTags(slug) {
  return slug
    .split("-")
    .filter((w) => w.length > 2)
    .slice(0, 5);
}

// ──────────────────────────────────────────────────────────────────────────
// 3. Build entries
// ──────────────────────────────────────────────────────────────────────────
const entries = [];
let preservedCount = 0;

for (const source of ["superpowers", "ecc"]) {
  const sourceDir = path.join(SKILLS_DIR, source);
  const folders = fs
    .readdirSync(sourceDir)
    .filter((f) => fs.statSync(path.join(sourceDir, f)).isDirectory())
    .sort();

  for (const folder of folders) {
    const skillMd = path.join(sourceDir, folder, "SKILL.md");
    if (!fs.existsSync(skillMd)) continue;
    const parsed = parseSkill(skillMd);
    if (!parsed) continue;

    const displayName = parsed.h1 || titleCase(parsed.slug);
    const id = `${source}-${folder}`;
    const sourceLabel = source === "superpowers" ? "Superpowers" : "ECC";

    // Preserve curated metadata via explicit id mapping
    const curated = curatedByNewId.get(id);
    if (curated) preservedCount += 1;

    entries.push({
      id,
      name: displayName,
      description: parsed.description,
      source,
      sourceLabel,
      category: curated?.category || inferCategory(displayName, parsed.body),
      content: parsed.body,
      compatible_agents: curated?.compatible_agents || [],
      tags: curated?.tags || inferTags(folder),
    });
  }
}

console.log(
  `[entries] built ${entries.length} entries (${preservedCount} matched curated metadata)`,
);
const bySource = entries.reduce((acc, e) => {
  acc[e.source] = (acc[e.source] || 0) + 1;
  return acc;
}, {});
console.log("[entries] by source:", bySource);

// ──────────────────────────────────────────────────────────────────────────
// 4. Emit TypeScript
// ──────────────────────────────────────────────────────────────────────────
function tsQuote(s) {
  return JSON.stringify(s);
}
function tsTemplate(s) {
  // Template literal — escape backticks, ${, and backslashes
  return (
    "`" +
    s.replace(/\\/g, "\\\\").replace(/`/g, "\\`").replace(/\$\{/g, "\\${") +
    "`"
  );
}
function tsList(arr) {
  return "[" + arr.map((x) => JSON.stringify(x)).join(", ") + "]";
}

const lines = [];
lines.push(`export interface SkillDef {
  id: string;
  name: string;
  description: string;
  source: "ecc" | "superpowers";
  sourceLabel: string;
  category: "testing" | "debugging" | "planning" | "collaboration" | "security" | "workflow" | "meta";
  content: string;
  compatible_agents: string[];
  tags: string[];
}
`);

lines.push("export const SKILLS: SkillDef[] = [");

let currentSection = null;
for (const e of entries) {
  if (e.source !== currentSection) {
    currentSection = e.source;
    const header =
      e.source === "superpowers"
        ? "  // ── SUPERPOWERS ──────────────────────────────────────────────────────────"
        : "  // ── EVERYTHING CLAUDE CODE (ECC) ─────────────────────────────────────────";
    lines.push(header);
  }
  lines.push("  {");
  lines.push(`    id: ${tsQuote(e.id)},`);
  lines.push(`    name: ${tsQuote(e.name)},`);
  lines.push(`    description: ${tsQuote(e.description)},`);
  lines.push(`    source: ${tsQuote(e.source)},`);
  lines.push(`    sourceLabel: ${tsQuote(e.sourceLabel)},`);
  lines.push(`    category: ${tsQuote(e.category)},`);
  lines.push(`    content: ${tsTemplate(e.content)},`);
  lines.push(`    compatible_agents: ${tsList(e.compatible_agents)},`);
  lines.push(`    tags: ${tsList(e.tags)},`);
  lines.push("  },");
}
lines.push("];");
lines.push("");

lines.push(`export const SKILL_CATEGORIES = [
  { id: "all", label: "All" },
  { id: "planning", label: "Planning" },
  { id: "testing", label: "Testing" },
  { id: "workflow", label: "Workflow" },
  { id: "security", label: "Security" },
  { id: "debugging", label: "Debugging" },
  { id: "collaboration", label: "Collaboration" },
  { id: "meta", label: "Meta" },
] as const;
`);

lines.push(`export const SKILL_SOURCES = [
  { id: "all", label: "All Sources" },
  { id: "ecc", label: "ECC" },
  { id: "superpowers", label: "Superpowers" },
] as const;`);

const output = lines.join("\n") + "\n";
fs.writeFileSync(SKILLS_TS, output);
console.log(`[write] ${SKILLS_TS}`);
console.log(`[write] size: ${(output.length / 1024).toFixed(1)} KB`);
