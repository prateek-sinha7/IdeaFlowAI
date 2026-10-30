import { afterAll, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { clearPdfUrlCache } from "@/lib/pdfObjectUrlCache";
import { SandboxPdfPreview } from "./SandboxPdfPreview";

// ─────────────────────────────────────────────────────────────────
// RCA item 9 — a finished run's PDF is fetched once per key and its object
// URL reused across Preview tab remounts (module-scope LRU, max 4) when the
// caller marks it `cacheable`; without the flag every mount fetches and the
// URL is revoked on unmount as before. Only the REST boundary is mocked.
//
// The key is scoped to the ACCOUNT (the token's `sub`), not to the bearer token:
// a token refresh keeps the entry, another account never reads it, and a token
// with no account id is never cached.
// ─────────────────────────────────────────────────────────────────

const auth = vi.hoisted(() => ({ token: "" as string | null }));
const getRunSandboxFileBlob = vi.fn();
const resolveRunDeliverable = vi.fn();
vi.mock("@/lib/api", () => ({
  getToken: () => auth.token,
  resolveRunDeliverable: (...args: unknown[]) => resolveRunDeliverable(...args),
  getRunSandboxFileBlob: (...args: unknown[]) => getRunSandboxFileBlob(...args),
}));

const b64url = (o: object) => btoa(JSON.stringify(o)).replace(/=+$/, "").replace(/\+/g, "-").replace(/\//g, "_");
/** A structurally valid JWT for `sub`. `issuedAt` changes the token without changing the account, as a refresh does. */
const jwtFor = (sub: string, issuedAt = 1) => `${b64url({ alg: "none" })}.${b64url({ sub, iat: issuedAt })}.sig`;

const createObjectURL = vi.fn();
const revokeObjectURL = vi.fn();
const originalCreate = URL.createObjectURL;
const originalRevoke = URL.revokeObjectURL;
let urlCounter = 0;

beforeEach(() => {
  auth.token = jwtFor("user-a");
  getRunSandboxFileBlob.mockReset();
  resolveRunDeliverable.mockReset();
  createObjectURL.mockReset();
  revokeObjectURL.mockReset();
  getRunSandboxFileBlob.mockImplementation(async () => new Blob(["%PDF-1.7"]));
  resolveRunDeliverable.mockImplementation(async (_t: string, _r: string, path: string, ref?: string) => ({ path, ref }));
  createObjectURL.mockImplementation(() => `blob:pdf-${++urlCounter}`);
  URL.createObjectURL = createObjectURL;
  URL.revokeObjectURL = revokeObjectURL;
  // The cache is module state and outlives a test: start each one empty, then
  // forget the revokes that emptying it caused.
  clearPdfUrlCache();
  revokeObjectURL.mockClear();
});

afterAll(() => {
  URL.createObjectURL = originalCreate;
  URL.revokeObjectURL = originalRevoke;
});

const fallback = <p>fallback</p>;

async function mountShown(runId: string, cacheable?: boolean) {
  const view = render(<SandboxPdfPreview runId={runId} path="Deck.pdf" fallback={fallback} cacheable={cacheable} />);
  const frame = await screen.findByTestId("sandbox-pdf-preview");
  return { view, src: frame.getAttribute("src") };
}

describe("SandboxPdfPreview object-URL cache", () => {
  it("fetches the blob once across mount, unmount and remount when cacheable", async () => {
    const first = await mountShown("cache-run-1", true);
    first.view.unmount();

    const second = render(<SandboxPdfPreview runId="cache-run-1" path="Deck.pdf" fallback={fallback} cacheable />);

    expect(screen.getByTestId("sandbox-pdf-preview").getAttribute("src")).toBe(first.src);
    second.unmount();
    expect(getRunSandboxFileBlob).toHaveBeenCalledTimes(1);
    expect(resolveRunDeliverable).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).not.toHaveBeenCalled();
  });

  it("fetches the blob on every mount and revokes on unmount when not cacheable", async () => {
    const first = await mountShown("plain-run-1");
    first.view.unmount();
    expect(revokeObjectURL).toHaveBeenCalledWith(first.src);

    const second = await mountShown("plain-run-1");
    second.view.unmount();

    expect(getRunSandboxFileBlob).toHaveBeenCalledTimes(2);
    expect(revokeObjectURL).toHaveBeenCalledWith(second.src);
  });

  it("evicts and revokes the oldest URL when a fifth distinct key is cached", async () => {
    const srcs: (string | null)[] = [];
    // Four fresh keys fill the cache.
    for (const runId of ["lru-1", "lru-2", "lru-3", "lru-4"]) {
      const shown = await mountShown(runId, true);
      srcs.push(shown.src);
      shown.view.unmount();
    }
    revokeObjectURL.mockClear();

    const fifth = await mountShown("lru-5", true);
    fifth.view.unmount();

    expect(revokeObjectURL).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith(srcs[0]);

    // The evicted key fetches again; a retained key does not.
    getRunSandboxFileBlob.mockClear();
    render(<SandboxPdfPreview runId="lru-5" path="Deck.pdf" fallback={fallback} cacheable />).unmount();
    expect(getRunSandboxFileBlob).not.toHaveBeenCalled();
    await mountShown("lru-1", true);
    expect(getRunSandboxFileBlob).toHaveBeenCalledTimes(1);
  });

  it("shows a cached PDF on the first render, before any effect has run", async () => {
    const first = await mountShown("first-paint-run", true);
    first.view.unmount();

    // renderToString runs state initializers but no effects, so it prints the very first frame.
    const html = renderToString(<SandboxPdfPreview runId="first-paint-run" path="Deck.pdf" fallback={fallback} cacheable />);

    expect(html).toContain(`src="${first.src}"`);
    expect(html).not.toContain("Loading PDF");
  });

  it("keeps two PDFs apart when a file name and a version tag differ only in where a separator falls", async () => {
    // A key built by joining on "|" would give both of these the same entry.
    const first = render(<SandboxPdfPreview runId="sep-run" path="a|b" selectedRef="c" fallback={fallback} cacheable />);
    await screen.findByTestId("sandbox-pdf-preview");
    first.unmount();

    const second = render(<SandboxPdfPreview runId="sep-run" path="a" selectedRef="b|c" fallback={fallback} cacheable />);
    await screen.findByTestId("sandbox-pdf-preview");
    second.unmount();

    expect(getRunSandboxFileBlob).toHaveBeenCalledTimes(2);
  });

  it("reuses the cached PDF when the token is refreshed for the same account", async () => {
    const first = await mountShown("refresh-run", true);
    first.view.unmount();

    // A refresh mints a new token (new `iat`) for the same account.
    auth.token = jwtFor("user-a", 2);
    const second = render(<SandboxPdfPreview runId="refresh-run" path="Deck.pdf" fallback={fallback} cacheable />);

    expect(screen.getByTestId("sandbox-pdf-preview").getAttribute("src")).toBe(first.src);
    second.unmount();
    expect(getRunSandboxFileBlob).toHaveBeenCalledTimes(1);
  });

  it("fetches with the new account's token instead of showing the previous account's PDF", async () => {
    const accountA = await mountShown("shared-run", true);
    accountA.view.unmount();

    const accountBToken = jwtFor("user-b");
    auth.token = accountBToken;
    const accountB = await mountShown("shared-run", true);
    accountB.view.unmount();

    expect(accountB.src).not.toBe(accountA.src);
    expect(getRunSandboxFileBlob).toHaveBeenCalledTimes(2);
    expect(getRunSandboxFileBlob).toHaveBeenLastCalledWith(accountBToken, "shared-run", "Deck.pdf", undefined);
    // The previous account's object URL is released, not just hidden.
    expect(revokeObjectURL).toHaveBeenCalledWith(accountA.src);
  });

  it("releases the previous account's PDF as soon as another account opens a preview, even if nothing is stored for it", async () => {
    const accountA = await mountShown("released-run", true);
    accountA.view.unmount();

    // The new account's download fails, so it never reaches the store path.
    auth.token = jwtFor("user-b");
    resolveRunDeliverable.mockResolvedValueOnce(null);
    render(<SandboxPdfPreview runId="released-run" path="Deck.pdf" fallback={fallback} cacheable />);
    await screen.findByText("fallback");

    expect(revokeObjectURL).toHaveBeenCalledWith(accountA.src);
  });

  it.each<[string, string | null]>([
    ["no token", null],
    ["a token that is not a JWT", "opaque-token"],
    ["a payload that cannot be decoded", "header.%%%.sig"],
    ["claims without a sub", `${b64url({ alg: "none" })}.${b64url({ iat: 1 })}.sig`],
    ["an empty sub", `${b64url({ alg: "none" })}.${b64url({ sub: "" })}.sig`],
    ["a sub that is not a string", `${b64url({ alg: "none" })}.${b64url({ sub: 42 })}.sig`],
  ])("fetches on every mount and revokes on unmount for %s", async (_label, token) => {
    auth.token = token;

    const first = await mountShown("unscoped-run", true);
    first.view.unmount();
    expect(revokeObjectURL).toHaveBeenCalledWith(first.src);

    const second = await mountShown("unscoped-run", true);
    second.view.unmount();

    expect(getRunSandboxFileBlob).toHaveBeenCalledTimes(2);
    expect(revokeObjectURL).toHaveBeenCalledWith(second.src);
  });

  it("does not keep a PDF that finishes downloading after the account signed out", async () => {
    let finishDownload: (blob: Blob) => void = () => {
      throw new Error("the download never started");
    };
    getRunSandboxFileBlob.mockImplementationOnce(
      () => new Promise<Blob>((resolve) => { finishDownload = resolve; }),
    );
    const view = render(<SandboxPdfPreview runId="late-run" path="Deck.pdf" fallback={fallback} cacheable />);
    await vi.waitFor(() => expect(getRunSandboxFileBlob).toHaveBeenCalledTimes(1));

    // The user signs out while the PDF is still downloading; the preview is still mounted.
    auth.token = null;
    finishDownload(new Blob(["%PDF-1.7"]));
    const shown = (await screen.findByTestId("sandbox-pdf-preview")).getAttribute("src");
    view.unmount();

    // Nothing was kept for the signed-out account: the URL is released on unmount,
    // and the same account signing back in downloads the file again.
    expect(revokeObjectURL).toHaveBeenCalledWith(shown);
    auth.token = jwtFor("user-a");
    const again = await mountShown("late-run", true);
    again.view.unmount();
    expect(getRunSandboxFileBlob).toHaveBeenCalledTimes(2);
  });
});
