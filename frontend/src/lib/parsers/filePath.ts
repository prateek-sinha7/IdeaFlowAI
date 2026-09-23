// ─── ISS-323 — shared file-path plausibility guard ────────────────────────────
// The markdown file-list parsers (PreviewPanel's parseAppBuilderFilesForIDE,
// FilesTab's parseCodeFiles, WorkflowHistory's parseFilesForIDE) label a fenced
// block as a project file from a `### heading` or a **bold** line before it.
// Those regexes match a documentation heading like `### Via Node.js` exactly as
// well as a real `### src/app.js`, and the "last segment contains a dot" check
// accepts it purely because of the dot in "Node.js" — so a prose subheading
// becomes a phantom file that downloads extensionless, named "Via Node.js".
// A generated file path never contains whitespace; a prose heading nearly always
// does, which is the one cheap signal that separates them.
export function isPlausibleFilePath(path: string): boolean {
  return !/\s/.test(path);
}
