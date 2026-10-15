// Moves the `if (REOPEN_TERMINAL_STATUSES.has(fullRun.status)) { ... }` reconcile block from AFTER the reopen
// handler's `for (const frame of durableFrames)` loop to just BEFORE it (the regression the ISS-126 lock exists for).
const fs = require("fs");
const [inFile, outFile] = process.argv.slice(2);
let s = fs.readFileSync(inFile, "utf8");
const startMarker = "            if (REOPEN_TERMINAL_STATUSES.has(fullRun.status)) {\n              // BOTH containers, one vocabulary.";
const endMarker = "              runStore.update(fullRun.id, { questionnaireData: null });\n            }\n";
const a = s.indexOf(startMarker);
const e = s.indexOf(endMarker, a);
if (a < 0 || e < 0) throw new Error("reconcile block markers not found");
const block = s.slice(a, e + endMarker.length);
s = s.slice(0, a) + s.slice(e + endMarker.length);
const loopMarker = "            for (const frame of durableFrames) {\n              // These frames all belong to the run being REOPENED";
const l = s.indexOf(loopMarker);
if (l < 0) throw new Error("reopen loop marker not found");
s = s.slice(0, l) + block + s.slice(l);
fs.writeFileSync(outFile, s);
const line = (i) => s.slice(0, i).split("\n").length;
const call = s.indexOf("applyTerminalStatus(prev, fullRun.status");
const fetchAt = s.indexOf("const durableFrames = await getRunEvents(currentToken, fullRun.id);");
const reopenLoop = s.indexOf(loopMarker);
const firstLoop = s.indexOf("for (const frame of durableFrames)");
console.log(`   mutated: reconcile call line ${line(call)} | reopen fetch line ${line(fetchAt)} | reopen loop line ${line(reopenLoop)} | FIRST loop in file (other handler) line ${line(firstLoop)}`);
console.log(`   reconcile is BEFORE the reopen loop: ${call < reopenLoop}`);
