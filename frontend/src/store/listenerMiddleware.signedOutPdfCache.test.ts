import { afterAll, beforeEach, describe, expect, it, vi } from "vitest";
import { configureStore } from "@reduxjs/toolkit";
import authReducer, { signedOut } from "@/store/slices/authSlice";
import { listenerMiddleware } from "@/store/listenerMiddleware";
import { clearToken, setToken } from "@/lib/api";
import { pdfCacheKey, readCachedPdfUrl, storeCachedPdfUrl, type PdfCacheKey } from "@/lib/pdfObjectUrlCache";

// ─────────────────────────────────────────────────────────────────
// The finished-run PDF object-URL cache (SandboxPdfPreview) is module memory,
// and a sign-out is a soft router.replace, so it survives into the next
// account unless the signedOut listener releases it. Real token seam, real
// cache, real listener; only the browser URL API jsdom lacks is stubbed.
// ─────────────────────────────────────────────────────────────────

const b64url = (o: object) => btoa(JSON.stringify(o)).replace(/=+$/, "").replace(/\+/g, "-").replace(/\//g, "_");
const jwtFor = (sub: string) => `${b64url({ alg: "none" })}.${b64url({ sub })}.sig`;

const revokeObjectURL = vi.fn();
const originalRevoke = URL.revokeObjectURL;

function keyFor(runId: string): PdfCacheKey {
  const key = pdfCacheKey(runId, "Deck.pdf", undefined);
  if (key === null) throw new Error("expected a signed-in account");
  return key;
}

function makeStore() {
  return configureStore({
    reducer: { auth: authReducer },
    middleware: (getDefault) => getDefault().prepend(listenerMiddleware.middleware),
  });
}

beforeEach(() => {
  revokeObjectURL.mockReset();
  URL.revokeObjectURL = revokeObjectURL;
  setToken(jwtFor("user-a"));
});

afterAll(() => {
  URL.revokeObjectURL = originalRevoke;
  clearToken();
});

describe("listenerMiddleware signedOut", () => {
  it("revokes and drops every cached PDF object URL when the user signs out", async () => {
    storeCachedPdfUrl(keyFor("run-1"), "blob:one");
    storeCachedPdfUrl(keyFor("run-2"), "blob:two");

    makeStore().dispatch(signedOut());

    await vi.waitFor(() => expect(revokeObjectURL).toHaveBeenCalledTimes(2));
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:one");
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:two");
    // Dropped, not only revoked: the same account, still holding a valid token, finds nothing.
    expect(readCachedPdfUrl(keyFor("run-1"))).toBeUndefined();
    expect(readCachedPdfUrl(keyFor("run-2"))).toBeUndefined();
  });
});
