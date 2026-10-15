// Read-only probe for QA-KB-085: does the proposed end anchor ("\n  }, [") pick the handler's own closing
// at every revision, still catch a real regression, and survive the NEXT deps change? Edits nothing in the repo.
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const FILE = "frontend/src/components/layout/DashboardLayout.tsx";
const START = "const handlePreviewPanelTabSelect = useCallback(";
const OLD = "}, [contentSourceRunId]);";                       // test today
const LITERAL = "}, [contentSourceRunId, pinnedVersion]);";    // triage option 2
const STRUCT = "\n  }, [";                                     // triage option 1
const lineOf = (s, i) => s.slice(0, i).split("\n").length;
function slice(src, anchor) {
  const start = src.indexOf(START);
  const end = src.indexOf(anchor, start);
  if (start < 0 || end < 0) return { ok: false, start, end };
  const body = src.slice(start, end).split("\n").filter((l) => !l.trim().startsWith("//")).join("\n");
  return { ok: true, startLine: lineOf(src, start), endLine: lineOf(src, end), span: lineOf(src, end) - lineOf(src, start),
           push: body.includes("window.history.pushState"), router: body.includes("router.push") };
}
const fmt = (r) => r.ok ? `L${r.startLine}->L${r.endLine} (${r.span} lines) pushState=${r.push} router.push=${r.router}` : "anchor NOT FOUND";
const git = (rev) => execFileSync("git", ["show", `${rev}:${FILE}`], { encoding: "utf8", maxBuffer: 1 << 26 });

console.log("== 1. proposed anchor vs the three candidates, at each revision ==");
for (const [label, src] of [["d027f16bd^ (before pin deps)", git("d027f16bd^")], ["d027f16bd      (deps change) ", git("d027f16bd")],
                            ["8cf967b0f^     (before live) ", git("8cf967b0f^")], ["8cf967b0f      (handleOpenLiveRun)", git("8cf967b0f")],
                            ["HEAD 024c03ef8              ", git("HEAD")], ["working tree                  ", fs.readFileSync(FILE, "utf8")]]) {
  console.log(label);
  console.log("   today's anchor     :", fmt(slice(src, OLD)));
  console.log("   literal deps anchor:", fmt(slice(src, LITERAL)));
  console.log("   '\\n  }, [' anchor  :", fmt(slice(src, STRUCT)));
}

const head = fs.readFileSync(FILE, "utf8");

console.log("\n== 2. negative control: re-introduce router.push INSIDE the handler (synthetic copy, repo untouched) ==");
const bad = head.replace("    window.history.pushState(null, \"\", targetRoute);\n  }, [contentSourceRunId, pinnedVersion]);",
                         "    router.push(targetRoute);\n    window.history.pushState(null, \"\", targetRoute);\n  }, [contentSourceRunId, pinnedVersion]);");
console.log("   injected:", bad !== head);
console.log("   '\\n  }, [' anchor  :", fmt(slice(bad, STRUCT)), " <- must be router.push=true (guard still bites)");

console.log("\n== 3. drift test: the NEXT deps change (synthetic copy) ==");
const drift = head.replace("  }, [contentSourceRunId, pinnedVersion]);", "  }, [contentSourceRunId, pinnedVersion, someFutureDep]);");
console.log("   drifted :", drift !== head);
console.log("   literal deps anchor:", fmt(slice(drift, LITERAL)));
console.log("   '\\n  }, [' anchor  :", fmt(slice(drift, STRUCT)), " <- must stay L516->L552, router.push=false");
// how many handler-body lines start with exactly two spaces + "}, [" before the handler's own close?
const s = head.indexOf(START), e = head.indexOf(STRUCT, s);
const inner = head.slice(s, e).split("\n").filter((l) => /^  \}, \[/.test(l)).length;
console.log("\n== 4. lines matching /^  }, \\[/ strictly inside the handler body (must be 0):", inner);
