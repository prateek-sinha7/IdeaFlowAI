import { describe, it, expect } from "vitest";
import { NextRequest } from "next/server";
import { proxy } from "./proxy";

/**
 * ISS-250: /workflow/create never redirects when `mode` is absent or empty,
 * leaving the legacy URL live and uncanonicalized. proxy.ts:8's `if (mode)`
 * check is falsy for both `null` (key absent) and `""` (key present, empty),
 * and the falsy branch has no fallback destination — it just calls
 * NextResponse.next(), rendering the page in place under the legacy URL.
 */
describe("proxy - ISS-250 /workflow/create canonicalization", () => {
  it("ISS-250: bare /workflow/create (no mode param) redirects instead of passing through", () => {
    const req = new NextRequest("http://localhost:3000/workflow/create");
    const res = proxy(req);
    expect(res.status).toBe(307);
  });

  it("ISS-250: /workflow/create?mode= (empty mode) redirects instead of passing through", () => {
    const req = new NextRequest("http://localhost:3000/workflow/create?mode=");
    const res = proxy(req);
    expect(res.status).toBe(307);
  });
});
