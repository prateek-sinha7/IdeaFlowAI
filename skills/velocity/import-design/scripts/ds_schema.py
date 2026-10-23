"""Read the token contract from design-systems/_schema/tokens.schema.ts.

The .ts file is the single source of truth. Nothing here hard-codes token names.
"""

from __future__ import annotations

import re
from pathlib import Path

ENTRY_RE = re.compile(r"\{\s*name:\s*\"(--[\w-]+)\"\s*,\s*layer:\s*\"([\w-]+)\"(.*?)\}", re.S)
FIELD_RE = {
    "fallback": re.compile(r"fallback:\s*(['\"])(.*?)\1", re.S),
    "aliasTo": re.compile(r"aliasTo:\s*(['\"])(.*?)\1", re.S),
    "description": re.compile(r"description:\s*\"(.*?)\"", re.S),
}
DECL_RE = re.compile(r"(--[\w-]+)\s*:\s*([^;]+);")


def od_root_from(path: Path) -> Path:
    """Walk up from a design-systems/<id> (or design-systems) path to the od root."""
    p = path.resolve()
    for cand in [p, *p.parents]:
        if (cand / "design-systems" / "_schema" / "tokens.schema.ts").is_file():
            return cand
    raise SystemExit(f"no design-systems/_schema/tokens.schema.ts above {path}")


def load_schema(od_root: Path | str) -> dict:
    """Token schema from <od_root>/design-systems/_schema/tokens.schema.ts (str or Path)."""
    od_root = Path(od_root)
    text = (od_root / "design-systems" / "_schema" / "tokens.schema.ts").read_text(encoding="utf-8")
    body = text.split("export const TOKEN_SCHEMA", 1)[1].split("];", 1)[0]
    tokens = []
    for m in ENTRY_RE.finditer(body):
        t = {"name": m.group(1), "layer": m.group(2)}
        for k, r in FIELD_RE.items():
            f = r.search(m.group(3))
            if f:
                t[k] = f.group(2) if k != "description" else f.group(1)
        tokens.append(t)
    ext_block = text.split("export const BRAND_EXTENSIONS", 1)[1].split("};", 1)[0]
    extensions: dict[str, list[str]] = {}
    for bm in re.finditer(r"([\w-]+|\"[\w-]+\")\s*:\s*\[(.*?)\]", ext_block, re.S):
        extensions[bm.group(1).strip('"')] = re.findall(r"\"(--[\w-]+)\"", bm.group(2))
    pref_block = text.split("export const BRAND_EXTENSION_PREFIXES", 1)[1].split("];", 1)[0]
    prefixes = re.findall(r"\"(--[\w-]+)\"", pref_block)
    return {"tokens": tokens, "extensions": extensions, "prefixes": prefixes}


def root_decls(css: str) -> dict[str, str]:
    """Declarations of the FIRST plain :root block, in order."""
    clean = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    m = re.search(r"(?<![\w\]\)-]):root\s*\{([^}]*)\}", clean)
    if not m:
        return {}
    return {k: " ".join(v.split()) for k, v in DECL_RE.findall(m.group(1))}
