import pptxgen from "pptxgenjs";
import type { SlideData, Slide } from "@/types";

// Enterprise color palette
const COLORS = {
  primary: "1E3A5F",      // Dark navy
  secondary: "C96442",    // Terracotta accent
  dark: "141413",         // Near black text
  medium: "5E5D59",       // Medium gray
  light: "87867F",        // Light gray
  bg: "FFFFFF",           // White
  bgAlt: "F5F4ED",       // Warm parchment
  bgCard: "FAF9F5",      // Ivory
  border: "E8E6DC",      // Cream border
  success: "10B981",      // Green
  chart1: "C96442",       // Terracotta
  chart2: "1E3A5F",       // Navy
  chart3: "10B981",       // Green
  chart4: "8B5CF6",       // Purple
  chart5: "F59E0B",       // Amber
};

// Shape type constants (pptxgenjs uses string literals internally)
const SHAPE_RECT = "rect" as pptxgen.ShapeType;
const SHAPE_ROUNDED_RECT = "roundRect" as pptxgen.ShapeType;
const SHAPE_LINE = "line" as pptxgen.ShapeType;

/**
 * Map chart type string to pptxgenjs CHART_NAME
 */
function getChartType(type: string): pptxgen.CHART_NAME {
  switch (type) {
    case "pie": return "pie" as pptxgen.CHART_NAME;
    case "line": return "line" as pptxgen.CHART_NAME;
    case "bar": return "bar" as pptxgen.CHART_NAME;
    case "doughnut": return "doughnut" as pptxgen.CHART_NAME;
    case "area": return "area" as pptxgen.CHART_NAME;
    default: return "bar" as pptxgen.CHART_NAME;
  }
}

/**
 * Professional PPT exporter using pptxgenjs.
 * Enterprise-grade styling with proper layouts, charts, tables, and shapes.
 */
export function exportToPptx(slideData: SlideData, filename?: string): void {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE"; // 13.3" x 7.5"
  pres.author = "IdeaFlow AI";

  // Derive filename from first slide title if not provided
  const derivedName = filename || (slideData.slides[0]?.title
    ? slideData.slides[0].title.replace(/[^a-zA-Z0-9\s-]/g, "").trim().replace(/\s+/g, "-").slice(0, 50)
    : "Presentation");
  pres.title = derivedName;

  for (let i = 0; i < slideData.slides.length; i++) {
    const slideInfo = slideData.slides[i];
    const slide = pres.addSlide();

    // White background for all slides
    slide.background = { color: COLORS.bg };

    // Add accent bar at top
    slide.addShape(SHAPE_RECT, {
      x: 0, y: 0, w: 13.3, h: 0.08,
      fill: { color: COLORS.secondary },
    });

    // Route by slide type AND data presence (handles mismatched type strings)
    const hasChart = slideInfo.chartData && slideInfo.chartData.labels && slideInfo.chartData.values && slideInfo.chartData.labels.length > 0;
    const hasTable = slideInfo.tableData && slideInfo.tableData.headers && slideInfo.tableData.headers.length > 0;
    const hasComparison = slideInfo.comparisonData && slideInfo.comparisonData.left && slideInfo.comparisonData.right;
    const hasColumns = slideInfo.columns && slideInfo.columns.length >= 2;
    const hasQuote = slideInfo.quote && slideInfo.quote.text;

    if (slideInfo.type === "title") {
      buildTitleSlide(pres, slide, slideInfo, i === 0);
    } else if (slideInfo.type === "chart" || hasChart) {
      buildChartSlide(pres, slide, slideInfo);
    } else if (slideInfo.type === "table" || hasTable) {
      buildTableSlide(pres, slide, slideInfo);
    } else if (slideInfo.type === "comparison" || hasComparison) {
      buildComparisonSlide(pres, slide, slideInfo);
    } else if (slideInfo.type === "two-column" || hasColumns) {
      buildTwoColumnSlide(pres, slide, slideInfo);
    } else if (slideInfo.type === "quote" || hasQuote) {
      buildQuoteSlide(pres, slide, slideInfo);
    } else {
      buildContentSlide(pres, slide, slideInfo);
    }

    // Speaker notes
    if (slideInfo.speakerNotes) {
      slide.addNotes(slideInfo.speakerNotes);
    }

    // Footer: slide number + branding
    slide.addText(`${i + 1} / ${slideData.slides.length}`, {
      x: 11.5, y: 7.0, w: 1.5, h: 0.4,
      fontSize: 9, color: COLORS.light, align: "right",
    });
    slide.addShape(SHAPE_RECT, {
      x: 0, y: 7.3, w: 13.3, h: 0.2,
      fill: { color: COLORS.bgAlt },
    });
  }

  pres.writeFile({ fileName: `${derivedName}.pptx` });
}

function buildTitleSlide(pres: pptxgen, slide: pptxgen.Slide, data: Slide, isFirst: boolean) {
  const highlights = (data.content || []).slice(0, 3);

  if (isFirst) {
    // Hero title slide with large accent shape
    slide.addShape(SHAPE_RECT, {
      x: 0, y: 0, w: 4.5, h: 7.5,
      fill: { color: COLORS.primary },
    });
    slide.addText(data.title, {
      x: 5, y: 1.5, w: 7.5, h: 2,
      fontSize: 32, bold: true, color: COLORS.dark, fontFace: "Arial",
      charSpacing: 1,
    });
    // Accent line
    slide.addShape(SHAPE_RECT, {
      x: 5, y: 3.5, w: 2, h: 0.05,
      fill: { color: COLORS.secondary },
    });
    if (data.subtitle) {
      slide.addText(data.subtitle, {
        x: 5, y: 3.8, w: 7.5, h: 1,
        fontSize: 16, color: COLORS.medium, fontFace: "Arial",
      });
    }
    // Key stats/highlights on the navy panel
    if (highlights.length > 0) {
      highlights.forEach((h, i) => {
        slide.addShape(SHAPE_ROUNDED_RECT, {
          x: 0.4, y: 4.5 + i * 0.9, w: 3.7, h: 0.7,
          fill: { color: "FFFFFF", transparency: 85 },
          rectRadius: 0.05,
        });
        slide.addText(h.text, {
          x: 0.6, y: 4.55 + i * 0.9, w: 3.3, h: 0.6,
          fontSize: 11, color: "FFFFFF", fontFace: "Arial", bold: true,
        });
      });
    }
  } else {
    // Closing/section title
    slide.addText(data.title, {
      x: 1.5, y: 2.0, w: 10, h: 1.5,
      fontSize: 28, bold: true, color: COLORS.dark, align: "center", fontFace: "Arial",
    });
    slide.addShape(SHAPE_RECT, {
      x: 5.5, y: 3.5, w: 2, h: 0.04,
      fill: { color: COLORS.secondary },
    });
    if (data.subtitle) {
      slide.addText(data.subtitle, {
        x: 2, y: 3.8, w: 9, h: 1,
        fontSize: 16, color: COLORS.medium, align: "center",
      });
    }
    // Key takeaways as bullets below
    if (highlights.length > 0) {
      const bullets: pptxgen.TextProps[] = highlights.map((h) => ({
        text: h.text,
        options: { fontSize: 13, color: COLORS.dark, bullet: true, breakLine: true, paraSpaceAfter: 6, align: "center" as const },
      }));
      slide.addText(bullets, {
        x: 2.5, y: 5.0, w: 8, h: 2, valign: "top",
      });
    }
  }
}

function buildContentSlide(pres: pptxgen, slide: pptxgen.Slide, data: Slide) {
  // Title
  slide.addText(data.title, {
    x: 0.8, y: 0.4, w: 11, h: 0.8,
    fontSize: 22, bold: true, color: COLORS.dark, fontFace: "Arial", margin: 0,
  });
  // Title underline
  slide.addShape(SHAPE_RECT, {
    x: 0.8, y: 1.15, w: 1.5, h: 0.04,
    fill: { color: COLORS.secondary },
  });

  // Subtitle
  if (data.subtitle) {
    slide.addText(data.subtitle, {
      x: 0.8, y: 1.3, w: 11, h: 0.5,
      fontSize: 13, color: COLORS.medium, italic: true,
    });
  }

  // Bullets
  const bullets: pptxgen.TextProps[] = [];
  for (const item of data.content || []) {
    bullets.push({
      text: item.text,
      options: { fontSize: 15, color: COLORS.dark, bullet: true, breakLine: true, paraSpaceAfter: 8 },
    });
    if (item.subPoints) {
      for (const sub of item.subPoints) {
        bullets.push({
          text: sub,
          options: { fontSize: 12, color: COLORS.medium, bullet: true, indentLevel: 1, breakLine: true, paraSpaceAfter: 4 },
        });
      }
    }
  }

  if (bullets.length > 0) {
    slide.addText(bullets, {
      x: 0.8, y: data.subtitle ? 2.0 : 1.5, w: 11.5, h: 5, valign: "top",
    });
  }
}

function buildChartSlide(pres: pptxgen, slide: pptxgen.Slide, data: Slide) {
  // Title
  slide.addText(data.title, {
    x: 0.8, y: 0.4, w: 11, h: 0.7,
    fontSize: 20, bold: true, color: COLORS.dark, fontFace: "Arial",
  });
  slide.addShape(SHAPE_RECT, {
    x: 0.8, y: 1.05, w: 1.5, h: 0.04,
    fill: { color: COLORS.secondary },
  });

  if (data.chartData) {
    const chartColors = [COLORS.chart1, COLORS.chart2, COLORS.chart3, COLORS.chart4, COLORS.chart5];
    const chartData = [{
      name: data.chartData.title || "Data",
      labels: data.chartData.labels || [],
      values: data.chartData.values || [],
    }];

    const chartType = getChartType(data.chartData.type || "bar");

    slide.addChart(chartType as pptxgen.CHART_NAME, chartData, {
      x: 1.5, y: 1.5, w: 10, h: 5.2,
      showTitle: !!data.chartData.title,
      title: data.chartData.title || "",
      titleColor: COLORS.dark,
      titleFontSize: 12,
      chartColors,
      showValue: true,
      catAxisLabelColor: COLORS.medium,
      valAxisLabelColor: COLORS.medium,
      catAxisLabelFontSize: 10,
      valAxisLabelFontSize: 10,
      showLegend: true,
      legendPos: "b",
      legendFontSize: 9,
      legendColor: COLORS.medium,
    } as pptxgen.IChartOpts);
  } else {
    buildContentSlide(pres, slide, data);
  }
}

function buildTableSlide(pres: pptxgen, slide: pptxgen.Slide, data: Slide) {
  // Title
  slide.addText(data.title, {
    x: 0.8, y: 0.4, w: 11, h: 0.7,
    fontSize: 20, bold: true, color: COLORS.dark, fontFace: "Arial",
  });
  slide.addShape(SHAPE_RECT, {
    x: 0.8, y: 1.05, w: 1.5, h: 0.04,
    fill: { color: COLORS.secondary },
  });

  if (data.tableData) {
    const rows: pptxgen.TableRow[] = [];

    // Header
    if (data.tableData.headers) {
      rows.push(data.tableData.headers.map((h) => ({
        text: h,
        options: { bold: true, color: "FFFFFF", fill: { color: COLORS.primary }, fontSize: 11, align: "center" as const },
      })));
    }

    // Data rows
    if (data.tableData.rows) {
      for (let r = 0; r < data.tableData.rows.length; r++) {
        rows.push(data.tableData.rows[r].map((cell) => ({
          text: cell,
          options: { color: COLORS.dark, fill: { color: r % 2 === 0 ? COLORS.bgCard : COLORS.bg }, fontSize: 11 },
        })));
      }
    }

    if (rows.length > 0) {
      const colCount = rows[0]?.length || 3;
      slide.addTable(rows, {
        x: 0.8, y: 1.4, w: 11.7, h: 5.5,
        fontSize: 11,
        border: { type: "solid", pt: 0.5, color: COLORS.border },
        colW: Array(colCount).fill(11.7 / colCount),
        rowH: Array(rows.length).fill(0.5),
      });
    }
  } else {
    buildContentSlide(pres, slide, data);
  }
}

function buildComparisonSlide(pres: pptxgen, slide: pptxgen.Slide, data: Slide) {
  // Title
  slide.addText(data.title, {
    x: 0.8, y: 0.4, w: 11, h: 0.7,
    fontSize: 20, bold: true, color: COLORS.dark, fontFace: "Arial",
  });
  slide.addShape(SHAPE_RECT, {
    x: 0.8, y: 1.05, w: 1.5, h: 0.04,
    fill: { color: COLORS.secondary },
  });

  if (data.comparisonData) {
    const { left, right } = data.comparisonData;

    // Left card
    slide.addShape(SHAPE_ROUNDED_RECT, {
      x: 0.8, y: 1.5, w: 5.8, h: 5.3,
      fill: { color: COLORS.bgCard }, rectRadius: 0.1,
      line: { color: COLORS.border, width: 1 },
    });
    slide.addText(left.title, {
      x: 1.2, y: 1.8, w: 5, h: 0.6,
      fontSize: 16, bold: true, color: COLORS.secondary,
    });
    const leftBullets: pptxgen.TextProps[] = left.items.map((item) => ({
      text: item,
      options: { fontSize: 13, color: COLORS.dark, bullet: true, breakLine: true, paraSpaceAfter: 6 },
    }));
    if (leftBullets.length > 0) {
      slide.addText(leftBullets, { x: 1.2, y: 2.5, w: 5, h: 4, valign: "top" });
    }

    // Right card
    slide.addShape(SHAPE_ROUNDED_RECT, {
      x: 6.9, y: 1.5, w: 5.8, h: 5.3,
      fill: { color: COLORS.bgCard }, rectRadius: 0.1,
      line: { color: COLORS.border, width: 1 },
    });
    slide.addText(right.title, {
      x: 7.3, y: 1.8, w: 5, h: 0.6,
      fontSize: 16, bold: true, color: COLORS.primary,
    });
    const rightBullets: pptxgen.TextProps[] = right.items.map((item) => ({
      text: item,
      options: { fontSize: 13, color: COLORS.dark, bullet: true, breakLine: true, paraSpaceAfter: 6 },
    }));
    if (rightBullets.length > 0) {
      slide.addText(rightBullets, { x: 7.3, y: 2.5, w: 5, h: 4, valign: "top" });
    }

    // VS divider
    slide.addText("VS", {
      x: 6.1, y: 3.5, w: 1, h: 0.8,
      fontSize: 14, bold: true, color: COLORS.light, align: "center", valign: "middle",
    });
  } else {
    buildContentSlide(pres, slide, data);
  }
}

function buildTwoColumnSlide(pres: pptxgen, slide: pptxgen.Slide, data: Slide) {
  // Title
  slide.addText(data.title, {
    x: 0.8, y: 0.4, w: 11, h: 0.7,
    fontSize: 20, bold: true, color: COLORS.dark, fontFace: "Arial",
  });
  slide.addShape(SHAPE_RECT, {
    x: 0.8, y: 1.05, w: 1.5, h: 0.04,
    fill: { color: COLORS.secondary },
  });

  if (data.columns && data.columns.length >= 2) {
    const leftItems: pptxgen.TextProps[] = (data.columns[0] as string[]).map((item) => ({
      text: typeof item === "string" ? item : "",
      options: { fontSize: 13, color: COLORS.dark, bullet: true, breakLine: true, paraSpaceAfter: 6 },
    }));
    if (leftItems.length > 0) {
      slide.addText(leftItems, { x: 0.8, y: 1.5, w: 5.8, h: 5.5, valign: "top" });
    }

    const rightItems: pptxgen.TextProps[] = (data.columns[1] as string[]).map((item) => ({
      text: typeof item === "string" ? item : "",
      options: { fontSize: 13, color: COLORS.dark, bullet: true, breakLine: true, paraSpaceAfter: 6 },
    }));
    if (rightItems.length > 0) {
      slide.addText(rightItems, { x: 7, y: 1.5, w: 5.8, h: 5.5, valign: "top" });
    }

    // Divider
    slide.addShape(SHAPE_LINE, {
      x: 6.5, y: 1.5, w: 0, h: 5,
      line: { color: COLORS.border, width: 1 },
    });
  } else {
    buildContentSlide(pres, slide, data);
  }
}

function buildQuoteSlide(pres: pptxgen, slide: pptxgen.Slide, data: Slide) {
  const quoteText = data.quote?.text || data.content?.[0]?.text || "";
  const quoteAuthor = data.quote?.author || "";

  // Large quote background shape
  slide.addShape(SHAPE_ROUNDED_RECT, {
    x: 1.5, y: 1.5, w: 10, h: 4.5,
    fill: { color: COLORS.bgAlt }, rectRadius: 0.15,
    line: { color: COLORS.border, width: 1 },
  });

  // Quote mark
  slide.addText("\u201C", {
    x: 2, y: 1.8, w: 1.5, h: 1.5,
    fontSize: 60, color: COLORS.secondary, bold: true, fontFace: "Georgia",
  });

  // Quote text
  slide.addText(quoteText, {
    x: 2.5, y: 2.8, w: 8, h: 2,
    fontSize: 18, color: COLORS.dark, italic: true, align: "center", valign: "middle",
    fontFace: "Georgia",
  });

  // Author
  if (quoteAuthor) {
    slide.addText(`\u2014 ${quoteAuthor}`, {
      x: 2.5, y: 5, w: 8, h: 0.5,
      fontSize: 13, color: COLORS.secondary, align: "center",
    });
  }
}
