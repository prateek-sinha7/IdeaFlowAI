import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { register } from "@/lib/api";

// ─────────────────────────────────────────────────────────────────
// ISS-256 — `ApiError`'s constructor (api.ts:77-79) independently
// re-implements the same broken idiom ISS-224 found in
// `authedJson` (api-handoff.ts:86-88): "only a plain-string `detail` gets a
// friendly message; anything else (FastAPI's list-shaped 422 `detail`) falls
// back to `JSON.stringify(...)`". Any `request()`-backed 422 whose `detail`
// carries a rejected value in an `input` field (e.g. a `string_too_long` /
// `string_too_short` Pydantic error) has that value embedded verbatim in
// `ApiError.message`, which `AccountSettings.tsx` (and any other page's catch
// block) renders raw.
// ─────────────────────────────────────────────────────────────────

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

/** A FastAPI/Pydantic list-shaped 422 body, the exact shape ISS-224/257 name. */
function listShaped422(rejectedValue: string) {
  return {
    ok: false,
    status: 422,
    statusText: "Unprocessable Entity",
    json: async () => ({
      detail: [
        {
          type: "string_too_short",
          loc: ["body", "password"],
          msg: "String should have at least 8 characters",
          input: rejectedValue,
          ctx: { min_length: 8 },
        },
      ],
    }),
  };
}

describe("ApiError — list-shaped 422 detail (ISS-256)", () => {
  it("ISS-256 — never echoes the rejected value back into ApiError.message", async () => {
    const rejectedPassword = "short7!";
    fetchMock.mockResolvedValue(listShaped422(rejectedPassword));

    let caught: unknown;
    try {
      await register("nobody@example.com", rejectedPassword);
    } catch (err) {
      caught = err;
    }

    expect(caught).toBeInstanceOf(Error);
    const message = (caught as Error).message;
    expect(message).not.toContain(rejectedPassword);
  });
});
