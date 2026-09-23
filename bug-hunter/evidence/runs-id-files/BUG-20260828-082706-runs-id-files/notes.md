# File size mismatch — displayed sizes are string-length, not byte-length

Run `b9feac1c-ec21-4531-8ba7-bb391786993e`, Files tab. Each row was downloaded via its
"Download <file>" button (Playwright `Downloaded file ...` events, filenames unchanged), then
measured with `wc -c` (true byte length) and cross-checked against JS UTF-16 code-unit length
(what `string.length` would report) using Python:

```python
s = open(path, encoding='utf-8').read()
byte_len = len(s.encode('utf-8'))
js_length = len(s)   # == JS .length for this content (no astral chars)
```

| Row (Files tab) | UI-declared size | Actual bytes on disk (`wc -c`) | `.length`-style char count | UI matches |
|---|---|---|---|---|
| `prompt.md` (Run input) | 620 B | 626 B | 620 | char count, not bytes |
| `01-presentation-strategist-agent.md` | 9.5 KB | 9845 B (9.62 KB) | 9686 (9.46 KB) | char count |
| `02-deck-engineer-agent.md` | 55.1 KB | 56564 B (55.24 KB) | 56398 (55.08 KB) | char count |
| `04-pptx-code-generator.md` | 28.8 KB | 29584 B (28.89 KB) | 29459 (28.77 KB) | char count |

`03-deck-qa-agent.md` was excluded from the table because its true-byte and char-count roundings
happen to coincide at 1.5 KB — not usable as independent evidence, but consistent with the same
pattern (1548 B vs 1544 chars).

Root cause: every file in this run's content contains a handful of multi-byte UTF-8 characters
(em dash `—`, right-arrow `→`) coming from LLM-generated text. A UTF-8 multi-byte character is 1
JS UTF-16 code unit but 2–4 bytes on disk. The Files tab's size label is computed from the
in-memory string's `.length` (or an equivalent character count) rather than the actual byte size
of the file being offered for download, so every row understates its real size by a few bytes to
several hundred bytes depending on how many non-ASCII characters the content contains.
