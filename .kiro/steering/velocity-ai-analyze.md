---
inclusion: manual
---

# Legacy command redirect: `/velocity-ai-analyze`

`/velocity-ai-analyze` is retired. Use `/velocity analyze <symptom>` instead.

The canonical `analyze` workflow primes the current knowledge store, semantically shortlists cards from `.knowledge/INDEX.md`, follows only relevant card and module links, and proves conclusions against source code. It is read-only until the separate fix workflow is explicitly invoked.

For a non-bug file or architecture lookup, use `/velocity prime`, select the relevant module in `.knowledge/CONTEXT.md`, then use `.knowledge/INDEX.md` to open only applicable cards. The former cache-query interface and `.knowledge/surface/` artifacts are retired.
