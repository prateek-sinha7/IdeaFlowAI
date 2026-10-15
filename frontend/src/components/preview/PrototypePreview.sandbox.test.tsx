import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { PrototypePreview } from "./PrototypePreview";

// ISS-1067 - agent HTML must never run same-origin. xfail marker removed after fix (FIX-775).
const CONTENT = "<!DOCTYPE html><html><head></head><body><h1>Hi</h1></body></html>";

afterEach(() => vi.restoreAllMocks());

describe("PrototypePreview sandbox — ISS-1067", () => {
  it("frames agent HTML via srcdoc with sandbox exactly allow-scripts", async () => {
    const { container } = render(<PrototypePreview content={CONTENT} />);
    await waitFor(() => expect(container.querySelector("iframe")).not.toBeNull());
    const iframe = container.querySelector("iframe")!;
    expect(iframe.getAttribute("sandbox")).toBe("allow-scripts");
    expect(iframe.getAttribute("srcdoc")).toContain("<h1>Hi</h1>");
    expect(iframe.getAttribute("src") ?? "").not.toMatch(/^blob:/);
  });

  it("Open in new tab does not hand the raw agent HTML to a top-level tab", async () => {
    const blobs: Blob[] = [];
    (URL as unknown as { createObjectURL: unknown }).createObjectURL = vi.fn((b: Blob) => {
      blobs.push(b);
      return "blob:http://localhost/x";
    });
    (URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = vi.fn();
    const open = vi.spyOn(window, "open").mockReturnValue(null);

    render(<PrototypePreview content={CONTENT} />);
    fireEvent.click(await screen.findByTitle("Open in new tab"));

    expect(open).toHaveBeenCalled();
    expect(open.mock.calls[0][2] ?? "").toContain("noopener");
    const opened = blobs[blobs.length - 1];
    const text = await new Promise<string>((res) => {
      const r = new FileReader();
      r.onload = () => res(String(r.result));
      r.readAsText(opened);
    });
    expect(text).toContain('sandbox="allow-scripts"');
    expect(text).toContain("srcdoc=");
    expect(text).not.toBe(CONTENT);
  });
});
