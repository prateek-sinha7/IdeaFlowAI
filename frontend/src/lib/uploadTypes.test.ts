import { describe, expect, it } from "vitest";

import {
  DOCUMENT_ACCEPT,
  DOCUMENT_EXTS,
  isBinaryUpload,
  isImageUpload,
  isTextUpload,
} from "./uploadTypes";

/**
 * The bug these guard: a `.xlsx` was missing from the picker's accept list AND
 * from the "stage this server-side" regex, so the UI drew an attachment chip
 * for a file it silently never uploaded.
 */
describe("upload types", () => {
  it("offers every document type the backend accepts", () => {
    // Mirrors backend run_files._ALLOWED_EXTS.
    expect([...DOCUMENT_EXTS].sort()).toEqual(
      ["csv", "docx", "json", "md", "pdf", "pptx", "txt", "xlsx"].sort(),
    );
  });

  it("every offered extension is handled by exactly one branch", () => {
    for (const ext of DOCUMENT_EXTS) {
      const name = `doc.${ext}`;
      expect(isTextUpload(name) !== isBinaryUpload(name)).toBe(true);
    }
  });

  it("stages xlsx server-side rather than dropping it", () => {
    expect(isBinaryUpload("4-azure.xlsx")).toBe(true);
    expect(DOCUMENT_ACCEPT).toContain(".xlsx");
  });

  it("reads text formats in the browser", () => {
    expect(isTextUpload("notes.md")).toBe(true);
    expect(isBinaryUpload("notes.md")).toBe(false);
  });

  it("is case-insensitive on the extension", () => {
    expect(isBinaryUpload("REPORT.PDF")).toBe(true);
  });

  it("does not offer types the backend rejects", () => {
    // .doc 415s server-side; offering it produces an unexplainable failure.
    expect(DOCUMENT_ACCEPT).not.toContain(".doc,");
    expect(isBinaryUpload("legacy.doc")).toBe(false);
  });

  it("classifies images by mime or by name", () => {
    expect(isImageUpload("shot.png")).toBe(true);
    expect(isImageUpload("blob", "image/webp")).toBe(true);
    expect(isImageUpload("1-crimson.pdf")).toBe(false);
  });
});
