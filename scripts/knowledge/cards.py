"""Shared card loading for the .knowledge/ store.

Zero external dependencies on purpose: this runs anywhere python3 does, and the
frontmatter dialect we accept is deliberately small (see .knowledge/schema.md).

Supported frontmatter forms:
    key: scalar
    key: [a, b, c]
    key:
      - a
      - b
    key: >-
      folded text that
      joins onto one line
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from records import load_records  # type: ignore[import-not-found]

# Primary types are always loaded (INDEX.md). Secondary types are migrated for
# completeness and listed in CATALOG.md, which is read on demand — otherwise the
# always-loaded tier stops being cheap, which is the whole point of the store.
PRIMARY_TYPES = ("decision", "fix", "issue", "phase")
SECONDARY_TYPES = ("bug", "test", "req", "doc", "task")
CARD_TYPES = PRIMARY_TYPES + SECONDARY_TYPES
# Every card lives in ONE flat directory. Type is a field, not a folder — splitting
# by type made the same record reachable by two different paths and meant `--show`
# had to know a card's type before it could find it.
CARDS_DIR = "cards"
TYPE_DIR = {t: CARDS_DIR for t in CARD_TYPES}


# --------------------------------------------------------------------------- paths


def repo_root(start: Path | None = None) -> Path:
    """Git toplevel for `start` (defaults to this file's location)."""
    start = start or Path(__file__).resolve().parent
    out = subprocess.run(
        ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(out.stdout.strip())


def knowledge_dir(root: Path | None = None) -> Path:
    return (root or repo_root()) / ".knowledge"


def cards_dir(root: Path | None = None) -> Path:
    return knowledge_dir(root) / CARDS_DIR


def surface_dir(root: Path | None = None) -> Path:
    """Generated views: the .md humans and agents read, the .json tools filter."""
    return knowledge_dir(root) / "surface"


# Kept as an alias so existing callers keep working after the surface/ move.
def cache_dir(root: Path | None = None) -> Path:
    return surface_dir(root)


# --------------------------------------------------------------- frontmatter parsing


_FM_DELIM = "---"


class CardError(Exception):
    """A card is malformed. Always carries the offending path."""


def _strip_inline_comment(value: str) -> str:
    """Drop a trailing ` # comment`, but never inside quotes."""
    out, quote = [], None
    for i, ch in enumerate(value):
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            out.append(ch)
            continue
        if ch == "#" and i > 0 and value[i - 1] in " \t":
            break
        out.append(ch)
    return "".join(out).rstrip()


def _scalar(value: str):
    value = _strip_inline_comment(value).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    if value in ("true", "false"):
        return value == "true"
    if value in ("null", "~", ""):
        return None
    return value


def _inline_list(value: str) -> list:
    inner = value.strip()[1:-1].strip()
    if not inner:
        return []
    return [_scalar(part) for part in inner.split(",") if part.strip()]


def parse_frontmatter(text: str, path: Path) -> tuple[dict, str]:
    """Return (frontmatter dict, body). Raises CardError on malformed input."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != _FM_DELIM:
        raise CardError(f"{path}: missing opening '---' frontmatter delimiter")

    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == _FM_DELIM)
    except StopIteration:
        raise CardError(f"{path}: unterminated frontmatter (no closing '---')") from None

    data: dict = {}
    i = 1
    while i < end:
        raw = lines[i]
        if not raw.strip() or raw.lstrip().startswith("#"):
            i += 1
            continue
        if raw[0] in " \t":
            raise CardError(f"{path}:{i + 1}: unexpected indentation outside a block")

        m = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", raw)
        if not m:
            raise CardError(f"{path}:{i + 1}: cannot parse frontmatter line: {raw!r}")
        key, rest = m.group(1), m.group(2)

        # folded / literal block scalar
        if rest.strip() in (">-", ">", "|", "|-"):
            fold = rest.strip().startswith(">")
            chunk, i = [], i + 1
            while i < end and (not lines[i].strip() or lines[i][:1] in (" ", "\t")):
                chunk.append(lines[i].strip())
                i += 1
            joined = " ".join(c for c in chunk if c) if fold else "\n".join(chunk)
            data[key] = joined.strip()
            continue

        # inline list
        if rest.strip().startswith("["):
            data[key] = _inline_list(rest)
            i += 1
            continue

        # block list
        if rest.strip() == "":
            items, j = [], i + 1
            while j < end and lines[j].lstrip().startswith("- "):
                items.append(_scalar(lines[j].lstrip()[2:]))
                j += 1
            if j > i + 1:
                data[key] = items
                i = j
                continue
            data[key] = None
            i += 1
            continue

        data[key] = _scalar(rest)
        i += 1

    return data, "\n".join(lines[end + 1 :]).lstrip("\n")


# ------------------------------------------------------------------------ card model


REQUIRED = ("id", "type", "summary_field")
LIST_FIELDS = ("area", "files", "relates", "produces", "supersedes", "derived_from", "enforced_by")


class Card:
    __slots__ = ("path", "fm", "body", "raw_fm")

    def __init__(self, path: Path, fm: dict, body: str, raw_fm: str):
        self.path = path
        self.fm = fm
        self.body = body
        self.raw_fm = raw_fm

    # -- convenience accessors ------------------------------------------------
    @property
    def id(self) -> str:
        return str(self.fm.get("id", "")).strip()

    @property
    def type(self) -> str:
        return str(self.fm.get("type", "")).strip()

    @property
    def status(self) -> str:
        return str(self.fm.get("status", "") or "").strip()

    @property
    def date(self) -> str:
        return str(self.fm.get("date", "") or "").strip()

    @property
    def summary(self) -> str:
        """The one line that lands in INDEX.md / RULES.md.

        Decisions carry a Y-statement in `y:`; history cards carry `summary:`.
        """
        for key in ("summary", "y"):
            val = self.fm.get(key)
            if val:
                return " ".join(str(val).split())
        return ""

    def list_field(self, key: str) -> list[str]:
        val = self.fm.get(key)
        if val is None:
            return []
        if isinstance(val, list):
            return [str(v).strip() for v in val if str(v).strip()]
        return [str(val).strip()]

    @property
    def area(self) -> list[str]:
        return self.list_field("area")

    @property
    def files(self) -> list[str]:
        return self.list_field("files")

    def links(self) -> list[str]:
        out: list[str] = []
        for key in ("relates", "produces", "supersedes", "derived_from"):
            out.extend(self.list_field(key))
        return out

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "type": self.type,
            "status": self.status,
            "date": self.date,
            "area": self.area,
            "files": self.files,
            "summary": self.summary,
            "path": str(self.path_rel),
            "source": self.fm.get("source") or "",
        }
        for key in ("relates", "produces", "supersedes", "derived_from", "enforced_by"):
            vals = self.list_field(key)
            if vals:
                d[key] = vals
        return d

    @property
    def path_rel(self) -> str:
        return f".knowledge/{CARDS_DIR}/{self.path.name}"


def load_card(path: Path) -> Card:
    text = path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text, path)
    raw = text.split(_FM_DELIM, 2)[1] if text.count(_FM_DELIM) >= 2 else ""

    if not fm.get("id"):
        raise CardError(f"{path}: frontmatter is missing required key 'id'")
    if fm.get("type") not in CARD_TYPES:
        raise CardError(
            f"{path}: 'type' must be one of {', '.join(CARD_TYPES)} (got {fm.get('type')!r})"
        )

    card = Card(path, fm, body, raw)
    if not card.summary:
        raise CardError(
            f"{path}: needs a one-line 'summary:' (history) or 'y:' (decision) — "
            "this is the line that appears in the index"
        )
    if not path.name.startswith(card.id):
        raise CardError(f"{path}: filename must start with its id {card.id!r}")
    return card


def load_cards_from_files(root: Path | None = None) -> list[Card]:
    """Scan the per-card .md files. Used by compact.py to fold them into records."""
    kdir = knowledge_dir(root)
    cards: list[Card] = []
    d = kdir / CARDS_DIR
    if d.is_dir():
        for p in sorted(d.glob("*.md")):
            cards.append(load_card(p))
    return cards


def card_from_record(rec: dict, kdir: Path) -> Card:
    """Wrap one records.jsonl line as a Card, so every consumer is unchanged."""
    rid, typ = str(rec.get("id", "")), str(rec.get("type", ""))
    if not rid:
        raise CardError("records.jsonl: a record is missing 'id'")
    if typ not in CARD_TYPES:
        raise CardError(f"records.jsonl: {rid} has invalid type {typ!r}")
    # Deterministic stand-in for raw frontmatter, so the index fingerprint is stable.
    raw = " ".join(f"{k}={rec[k]}" for k in sorted(rec) if k != "body")
    path = kdir / TYPE_DIR[typ] / f"{rid}.md"
    card = Card(path, dict(rec), str(rec.get("body") or ""), raw)
    if not card.summary:
        raise CardError(f"records.jsonl: {rid} has no 'summary' or 'y'")
    return card


def load_all(root: Path | None = None) -> list[Card]:
    """Prefer the single-file store; fall back to per-card files."""
    cards = load_cards_from_files(root)
    if cards:
        return cards
    # Fall back to the compact export if the card files are not present.
    kdir = knowledge_dir(root)
    return [card_from_record(r, kdir) for r in load_records(kdir)]


# ---------------------------------------------------------------------- fingerprints


def frontmatter_hash(cards: list[Card]) -> str:
    """Fingerprint of every card's frontmatter — the index is a pure function of this."""
    h = hashlib.sha1()
    for c in sorted(cards, key=lambda c: c.id):
        h.update(c.id.encode())
        h.update(b"\0")
        h.update(" ".join(c.raw_fm.split()).encode())
        h.update(b"\n")
    return h.hexdigest()


def read_json(path: Path, default=None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
