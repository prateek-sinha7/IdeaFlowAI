import { beforeEach, describe, expect, it, vi } from "vitest";
import { exportToPptx } from "@/lib/exporters/pptExporter";
import type { ChartData, Slide, SlideData } from "@/types";

/**
 * Boundary: "pptxgenjs" (heavy, produces a downloadable file). It is replaced
 * by an in-memory recorder; the subject's real routing/layout logic runs.
 */
type Opts = Record<string, unknown>;
interface RecordedText {
  text: string | Array<{ text: string; options: Opts }>;
  opts: Opts;
}
interface RecordedShape {
  type: string;
  opts: Opts;
}

const { presentations, FakePptx } = vi.hoisted(() => {
  type Opts = Record<string, unknown>;

  class FakeSlide {
    background: unknown = undefined;
    shapes: Array<{ type: string; opts: Opts }> = [];
    texts: Array<{ text: string | Array<{ text: string; options: Opts }>; opts: Opts }> = [];
    charts: Array<{ type: string; data: unknown; opts: Opts }> = [];
    tables: Array<{ rows: unknown; opts: Opts }> = [];
    notes: string[] = [];

    addShape(type: string, opts: Opts) {
      this.shapes.push({ type, opts });
    }
    addText(text: string | Array<{ text: string; options: Opts }>, opts: Opts) {
      this.texts.push({ text, opts });
    }
    addChart(type: string, data: unknown, opts: Opts) {
      this.charts.push({ type, data, opts });
    }
    addTable(rows: unknown, opts: Opts) {
      this.tables.push({ rows, opts });
    }
    addNotes(notes: string) {
      this.notes.push(notes);
    }
  }

  const presentations: FakePptxInstance[] = [];

  class FakePptx {
    layout = "";
    author = "";
    title = "";
    slides: FakeSlide[] = [];
    written: Array<{ fileName: string }> = [];

    constructor() {
      presentations.push(this as unknown as FakePptxInstance);
    }
    addSlide() {
      const slide = new FakeSlide();
      this.slides.push(slide);
      return slide;
    }
    writeFile(options: { fileName: string }) {
      this.written.push(options);
      return Promise.resolve(options.fileName);
    }
  }

  interface FakePptxInstance {
    layout: string;
    author: string;
    title: string;
    slides: FakeSlide[];
    written: Array<{ fileName: string }>;
  }

  return { presentations, FakePptx };
});

vi.mock("pptxgenjs", () => ({ default: FakePptx }));

interface RecordedSlide {
  background: unknown;
  shapes: RecordedShape[];
  texts: RecordedText[];
  charts: Array<{ type: string; data: unknown; opts: Opts }>;
  tables: Array<{ rows: unknown; opts: Opts }>;
  notes: string[];
}
interface RecordedPresentation {
  layout: string;
  author: string;
  title: string;
  slides: RecordedSlide[];
  written: Array<{ fileName: string }>;
}

// ---------------------------------------------------------------- builders

function makeSlide(overrides: Partial<Slide> = {}): Slide {
  return {
    title: "Slide title",
    content: [],
    type: "text",
    colorScheme: { background: "#fff", text: "#000", accent: "#f00" },
    ...overrides,
  };
}

function exportSlides(slides: Slide[], filename?: string): RecordedPresentation {
  exportToPptx({ slides }, filename);
  return presentations[presentations.length - 1] as unknown as RecordedPresentation;
}

function exportOne(overrides: Partial<Slide>): RecordedSlide {
  return exportSlides([makeSlide(overrides)]).slides[0];
}

/** Loosely typed chart payload so tests can feed type strings outside the TS union. */
function chart(type: string, extra: Partial<ChartData> = {}): ChartData {
  return { type, labels: ["Q1", "Q2"], values: [10, 20], ...extra } as unknown as ChartData;
}

/** Feed deliberately malformed slide data past the type system. */
function malformed(partial: Record<string, unknown>): Slide {
  return { ...makeSlide(), ...partial } as unknown as Slide;
}

function plainTexts(slide: RecordedSlide): string[] {
  return slide.texts.flatMap((t) => (typeof t.text === "string" ? [t.text] : []));
}

function textOpts(slide: RecordedSlide, text: string): Opts {
  const found = slide.texts.find((t) => t.text === text);
  if (!found) {
    throw new Error(`No text "${text}" recorded. Recorded: ${JSON.stringify(plainTexts(slide))}`);
  }
  return found.opts;
}

function bulletBlocks(slide: RecordedSlide) {
  return slide.texts.flatMap((t) => (Array.isArray(t.text) ? [{ items: t.text, opts: t.opts }] : []));
}

function shapesOfType(slide: RecordedSlide, type: string): RecordedShape[] {
  return slide.shapes.filter((s) => s.type === type);
}

/**
 * Direct content layout: the title is drawn exactly once, at 22pt. (A slide
 * that was routed to another builder first and fell back would draw it twice.)
 */
function usesContentLayout(slide: RecordedSlide): boolean {
  const titles = slide.texts.filter((t) => t.text === "Slide title");
  return titles.length === 1 && titles[0].opts.fontSize === 22;
}

const LABELS_TABLE = { headers: ["Region", "Revenue"], rows: [["EMEA", "10"], ["APAC", "20"], ["AMER", "30"]] };
const COMPARISON = {
  left: { title: "Pros", items: ["Fast", "Cheap"] },
  right: { title: "Cons", items: ["Risky"] },
};

beforeEach(() => {
  presentations.length = 0;
  vi.clearAllMocks();
});

// ------------------------------------------------------------------- tests

describe("exportToPptx deck metadata and file name", () => {
  it("configures wide layout and VelocityAI author when exporting", () => {
    const pres = exportSlides([makeSlide()]);

    expect(presentations).toHaveLength(1);
    expect(pres.layout).toBe("LAYOUT_WIDE");
    expect(pres.author).toBe("VelocityAI");
  });

  it("uses the supplied filename for title and written file when a filename is given", () => {
    const pres = exportSlides([makeSlide({ title: "Ignored title" })], "Board Deck");

    expect(pres.title).toBe("Board Deck");
    expect(pres.written).toEqual([{ fileName: "Board Deck.pptx" }]);
  });

  it("derives a sanitized hyphenated name from the first slide title when no filename is given", () => {
    const pres = exportSlides([makeSlide({ title: "Q3 Report: Growth & Plans!" })]);

    expect(pres.title).toBe("Q3-Report-Growth-Plans");
    expect(pres.written).toEqual([{ fileName: "Q3-Report-Growth-Plans.pptx" }]);
  });

  it("collapses runs of whitespace and trims when deriving the name", () => {
    const pres = exportSlides([makeSlide({ title: "  Hello   brave\tnew  world  " })]);

    expect(pres.title).toBe("Hello-brave-new-world");
  });

  it("keeps existing hyphens and digits when deriving the name", () => {
    const pres = exportSlides([makeSlide({ title: "Go-to-market 2025" })]);

    expect(pres.title).toBe("Go-to-market-2025");
  });

  it("truncates the derived name to 50 characters when the first title is long", () => {
    const pres = exportSlides([makeSlide({ title: "a".repeat(60) })]);

    expect(pres.title).toBe("a".repeat(50));
    expect(pres.written).toEqual([{ fileName: `${"a".repeat(50)}.pptx` }]);
  });

  it("derives the name from the title when the filename is an empty string", () => {
    const pres = exportSlides([makeSlide({ title: "Roadmap" })], "");

    expect(pres.written).toEqual([{ fileName: "Roadmap.pptx" }]);
  });

  it("falls back to Presentation and still writes the file when the deck has no slides", () => {
    const pres = exportSlides([]);

    expect(pres.slides).toHaveLength(0);
    expect(pres.title).toBe("Presentation");
    expect(pres.written).toEqual([{ fileName: "Presentation.pptx" }]);
  });

  it("falls back to Presentation when the first slide title is empty", () => {
    const pres = exportSlides([makeSlide({ title: "" })]);

    expect(pres.title).toBe("Presentation");
    expect(pres.written).toEqual([{ fileName: "Presentation.pptx" }]);
  });

  it("writes the file exactly once after all slides are built when exporting many slides", () => {
    const pres = exportSlides([makeSlide(), makeSlide(), makeSlide()]);

    expect(pres.slides).toHaveLength(3);
    expect(pres.written).toHaveLength(1);
  });
});

describe("exportToPptx per-slide chrome", () => {
  it("adds white background, top accent bar, numbered footer and bottom bar to every slide", () => {
    const pres = exportSlides([makeSlide(), makeSlide(), makeSlide()]);

    pres.slides.forEach((slide, index) => {
      expect(slide.background).toEqual({ color: "FFFFFF" });
      expect(slide.shapes[0]).toEqual({
        type: "rect",
        opts: { x: 0, y: 0, w: 13.3, h: 0.08, fill: { color: "C96442" } },
      });
      expect(slide.texts[slide.texts.length - 1]).toEqual({
        text: `${index + 1} / 3`,
        opts: { x: 11.5, y: 7.0, w: 1.5, h: 0.4, fontSize: 9, color: "87867F", align: "right" },
      });
      expect(slide.shapes[slide.shapes.length - 1]).toEqual({
        type: "rect",
        opts: { x: 0, y: 7.3, w: 13.3, h: 0.2, fill: { color: "F5F4ED" } },
      });
    });
  });

  it("adds speaker notes when the slide has notes", () => {
    const slide = exportOne({ speakerNotes: "Say hello first" });

    expect(slide.notes).toEqual(["Say hello first"]);
  });

  it("adds no speaker notes when notes are absent", () => {
    expect(exportOne({}).notes).toEqual([]);
  });

  it("adds no speaker notes when notes are an empty string", () => {
    expect(exportOne({ speakerNotes: "" }).notes).toEqual([]);
  });
});

describe("exportToPptx title slides", () => {
  const highlightContent = [{ text: "Alpha" }, { text: "Beta" }, { text: "Gamma" }, { text: "Delta" }];

  it("renders the hero layout with navy panel and large title when a title slide is first", () => {
    const slide = exportOne({ type: "title", title: "Launch Plan" });

    expect(slide.shapes).toContainEqual({
      type: "rect",
      opts: { x: 0, y: 0, w: 4.5, h: 7.5, fill: { color: "1E3A5F" } },
    });
    expect(textOpts(slide, "Launch Plan")).toEqual({
      x: 5, y: 1.5, w: 7.5, h: 2,
      fontSize: 32, bold: true, color: "141413", fontFace: "Arial", charSpacing: 1,
    });
    expect(slide.shapes).toContainEqual({
      type: "rect",
      opts: { x: 5, y: 3.5, w: 2, h: 0.05, fill: { color: "C96442" } },
    });
  });

  it("renders the hero subtitle when a first title slide has a subtitle", () => {
    const slide = exportOne({ type: "title", subtitle: "Fiscal 2026" });

    expect(textOpts(slide, "Fiscal 2026")).toEqual({
      x: 5, y: 3.8, w: 7.5, h: 1, fontSize: 16, color: "5E5D59", fontFace: "Arial",
    });
  });

  it("omits the hero subtitle when a first title slide has none", () => {
    const slide = exportOne({ type: "title" });

    expect(plainTexts(slide)).toEqual(["Slide title", "1 / 1"]);
  });

  it("renders at most three stacked highlight cards on the hero panel when content has four items", () => {
    const slide = exportOne({ type: "title", content: highlightContent });
    const cards = shapesOfType(slide, "roundRect");

    expect(cards).toHaveLength(3);
    expect(cards.map((c) => c.opts.y)).toEqual([4.5, 5.4, 6.3]);
    expect(cards[0].opts).toEqual({
      x: 0.4, y: 4.5, w: 3.7, h: 0.7,
      fill: { color: "FFFFFF", transparency: 85 }, rectRadius: 0.05,
    });
    expect(plainTexts(slide)).toEqual(["Slide title", "Alpha", "Beta", "Gamma", "1 / 1"]);
    expect(textOpts(slide, "Alpha")).toEqual({
      x: 0.6, y: 4.55, w: 3.3, h: 0.6, fontSize: 11, color: "FFFFFF", fontFace: "Arial", bold: true,
    });
  });

  it("renders one highlight card when the hero slide has a single content item", () => {
    const slide = exportOne({ type: "title", content: [{ text: "Only" }] });

    expect(shapesOfType(slide, "roundRect")).toHaveLength(1);
  });

  it.each([
    ["empty content", []],
    ["missing content", undefined],
  ])("renders no highlight cards when the hero slide has %s", (_label, content) => {
    const slide = exportSlides([malformed({ type: "title", content })]).slides[0];

    expect(shapesOfType(slide, "roundRect")).toHaveLength(0);
  });

  it("renders the closing layout with centered title when a title slide is not first", () => {
    const pres = exportSlides([makeSlide(), makeSlide({ type: "title", title: "Thank you" })]);
    const closing = pres.slides[1];

    expect(textOpts(closing, "Thank you")).toEqual({
      x: 1.5, y: 2.0, w: 10, h: 1.5,
      fontSize: 28, bold: true, color: "141413", align: "center", fontFace: "Arial",
    });
    expect(closing.shapes).toContainEqual({
      type: "rect",
      opts: { x: 5.5, y: 3.5, w: 2, h: 0.04, fill: { color: "C96442" } },
    });
    expect(closing.shapes).not.toContainEqual(expect.objectContaining({ opts: expect.objectContaining({ w: 4.5, h: 7.5 }) }));
  });

  it("renders a centered subtitle when a closing title slide has a subtitle", () => {
    const pres = exportSlides([makeSlide(), makeSlide({ type: "title", subtitle: "Questions?" })]);

    expect(textOpts(pres.slides[1], "Questions?")).toEqual({
      x: 2, y: 3.8, w: 9, h: 1, fontSize: 16, color: "5E5D59", align: "center",
    });
  });

  it("omits the subtitle when a closing title slide has none", () => {
    const pres = exportSlides([makeSlide(), makeSlide({ type: "title" })]);

    expect(plainTexts(pres.slides[1])).toEqual(["Slide title", "2 / 2"]);
  });

  it("renders at most three centered bullet takeaways when a closing slide has four content items", () => {
    const pres = exportSlides([makeSlide(), makeSlide({ type: "title", content: highlightContent })]);
    const blocks = bulletBlocks(pres.slides[1]);

    expect(blocks).toHaveLength(1);
    expect(blocks[0].opts).toEqual({ x: 2.5, y: 5.0, w: 8, h: 2, valign: "top" });
    expect(blocks[0].items).toEqual(
      ["Alpha", "Beta", "Gamma"].map((text) => ({
        text,
        options: { fontSize: 13, color: "141413", bullet: true, breakLine: true, paraSpaceAfter: 6, align: "center" },
      })),
    );
  });

  it.each([
    ["empty content", []],
    ["missing content", undefined],
  ])("renders no takeaway bullets when a closing slide has %s", (_label, content) => {
    const pres = exportSlides([makeSlide(), malformed({ type: "title", content })]);

    expect(bulletBlocks(pres.slides[1])).toHaveLength(0);
  });
});

describe("exportToPptx content slides", () => {
  it("renders title, underline and bullets at y 1.5 when the slide has no subtitle", () => {
    const slide = exportOne({ content: [{ text: "Point A" }, { text: "Point B" }] });
    const [block] = bulletBlocks(slide);

    expect(textOpts(slide, "Slide title")).toEqual({
      x: 0.8, y: 0.4, w: 11, h: 0.8,
      fontSize: 22, bold: true, color: "141413", fontFace: "Arial", margin: 0,
    });
    expect(slide.shapes).toContainEqual({
      type: "rect",
      opts: { x: 0.8, y: 1.15, w: 1.5, h: 0.04, fill: { color: "C96442" } },
    });
    expect(block.opts).toEqual({ x: 0.8, y: 1.5, w: 11.5, h: 5, valign: "top" });
    expect(block.items.map((b) => b.text)).toEqual(["Point A", "Point B"]);
    expect(block.items[0].options).toEqual({
      fontSize: 15, color: "141413", bullet: true, breakLine: true, paraSpaceAfter: 8,
    });
  });

  it("renders an italic subtitle and lowers the bullets to y 2.0 when the slide has a subtitle", () => {
    const slide = exportOne({ subtitle: "Key points", content: [{ text: "Point A" }] });

    expect(textOpts(slide, "Key points")).toEqual({
      x: 0.8, y: 1.3, w: 11, h: 0.5, fontSize: 13, color: "5E5D59", italic: true,
    });
    expect(bulletBlocks(slide)[0].opts).toMatchObject({ y: 2.0 });
  });

  it("renders indented sub-points directly after their parent bullet when subPoints exist", () => {
    const slide = exportOne({
      content: [{ text: "A" }, { text: "B", subPoints: ["B1", "B2"] }, { text: "C" }],
    });
    const [block] = bulletBlocks(slide);

    expect(block.items.map((b) => b.text)).toEqual(["A", "B", "B1", "B2", "C"]);
    expect(block.items[2].options).toEqual({
      fontSize: 12, color: "5E5D59", bullet: true, indentLevel: 1, breakLine: true, paraSpaceAfter: 4,
    });
    expect(block.items[0].options).not.toHaveProperty("indentLevel");
  });

  it("adds only the parent bullet when subPoints is an empty array", () => {
    const slide = exportOne({ content: [{ text: "A", subPoints: [] }] });

    expect(bulletBlocks(slide)[0].items.map((b) => b.text)).toEqual(["A"]);
  });

  it.each([
    ["empty content", []],
    ["missing content", undefined],
  ])("adds no bullet block when the slide has %s", (_label, content) => {
    const slide = exportSlides([malformed({ content })]).slides[0];

    expect(bulletBlocks(slide)).toHaveLength(0);
    expect(plainTexts(slide)).toEqual(["Slide title", "1 / 1"]);
  });

  it.each(["text", "icon", "timeline"] as const)(
    "falls back to the content layout when type is %s and no payload exists",
    (type) => {
      expect(usesContentLayout(exportOne({ type }))).toBe(true);
    },
  );
});

describe("exportToPptx chart slides", () => {
  it.each([
    ["pie", "pie"],
    ["line", "line"],
    ["bar", "bar"],
    ["doughnut", "doughnut"],
    ["area", "area"],
  ])("maps chart type %s to the %s chart", (type, expected) => {
    const slide = exportOne({ type: "chart", chartData: chart(type) });

    expect(slide.charts).toHaveLength(1);
    expect(slide.charts[0].type).toBe(expected);
  });

  it("defaults to a bar chart when the chart type is unknown", () => {
    const slide = exportOne({ type: "chart", chartData: chart("radar") });

    expect(slide.charts[0].type).toBe("bar");
  });

  it("defaults to a bar chart when the chart type is missing", () => {
    const slide = exportOne({ type: "chart", chartData: chart("", {}) });

    expect(slide.charts[0].type).toBe("bar");
  });

  it("renders a titled chart with series name, labels, values and shown title when chartData has a title", () => {
    const slide = exportOne({ type: "chart", chartData: chart("pie", { title: "Revenue Mix" }) });
    const [rendered] = slide.charts;

    expect(rendered.data).toEqual([{ name: "Revenue Mix", labels: ["Q1", "Q2"], values: [10, 20] }]);
    expect(rendered.opts).toMatchObject({
      x: 1.5, y: 1.5, w: 10, h: 5.2,
      showTitle: true, title: "Revenue Mix", titleColor: "141413", titleFontSize: 12,
      chartColors: ["C96442", "1E3A5F", "10B981", "8B5CF6", "F59E0B"],
      showValue: true, showLegend: true, legendPos: "b", legendFontSize: 9, legendColor: "5E5D59",
    });
  });

  it("names the series Data and hides the title when chartData has no title", () => {
    const slide = exportOne({ type: "chart", chartData: chart("bar") });
    const [rendered] = slide.charts;

    expect(rendered.data).toEqual([{ name: "Data", labels: ["Q1", "Q2"], values: [10, 20] }]);
    expect(rendered.opts).toMatchObject({ showTitle: false, title: "" });
  });

  it("draws the chart slide title at 20pt with its underline when a chart is rendered", () => {
    const slide = exportOne({ type: "chart", chartData: chart("bar") });

    expect(textOpts(slide, "Slide title")).toEqual({
      x: 0.8, y: 0.4, w: 11, h: 0.7, fontSize: 20, bold: true, color: "141413", fontFace: "Arial",
    });
    expect(slide.shapes).toContainEqual({
      type: "rect",
      opts: { x: 0.8, y: 1.05, w: 1.5, h: 0.04, fill: { color: "C96442" } },
    });
  });

  it("renders a chart when a text slide carries valid chart data", () => {
    const slide = exportOne({ type: "text", chartData: chart("line") });

    expect(slide.charts).toHaveLength(1);
    expect(slide.charts[0].type).toBe("line");
  });

  it("renders empty series when a chart slide's labels and values are missing", () => {
    const slide = exportOne({
      type: "chart",
      chartData: { type: "bar" } as unknown as ChartData,
    });

    expect(slide.charts[0].data).toEqual([{ name: "Data", labels: [], values: [] }]);
  });

  it("falls back to the content layout without a chart when a chart slide has no chartData", () => {
    const slide = exportOne({ type: "chart", content: [{ text: "Fallback bullet" }] });

    expect(slide.charts).toHaveLength(0);
    expect(bulletBlocks(slide)[0].items.map((b) => b.text)).toEqual(["Fallback bullet"]);
  });

  it("does not treat a text slide as a chart when labels are empty", () => {
    const slide = exportOne({ type: "text", chartData: chart("bar", { labels: [], values: [] }) });

    expect(slide.charts).toHaveLength(0);
    expect(usesContentLayout(slide)).toBe(true);
  });

  it("does not treat a text slide as a chart when values are missing", () => {
    const slide = exportOne({ type: "text", chartData: { type: "bar", labels: ["Q1"] } as unknown as ChartData });

    expect(slide.charts).toHaveLength(0);
    expect(usesContentLayout(slide)).toBe(true);
  });
});

describe("exportToPptx table slides", () => {
  it("renders a navy centered header row and zebra-striped data rows when tableData is complete", () => {
    const slide = exportOne({ type: "table", tableData: LABELS_TABLE });
    const [table] = slide.tables;
    const rows = table.rows as Array<Array<{ text: string; options: Opts }>>;

    expect(rows.map((r) => r.map((c) => c.text))).toEqual([
      ["Region", "Revenue"],
      ["EMEA", "10"],
      ["APAC", "20"],
      ["AMER", "30"],
    ]);
    expect(rows[0][0].options).toEqual({
      bold: true, color: "FFFFFF", fill: { color: "1E3A5F" }, fontSize: 11, align: "center",
    });
    expect(rows.slice(1).map((r) => (r[0].options.fill as { color: string }).color)).toEqual([
      "FAF9F5", "FFFFFF", "FAF9F5",
    ]);
    expect(rows[1][0].options).toMatchObject({ color: "141413", fontSize: 11 });
  });

  it("sizes columns evenly and rows at 0.5 when rendering a table", () => {
    const slide = exportOne({ type: "table", tableData: LABELS_TABLE });

    expect(slide.tables[0].opts).toEqual({
      x: 0.8, y: 1.4, w: 11.7, h: 5.5, fontSize: 11,
      border: { type: "solid", pt: 0.5, color: "E8E6DC" },
      colW: [5.85, 5.85],
      rowH: [0.5, 0.5, 0.5, 0.5],
    });
  });

  it("draws the table slide title at 20pt when a table is rendered", () => {
    const slide = exportOne({ type: "table", tableData: LABELS_TABLE });

    expect(textOpts(slide, "Slide title")).toMatchObject({ fontSize: 20, y: 0.4, h: 0.7 });
  });

  it("renders a table when a text slide carries valid table data", () => {
    const slide = exportOne({ type: "text", tableData: LABELS_TABLE });

    expect(slide.tables).toHaveLength(1);
  });

  it("falls back to the content layout when a table slide has no tableData", () => {
    const slide = exportOne({ type: "table", content: [{ text: "Fallback bullet" }] });

    expect(slide.tables).toHaveLength(0);
    expect(bulletBlocks(slide)[0].items.map((b) => b.text)).toEqual(["Fallback bullet"]);
  });

  it("does not treat a text slide as a table when headers are empty", () => {
    const slide = exportOne({ type: "text", tableData: { headers: [], rows: [["x"]] } });

    expect(slide.tables).toHaveLength(0);
    expect(usesContentLayout(slide)).toBe(true);
  });

  it("renders only the header row when a table slide has no rows array", () => {
    const slide = exportSlides([malformed({ type: "table", tableData: { headers: ["A", "B"] } })]).slides[0];
    const rows = slide.tables[0].rows as Array<Array<{ text: string }>>;

    expect(rows.map((r) => r.map((c) => c.text))).toEqual([["A", "B"]]);
    expect(slide.tables[0].opts.rowH).toEqual([0.5]);
  });

  it("renders only data rows starting with the light stripe when headers are missing", () => {
    const slide = exportSlides([malformed({ type: "table", tableData: { rows: [["x", "y"]] } })]).slides[0];
    const rows = slide.tables[0].rows as Array<Array<{ text: string; options: Opts }>>;

    expect(rows.map((r) => r.map((c) => c.text))).toEqual([["x", "y"]]);
    expect(rows[0][0].options.fill).toEqual({ color: "FAF9F5" });
  });

  it("adds no table when headers are missing and there are no rows", () => {
    const slide = exportSlides([malformed({ type: "table", tableData: { rows: [] } })]).slides[0];

    expect(slide.tables).toHaveLength(0);
  });

  it("defaults to three equal columns when the first row has no cells", () => {
    const slide = exportOne({ type: "table", tableData: { headers: [], rows: [] } });
    const colW = slide.tables[0].opts.colW as number[];

    expect(colW).toHaveLength(3);
    colW.forEach((w) => expect(w).toBeCloseTo(3.9, 10));
    expect(slide.tables[0].opts.rowH).toEqual([0.5]);
  });
});

describe("exportToPptx comparison slides", () => {
  it("renders two cards with titles, bullets and a VS divider when comparisonData is complete", () => {
    const slide = exportOne({ type: "comparison", comparisonData: COMPARISON });
    const cards = shapesOfType(slide, "roundRect");

    expect(cards.map((c) => c.opts)).toEqual([
      { x: 0.8, y: 1.5, w: 5.8, h: 5.3, fill: { color: "FAF9F5" }, rectRadius: 0.1, line: { color: "E8E6DC", width: 1 } },
      { x: 6.9, y: 1.5, w: 5.8, h: 5.3, fill: { color: "FAF9F5" }, rectRadius: 0.1, line: { color: "E8E6DC", width: 1 } },
    ]);
    expect(textOpts(slide, "Pros")).toEqual({ x: 1.2, y: 1.8, w: 5, h: 0.6, fontSize: 16, bold: true, color: "C96442" });
    expect(textOpts(slide, "Cons")).toEqual({ x: 7.3, y: 1.8, w: 5, h: 0.6, fontSize: 16, bold: true, color: "1E3A5F" });
    expect(textOpts(slide, "VS")).toEqual({
      x: 6.1, y: 3.5, w: 1, h: 0.8, fontSize: 14, bold: true, color: "87867F", align: "center", valign: "middle",
    });

    const [leftBlock, rightBlock] = bulletBlocks(slide);
    expect(leftBlock.items.map((b) => b.text)).toEqual(["Fast", "Cheap"]);
    expect(leftBlock.opts).toEqual({ x: 1.2, y: 2.5, w: 5, h: 4, valign: "top" });
    expect(rightBlock.items.map((b) => b.text)).toEqual(["Risky"]);
    expect(rightBlock.opts).toEqual({ x: 7.3, y: 2.5, w: 5, h: 4, valign: "top" });
    expect(leftBlock.items[0].options).toEqual({
      fontSize: 13, color: "141413", bullet: true, breakLine: true, paraSpaceAfter: 6,
    });
  });

  it("renders a comparison when a text slide carries valid comparison data", () => {
    const slide = exportOne({ type: "text", comparisonData: COMPARISON });

    expect(plainTexts(slide)).toContain("VS");
  });

  it.each([
    ["left side", { right: COMPARISON.right }],
    ["right side", { left: COMPARISON.left }],
  ])("does not treat a text slide as a comparison when the %s is missing", (_label, comparisonData) => {
    const slide = exportSlides([malformed({ type: "text", comparisonData })]).slides[0];

    expect(plainTexts(slide)).not.toContain("VS");
    expect(usesContentLayout(slide)).toBe(true);
  });

  it("falls back to the content layout when a comparison slide has no comparisonData", () => {
    const slide = exportOne({ type: "comparison", content: [{ text: "Fallback bullet" }] });

    expect(plainTexts(slide)).not.toContain("VS");
    expect(bulletBlocks(slide)[0].items.map((b) => b.text)).toEqual(["Fallback bullet"]);
  });

  it("omits the left bullet block when the left card has no items", () => {
    const slide = exportOne({
      type: "comparison",
      comparisonData: { left: { title: "Pros", items: [] }, right: COMPARISON.right },
    });
    const blocks = bulletBlocks(slide);

    expect(blocks).toHaveLength(1);
    expect(blocks[0].opts).toMatchObject({ x: 7.3 });
  });

  it("omits the right bullet block when the right card has no items", () => {
    const slide = exportOne({
      type: "comparison",
      comparisonData: { left: COMPARISON.left, right: { title: "Cons", items: [] } },
    });
    const blocks = bulletBlocks(slide);

    expect(blocks).toHaveLength(1);
    expect(blocks[0].opts).toMatchObject({ x: 1.2 });
  });
});

describe("exportToPptx two-column slides", () => {
  const COLUMNS: Slide["columns"] = [["L1", "L2"], ["R1"]];

  it("renders both column bullet blocks and a divider line when two columns are present", () => {
    const slide = exportOne({ type: "two-column", columns: COLUMNS });
    const [left, right] = bulletBlocks(slide);

    expect(left.items.map((b) => b.text)).toEqual(["L1", "L2"]);
    expect(left.opts).toEqual({ x: 0.8, y: 1.5, w: 5.8, h: 5.5, valign: "top" });
    expect(right.items.map((b) => b.text)).toEqual(["R1"]);
    expect(right.opts).toEqual({ x: 7, y: 1.5, w: 5.8, h: 5.5, valign: "top" });
    expect(shapesOfType(slide, "line")).toEqual([
      { type: "line", opts: { x: 6.5, y: 1.5, w: 0, h: 5, line: { color: "E8E6DC", width: 1 } } },
    ]);
  });

  it("renders two columns when a text slide carries two column arrays", () => {
    const slide = exportOne({ type: "text", columns: COLUMNS });

    expect(shapesOfType(slide, "line")).toHaveLength(1);
  });

  it("falls back to the content layout when only one column is present", () => {
    const slide = exportSlides([malformed({ type: "text", columns: [["only"]] })]).slides[0];

    expect(shapesOfType(slide, "line")).toHaveLength(0);
    expect(usesContentLayout(slide)).toBe(true);
  });

  it("falls back to the content layout when a two-column slide has no columns", () => {
    const slide = exportOne({ type: "two-column", content: [{ text: "Fallback bullet" }] });

    expect(shapesOfType(slide, "line")).toHaveLength(0);
    expect(bulletBlocks(slide)[0].items.map((b) => b.text)).toEqual(["Fallback bullet"]);
  });

  it("renders empty text for left column items that are not strings", () => {
    const slide = exportSlides([
      malformed({ type: "two-column", columns: [[{ text: "object item" }], ["ok"]] }),
    ]).slides[0];
    const [left, right] = bulletBlocks(slide);

    expect(left.items.map((b) => b.text)).toEqual([""]);
    expect(right.items.map((b) => b.text)).toEqual(["ok"]);
  });

  it("renders empty text for right column items that are not strings", () => {
    const slide = exportSlides([
      malformed({ type: "two-column", columns: [["ok"], [{ text: "object item" }]] }),
    ]).slides[0];
    const [left, right] = bulletBlocks(slide);

    expect(left.items.map((b) => b.text)).toEqual(["ok"]);
    expect(right.items.map((b) => b.text)).toEqual([""]);
  });

  it("omits the left block when the left column is empty", () => {
    const slide = exportOne({ type: "two-column", columns: [[], ["R1"]] });
    const blocks = bulletBlocks(slide);

    expect(blocks).toHaveLength(1);
    expect(blocks[0].opts).toMatchObject({ x: 7 });
  });

  it("omits the right block when the right column is empty", () => {
    const slide = exportOne({ type: "two-column", columns: [["L1"], []] });
    const blocks = bulletBlocks(slide);

    expect(blocks).toHaveLength(1);
    expect(blocks[0].opts).toMatchObject({ x: 0.8 });
  });
});

describe("exportToPptx quote slides", () => {
  it("renders the quote card, mark, text and author when a quote has text and author", () => {
    const slide = exportOne({ type: "quote", quote: { text: "Stay hungry", author: "Jobs" } });

    expect(shapesOfType(slide, "roundRect")).toEqual([
      {
        type: "roundRect",
        opts: { x: 1.5, y: 1.5, w: 10, h: 4.5, fill: { color: "F5F4ED" }, rectRadius: 0.15, line: { color: "E8E6DC", width: 1 } },
      },
    ]);
    expect(textOpts(slide, "\u201C")).toEqual({
      x: 2, y: 1.8, w: 1.5, h: 1.5, fontSize: 60, color: "C96442", bold: true, fontFace: "Georgia",
    });
    expect(textOpts(slide, "Stay hungry")).toEqual({
      x: 2.5, y: 2.8, w: 8, h: 2,
      fontSize: 18, color: "141413", italic: true, align: "center", valign: "middle", fontFace: "Georgia",
    });
    expect(textOpts(slide, "\u2014 Jobs")).toEqual({
      x: 2.5, y: 5, w: 8, h: 0.5, fontSize: 13, color: "C96442", align: "center",
    });
  });

  it("omits the author line when the quote has an empty author", () => {
    const slide = exportOne({ type: "quote", quote: { text: "Stay hungry", author: "" } });

    expect(plainTexts(slide)).toEqual(["\u201C", "Stay hungry", "1 / 1"]);
  });

  it("renders a quote when a text slide carries a quote with text", () => {
    const slide = exportOne({ type: "text", quote: { text: "Less is more", author: "Mies" } });

    expect(plainTexts(slide)).toContain("\u201C");
    expect(plainTexts(slide)).toContain("\u2014 Mies");
  });

  it("uses the first content item as the quote when a quote slide has no quote object", () => {
    const slide = exportOne({ type: "quote", content: [{ text: "From content" }, { text: "ignored" }] });

    expect(plainTexts(slide)).toEqual(["\u201C", "From content", "1 / 1"]);
  });

  it("renders an empty quote text when a quote slide has neither quote nor content", () => {
    const slide = exportOne({ type: "quote", content: [] });

    expect(plainTexts(slide)).toEqual(["\u201C", "", "1 / 1"]);
  });

  it("does not treat a text slide as a quote when the quote text is empty", () => {
    const slide = exportOne({ type: "text", quote: { text: "", author: "Nobody" } });

    expect(usesContentLayout(slide)).toBe(true);
    expect(plainTexts(slide)).not.toContain("\u2014 Nobody");
  });
});

describe("exportToPptx layout routing precedence", () => {
  const everything: Partial<Slide> = {
    chartData: chart("bar"),
    tableData: LABELS_TABLE,
    comparisonData: COMPARISON,
    columns: [["L"], ["R"]],
    quote: { text: "Q", author: "A" },
  };

  it("prefers the title layout over every data payload when type is title", () => {
    const slide = exportOne({ ...everything, type: "title" });

    expect(slide.charts).toHaveLength(0);
    expect(slide.tables).toHaveLength(0);
    expect(slide.shapes).toContainEqual(expect.objectContaining({ opts: expect.objectContaining({ w: 4.5, h: 7.5 }) }));
  });

  it("prefers the chart over table, comparison, columns and quote when all payloads exist", () => {
    const slide = exportOne({ ...everything, type: "text" });

    expect(slide.charts).toHaveLength(1);
    expect(slide.tables).toHaveLength(0);
    expect(plainTexts(slide)).not.toContain("VS");
  });

  it("prefers the table over comparison, columns and quote when no chart exists", () => {
    const { chartData: _chart, ...rest } = everything;
    const slide = exportOne({ ...rest, type: "text" });

    expect(slide.tables).toHaveLength(1);
    expect(plainTexts(slide)).not.toContain("VS");
  });

  it("prefers the comparison over columns and quote when no chart or table exists", () => {
    const slide = exportOne({
      type: "text",
      comparisonData: COMPARISON,
      columns: [["L"], ["R"]],
      quote: { text: "Q", author: "A" },
    });

    expect(plainTexts(slide)).toContain("VS");
    expect(shapesOfType(slide, "line")).toHaveLength(0);
  });

  it("prefers the two-column layout over the quote when no earlier payload exists", () => {
    const slide = exportOne({ type: "text", columns: [["L"], ["R"]], quote: { text: "Q", author: "A" } });

    expect(shapesOfType(slide, "line")).toHaveLength(1);
    expect(plainTexts(slide)).not.toContain("\u201C");
  });

  it("lets valid table data on an earlier route override a later explicit quote type", () => {
    const slide = exportOne({ type: "quote", quote: { text: "Q", author: "A" }, tableData: LABELS_TABLE });

    expect(slide.tables).toHaveLength(1);
    expect(plainTexts(slide)).not.toContain("\u201C");
  });

  it("builds each slide with its own layout when a deck mixes slide kinds", () => {
    const pres = exportSlides([
      makeSlide({ type: "title" }),
      makeSlide({ type: "chart", chartData: chart("bar") }),
      makeSlide({ type: "table", tableData: LABELS_TABLE }),
      makeSlide({ type: "quote", quote: { text: "Q", author: "" } }),
    ]);

    expect(pres.slides.map((s) => [s.charts.length, s.tables.length])).toEqual([
      [0, 0],
      [1, 0],
      [0, 1],
      [0, 0],
    ]);
    expect(plainTexts(pres.slides[3])).toContain("4 / 4");
  });
});

describe("exportToPptx malformed input", () => {
  it("throws a TypeError and writes nothing when slides is missing", () => {
    expect(() => exportToPptx({} as unknown as SlideData)).toThrow(TypeError);
    expect(presentations[0].written).toEqual([]);
  });

  it("throws a TypeError and writes nothing when comparison items are missing", () => {
    const bad = malformed({
      type: "comparison",
      comparisonData: { left: { title: "L" }, right: { title: "R", items: [] } },
    });

    expect(() => exportToPptx({ slides: [bad] })).toThrow(TypeError);
    expect(presentations[0].written).toEqual([]);
  });
});
