/**
 * Unit tests for fenceAgentPayloads defect fixes.
 *
 * DEFECT 1: Fence markers glued to narration (e.g., "text:```json")
 * DEFECT 2: Wrapper tags split by internal fenced blocks (e.g., <spec>...```...</spec>)
 *
 * Both are proven by small inline fixtures, not by reading real files.
 */

import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { fenceAgentPayloads } from "./SandboxTab";

describe("fenceAgentPayloads defect fixes", () => {
  describe("DEFECT 1: fence markers glued to narration", () => {
    it("splits glued fence markers to their own lines", () => {
      const input = "Some text:" + "```" + "json\n" +
        '{"key": "value"}\n' +
        "```" + "\n" +
        "More text";

      const result = fenceAgentPayloads(input);

      // Fence markers should be balanced
      const fences = (result.match(/^(`{3,}|~{3,})/gm) || []).length;
      expect(fences % 2).toBe(0);
      expect(fences).toBeGreaterThan(0);
    });

    it("handles fence markers glued to text at the end", () => {
      const input = "Let me create the task list:" + "```" + "json\n" +
        '[{"id": "t1"}]\n' +
        "```";

      const result = fenceAgentPayloads(input);

      // Fence markers should be balanced
      const fences = (result.match(/^(`{3,}|~{3,})/gm) || []).length;
      expect(fences % 2).toBe(0);
    });

    it("does not leak fence markers into rendered paragraphs", () => {
      const input = "Let me create:" + "```" + "json\n" +
        '[{"id": "t1"}]\n' +
        "```" + "\n" +
        "Done.";

      const result = fenceAgentPayloads(input);
      const { container } = render(
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{result}</ReactMarkdown>,
      );

      const paragraphs = [...container.querySelectorAll("p")].map((n) => n.textContent || "");
      expect(paragraphs.some((text) => text.includes("```"))).toBe(false);
    });
  });

  describe("DEFECT 2: wrapper tags split by internal fences", () => {
    it("keeps wrapper tag and internal fences together", () => {
      const input = "<spec>\n" +
        "# Specification\n\n" +
        "Here's some code:\n\n" +
        "```" + "javascript\n" +
        "function hello() {\n" +
        "  console.log(\"world\");\n" +
        "}\n" +
        "```" + "\n\n" +
        "More content inside the spec.\n" +
        "</spec>\n\n" +
        "Text after the spec.";

      const result = fenceAgentPayloads(input);

      // Fence markers should be balanced
      const fences = (result.match(/^(`{3,}|~{3,})/gm) || []).length;
      expect(fences % 2).toBe(0);
    });

    it("does not leak spec tags into paragraphs", () => {
      const input = "<spec>\n" +
        "# Specification\n\n" +
        "```" + "javascript\n" +
        "code here\n" +
        "```" + "\n\n" +
        "Content.\n" +
        "</spec>";

      const result = fenceAgentPayloads(input);
      const { container } = render(
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{result}</ReactMarkdown>,
      );

      const paragraphs = [...container.querySelectorAll("p")].map((n) => n.textContent || "");
      expect(paragraphs.some((text) => text.includes("<spec>"))).toBe(false);
    });

    it("handles artifact tags with internal fences", () => {
      const input = '<artifact type="text/html">\n' +
        "<!DOCTYPE html>\n" +
        "```" + "html\n" +
        "<div>content</div>\n" +
        "```" + "\n" +
        "</artifact>";

      const result = fenceAgentPayloads(input);

      // Fence markers should be balanced
      const fences = (result.match(/^(`{3,}|~{3,})/gm) || []).length;
      expect(fences % 2).toBe(0);
    });

    it("handles tasks tags with internal fences", () => {
      const input = "<tasks>\n" +
        "# Task List\n\n" +
        "```" + "json\n" +
        '{"tasks": []}\n' +
        "```" + "\n\n" +
        "Done.\n" +
        "</tasks>";

      const result = fenceAgentPayloads(input);

      // Fence markers should be balanced
      const fences = (result.match(/^(`{3,}|~{3,})/gm) || []).length;
      expect(fences % 2).toBe(0);
    });

    it("handles analysis tags with internal fences", () => {
      const input = "<analysis>\n" +
        "# Analysis Report\n\n" +
        "```" + "python\n" +
        "def analyze():\n" +
        "    pass\n" +
        "```" + "\n\n" +
        "Conclusion.\n" +
        "</analysis>";

      const result = fenceAgentPayloads(input);

      // Fence markers should be balanced
      const fences = (result.match(/^(`{3,}|~{3,})/gm) || []).length;
      expect(fences % 2).toBe(0);
    });

    it("renders markdown content inside unwrapped spec tags", () => {
      const input = "<spec>\n" +
        "# Heading\n\n" +
        "Paragraph text.\n" +
        "</spec>";

      const result = fenceAgentPayloads(input);
      const { container } = render(
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{result}</ReactMarkdown>,
      );

      // The heading should be rendered as h1
      const headings = [...container.querySelectorAll("h1")];
      expect(headings.length).toBeGreaterThan(0);
      expect(headings[0].textContent).toContain("Heading");

      // The paragraph should render
      const paragraphs = [...container.querySelectorAll("p")];
      expect(paragraphs.some((p) => p.textContent?.includes("Paragraph text"))).toBe(true);
    });

    it("handles nested multiple fenced blocks inside a wrapper", () => {
      const input = "<spec>\n" +
        "# Title\n\n" +
        "First code:\n" +
        "```" + "python\n" +
        "x = 1\n" +
        "```" + "\n\n" +
        "Middle text.\n\n" +
        "Second code:\n" +
        "```" + "javascript\n" +
        "let y = 2;\n" +
        "```" + "\n\n" +
        "End.\n" +
        "</spec>";

      const result = fenceAgentPayloads(input);

      // Fence markers should be balanced
      const fences = (result.match(/^(`{3,}|~{3,})/gm) || []).length;
      expect(fences % 2).toBe(0);
    });
  });

  describe("combined defects", () => {
    it("handles both glued fences and wrapper-wrapped fences together", () => {
      const input = "Before text:" + "```" + "json\n" +
        '{"data": "here"}\n' +
        "```" + "\n\n" +
        "<spec>\n" +
        "# Spec with code\n\n" +
        "```" + "python\n" +
        "def func():\n" +
        "    pass\n" +
        "```" + "\n\n" +
        "Done.\n" +
        "</spec>\n\n" +
        "After text.";

      const result = fenceAgentPayloads(input);

      // Fence markers should be balanced
      const fences = (result.match(/^(`{3,}|~{3,})/gm) || []).length;
      expect(fences % 2).toBe(0);

      // Render should not show fence markers or spec tags in paragraphs
      const { container } = render(
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{result}</ReactMarkdown>,
      );
      const paragraphs = [...container.querySelectorAll("p")].map((n) => n.textContent || "");
      expect(paragraphs.some((text) => text.includes("```"))).toBe(false);
      expect(paragraphs.some((text) => text.includes("<spec>"))).toBe(false);
    });
  });
});
