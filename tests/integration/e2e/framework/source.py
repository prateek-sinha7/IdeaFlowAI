"""Ask the frontend source whether a control is still declared.

`23-controls-inventory` exists because `_coverage.py` found that 150 of 298
addressable controls were named in no spec at all. Most of them live in states
the offline tier cannot reach — an agent proposal, a live audit, a refinement
chip — so a runtime assertion is impossible for them today.

What IS assertable is that the control is still DECLARED. A renamed or deleted
testid is exactly the change that silently breaks a future test, and this
catches it the moment it happens, from the same direction `_coverage.py` reads.

The index is built once per session: ~800 files, read once, held as one string.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

# …/tests/integration/e2e/framework/source.py -> the repo root is four levels
# up: framework, e2e, integration, tests.
FRONTEND = Path(__file__).resolve().parents[4] / "frontend" / "src"


@lru_cache(maxsize=1)
def _corpus() -> str:
    parts = []
    for path in FRONTEND.rglob("*.ts*"):
        if ".test." in path.name or path.name.endswith(".d.ts"):
            continue
        parts.append(path.read_text(errors="ignore"))
    assert parts, f"no frontend sources under {FRONTEND}"
    return "\n".join(parts)


@lru_cache(maxsize=512)
def declares(identifier: str) -> bool:
    """True when `identifier` is still produced by the frontend.

    Three forms, in order of strength:

    1. A whole quoted value — `data-testid="canvas-brief"`. Exact, so
       `agent-search` does not match `agent-search-results`.
    2. The identifier as a bare substring, which covers a value assembled by
       concatenation.
    3. A TEMPLATED id: `canvas-node-route` is written
       `` `canvas-node-${node.kind}` `` and the suffix never appears in source
       at all. Only the static prefix can be verified, so a match on
       `canvas-node-${` is accepted — and it is a weaker claim, deliberately.
       Renaming the prefix still fails; renaming an outcome value does not.
    """
    corpus = _corpus()
    if re.search(rf"""["'`]{re.escape(identifier)}["'`]""", corpus):
        return True
    if identifier in corpus:
        return True
    parts = identifier.split("-")
    return any(
        f"{'-'.join(parts[:n])}-${{" in corpus for n in range(len(parts) - 1, 0, -1)
    )


def assert_declared(*identifiers: str) -> None:
    missing = [i for i in identifiers if not declares(i)]
    assert not missing, (
        f"the frontend no longer declares {missing} — the control was renamed or "
        "removed, and every test that would have addressed it is now silently "
        "matching nothing"
    )
