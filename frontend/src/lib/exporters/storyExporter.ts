/**
 * Takes user story markdown content and downloads as .txt file.
 */
export function exportUserStories(content: string, filename?: string): void {
  const outputFilename = filename || "user-stories";
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);

  const link = document.createElement("a");
  link.href = url;
  link.download = `${outputFilename}.txt`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
