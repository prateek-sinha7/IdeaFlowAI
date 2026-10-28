import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api";
import {
  UPLOADS_MISSING_MESSAGE,
  UPLOAD_FAILED_MESSAGE,
  UPLOAD_RATE_LIMITED_MESSAGE,
  UPLOAD_TIMEOUT_MESSAGE,
  UPLOAD_TOO_LARGE_MESSAGE,
  describeUploadError,
  isOverUploadLimit,
  isUploadsMissingError,
} from "./uploadErrors";

describe("describeUploadError", () => {
  it("names the server limit for a 413 (nginx or backend)", () => {
    expect(describeUploadError(new ApiError(413, "Request Entity Too Large"))).toBe(
      "File is too large for this server (limit 10 MB)",
    );
    expect(UPLOAD_TOO_LARGE_MESSAGE).toBe("File is too large for this server (limit 10 MB)");
  });

  it("tells the user to wait and retry for a 429 rate limit", () => {
    expect(describeUploadError(new ApiError(429, "Too Many Requests"))).toBe(
      "Too many uploads at once. Wait a moment, then try again.",
    );
    expect(UPLOAD_RATE_LIMITED_MESSAGE).toBe(
      "Too many uploads at once. Wait a moment, then try again.",
    );
  });

  it("reports a client-side timeout abort", () => {
    expect(describeUploadError(new ApiError(0, "Request timeout after 120000ms (aborted)"))).toBe(
      UPLOAD_TIMEOUT_MESSAGE,
    );
  });

  it("falls back to a generic reason and never echoes the server detail", () => {
    const message = describeUploadError(new ApiError(500, "<html>internal stack</html>"));
    expect(message).toBe(UPLOAD_FAILED_MESSAGE);
    expect(message).not.toContain("stack");
  });

  it("treats a non-API error as a generic failure", () => {
    expect(describeUploadError(new TypeError("Failed to fetch"))).toBe(UPLOAD_FAILED_MESSAGE);
    expect(describeUploadError(undefined)).toBe(UPLOAD_FAILED_MESSAGE);
  });
});

describe("isOverUploadLimit", () => {
  it("allows exactly 10 MiB and rejects one byte more", () => {
    expect(isOverUploadLimit(10 * 1024 * 1024)).toBe(false);
    expect(isOverUploadLimit(10 * 1024 * 1024 + 1)).toBe(true);
  });
});

describe("isUploadsMissingError", () => {
  it("matches the backend's 422 uploads_missing rejection", () => {
    const err = new ApiError(422, { code: "uploads_missing", error: "x", recoverable: true });
    expect(isUploadsMissingError(err)).toBe(true);
    expect(UPLOADS_MISSING_MESSAGE).toMatch(/re-attach/i);
  });

  it("ignores other 422s and other statuses", () => {
    expect(isUploadsMissingError(new ApiError(422, { code: "empty_brief" }))).toBe(false);
    expect(isUploadsMissingError(new ApiError(422, "plain string detail"))).toBe(false);
    expect(isUploadsMissingError(new ApiError(400, { code: "uploads_missing" }))).toBe(false);
    expect(isUploadsMissingError(new Error("boom"))).toBe(false);
  });
});
