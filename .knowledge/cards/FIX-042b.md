---
id: FIX-042b
type: fix
date: 2026-07-08
status: done
area: [backend, runtime]
files:
  - backend/app/services/od_loader.py
summary: >-
  GET /api/{prototype,ppt}/templates/{id}/thumbnail returns 500 (not 404) when a
  thumbnail file is missing at request time
source: .planning/FIX-REGISTER.md#fix-042
collision_of: FIX-042
invariants: [INV-1, INV-3, INV-12, SC-001]
relates: [FIX-039]
---

# FIX-042b

> **Reused id.** The register uses `FIX-042` for more than one unrelated
> fix. This card is one of them; the suffix exists only here, so that one card
> means one fix. The register itself is unchanged — see `source:`.

**Phase / trigger:** Phase 4 (OD catalog UI) · builds on FIX-039/040/041

> No detail section exists in the register for this entry — only the
> summary-table row below. Nothing has been invented to fill the gap.

## Description

GET /api/{prototype,ppt}/templates/{id}/thumbnail returns 500 (not 404) when a thumbnail file is missing at request time

## Root cause

get_template_thumbnail_path trusted the has_thumbnail flag, which is computed once by the lru_cache(maxsize=1) _all_templates() at process start. A thumbnail deleted (or generated) after startup left the flag stale → the function returned a path to a missing file → FileResponse os.stat'd it mid-response → FileNotFoundError → RuntimeError: File ... does not exist → 500. Fix (backend-only): re-check path.is_file() on disk at serve time; return None (→ existing 404 branch) when the file is gone, so the gallery falls back to the FIX-041 live iframe.

## Files changed

- `backend/app/services/od_loader.py`
