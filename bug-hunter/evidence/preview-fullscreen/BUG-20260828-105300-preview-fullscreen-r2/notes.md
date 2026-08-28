# Notes — phantom "Via Node.js" file entry

Source deliverable excerpt (via `GET /api/runs/37aabc96-6e71-4d2b-ac30-90a827c8b862`,
`agent_outputs[0].output`), confirming "Via Node.js" is a markdown `###` subheading with a
fenced code sample inside the generated README, not a project file:

```
### Via Node.js

```javascript
const http = require('http');

http.get('http://localhost:3000/api/hello', (res) => {
  let data = '';
  res.on('data', chunk => data += chunk);
  res.on('end', () => console.log(JSON.parse(data)));
});
```
```

Client-side confirmation: `frontend/src/components/preview/AppBuilderPreview.tsx:248-254`
(`handleDownload`) sets `a.download = file.name` directly from the parsed file's `name` field
with no sanitization/extension fallback — so whatever the (buggy) file-list builder produced as
`name`/`path` for this phantom entry is used verbatim as the saved filename.

Reproduced twice via Playwright's `download.suggestedFilename()` on the individual per-file
Download button inside the genuine `/preview-fullscreen` popup tab (opened via the real
`AppBuilderPreview.handleFullscreen()` "Full Screen" button, not a hand-seeded payload):
both times `"Via Node.js"`.

Real run used: `37aabc96-6e71-4d2b-ac30-90a827c8b862` ("A hello world app.", App Builder, Done).

Also confirmed the phantom entry pollutes "Download ZIP" — the ZIP contains a top-level
`Via Node.js` entry (203 bytes, no extension) alongside the 3 real markdown files.
