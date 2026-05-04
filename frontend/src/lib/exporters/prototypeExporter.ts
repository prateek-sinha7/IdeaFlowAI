/**
 * Takes prototype JSON content and downloads as .json file.
 */
export function exportPrototype(content: string, filename?: string): void {
  const outputFilename = filename || "prototype";

  // Pretty-print the JSON if possible
  let formattedContent = content;
  try {
    const parsed = JSON.parse(content);
    formattedContent = JSON.stringify(parsed, null, 2);
  } catch {
    // If it's not valid JSON, export as-is
  }

  const blob = new Blob([formattedContent], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);

  const link = document.createElement("a");
  link.href = url;
  link.download = `${outputFilename}.json`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
