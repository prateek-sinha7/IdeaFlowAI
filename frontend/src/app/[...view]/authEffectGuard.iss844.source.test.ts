/**
 * ISS-844 (QA-PS-040) — the auth-check mount effect in page.tsx dispatches
 * `signedIn({ token })` unconditionally, with no one-shot guard. Its sibling
 * `recentRuns` effect a few hundred lines below got exactly this guard
 * (`recentRunsRequestedRef`, landed as FIX-630) specifically to stop a
 * second effect invocation (React 18 StrictMode double-invoke, or a genuine
 * second mount per ISS-843/ISS-845) from re-dispatching and duplicating the
 * network call it triggers (`fetchWorkflows()` -> `GET /api/workflows`, via
 * listenerMiddleware.ts's `signedIn` listener). The auth-check effect never
 * received the same fix — this test pins that asymmetry directly against
 * the real source.
 *
 * A live network-duplication test was tried first (per ISS-844's own
 * trailing notes) and does not reliably reproduce — the doubling is a race
 * that depends on dev-server/StrictMode timing, not a deterministic
 * per-request count a browser test can assert on. The structural gap ISS-844
 * names as the actual fix target (mirror `recentRunsRequestedRef` on this
 * effect) is deterministic and file-local, so — following the same
 * "grep-style source assertion" idiom already used in this directory for
 * ISS-657 and BUG-003 (reviseGuard.source.test.ts) — this test asserts the
 * guard is present. It fails today (no guard exists) and passes the moment
 * one is added.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

describe("page.tsx auth-check effect — ISS-844 one-shot guard", () => {
  it("guards dispatch(signedIn(...)) against a second effect invocation", () => {
    const src = readFileSync(path.join(__dirname, "page.tsx"), "utf8");

    const startMarker = "// Auth check on mount";
    const start = src.indexOf(startMarker);
    expect(start).toBeGreaterThan(-1);
    const endMarker = "}, [router, dispatch]);";
    const end = src.indexOf(endMarker, start);
    expect(end).toBeGreaterThan(start);
    const body = src.slice(start, end);

    // Sanity: this is genuinely the effect ISS-844 describes — if these
    // markers move, the slice above is no longer the right effect and this
    // test would otherwise pass/fail for the wrong reason.
    expect(body).toContain("dispatch(signedIn(");
    expect(body).toContain("getMe(storedToken)");

    // ISS-844 unfixed: no one-shot guard exists anywhere in this effect
    // today. The sibling `recentRuns` effect's fix (FIX-630) used a
    // useRef-backed early return set synchronously before the dispatch that
    // matters; this test accepts that same shape (or an equivalent
    // ref/generation check) here.
    const hasOneShotGuard = /\.current\s*\)\s*return;/.test(body) || /\.current\s*=\s*true;/.test(body);

    expect(hasOneShotGuard).toBe(true);
  });
});
