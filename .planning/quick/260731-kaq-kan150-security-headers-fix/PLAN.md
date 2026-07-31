---
phase: quick-260731-kaq
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - infra/scripts/reconcile-host-config.sh
autonomous: true
requirements:
  - KAN-150

must_haves:
  truths:
    - "/_next/static/ location block declares NO add_header directives (inherits all 5 from server)"
    - "proxy_cache_valid 200 1y directive is removed (inert, no proxy_cache zone exists)"
    - "Cache-Control header appears exactly once on /_next/static/ responses (from upstream, not duplicated by nginx)"
    - "Security headers (HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, CSP) appear on all responses (/_next/static/ and /login)"
    
  artifacts:
    - path: infra/scripts/reconcile-host-config.sh
      provides: "Corrected nginx configuration for /_next/static/ location"
      contains: "location /_next/static/ {" with NO "add_header Cache-Control"
      
  key_links:
    - from: "nginx location-level add_header directive (replace-not-merge rule)"
      to: "inheritance void of server-level security headers"
      via: "Delete the add_header and proxy_cache_valid directives"
      pattern: "add_header Cache-Control.*|proxy_cache_valid.*200 1y"

---

## Objective

**nginx /_next/static/ location silently drops all five security headers on static assets.**

Static JavaScript, CSS, fonts, and other assets served under `/_next/static/` carry 0 of 5 expected response security headers (HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Content-Security-Policy), while internal API paths (`/login`, `/api/`) correctly carry all 5. The root cause is nginx's replace-not-merge inheritance rule: a single `add_header` directive at the location level discards all inherited `add_header` directives from the server level.

**The two problematic directives in the `/_next/static/` location block:**
1. `add_header Cache-Control "public, max-age=31536000, immutable";` — triggers the replace-not-merge rule, voiding all five server-level headers. The directive is also redundant (Next.js upstream already emits the identical header).
2. `proxy_cache_valid 200 1y;` — inert (no `proxy_cache` zone is declared anywhere in the infrastructure).

**Fix:** Delete both directives from the `/_next/static/` location block so it inherits all five security headers from the server level.

---

## Context

- **Issue:** [KAN-150](https://velocityai-hex.atlassian.net/browse/KAN-150) — nginx /_next/static/ location silently drops security headers on static assets
- **Root cause:** nginx's add_header replace-not-merge semantics; measured live 2026-07-29 and reproduced offline on nginx 1.24.0
- **Severity:** Medium — static assets lack security posture controls (particularly nosniff for MIME-type validation)
- **Affected file:** `infra/scripts/reconcile-host-config.sh` (the new delivery mechanism per C1)
- **Scope:** Host infrastructure only; no backend/engine changes; no Python modifications

### References

- **Deep investigation:** `.planning/dev-sse-infra-investigations/D3.md` — full root cause analysis, measurements, offline reproduction, test harness, rejected alternatives
- **Related issues:** A1 (SSE rate-limiting, same file), C1 (reconcile-host-config.sh delivery mechanism), E1 (log_format JSON)
- **Coordination:** A1's regex location for SSE streams must NOT declare `add_header` (safe as written; guard comment recommended to prevent future re-introduction)

---

## Facts Verified During Planning

- Nginx config is now in `infra/scripts/reconcile-host-config.sh` (per C1's extraction from bootstrap-ec2.sh)
- The `/_next/static/` location block is present with the two problematic directives
- Server-level security headers are correctly declared (lines 181–186 in the file)
- No `proxy_cache` zone is declared anywhere in the infrastructure (verified by grep on bootstrap-ec2.sh and reconcile-host-config.sh)
- The A1 regex location (for SSE `/api/runs/{id}/events/stream`) correctly declares NO `add_header`
- Characterization goldens are unaffected (engine unmodified; host-only change)

---

## Files to Change

| File | Change | Why |
|------|--------|-----|
| `infra/scripts/reconcile-host-config.sh` | Delete lines containing `proxy_cache_valid 200 1y;` and `add_header Cache-Control "public, max-age=31536000, immutable";` from the `/_next/static/` location block | The `add_header` triggers nginx's replace-not-merge inheritance rule, discarding all five server-level security headers. The `proxy_cache_valid` is inert (no proxy_cache zone exists). Both should be deleted so the location inherits all five headers from the server level. |

---

## What Is Not Changing

- The five server-level security headers (HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, CSP) — these stay in place
- The `proxy_pass` and `include` directives in the location block — these stay
- A1's regex SSE location block — this is already safe (declares no `add_header`); an optional guard comment will be added (out of scope for this fix but noted for coordination)
- Characterization goldens — unaffected by construction (engine not modified)

---

## Deleted Code Check

No deleted code is being resurrected. The `add_header Cache-Control` and `proxy_cache_valid` directives were introduced in commit `27483e6a` (2026-05-11, "infra: close 4 High audit findings"); they have never been marked for deletion in any phase register. This fix is removing them as part of correcting a bug, not resurrecting intentionally-deleted code.

---

## Locked Decisions Respected

No locked decisions are contradicted by this fix:
- **INV-1 (kernel knows no workflow by name):** Not affected — this is infrastructure config only
- **INV-3 (golden parity):** Not affected — engine unmodified; goldens byte-identical by construction
- **INV-12 (no duplication):** Not affected — removing code, not duplicating
- **SC-001 (new workflows need zero engine edits):** Not affected — no engine changes
- **Architecture (ports & adapters):** Not affected — configuration file only

---

## Verification Strategy

The fix will be verified by:
1. **Syntax validation:** `nginx -t` must pass (the reconcile script already does this)
2. **Before/after header count:** A probe script will confirm `/_next/static/` assets go from 0/5 to 5/5 security headers
3. **Duplicate header check:** Cache-Control count goes from 2× to 1× (eliminating the duplicate)
4. **Regression check:** Other paths (/login, /api/) must still return 5/5 (no regressions)
5. **Characterization goldens:** Must remain byte-identical (engine-only regression check)

---

## Notes

- **Coordination with A1:** A1's regex SSE location is safe as written (declares no `add_header`). An optional guard comment should be added to A1's block to prevent future authors from accidentally re-introducing this bug by adding X-Accel-Buffering or other headers.
- **Host-side reconciliation:** The fix is repo-only. Once committed, it will reach live hosts via C1's `reconcile-host-config.sh` fetch-and-run mechanism on the next deploy or scheduled reconcile.
- **No migration needed:** This is a configuration change, not a schema change. No Alembic migration required.
- **Backward compat:** The change strengthens security posture (headers restored on assets), it does not break anything.
