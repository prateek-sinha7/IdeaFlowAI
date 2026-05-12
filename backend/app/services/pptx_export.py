"""PPTX Export Service — Executes PptxGenJS code server-side via Node.js.

Extracts the generatePresentation() function from Agent 3's output
and runs it with Node.js to produce a real .pptx file.

================================================================================
SECURITY MODEL — LAYERED DEFENCE
================================================================================
Agent 3 (an LLM) produces JavaScript that this service feeds into a Node.js
subprocess. The LLM is *not* a trusted code source — prompt injection,
hallucination, or a model swap can yield JavaScript that is hostile to the
host. We therefore treat ``js_code`` as **attacker-influenced input** and
defend in depth. No single layer is sufficient.

Layer 1 — Syntactic sanitisation (in this file).
    The regex passes near the top of ``generate_pptx_from_code`` (hex-color
    fixing, negative-offset clamping, ``.line.`` filtering, writeFile→write
    rewrites) exist for **render quality**, not security. They prevent
    PptxGenJS from crashing on commonly-mangled output. A motivated attacker
    can trivially bypass them — DO NOT TREAT THEM AS A SECURITY BOUNDARY.

Layer 2 — Process isolation (this file).
    The Node subprocess runs with:
      * A scrubbed environment (no AWS_*, DATABASE_URL, SECRET_KEY, etc.).
        An attacker who achieves RCE inside Node cannot exfiltrate secrets
        via env vars or reach Bedrock/RDS/Redis with our credentials.
      * POSIX rlimits (CPU, AS, FSIZE, NOFILE, NPROC) so a runaway script
        is killed by the kernel before it exhausts the host.
      * NODE_OPTIONS=--max-old-space-size=1024 so V8 OOMs cleanly inside
        its own heap budget (well below the RLIMIT_AS ceiling).
      * cwd=temp_dir + 0o700 mode so the script cannot read another
        request's temp dir even if scheduling overlaps.
      * A 120s wall-clock Python timeout DECOUPLED from the 60s RLIMIT_CPU
        (each protects against a different abuse mode — see the rationale
        block below).

Layer 3 — Concurrency cap (this file).
    A module-level Semaphore caps concurrent Node subprocesses at 3. This
    protects the host from a thundering herd (an attacker requesting many
    /pptx/export at once cannot fork-bomb the box via legitimate API
    calls). The acquire has a 5s timeout to keep the API responsive.

Layer 4 — Container egress (NOT in this file).
    The Linux container runs in a VPC with security-group egress rules
    restricting traffic to Bedrock/RDS/Redis only — 0.0.0.0/0 is BLOCKED.
    Even if a hostile JS callout escapes Layers 1-3 and tries to phone
    home, the SG drops the SYN. We rely on this for full network
    isolation because Node has no in-process flag to disable networking
    and ``unshare -n`` would require CAP_SYS_ADMIN we don't grant.

Layer 5 — Output validation (this file).
    The output ``.pptx`` is size-capped at 50 MB before being returned.
    Stderr is path-redacted and truncated before any error string can
    leak to the HTTP response (avoiding container-path disclosure).

================================================================================
RESOURCE-LIMIT RATIONALE
================================================================================
RLIMIT_CPU    = 60 s         Bounds *CPU time* a runaway script can
                             consume — catches infinite loops / pure-
                             compute attacks. NOT the same as wall-
                             clock: a real deck render is mostly I/O
                             (zip compression + file writes), so
                             actual CPU consumed for a 30-slide deck
                             is <5 s even when wall-clock is 60-90 s.
                             Was 30 s originally; bumped after a real
                             deck with embedded chart base64 hit it.
RLIMIT_AS     = 1536 MB      NODE_OPTIONS caps the V8 *heap* at
                             1024 MB. RLIMIT_AS is the *virtual
                             memory* ceiling which must include
                             native libs, stacks, and JIT scratch —
                             1.5 GB lets Node OOM cleanly via V8
                             rather than via SIGKILL. Was 768 MB
                             originally; bumped alongside the heap.
RLIMIT_FSIZE  = 50 MB        A 50 MB .pptx is already absurd. Caps
                             attackers writing huge files to fill disk.
RLIMIT_NOFILE = 64           Enough for pptxgenjs's internal file
                             handles + 4 inherited fds + headroom; far
                             below what a fork-bomb or fd-leak needs.
RLIMIT_NPROC  = 256          Bounds fork-bomb damage from this UID.
                             NPROC is per-uid on Linux and counts the
                             TOTAL processes the uid already has — the
                             flowin uid in production hosts uvicorn
                             workers + cwagent + the Python interpreter
                             doing this subprocess.run itself, easily
                             20+ before Node starts. Setting the cap
                             too low (originally 16) made V8 fail at
                             startup with
                               Assertion failed: uv_thread_create(...)
                             since V8 spawns ~4 worker threads at boot.
                             256 leaves headroom for Node + existing
                             processes + pptxgenjs internals while
                             still preventing a runaway fork. The
                             container's pid-namespace and the bounded
                             render semaphore (max 3 concurrent) are
                             the outer caps.
Wall-clock    = 120 s        Python-side ``subprocess.run(timeout=)``.
                             DECOUPLED from RLIMIT_CPU because the two
                             protect against different abuse:
                               * RLIMIT_CPU is CPU-time (catches
                                 compute loops, not I/O hangs).
                               * Wall-clock catches a stuck-on-syscall
                                 child that the kernel won't SIGXCPU.
                             A 30-slide deck with charts can take
                             60-90 s wall-clock on this box; 120 s
                             gives generous headroom for a legitimately
                             large deck without giving an attacker the
                             whole afternoon.
NODE heap     = 1024 MB      V8 ``--max-old-space-size``. Bigger heap
                             keeps the GC from thrashing when a deck
                             carries many base64-encoded chart /
                             image payloads. Stays below RLIMIT_AS
                             so V8 OOM fires before the kernel SIGKILL.
Semaphore     = 3            Bounds host memory at ~3 * 1536 MB =
                             4.6 GB worst case. Box is m6i.2xlarge
                             (32 GB) so this is ~14% — acceptable.
                             Tune via PPTX_MAX_CONCURRENT.
Acquire wait  = 5 s          Long enough to absorb micro-bursts; short
                             enough that the API returns a clear 503
                             rather than holding the connection open.

================================================================================
PLATFORM NOTES
================================================================================
* macOS dev path: ``RLIMIT_AS`` is not honoured the same way (Darwin
  enforces a much higher implicit cap), and ``RLIMIT_NPROC`` can be
  finicky. Each ``setrlimit`` is guarded by try/except so a Mac dev
  still gets working PPTX export. Production runs on the Linux
  container where these limits are properly enforced.
* Windows is unsupported — ``preexec_fn`` and POSIX rlimits do not
  exist there. The codebase as a whole assumes POSIX (gunicorn,
  fork-based workers).

================================================================================
FOLLOW-UPS (not in this hardening pass)
================================================================================
* The caller in ``api/workflows.py`` currently maps every exception to
  HTTP 500. The "renderer busy" RuntimeError should be a 503 Retry-After.
  Out of scope for this change — touching the caller is non-negotiable
  per the hardening brief. Tracked as a separate ticket.
"""

import logging
import os
import re
import resource
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Resolve the pptxgenjs install location.
#
# Production (Docker): pptxgenjs is pre-installed into /opt/pptx/node_modules
#   by the pptx-builder stage of backend/Dockerfile. The runtime image has no
#   access to the frontend tree, so we must point at this deterministic path.
# Local dev: developers run uvicorn outside Docker against the sibling
#   frontend/node_modules tree they already have from `npm install`.
#
# Override priority:
#   1. PPTX_NODE_MODULES_DIR env var (explicit override, wins everywhere)
#   2. /opt/pptx/node_modules if it exists (production Docker)
#   3. frontend/node_modules relative to repo root (local dev fallback)
_DEFAULT_PROD = Path("/opt/pptx/node_modules")
_DEFAULT_DEV = Path(__file__).parent.parent.parent.parent / "frontend" / "node_modules"
_node_modules_env = os.environ.get("PPTX_NODE_MODULES_DIR")
if _node_modules_env:
    NODE_MODULES_DIR = Path(_node_modules_env)
elif _DEFAULT_PROD.exists():
    NODE_MODULES_DIR = _DEFAULT_PROD
else:
    NODE_MODULES_DIR = _DEFAULT_DEV
NODE_MODULES_PPTXGENJS = NODE_MODULES_DIR / "pptxgenjs"


# ---------------------------------------------------------------------------
# Concurrency cap.
# ---------------------------------------------------------------------------
# The FastAPI route is sync (runs in the thread pool), so a threading
# Semaphore is the right primitive. An asyncio.Semaphore would not block
# the sync-threadpool worker correctly. We use a BoundedSemaphore so a
# bug in release/acquire pairing raises immediately instead of silently
# allowing extra parallelism.
_DEFAULT_MAX_CONCURRENT = 3
try:
    _MAX_CONCURRENT = max(1, int(os.environ.get("PPTX_MAX_CONCURRENT", _DEFAULT_MAX_CONCURRENT)))
except ValueError:
    _MAX_CONCURRENT = _DEFAULT_MAX_CONCURRENT
_RENDER_SEMAPHORE = threading.BoundedSemaphore(_MAX_CONCURRENT)
_ACQUIRE_TIMEOUT_S = 5.0


# ---------------------------------------------------------------------------
# Stderr scrubbing — strip container paths and skill-file references before
# any error string is allowed to reach the HTTP response.
# ---------------------------------------------------------------------------
_PATH_REDACT_PATTERNS = [
    # Absolute paths under known infra prefixes.
    re.compile(r"/app/[^\s:'\"`)]+"),
    re.compile(r"/opt/[^\s:'\"`)]+"),
    re.compile(r"/tmp/[^\s:'\"`)]+"),
    re.compile(r"/var/[^\s:'\"`)]+"),
    # SKILL.md references (e.g. "/something/SKILL.md" — paths into the
    # agent's skill files that we don't want to disclose).
    re.compile(r"/[A-Za-z0-9_-]+/SKILL\.md"),
]


def _redact_stderr(stderr: str, max_len: int = 256) -> str:
    """Scrub container paths from stderr and truncate.

    Replaces absolute paths under known infra prefixes (/app, /opt, /tmp,
    /var) and any ``/<segment>/SKILL.md`` references with ``<path>``. The
    result is truncated to ``max_len`` characters so a verbose Node trace
    cannot dominate the HTTP error body.

    This is the **last line of defence**. Earlier layers (env scrubbing,
    cwd isolation) reduce what stderr can legitimately contain in the
    first place; this regex pass deals with whatever leaks through, e.g.
    pptxgenjs printing its own install path.
    """
    if not stderr:
        return ""
    cleaned = stderr.strip()
    for pat in _PATH_REDACT_PATTERNS:
        cleaned = pat.sub("<path>", cleaned)
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 3] + "..."
    return cleaned


# ---------------------------------------------------------------------------
# preexec_fn — POSIX resource limits applied in the child process after
# fork() but before execve(). Each setrlimit is independently guarded
# because some platforms (notably macOS) silently reject specific
# resource types — we want best-effort hardening, not a hard failure
# on the dev box.
# ---------------------------------------------------------------------------
_RLIMIT_CPU_SECONDS = 60
_RLIMIT_AS_BYTES = 1536 * 1024 * 1024
_RLIMIT_FSIZE_BYTES = 50 * 1024 * 1024
_RLIMIT_NOFILE = 64
# NPROC is per-uid on Linux and counts the TOTAL processes that user
# already has (not just children of this subprocess). The flowin uid in
# the production container hosts uvicorn workers + cw-agent + the
# Python interpreter doing this `subprocess.run` itself, easily 20+
# processes before Node starts. The previous value of 16 made Node's
# V8 fail at startup with
#   Assertion failed: (0) == (uv_thread_create(t.get(), start_thread, this))
# in node_platform.cc:68 — V8 needs ~4 worker threads on boot and
# uv_thread_create increments the per-uid process count. The abort
# then cascaded through the async wrapper as a 120 s wall-clock hang.
# 256 leaves Node + existing processes + pptxgenjs internals plenty
# of room while still bounding a runaway fork (which the bounded
# render semaphore + container pid-namespace already cap). Confirmed
# safe in prod via the bisect script — Node aborts immediately at
# 16, renders cleanly at every value tested at or above ~64.
_RLIMIT_NPROC = 256
_OUTPUT_MAX_BYTES = _RLIMIT_FSIZE_BYTES  # Same number, two enforcements.

# Wall-clock timeout for the Node subprocess. DECOUPLED from RLIMIT_CPU
# so each cap protects against the abuse it actually addresses:
#   - RLIMIT_CPU = pure CPU-time runaway (compute loops, etc.).
#   - Wall-clock = stuck-on-syscall / slow-I/O / GC thrash that the
#                  kernel can't catch via SIGXCPU.
# 120 s is generous for legitimately large decks (30+ slides with
# charts) and still bounded enough that an attacker can't park a
# request open all day. See module docstring for the trade-off.
_SUBPROCESS_WALL_TIMEOUT_S = 120


def _apply_child_rlimits() -> None:
    """Apply POSIX resource limits to the current (child) process.

    Called via ``preexec_fn`` in subprocess.run — runs in the forked
    child after fork() and before execve(). MUST be picklable / safe
    in a fork context: no logger.* calls (the lock state is undefined
    post-fork), no global mutation.

    Each rlimit is best-effort: ``setrlimit`` can fail on macOS for
    RLIMIT_AS and RLIMIT_NPROC and we'd rather continue with weaker
    limits than abort the child. Production (Linux) enforces all of
    them; macOS dev gets whatever Darwin allows.
    """
    # CPU seconds — kernel sends SIGXCPU at soft limit, SIGKILL at hard.
    try:
        resource.setrlimit(
            resource.RLIMIT_CPU,
            (_RLIMIT_CPU_SECONDS, _RLIMIT_CPU_SECONDS),
        )
    except (ValueError, OSError, resource.error):  # type: ignore[attr-defined]
        pass

    # Address space (virtual memory). Capped above NODE_OPTIONS heap
    # cap so V8 OOMs cleanly via its own machinery first.
    try:
        resource.setrlimit(
            resource.RLIMIT_AS,
            (_RLIMIT_AS_BYTES, _RLIMIT_AS_BYTES),
        )
    except (ValueError, OSError, resource.error):  # type: ignore[attr-defined]
        # macOS is well-known for refusing RLIMIT_AS; not fatal.
        pass

    # Max file size. A single write that would exceed this gets SIGXFSZ.
    try:
        resource.setrlimit(
            resource.RLIMIT_FSIZE,
            (_RLIMIT_FSIZE_BYTES, _RLIMIT_FSIZE_BYTES),
        )
    except (ValueError, OSError, resource.error):  # type: ignore[attr-defined]
        pass

    # File descriptors.
    try:
        resource.setrlimit(
            resource.RLIMIT_NOFILE,
            (_RLIMIT_NOFILE, _RLIMIT_NOFILE),
        )
    except (ValueError, OSError, resource.error):  # type: ignore[attr-defined]
        pass

    # Process count — fork bomb prevention.
    try:
        resource.setrlimit(
            resource.RLIMIT_NPROC,
            (_RLIMIT_NPROC, _RLIMIT_NPROC),
        )
    except (ValueError, OSError, AttributeError, resource.error):  # type: ignore[attr-defined]
        # RLIMIT_NPROC missing on some platforms; tolerate it.
        pass


def _build_clean_env(temp_dir: str) -> dict:
    """Build a minimal env dict for the Node subprocess.

    Explicitly excludes every variable the parent process has — by
    passing this dict to ``subprocess.run(env=...)`` the child sees
    *only* what we list here. No AWS_*, no DATABASE_URL, no SECRET_KEY,
    no BEDROCK_*, no JWT_*, no FLOWIN_*. An RCE in the child therefore
    cannot dump our credentials via ``process.env``.

    NODE_OPTIONS sets the V8 heap cap AND a DNS resolution hint
    (ipv4first — defence-in-depth nudge so if a hostile script tries
    DNS it resolves A records before AAAA). NODE_NO_WARNINGS silences
    deprecation noise that would otherwise inflate stderr. TMPDIR
    points anything respecting it at our cleanup-able dir.

    Note: real egress prevention happens at the VPC security-group
    level — see the layered-defence note in the module docstring.
    Node has no flag for "deny all network"; the security group blocks
    0.0.0.0/0 except known service endpoints, which is the actual
    network control.
    """
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": "/tmp",
        "TMPDIR": temp_dir,
        "NODE_OPTIONS": "--max-old-space-size=1024 --dns-result-order=ipv4first",
        "NODE_NO_WARNINGS": "1",
    }


def generate_pptx_from_code(js_code: str, title: str = "Presentation") -> bytes:
    """Execute PptxGenJS code server-side and return .pptx bytes.

    Public signature is intentionally stable — the API route at
    ``app.api.workflows`` calls this with two positional arguments.
    Errors are raised as ``RuntimeError`` with redacted messages safe
    to surface in an HTTP response body.
    """

    func_code = js_code.strip()

    # Strip markdown fences
    if func_code.startswith("```"):
        func_code = re.sub(r'^```(?:javascript|js)?\s*\n?', '', func_code)
        func_code = re.sub(r'\n?```\s*$', '', func_code)

    pptxgenjs_path = str(NODE_MODULES_PPTXGENJS).replace("\\", "/")

    # ------------------------------------------------------------------
    # Render-quality sanitisation. See module docstring — this is NOT
    # a security control, it just prevents PptxGenJS from crashing on
    # common LLM-output mangling.
    # ------------------------------------------------------------------
    # 1. Remove # from hex colors
    func_code = re.sub(r'color:\s*"#([0-9A-Fa-f]{6})"', r'color: "\1"', func_code)
    func_code = re.sub(r"color:\s*'#([0-9A-Fa-f]{6})'", r"color: '\1'", func_code)
    # 2. Fix 8-char hex colors
    func_code = re.sub(r'color:\s*"([0-9A-Fa-f]{8})"', lambda m: f'color: "{m.group(1)[:6]}"', func_code)
    # 3. Fix negative shadow offsets
    func_code = re.sub(r'offset:\s*-(\d+)', r'offset: \1', func_code)
    # 4. Remove standalone .line property access (crashes in Node)
    lines = func_code.split('\n')
    safe_lines = []
    for line in lines:
        stripped = line.strip()
        if (stripped and not stripped.startswith('//') and
                '.line.' in stripped and 'line:' not in stripped and
                'addShape' not in stripped and 'addText' not in stripped):
            safe_lines.append(f'  // skipped: {stripped}')
        else:
            safe_lines.append(line)
    func_code = '\n'.join(safe_lines)
    # 5. Repair data URIs missing the `data:` scheme prefix. The LLM
    # occasionally emits an `addImage({ path: "image/svg+xml;base64,..." })`
    # or builds the string via concat (`"image/svg+xml;base64," + b64`)
    # without the leading `data:`. PptxGenJS routes anything not starting
    # with `data:` through its file-path branch, calls `fs.open` on the
    # whole base64 blob, and throws ENOENT inside encodeSlideMediaRels at
    # `pres.write()` time. That throw cascades up the async chain in a way
    # that has stalled the export subprocess for the full wall-clock
    # budget on real decks (observed in prod, 12-slide deck with svgIcon()
    # helper that returned "image/svg+xml;base64,...").
    # The lookbehind on the quote character avoids touching strings that
    # already have a valid `data:` prefix. Covers `"`, `'`, and backtick.
    func_code = re.sub(
        r"""(?P<q>["'`])image/(?P<mime>svg\+xml|png|jpe?g|gif|webp);base64,""",
        r"\g<q>data:image/\g<mime>;base64,",
        func_code,
    )

    # Replace writeFile/save with write("nodebuffer")
    for pattern in [
        r'(?:await\s+)?pres\.writeFile\s*\(\s*\{[^}]*\}\s*\)',
        r'(?:await\s+)?pres\.writeFile\s*\([^)]*\)',
        r'(?:await\s+)?pres\.save\s*\([^)]*\)',
    ]:
        func_code = re.sub(pattern, 'return pres.write("nodebuffer")', func_code)
    func_code = func_code.replace('return return', 'return')

    # Make function async
    if 'async function generatePresentation' not in func_code:
        func_code = func_code.replace('function generatePresentation', 'async function generatePresentation')

    # Wrap in one if no function found
    if 'function generatePresentation' not in func_code:
        func_code = f"async function generatePresentation() {{\n{func_code}\n}}"

    temp_dir = tempfile.mkdtemp(prefix="pptx_export_")
    # Owner-only — keeps a co-located process from another uid out of our
    # working dir. ``mkdtemp`` already creates with 0o700 on POSIX but
    # we set it explicitly so the contract is auditable and survives any
    # future move to a custom temp factory.
    try:
        os.chmod(temp_dir, 0o700)
    except OSError:
        pass

    js_file = os.path.join(temp_dir, "input.js")
    out_file = os.path.join(temp_dir, "output.pptx")
    out_path = out_file.replace("\\", "/")

    node_script = f'''
const fs = require("fs");
const Module = require("module");
const _orig = Module._resolveFilename;
Module._resolveFilename = function(req, parent, isMain, opts) {{
  if (req === "pptxgenjs") return require.resolve("{pptxgenjs_path}");
  return _orig.call(this, req, parent, isMain, opts);
}};
const _pptx = require("{pptxgenjs_path}");
global.PptxGenJS = _pptx;
global.pptxgen = _pptx;

// ────────────────────────────────────────────────────────────────────
// Runtime patch: Slide.addImage({{ path: "data:..." }}) → addImage({{
// data: "data:..." }}).
//
// PptxGenJS routes every `addImage` call's `path:` value through
// `fs.open` at write time — even when the string is a `data:` URI. The
// LLM commonly produces:
//
//   function svgIcon(p) {{ return "data:image/svg+xml;base64," + btoa(...); }}
//   slide.addImage({{ path: svgIcon(...) }});
//
// which crashes inside encodeSlideMediaRels with ENOENT, and the error
// then cascades through the async chain in a way that parks the export
// subprocess for the full wall-clock timeout (observed in prod).
//
// We patch the Slide prototype once at startup so all `addImage` calls
// re-route automatically. We get the prototype by constructing a
// throwaway pres + slide; the resulting `.constructor.prototype` is the
// real Slide class. Real http://...  or file paths (rare in LLM output,
// but possible) keep their original `path:` routing untouched.
//
// This is render-quality repair, not security — the Layer-1 / Layer-2 /
// Layer-3 boundaries from the module docstring are unchanged.
(() => {{
  try {{
    const _probePres = new _pptx();
    const _Slide = _probePres.addSlide().constructor.prototype;
    if (typeof _Slide.addImage === "function" && !_Slide.__addImagePatched__) {{
      const _origAddImage = _Slide.addImage;
      _Slide.addImage = function patchedAddImage(opts) {{
        if (
          opts && typeof opts === "object" &&
          typeof opts.path === "string" && opts.path.startsWith("data:")
        ) {{
          const fixed = Object.assign({{}}, opts);
          fixed.data = opts.path;
          delete fixed.path;
          return _origAddImage.call(this, fixed);
        }}
        return _origAddImage.call(this, opts);
      }};
      _Slide.__addImagePatched__ = true;
    }}
  }} catch (e) {{
    // Patching is best-effort. If the pptxgenjs internal shape ever
    // changes (e.g. Slide moves off a JS prototype chain) this would
    // silently no-op and the deck would hit the original bug. We log
    // for diagnosability but don't fail the export.
    console.error("[wrapper] addImage data-URI patch failed:", e.message);
  }}
}})();

{func_code}

const _FallbackPptx = require("{pptxgenjs_path}");
const _OrigFunc = generatePresentation;
generatePresentation = async function() {{
  try {{
    const r = await _OrigFunc();
    return r;
  }} catch(e) {{
    console.error("Crashed:", e.message, "- creating fallback");
    const p = new _FallbackPptx();
    p.layout = "LAYOUT_16x9";
    const s = p.addSlide();
    s.background = {{ color: "FFFFFF" }};
    s.addText("Export error: " + e.message, {{x:0.5,y:2,w:9,h:1,fontSize:14,color:"1A1A1A"}});
    return await p.write("nodebuffer");
  }}
}};

async function main() {{
  try {{
    let r = generatePresentation();
    if (r && typeof r.then === "function") r = await r;
    if (Buffer.isBuffer(r)) {{
      fs.writeFileSync("{out_path}", r);
      process.stdout.write("OK");
    }} else if (r instanceof Uint8Array) {{
      fs.writeFileSync("{out_path}", Buffer.from(r));
      process.stdout.write("OK");
    }} else {{
      const p = new _FallbackPptx();
      p.layout = "LAYOUT_16x9";
      const s = p.addSlide();
      s.addText("Export failed: no buffer returned", {{x:0.5,y:2,w:9,h:1,fontSize:14,color:"1A1A1A"}});
      const buf = await p.write("nodebuffer");
      fs.writeFileSync("{out_path}", buf);
      process.stdout.write("OK");
    }}
  }} catch(e) {{
    process.stderr.write("Fatal: " + e.message);
    process.exit(1);
  }}
}}
main();
'''

    with open(js_file, "w", encoding="utf-8") as f:
        f.write(node_script)

    clean_env = _build_clean_env(temp_dir)

    # preexec_fn is unavailable on Windows. We assume POSIX (the codebase
    # only supports Linux/macOS) but guard explicitly so an accidental
    # Windows runtime fails loudly here rather than at fork.
    preexec = _apply_child_rlimits if sys.platform != "win32" else None

    try:
        # --------------------------------------------------------------
        # Acquire the concurrency semaphore. Only the subprocess call
        # is inside the semaphore — string templating and disk writes
        # happen freely outside it.
        # --------------------------------------------------------------
        acquired = _RENDER_SEMAPHORE.acquire(timeout=_ACQUIRE_TIMEOUT_S)
        if not acquired:
            # Caller maps RuntimeError to HTTP 500 today; a future
            # refactor should distinguish this as a 503 with Retry-After.
            raise RuntimeError("PPTX renderer busy; please retry in a moment.")

        try:
            # time.monotonic() (not time.time()) — wall-clock here is for
            # operational telemetry, not security. Monotonic is immune
            # to NTP adjustments mid-render.
            _t_start = time.monotonic()
            result = subprocess.run(
                ["node", js_file],
                capture_output=True,
                text=True,
                timeout=_SUBPROCESS_WALL_TIMEOUT_S,
                cwd=temp_dir,
                env=clean_env,
                preexec_fn=preexec,
            )
            _render_wall_s = time.monotonic() - _t_start
        finally:
            _RENDER_SEMAPHORE.release()

        if not os.path.exists(out_file):
            err = _redact_stderr(result.stderr) or "PPTX file not created"
            logger.error("Node.js PPTX generation failed: %s", err)
            raise RuntimeError(f"PPTX generation failed: {err}")

        # Size cap BEFORE reading — an attacker writing a huge file
        # shouldn't get to consume our memory on the read.
        out_size = os.path.getsize(out_file)
        if out_size > _OUTPUT_MAX_BYTES:
            logger.error(
                "PPTX output exceeded cap: %d bytes > %d",
                out_size, _OUTPUT_MAX_BYTES,
            )
            raise RuntimeError("Generated PPTX exceeded 50 MB cap")

        with open(out_file, "rb") as f:
            pptx_bytes = f.read()

        # Logged at INFO with both the output size and the actual
        # wall-clock so we can build a distribution and tune the
        # _SUBPROCESS_WALL_TIMEOUT_S / heap cap from real traffic.
        logger.info(
            "Generated PPTX: %d bytes in %.2fs (timeout cap=%ds)",
            len(pptx_bytes),
            _render_wall_s,
            _SUBPROCESS_WALL_TIMEOUT_S,
        )
        return pptx_bytes

    except subprocess.TimeoutExpired:
        # Wall-clock timeout — child blew past _SUBPROCESS_WALL_TIMEOUT_S.
        # Either it's looping at low CPU (would've hit SIGXCPU first if
        # CPU-bound) or doing slow I/O / GC thrashing. Python SIGKILLs.
        logger.error(
            "PPTX generation timed out after %ds wall-clock",
            _SUBPROCESS_WALL_TIMEOUT_S,
        )
        raise RuntimeError("PPTX generation timed out")

    finally:
        # Recursive cleanup — replaces the per-file unlink+rmdir which
        # left orphan intermediates if pptxgenjs wrote scratch files.
        shutil.rmtree(temp_dir, ignore_errors=True)
