#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

function usage() {
  console.log(`Usage:
  node scripts/init-clone.mjs <site-name-or-slug> [--url <url>] [--mode <mode>] [--level <L1-L6>]

Creates:
  ./website-clones/<normalized-slug>-clone/
  ./website-clones/<normalized-slug>-clone/NOTES.md
  ./website-clones/<normalized-slug>-clone/RECON/screenshots/

Set WEB_CLONE_ROOT=/absolute/path to write projects somewhere else.
Non-ASCII names fall back to the --url hostname, then a stable short hash.
`);
}

function parseArgs(argv) {
  const out = { slug: null, url: "", mode: "", level: "" };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--help" || arg === "-h") out.help = true;
    else if (arg === "--url") out.url = argv[++i] || "";
    else if (arg === "--mode") out.mode = argv[++i] || "";
    else if (arg === "--level") out.level = argv[++i] || "";
    else if (!out.slug) out.slug = arg;
    else throw new Error(`Unexpected argument: ${arg}`);
  }
  return out;
}

function cleanSlug(input) {
  return input
    .trim()
    .toLowerCase()
    .replace(/https?:\/\//g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function slugFromUrl(url) {
  if (!url) return "";
  try {
    const parsed = new URL(url);
    return cleanSlug(parsed.hostname.replace(/^www\./i, ""));
  } catch {
    return "";
  }
}

function fallbackSlug(input, url) {
  const direct = cleanSlug(input);
  if (direct) return direct;

  const fromUrl = slugFromUrl(url);
  if (fromUrl) return fromUrl;

  const hash = crypto.createHash("sha1").update(`${input}\n${url}`).digest("hex").slice(0, 8);
  return `site-${hash}`;
}

function shellQuote(value) {
  return `'${value.replace(/'/g, "'\\''")}'`;
}

function notesTemplate({ name, url, mode, level, projectPath }) {
  return `# ${name} · Clone Notes

## Source Info
- Original site URL: ${url}
- Source repo:
- Original author:
- License:
- Attribution requirements:

## Tech Stack
- Framework / key libraries / Node version:

## Pre-clone Assessment
- Complexity level: ${level}
- Recommended mode: ${mode}
- Parts that can be high-fidelity:
- Parts that need approximation or substitution:
- Parts not being cloned:
- Main risks:

## Running It
\`\`\`bash
cd ${shellQuote(projectPath)}
python3 -m http.server 8123
\`\`\`

## What Changed (vs. Original)
-

## Original vs. Clone
| Module | Original behavior | Clone implementation | Differences / tradeoffs | Evidence |
|---|---|---|---|---|
| Above the fold |  |  |  |  |
| Navigation |  |  |  |  |
| Core animations |  |  |  |  |
| Content sections |  |  |  |  |
| Mobile |  |  |  |  |

## Clone Score
- Source evidence: /5
- Structural fidelity: /5
- Visual fidelity: /5
- Animation/interaction: /5
- Responsiveness: /5
- Functional completeness: /5
- Content replacement: /5
- Legal/deployment risk: /5
- Overall:

## Replacement Map (what to swap, where)
- Text -> file line
- Images/media -> directory
- Colors -> CSS variables / theme
- 3D models / fonts ->

## Verification
- [ ] Runs locally, 0 console errors
- [ ] Screenshots compared against original site (RECON/screenshots/)
- Items that couldn't be verified (record honestly, don't fabricate):
`;
}

try {
  const args = parseArgs(process.argv.slice(2));
  if (args.help || !args.slug) {
    usage();
    process.exit(args.help ? 0 : 1);
  }

  const slug = fallbackSlug(args.slug, args.url);
  const name = slug.endsWith("-clone") ? slug : `${slug}-clone`;
  const root = process.env.WEB_CLONE_ROOT
    ? path.resolve(process.env.WEB_CLONE_ROOT)
    : path.join(process.cwd(), "website-clones");
  const project = path.join(root, name);

  if (fs.existsSync(project)) {
    throw new Error(`Project already exists: ${project}`);
  }

  fs.mkdirSync(path.join(project, "RECON", "screenshots"), { recursive: true });
  fs.writeFileSync(
    path.join(project, "NOTES.md"),
    notesTemplate({
      name,
      url: args.url,
      mode: args.mode,
      level: args.level,
      projectPath: project,
    })
  );
  fs.writeFileSync(path.join(project, ".gitignore"), "node_modules/\n.DS_Store\n");

  console.log(project);
} catch (error) {
  console.error(`init-clone failed: ${error.message}`);
  process.exit(1);
}
