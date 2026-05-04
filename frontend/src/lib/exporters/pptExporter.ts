import pptxgen from "pptxgenjs";
import type { SlideData } from "@/types";

/**
 * Takes SlideData, creates a real .pptx file and triggers download.
 */
export function exportToPptx(slideData: SlideData, filename?: string): void {
  const pptx = new pptxgen();
  pptx.layout = "LAYOUT_WIDE";

  for (const slide of slideData.slides) {
    const pptSlide = pptx.addSlide();

    // Set background color
    if (slide.colorScheme?.background) {
      pptSlide.background = { color: slide.colorScheme.background.replace("#", "") };
    }

    // Add title
    const textColor = slide.colorScheme?.text?.replace("#", "") || "FFFFFF";
    const accentColor = slide.colorScheme?.accent?.replace("#", "") || "AAAAAA";

    pptSlide.addText(slide.title, {
      x: 0.5,
      y: 0.3,
      w: "90%",
      h: 0.8,
      fontSize: 24,
      bold: true,
      color: textColor,
    });

    // Add bullet content
    const bulletTexts: pptxgen.TextProps[] = [];
    for (const bullet of slide.content) {
      bulletTexts.push({
        text: bullet.text,
        options: {
          fontSize: 14,
          color: textColor,
          bullet: true,
          breakLine: true,
        },
      });
      if (bullet.subPoints) {
        for (const sub of bullet.subPoints) {
          bulletTexts.push({
            text: sub,
            options: {
              fontSize: 12,
              color: accentColor,
              bullet: true,
              indentLevel: 1,
              breakLine: true,
            },
          });
        }
      }
    }

    if (bulletTexts.length > 0) {
      pptSlide.addText(bulletTexts, {
        x: 0.5,
        y: 1.3,
        w: "90%",
        h: "70%",
        valign: "top",
      });
    }

    // Add speaker notes if available
    if (slide.speakerNotes) {
      pptSlide.addNotes(slide.speakerNotes);
    }

    // Add slide number in footer
    pptSlide.addText(`${slideData.slides.indexOf(slide) + 1} / ${slideData.slides.length}`, {
      x: "85%",
      y: "92%",
      w: 1.2,
      h: 0.3,
      fontSize: 9,
      color: accentColor,
      align: "right",
    });
  }

  const outputFilename = filename || "presentation";
  pptx.writeFile({ fileName: `${outputFilename}.pptx` });
}
