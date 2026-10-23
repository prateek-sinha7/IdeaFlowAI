"""Read the token contract from design-systems/_schema/tokens.schema.ts.

Modified from import-design/scripts/ds_schema.py to support the
OD_SCHEMA_PATH environment variable, which allows sandbox-compatible
operation without needing the full skills/opendesign/ catalog present.

OD_SCHEMA_PATH: if set, the directory containing tokens.schema.ts directly
                (e.g. "skills/figma-ingestor/scripts/schema").
                Falls back to walking up the directory tree otherwise.
"""

from __future__ import annotations

import os
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
    """Walk up from a design-systems/<id> (or design-systems) path to the od root.

    Checks OD_SCHEMA_PATH env var first.  If set to a directory that
    directly contains tokens.schema.ts, returns a synthetic root so that
    the file is found at <root>/design-systems/_schema/tokens.schema.ts.
    """
    env_path = os.environ.get("OD_SCHEMA_PATH")
    if env_path:
        p = Path(env_path).resolve()
        if (p / "tokens.schema.ts").is_file():
            # Synthesize an od_root where design-systems/_schema/ resolves to p.
            # p is already the _schema dir equivalent, so return p.parent.parent
            # such that od_root / "design-systems" / "_schema" / "tokens.schema.ts"
            # points at the real file.
            # We create a temporary symlink structure is not needed —
            # load_schema calls:  (od_root / "design-systems" / "_schema" / "tokens.schema.ts").read_text()
            # So we need to return a synthetic root where that path resolves.
            # Strategy: wrap the schema lookup in load_schema instead.
            return _SyntheticRoot(p)  # type: ignore[return-value]

    p = path.resolve()
    for cand in [p, *p.parents]:
        if (cand / "design-systems" / "_schema" / "tokens.schema.ts").is_file():
            return cand
    raise SystemExit(f"no design-systems/_schema/tokens.schema.ts above {path}")


class _SyntheticRoot:
    """A path-like object that resolves design-systems/_schema/ to a real dir."""

    def __init__(self, schema_dir: Path) -> None:
        self._schema_dir = schema_dir

    def __truediv__(self, other: str) -> Path:
        # Intercept "design-systems" / "_schema" / "tokens.schema.ts"
        parts = Path(other).parts
        if parts and parts[0] == "design-systems":
            # Route to the bundled schema directory
            remainder = parts[1:]  # ("_schema", "tokens.schema.ts") or subset
            if remainder and remainder[0] == "_schema":
                return self._schema_dir / Path(*remainder[1:]) if len(remainder) > 1 else self._schema_dir
        return Path(str(self._schema_dir.parent.parent)) / other


def load_schema(od_root: "Path | _SyntheticRoot | str") -> dict:
    """Token schema from <od_root>/design-systems/_schema/tokens.schema.ts."""
    if isinstance(od_root, _SyntheticRoot):
        # Use the synthetic root's schema dir directly
        schema_path = od_root._schema_dir / "tokens.schema.ts"
    else:
        od_root = Path(od_root)
        schema_path = od_root / "design-systems" / "_schema" / "tokens.schema.ts"

    text = schema_path.read_text(encoding="utf-8")
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
