---
name: file-extraction
display_name: File Extraction (PDF, Word, Excel, PowerPoint)
description: Read uploaded PDF, Word, Excel and PowerPoint files — inventory the uploads, extract only what the request needs, look at the page images, and cite pages honestly.
category: workflow
isBeta: false
tags:
- pdf
- docx
- xlsx
- pptx
- documents
---

# File Extraction

Uploaded documents land in `.uploads/`. Nothing reads them for you: a `.pdf`,
`.docx`, `.xlsx` or `.pptx` is a binary container, and `read_file` on one returns
bytes. This skill covers turning those four formats into text and page images you
can actually reason about.

## When to Activate

- The run has uploads and the request depends on what is inside them.
- Someone refers to "the guide", "the rate sheet", "the deck" — a document you
  have not opened.
- You are about to answer a question about a document whose contents you have
  only inferred from its filename.

## Prerequisite

The step must be granted the `file_extract` tool group. Without it these four
tools are simply absent — nothing errors, they are not in your tool list:

| Tool | Cost | What it does |
|---|---|---|
| `file_info()` | free, writes nothing | Every upload with the route it takes |
| `extract_text(path)` | writes to disk | Materialises one document |
| `file_find(query)` | cheap | Locates a string across what is already materialised |
| `file_page_image(...)` | cheap | Fetches one page's rendered crop |

## The one rule that decides your cost

**Inventory before you extract.** `extract_text()` on a large PDF materialises
every page and every image on it — a real 21-page document is roughly 22,000
tokens for whoever reads it next. Extracting five uploads when the request
concerns one is money spent on pages nobody opens.

So: `file_info()` first, then extract only what the request implicates.

- Named or quoted directly → extract it.
- Clearly the subject of the request → extract it.
- Present but unrelated → **do not extract it.** Note it as available and move on.
- Genuinely ambiguous which of several files is meant → extract the candidates
  rather than guessing. A wasted extraction is cheaper than an answer built on
  the wrong document.

## What `extract_text` gives back

One entry point, three outcomes. You do not have to know which in advance.

**Plain text** (`.txt`, `.md`, `.csv`, `.json`) — the content is in the tool
result itself. Nothing was written to disk, so there is no folder for anyone to
read later. Quote what matters directly.

**Paged** (`.pdf`, `.docx`, `.xlsx`, `.pptx`) — you get a receipt, never the
content. It names a `document.md` under `.extract/{format}/{slug}/` and how many
pages there are. Read that path when you need the text; point at it when someone
else needs it.

**Unsupported** — a refusal naming the type. Report it as unreadable. Do not
retry it and do not invent its contents.

## Looking at the pictures

Page crops do **not** arrive on the turn you extract — nothing was on disk when
that message was built. They appear on your **next** turn, attached as images.
The order is: extract, then look.

- On the turn where crops are attached, read them and fold in what they show:
  which control an arrow points at, what a chart says, what a dialog asks. This
  is the part of a document its text does not carry.
- A `@[[image-N.png]]` marker in the text is a placeholder for where a picture
  sits. It is not a link. **Never describe a picture you have not been shown.**
- Every attached image is re-sent on every later turn. Once you have described
  what the pictures show, stop looping — a long tool loop after extraction
  re-sends the whole image set each time.

## The caveat that misleads people

A `.docx`, `.xlsx` or `.pptx` is converted to PDF before extraction, so its pages
are paginated **by the converter, not by the authoring application**. The receipt
tells you when this happened. Cite such a page as "page 4 as converted" — Word or
PowerPoint may well disagree about where page 4 begins, and citing it as though
they agree is a quiet way to be wrong.

A spreadsheet is the sharpest case. It has no pages at all until something
paginates it, and adjacent column values can run together in the extracted text.
Treat an `.xlsx` page number as an artefact of conversion, and never present its
extracted rows as though they were cell-addressed.

## What not to do

- **Do not pull a whole `document.md` into context to answer a narrow question.**
  `file_find` exists for that. A 200-page document read whole to find one clause
  is the most expensive mistake available here.
- **Do not repeat a document's text back in full.** Cite the path and the page.
- **Do not extract on speculation.** If the request does not touch a file, leave
  it on disk.
