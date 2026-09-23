# Contract — the materialised document on disk

**Spec**: [019-file-extract-support](../spec.md) · FR-003 … FR-008a
**Status**: normative. Four components depend on this layout, so it is a contract, not an
implementation detail: the extractor writes it, `pdf_find` reads it, the `pdf_pages` input
provider reads it, and an agent reads `text.md` with `read_file`.

## Layout

```
.extract/                              reserved sandbox prefix, deliverable-excluded
├── pdf/                               ONE DIRECTORY PER SOURCE FORMAT
│   └── {slug}/                        slug: upload filename, extension stripped
│       ├── manifest.json
│       ├── document.md                every completed page concatenated, in order
│       └── pages/
│           ├── 01/
│           │   ├── text.md
│           │   ├── image-1.png
│           │   └── image-2.png
│           └── 02/ …
├── docx/
│   └── {slug}/
│       ├── manifest.json
│       ├── source.pdf                 CONVERTED SOURCES ONLY — the cached soffice
│       │                              output, present iff conversion completed
│       ├── document.md
│       └── pages/ …
├── xlsx/
└── pptx/
```

**The format is a directory level, not a slug suffix** (FR-030). `report.docx` and
`report.pdf` share a slug on purpose and are kept apart by the level above it; with
neither mechanism they name one folder, and each extract discards the other's pages on
the `source_sha256` check — alternating forever. A consumer enumerating documents must
therefore walk **two** levels: one level down finds format directories and no manifests.

**A page directory exists if and only if that page is complete** (FR-007a). There is no
partial state and no marker file. Consumers may treat presence as proof.

## `manifest.json`

```json
{
  "source":         "Inland Marine Creating a Quote 2.pdf",
  "source_sha256":  "<hex>",
  "source_format":  "pdf",
  "converted_by":   null,
  "slug":           "inland-marine-creating-a-quote-2",
  "page_count":     21,
  "scale":          2.0,
  "created_at":     "2026-08-28T13:00:00Z",
  "pages": {
    "1": { "images": ["image-1.png", "image-2.png"], "chars": 1517 },
    "2": { "images": ["image-1.png", "pages/01/image-1.png"], "chars": 555 }
  },
  "totals": { "raw_images": 67, "after_merge": 57, "unique": 50 }
}
```

- `source_sha256` is the hash of **the uploaded file's own bytes** — the `.docx`, never the
  PDF derived from it (FR-029). On open, a mismatch means the whole folder is stale and must
  be discarded (FR-008) — uploads dedupe by filename, so the same name can carry different
  content.
- `source_format` is the uploaded extension (`pdf`, `docx`, `xlsx`, `pptx`). `converted_by`
  is `null` for a native PDF and names the converter otherwise (`"libreoffice"`).
- **A converted document's page numbers are the converter's, not the authoring
  application's** (FR-035). Anything citing a page from a document whose `converted_by` is
  non-null must say so; Word and LibreOffice do not agree on where page 4 begins.
- `slug` is the upload filename with its extension stripped; the containing directory
  names the format. `.extract/docx/` reads as "every Word document this run has
  materialised" (FR-030).
- `page_count` is authoritative for resume: remaining work is
  `set(range(1, page_count+1)) − set(existing page dirs)`.
- An entry in `pages.*.images` is either a **bare filename** (the image lives in this page's
  own directory) or a **repo-relative path under `{slug}/`** (a repeat, stored once on an
  earlier page). Consumers must handle both.

## `text.md`

Layout-aware page text with image placeholders interleaved **in reading order**, derived by
sorting text lines and image bounding boxes on vertical position (FR-004).

```markdown
• In Spinnaker, search for the policy under Specialty Accounts. Search by policy number
  (prefix is not required), policy name, or submission number.

@[[image-2.png]]  <!-- 936x518, 1 source object -->

• Once you have found the applicable account and click on the folder icon under "Trans".

@[[image-3.png]]  <!-- 936x218, 2 source objects -->
```

### Placeholder grammar

```
placeholder := "@[[" ref "]]" [ ws comment ]
ref         := filename | relative-path      ; e.g. image-2.png | pages/01/image-1.png
comment     := "<!--" ws WxH "," ws N "source object" ["s"] ws "-->"
             | "<!-- repeat of" ws relative-path ws "-->"
```

- A placeholder occupies its **own line**, blank-line separated from surrounding text, so a
  line-based reader can find it without parsing markdown.
- `ref` is resolved relative to the page directory; a `ref` containing `/` is relative to
  `{slug}/`.
- **A placeholder is a marker, never a link.** `read_file` on a PNG returns binary garbage;
  the only path from a placeholder to an actual image is the `pdf_pages` input provider.
- The trailing comment is advisory — it exists so a human auditing `text.md` can see the crop
  size and whether fragments were merged. Consumers must not depend on it.

## `image-N.png`

A **crop of the rendered page** at the picture's bounding box — not the embedded image
(FR-005, and §3.1 of the spec for why). Numbering is per page, in reading order, starting at 1.
A repeated picture is written once and later pages reference it by path rather than
re-saving it.

## `document.md`

Every completed page's `text.md`, in page order, separated by:

```
<!-- ================= PAGE {n} ================= -->
```

Placeholder `ref`s inside `document.md` are relative to `{slug}/` (i.e. `pages/NN/image-1.png`),
**not** to a page directory — this is the one place the ref form differs, because there is no
single page directory to be relative to.
