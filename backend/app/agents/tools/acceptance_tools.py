"""app/agents/tools/acceptance_tools.py -- acceptance-test runner and page outline (P27 goal W1).

Two sandbox-confined tools:

  run_acceptance(ids, page)  runs ``.goal/acceptance/<id>.json`` (v2 format) in headless
                             Chromium against the sandbox page (file://), every case from a
                             fresh page load, and WRITES ``.goal/trace.json`` itself.
  page_outline(page)         a map of a (large) page without its body text.

Acceptance v2 file: ``{"id", "title", "fixtures": [...], "cases": [{"name", "steps": [...]}]}``.
A step is ``{"verb": "<verb>", ...fields}``; the verb set and each verb's fields are the
closed table ``STEP_SPEC`` below, which ``ledger_check acceptance_schema`` also validates
against. ``target`` is a ``data-test`` name unless it starts with ``#``, ``.`` or ``[``.

Trace: ``{"runner": "run_acceptance", "run_at", "page", "page_sha256", "pass", "partial",
"results": [...]}``. A run over "all" writes a fresh full trace (``pass`` = previous + 1,
``partial`` false). A run over a subset MERGES into the existing trace (replacing those ids),
sets ``partial`` true and leaves ``pass`` unchanged -- ``trace_fresh`` rejects partial traces,
so the verifier has to run "all".

Stuck tests: ``.goal/fail-history.json`` (written only by this runner) counts fix attempts per
failing id. An attempt is a targeted (partial) run that named the id, followed by a full run where
it still fails at the same step. After ``STUCK_AFTER_ATTEMPTS`` attempts the id's trace result
carries ``"stuck": true``; a failure at a different step resets its count, a pass clears it.

Never-raise discipline: every failure comes back as JSON. Time is capped per case and per call
and the browser is always closed. The browser is launched the way ``render_check`` does
(``chromium.launch(args=["--no-sandbox"])``) on the shared Playwright bridge loop, and the
browser context aborts http(s) requests so a generated page cannot reach the network.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any

from langchain_core.tools import tool

RUN_ACCEPTANCE = "run_acceptance"
PAGE_OUTLINE = "page_outline"

TRACE_REL = ".goal/trace.json"
HISTORY_REL = ".goal/fail-history.json"
STUCK_AFTER_ATTEMPTS = 2
LEDGER_REL = ".goal/ledger.json"
ACCEPTANCE_DIR = ".goal/acceptance"
DEFAULT_PAGE = "prototype.html"

CASE_TIMEOUT_S = 25
CALL_TIMEOUT_S = 600
STEP_TIMEOUT_MS = 5000
OUTLINE_MAX_CHARS = 8000

_SANDBOX: Any = None


def bind_sandbox(sandbox: Any) -> None:
    """Bind the run sandbox (called by the factory at tool-resolution time)."""
    global _SANDBOX
    _SANDBOX = sandbox


# verb -> (required fields, optional fields). Extra one-of rules live in validate_steps().
STEP_SPEC: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "goto_tab": (frozenset({"target"}), frozenset()),
    "load_file": (frozenset({"target", "file"}), frozenset()),
    "paste": (frozenset({"target"}), frozenset({"file", "text"})),
    "click": (frozenset({"target"}), frozenset()),
    "fill": (frozenset({"target", "value"}), frozenset()),
    "select": (frozenset({"target", "value"}), frozenset()),
    "check": (frozenset({"target"}), frozenset()),
    "uncheck": (frozenset({"target"}), frozenset()),
    "expect_visible": (frozenset({"target"}), frozenset()),
    "expect_hidden": (frozenset({"target"}), frozenset()),
    "expect_enabled": (frozenset({"target"}), frozenset()),
    "expect_disabled": (frozenset({"target"}), frozenset()),
    "expect_text": (frozenset({"target"}), frozenset({"contains", "equals"})),
    "expect_count": (frozenset({"target"}), frozenset({"equals", "min", "max"})),
    "expect_xml": (
        frozenset({"target", "well_formed"}),
        frozenset({"root", "contains", "not_contains", "xpath_text"}),
    ),
    "eval": (frozenset({"js"}), frozenset()),
}
FILE_VERBS = ("load_file", "paste")
_FILE_KEYS = {"load_file": "file", "paste": "file"}
_TOP_KEYS = frozenset({"id", "title", "fixtures", "cases"})
_CASE_KEYS = frozenset({"name", "steps"})


# --------------------------------------------------------------------------- shared helpers


def read_text(sandbox: Any, rel: str) -> str | None:
    try:
        p = sandbox.path_for(rel)
        if not p.is_file():
            return None
        return p.read_text(encoding="utf-8", errors="replace")
    except (ValueError, OSError):
        return None


def read_json(sandbox: Any, rel: str) -> Any:
    """Parsed JSON, or None when missing / invalid / unsafe."""
    text = read_text(sandbox, rel)
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def page_sha256(sandbox: Any, page: str) -> str | None:
    try:
        p = sandbox.path_for(page)
        if not p.is_file():
            return None
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except (ValueError, OSError):
        return None


def sandbox_file_exists(sandbox: Any, rel: Any) -> bool:
    try:
        return isinstance(rel, str) and bool(rel) and sandbox.path_for(rel).is_file()
    except (ValueError, OSError):
        return False


def validate_acceptance_doc(sandbox: Any, doc: Any, expect_id: str) -> list[str]:
    """Schema problems of one parsed acceptance file (empty list = valid)."""
    if not isinstance(doc, dict):
        return ["file is not a JSON object"]
    problems: list[str] = []
    for k in sorted(set(doc) - _TOP_KEYS):
        problems.append(f"unknown top-level field {k!r}")
    if doc.get("id") != expect_id:
        problems.append(f"id must be {expect_id!r}, got {doc.get('id')!r}")
    if "title" in doc and not isinstance(doc["title"], str):
        problems.append("title must be a string")
    fx = doc.get("fixtures", [])
    if not isinstance(fx, list) or not all(isinstance(f, str) for f in fx):
        problems.append("fixtures must be a list of sandbox paths")
    else:
        for f in fx:
            if not sandbox_file_exists(sandbox, f):
                problems.append(f"fixture not found in sandbox: {f}")
    cases = doc.get("cases")
    if not isinstance(cases, list) or not cases:
        problems.append("cases must be a non-empty list")
        return problems
    for ci, case in enumerate(cases):
        cw = f"case {ci + 1}"
        if not isinstance(case, dict):
            problems.append(f"{cw}: not an object")
            continue
        for k in sorted(set(case) - _CASE_KEYS):
            problems.append(f"{cw}: unknown field {k!r}")
        if not isinstance(case.get("name"), str) or not case.get("name"):
            problems.append(f"{cw}: name must be a non-empty string")
        steps = case.get("steps")
        if not isinstance(steps, list) or not steps:
            problems.append(f"{cw}: steps must be a non-empty list")
            continue
        for si, step in enumerate(steps):
            problems.extend(
                f"{cw} step {si + 1}: {p}" for p in _validate_step(sandbox, step)
            )
    return problems


def _validate_step(sandbox: Any, step: Any) -> list[str]:
    if not isinstance(step, dict):
        return ["not an object"]
    verb = step.get("verb")
    if verb not in STEP_SPEC:
        return [f"unknown verb {verb!r}; valid verbs: {', '.join(STEP_SPEC)}"]
    required, optional = STEP_SPEC[verb]
    out: list[str] = []
    for k in sorted(set(step) - required - optional - {"verb"}):
        out.append(f"{verb}: unknown field {k!r}")
    for k in sorted(required - set(step)):
        out.append(f"{verb}: missing field {k!r}")
    if "target" in step and (not isinstance(step["target"], str) or not step["target"]):
        out.append(f"{verb}: target must be a non-empty string")
    if verb == "paste" and ("file" in step) == ("text" in step):
        out.append("paste: give exactly one of file, text")
    if verb == "expect_text" and ("contains" in step) == ("equals" in step):
        out.append("expect_text: give exactly one of contains, equals")
    if verb == "expect_count":
        if not (set(step) & {"equals", "min", "max"}):
            out.append("expect_count: give at least one of equals, min, max")
        for k in ("equals", "min", "max"):
            if k in step and (
                not isinstance(step[k], int) or isinstance(step[k], bool)
            ):
                out.append(f"expect_count: {k} must be an integer")
    if verb == "expect_xml":
        if step.get("well_formed") is not True:
            out.append("expect_xml: well_formed must be true")
        for k in ("contains", "not_contains"):
            if k in step and not (
                isinstance(step[k], list) and all(isinstance(s, str) for s in step[k])
            ):
                out.append(f"expect_xml: {k} must be a list of strings")
        if "root" in step and not isinstance(step["root"], str):
            out.append("expect_xml: root must be a string")
        if "xpath_text" in step and not (
            isinstance(step["xpath_text"], dict)
            and all(
                isinstance(k, str) and isinstance(v, str)
                for k, v in step["xpath_text"].items()
            )
        ):
            out.append(
                "expect_xml: xpath_text must be an object of xpath -> expected text"
            )
        else:
            for xp in step.get("xpath_text") or {}:
                if _xpath_compile(xp) is None:
                    out.append(
                        f"expect_xml: xpath {xp!r} cannot be evaluated by the runner "
                        "(functions such as count(), local-name() or text() are not "
                        "supported); use a plain element path, an [@attr='v'] predicate, "
                        "or a contains check instead"
                    )
    if verb == "eval" and not isinstance(step.get("js"), str):
        out.append("eval: js must be a string")
    if (
        verb in ("fill", "select")
        and "value" in step
        and not isinstance(step["value"], str)
    ):
        out.append(f"{verb}: value must be a string")
    fkey = _FILE_KEYS.get(verb)
    if fkey and fkey in step:
        if not sandbox_file_exists(sandbox, step[fkey]):
            out.append(f"{verb}: file not found in sandbox: {step[fkey]!r}")
    return out


# --------------------------------------------------------------------------- XML checks


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else tag


def _strip_ns(root: ET.Element) -> None:
    for el in root.iter():
        el.tag = _local(el.tag)
        if el.attrib:
            el.attrib = {_local(k): v for k, v in el.attrib.items()}


def check_xml(text: str, step: dict[str, Any]) -> str | None:
    """None when the XML satisfies the step, else a one-line reason."""
    if len(re.findall(r"<\?xml\b", text)) > 1:
        return "more than one XML declaration (two documents in one)"
    # Entity-expansion and external-entity attacks need a DTD; a generated request
    # never carries one, so refuse it before parsing (the parse below is then safe).
    if re.search(r"<!(DOCTYPE|ENTITY)\b", text, re.IGNORECASE):
        return "XML carries a DOCTYPE/ENTITY declaration, which is not allowed"
    try:
        root = ET.fromstring(text.strip().encode("utf-8"))  # nosec B314 - DTDs refused above
    except (ET.ParseError, ValueError) as exc:
        return f"not well-formed XML: {exc}"
    _strip_ns(root)
    want_root = step.get("root")
    if want_root is not None and root.tag != _local(want_root):
        return f"root element is <{root.tag}>, expected <{_local(want_root)}>"
    for s in step.get("contains") or []:
        if s not in text:
            return f"XML does not contain {s!r}"
    for s in step.get("not_contains") or []:
        if s in text:
            return f"XML contains forbidden {s!r}"
    for xp, expected in (step.get("xpath_text") or {}).items():
        got = _xpath_first(root, xp)
        if got is None:
            return f"xpath {xp!r} matched nothing"
        if got.strip() != expected.strip():
            return f"xpath {xp!r} is {got.strip()!r}, expected {expected.strip()!r}"
    return None


def _xpath_compile(xpath: str) -> tuple[str | None, str, str | None] | None:
    """Split an xpath into (absolute root tag or None, ElementTree path, attribute).

    None when ElementTree cannot evaluate it (functions such as count() or local-name()).
    """
    xp = xpath.strip()
    attr = None
    m = re.search(r"/@([\w.-]+)$", xp)
    if m:
        attr, xp = m.group(1), xp[: m.start()]
    # local-name()='x' and prefixes are not supported; plain paths and [@a='v'] predicates are.
    xp = re.sub(r"\b[\w.-]+:(?=[\w*])", "", xp)
    root_tag = None
    if xp.startswith("//"):
        xp = "." + xp
    elif xp.startswith("/"):
        parts = xp.lstrip("/").split("/", 1)
        root_tag = _local(parts[0].split("[")[0])
        xp = parts[1] if len(parts) > 1 else "."
    if xp != ".":
        try:
            ET.Element("probe").findall(xp)
        except (SyntaxError, ValueError, KeyError, TypeError):
            return None
    return root_tag, xp, attr


def _xpath_first(root: ET.Element, xpath: str) -> str | None:
    """Text (or attribute value) of the first match; namespaces already stripped."""
    compiled = _xpath_compile(xpath)
    if compiled is None:
        return None
    root_tag, xp, attr = compiled
    if root_tag is not None and root_tag != root.tag:
        return None
    try:
        found = root.findall(xp) if xp != "." else [root]
    except (SyntaxError, ValueError, KeyError, TypeError):
        return None
    if not found:
        return None
    el = found[0]
    if attr:
        return el.attrib.get(attr)
    return "".join(el.itertext())


# --------------------------------------------------------------------------- browser runner


class _Fail(AssertionError):
    """A test assertion failed (status fail), as opposed to an error in the run itself."""


def _selector(target: str) -> str:
    if target[:1] in ("#", ".", "["):
        return target
    return f'[data-test="{target}"]'


_READ_VALUE_JS = "el => (('value' in el) && typeof el.value === 'string') ? el.value : (el.textContent || '')"
_PASTE_JS = """(el, text) => {
  el.focus();
  const dt = new DataTransfer(); dt.setData('text/plain', text);
  const ev = new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true});
  const proceed = el.dispatchEvent(ev);
  if (proceed) {
    if ('value' in el) { el.value = text; } else { el.textContent = text; }
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
  }
}"""


def _fixture_path(sandbox: Any, rel: str):
    p = sandbox.path_for(rel)  # raises ValueError on traversal
    if not p.is_file():
        raise ValueError(f"file not found in sandbox: {rel}")
    return p


async def _do_step(page: Any, sandbox: Any, step: dict[str, Any]) -> None:
    verb = step["verb"]
    if verb == "eval":
        js = step["js"].strip()
        fn = f"() => {{ {js} }}" if re.search(r"\breturn\b", js) else f"() => ({js})"
        if await page.evaluate(fn) is not True:
            raise _Fail(f"eval did not return true: {js[:200]}")
        return
    loc = page.locator(_selector(step["target"]))
    sel = _selector(step["target"])
    if verb == "expect_count":
        n = await loc.count()
        if "equals" in step and n != step["equals"]:
            raise _Fail(f"{sel}: count is {n}, expected {step['equals']}")
        if "min" in step and n < step["min"]:
            raise _Fail(f"{sel}: count is {n}, expected at least {step['min']}")
        if "max" in step and n > step["max"]:
            raise _Fail(f"{sel}: count is {n}, expected at most {step['max']}")
        return
    first = loc.first
    if verb in ("expect_visible", "expect_hidden", "expect_enabled", "expect_disabled"):
        if await loc.count() == 0:
            if verb == "expect_hidden":
                return
            raise _Fail(f"{sel}: element not found")
        if verb in ("expect_visible", "expect_hidden"):
            vis = await first.is_visible()
            if vis != (verb == "expect_visible"):
                raise _Fail(f"{sel}: is {'visible' if vis else 'hidden'}")
        else:
            en = await first.is_enabled()
            if en != (verb == "expect_enabled"):
                raise _Fail(f"{sel}: is {'enabled' if en else 'disabled'}")
        return
    if verb in ("expect_text", "expect_xml"):
        if await loc.count() == 0:
            raise _Fail(f"{sel}: element not found")
        text = await first.evaluate(_READ_VALUE_JS)
        if verb == "expect_text":
            if "equals" in step and text.strip() != str(step["equals"]).strip():
                raise _Fail(
                    f"{sel}: text is {text.strip()[:200]!r}, expected {str(step['equals'])[:200]!r}"
                )
            if "contains" in step and str(step["contains"]) not in text:
                raise _Fail(
                    f"{sel}: text {text.strip()[:200]!r} does not contain {str(step['contains'])[:200]!r}"
                )
            return
        problem = check_xml(text, step)
        if problem:
            raise _Fail(f"{sel}: {problem}; starts {text.strip()[:120]!r}")
        return
    # actions: a missing element or timeout is an error, not a failed assertion
    if verb in ("click", "goto_tab"):
        await first.click(timeout=STEP_TIMEOUT_MS)
    elif verb == "fill":
        await first.fill(step["value"], timeout=STEP_TIMEOUT_MS)
    elif verb == "select":
        await first.select_option(step["value"], timeout=STEP_TIMEOUT_MS)
    elif verb == "check":
        await first.check(timeout=STEP_TIMEOUT_MS)
    elif verb == "uncheck":
        await first.uncheck(timeout=STEP_TIMEOUT_MS)
    elif verb == "load_file":
        await first.set_input_files(
            str(_fixture_path(sandbox, step["file"])), timeout=STEP_TIMEOUT_MS
        )
    elif verb == "paste":
        if "file" in step:
            text = _fixture_path(sandbox, step["file"]).read_text(
                encoding="utf-8", errors="replace"
            )
        else:
            text = step["text"]
        await first.wait_for(state="attached", timeout=STEP_TIMEOUT_MS)
        await first.evaluate(_PASTE_JS, text)
    else:
        raise ValueError(f"unknown verb {verb!r}")


def _describe(step: dict[str, Any]) -> str:
    bits = [str(step.get("verb"))]
    if "target" in step:
        bits.append(str(step["target"]))
    return " ".join(bits)


async def _run_case(
    browser: Any, sandbox: Any, url: str, case: dict[str, Any]
) -> tuple[str, int | None, str]:
    """(status, failing step index (1-based) or None, observed)."""
    ctx = await browser.new_context()
    try:

        async def _route(route: Any) -> None:
            if route.request.url.startswith(("http://", "https://")):
                await route.abort()
            else:
                await route.continue_()

        await ctx.route("**/*", _route)
        page = await ctx.new_page()
        page.set_default_timeout(STEP_TIMEOUT_MS)
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)[:200]))
        await page.goto(url, wait_until="load", timeout=15000)
        idx = 0
        try:
            _stay_on_page(page, url)
            for idx, step in enumerate(case["steps"], start=1):
                await _do_step(page, sandbox, step)
                _stay_on_page(page, url)
        except _Fail as exc:
            return "fail", idx, _with_errors(str(exc), errors)
        except Exception as exc:  # noqa: BLE001 -- timeouts, missing elements, bad fixtures
            return (
                "error",
                idx,
                _with_errors(
                    f"{type(exc).__name__}: {str(exc).splitlines()[0][:300]}", errors
                ),
            )
        return "pass", None, ""
    finally:
        try:
            await ctx.close()
        except Exception:  # noqa: BLE001
            pass


def _stay_on_page(page: Any, url: str) -> None:
    """Fail when the page has navigated away from the page under test (a redirect or a
    link to another file): the tests judge prototype.html itself, never what it opens."""
    current = (page.url or "").split("#", 1)[0].split("?", 1)[0]
    if current != url:
        raise _Fail(
            f"the page navigated away from {url.rsplit('/', 1)[-1]} to {current or 'nothing'}"
        )


def _with_errors(msg: str, errors: list[str]) -> str:
    return msg if not errors else f"{msg} [page errors: {'; '.join(errors[:3])}]"


async def _run_file(
    browser: Any, sandbox: Any, url: str, rid: str, doc: dict[str, Any], deadline: float
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": rid,
        "status": "pass",
        "test": doc.get("title") or rid,
        "failing_step": None,
        "observed": "",
        "evidence": "",
    }
    cases = doc["cases"]
    done_steps = 0
    for case in cases:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return {
                **row,
                "status": "error",
                "test": case["name"],
                "observed": "call time budget exceeded",
                "evidence": "run_acceptance stopped at its 10 minute cap",
            }
        try:
            status, idx, observed = await asyncio.wait_for(
                _run_case(browser, sandbox, url, case),
                timeout=min(CASE_TIMEOUT_S, remaining),
            )
        except asyncio.TimeoutError:
            status, idx, observed = "error", None, f"case exceeded {CASE_TIMEOUT_S}s"
        except Exception as exc:  # noqa: BLE001
            status, idx, observed = (
                "error",
                None,
                f"{type(exc).__name__}: {str(exc).splitlines()[0][:300] if str(exc) else ''}",
            )
        if status != "pass":
            fs = f"case {case['name']!r}" + (
                f" step {idx}: {_describe(case['steps'][idx - 1])}" if idx else ""
            )
            return {
                **row,
                "status": status,
                "test": case["name"],
                "failing_step": fs,
                "observed": observed,
                "evidence": f"{done_steps} step(s) passed before the failure",
            }
        done_steps += len(case["steps"])
    row["evidence"] = f"{len(cases)} case(s), {done_steps} step(s) passed"
    return row


def _select_ids(token: str, candidates: list[str]) -> list[str]:
    toks = [t.strip() for t in token.split(",") if t.strip()]
    if not toks or any(t.lower() == "all" for t in toks):
        return list(candidates)
    return [c for c in candidates if any(c == t or c.startswith(t) for t in toks)]


def _not_testable_reason(row: dict[str, Any]) -> str:
    for k in ("reason", "not_testable_reason", "testable_reason"):
        if isinstance(row.get(k), str) and row[k].strip():
            return row[k].strip()
    return "marked not testable in the ledger"


def _signature(result: dict[str, Any]) -> str:
    """Where a failure happens: the failing step, else the start of the observation."""
    return str(result.get("failing_step") or result.get("observed") or "")[:200]


def update_fail_history(
    history: Any, results: list[dict[str, Any]], full: bool
) -> dict[str, Any]:
    """Count fix attempts per failing id and mark ``stuck`` on the results (in place).

    A partial run marks the ids it ran as targeted. A full run turns each targeted id that
    still fails at the same step into one more attempt; a new failing step resets the count,
    a pass or not-testable result drops the id. Returns the new history.
    """
    hist: dict[str, Any] = {
        k: dict(v)
        for k, v in (history if isinstance(history, dict) else {}).items()
        if isinstance(v, dict)
    }
    for r in results:
        rid = r["id"]
        if r["status"] not in ("fail", "error"):
            hist.pop(rid, None)
            continue
        sig = _signature(r)
        h = hist.get(rid)
        if h is None or h.get("signature") != sig:
            h = {"signature": sig, "attempts": 0, "targeted": False}
        if not full:
            h["targeted"] = True
        elif h.get("targeted"):
            h["attempts"] = int(h.get("attempts") or 0) + 1
            h["targeted"] = False
        hist[rid] = h
        r["fix_attempts"] = h["attempts"]
        r["stuck"] = h["attempts"] >= STUCK_AFTER_ATTEMPTS
    return hist


def _summary(ok: bool, results: list[dict[str, Any]], **extra: Any) -> str:
    counts = {s: 0 for s in ("pass", "fail", "error", "not-testable")}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    failures = [
        {
            k: r.get(k)
            for k in (
                "id",
                "status",
                "test",
                "failing_step",
                "observed",
                "fix_attempts",
                "stuck",
            )
        }
        for r in results
        if r["status"] in ("fail", "error")
    ]
    return json.dumps({"ok": ok, "counts": counts, "failures": failures[:50], **extra})


def _err(msg: str) -> str:
    return json.dumps({"ok": False, "error": msg, "counts": {}, "failures": []})


async def _run_acceptance_async(sandbox: Any, ids: str, page: str) -> str:
    sha = page_sha256(sandbox, page)
    if sha is None:
        return _err(f"page not found in sandbox: {page}")
    ledger = read_json(sandbox, LEDGER_REL)
    rows = [
        r
        for r in (ledger.get("rows") if isinstance(ledger, dict) else None) or []
        if isinstance(r, dict) and r.get("id")
    ]
    by_ledger = {str(r["id"]): r for r in rows}

    files: dict[str, Any] = {}
    try:
        adir = sandbox.path_for(ACCEPTANCE_DIR)
        names = sorted(p.stem for p in adir.glob("*.json")) if adir.is_dir() else []
    except (ValueError, OSError):
        names = []
    for n in names:
        files[n] = read_json(sandbox, f"{ACCEPTANCE_DIR}/{n}.json")

    candidates = list(dict.fromkeys([*by_ledger, *files]))
    selected = _select_ids(ids, candidates)
    if not selected:
        return _err(f"no ledger or acceptance ids match {ids!r}")

    results: list[dict[str, Any]] = []
    to_run: list[tuple[str, dict[str, Any]]] = []
    for rid in selected:
        row = by_ledger.get(rid)
        base = {
            "id": rid,
            "test": "",
            "failing_step": None,
            "observed": "",
            "evidence": "",
        }
        if row is not None and row.get("testable", True) is False:
            results.append(
                {
                    **base,
                    "status": "not-testable",
                    "evidence": _not_testable_reason(row),
                }
            )
            continue
        doc = files.get(rid)
        if doc is None:
            results.append(
                {
                    **base,
                    "status": "error",
                    "observed": "missing or unparseable acceptance file",
                }
            )
            continue
        problems = validate_acceptance_doc(sandbox, doc, rid)
        if problems:
            results.append(
                {
                    **base,
                    "status": "error",
                    "observed": "invalid acceptance file: " + "; ".join(problems[:3]),
                }
            )
            continue
        to_run.append((rid, doc))

    if to_run:
        try:
            from playwright.async_api import async_playwright
        except Exception as exc:  # noqa: BLE001
            return _err(f"Playwright unavailable: {exc}")
        url = sandbox.path_for(page).as_uri()
        deadline = time.monotonic() + CALL_TIMEOUT_S
        try:
            async with async_playwright() as pw:
                try:
                    browser = await pw.chromium.launch(args=["--no-sandbox"])
                except Exception as exc:  # noqa: BLE001
                    return _err(f"Chromium unavailable: {exc}")
                try:
                    for rid, doc in to_run:
                        results.append(
                            await _run_file(browser, sandbox, url, rid, doc, deadline)
                        )
                finally:
                    try:
                        await browser.close()
                    except Exception:  # noqa: BLE001
                        pass
        except Exception as exc:  # noqa: BLE001
            return _err(f"browser run failed: {type(exc).__name__}: {exc}")

    order = {rid: i for i, rid in enumerate(selected)}
    results.sort(key=lambda r: order[r["id"]])

    full = ids.strip().lower() == "all" or not ids.strip()
    history = update_fail_history(read_json(sandbox, HISTORY_REL), results, full)
    prev = read_json(sandbox, TRACE_REL)
    prev = prev if isinstance(prev, dict) else {}
    prev_pass = prev.get("pass") if isinstance(prev.get("pass"), int) else 0
    if full:
        merged, pass_n = results, prev_pass + 1
    else:
        replaced = {r["id"] for r in results}
        old = prev.get("results") if isinstance(prev.get("results"), list) else []
        merged = [
            r for r in old if isinstance(r, dict) and r.get("id") not in replaced
        ] + results
        pass_n = prev_pass
    trace = {
        "runner": RUN_ACCEPTANCE,
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "page": page,
        "page_sha256": sha,
        "pass": pass_n,
        "partial": not full,
        "results": merged,
    }
    try:
        tp = sandbox.path_for(TRACE_REL)
        tp.parent.mkdir(parents=True, exist_ok=True)
        tp.write_text(json.dumps(trace, indent=1), encoding="utf-8")
        sandbox.path_for(HISTORY_REL).write_text(
            json.dumps(history, indent=1), encoding="utf-8"
        )
    except (ValueError, OSError) as exc:
        return _err(f"could not write {TRACE_REL}: {exc}")
    ok = all(r["status"] in ("pass", "not-testable") for r in results)
    return _summary(ok, results, pass_number=pass_n, partial=not full, page_sha256=sha)


def run_acceptance_core(
    sandbox: Any, ids: str = "all", page: str = DEFAULT_PAGE
) -> str:
    """Sync entry (also used by tests). Never raises."""
    try:
        from app.agents.playwright_session import run_sync

        return run_sync(
            _run_acceptance_async(
                sandbox, ids if isinstance(ids, str) else "all", page or DEFAULT_PAGE
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(f"internal error: {type(exc).__name__}: {exc}")


@tool
def run_acceptance(ids: str = "all") -> str:
    """Run the acceptance tests in .goal/acceptance/ against prototype.html in headless Chrome.

    ids: "all", a comma list of ledger ids, or an id prefix such as "U6-" or "G".
    The page is always prototype.html (the deliverable); a case fails if the page navigates
    to another document.
    Each test case starts from a fresh page load. This tool WRITES .goal/trace.json
    itself ("all" = full trace, pass counter + 1; any other ids = merged partial trace,
    counter unchanged). Returns JSON: {"ok", "counts", "failures": [...], "pass_number"}.
    A failure marked "stuck": true has survived two fix attempts at the same step; do not
    edit the page for it again -- record it in .goal/blocked.json instead.
    """
    if _SANDBOX is None:
        return _err("no run sandbox bound")
    return run_acceptance_core(_SANDBOX, ids, DEFAULT_PAGE)


# --------------------------------------------------------------------------- page outline

_RUNTIME_SCRIPTS = frozenset({"state", "icons", "theme-init", "contract"})
_VOID = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }
)
_FN_RE = re.compile(r"^(\s*)(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)\s*\(")
_CONST_RE = re.compile(
    r"^(\s*)(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\(|function\b|[A-Za-z_$][\w$]*\s*=>)"
)


class _Outline(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[
            tuple[str, int, int | None]
        ] = []  # (tag, start line, screen index)
        self.screens: list[list[Any]] = []  # [id, start, end]
        self.tests: list[tuple[str, int]] = []
        self.scripts: list[list[Any]] = []  # [start, end, src, type, data-vt]

    def handle_starttag(self, tag: str, attrs: list) -> None:
        line = self.getpos()[0]
        a = {k: (v or "") for k, v in attrs}
        if "data-test" in a:
            self.tests.append((a["data-test"], line))
        if tag == "script":
            self.scripts.append(
                [line, line, a.get("src", ""), a.get("type", ""), a.get("data-vt", "")]
            )
        if tag in _VOID:
            return
        screen = None
        if tag == "section" or "data-screen" in a:
            self.screens.append(
                [a.get("data-screen") or a.get("id") or f"<{tag}>", line, line]
            )
            screen = len(self.screens) - 1
        self.stack.append((tag, line, screen))

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        a = {k: (v or "") for k, v in attrs}
        if "data-test" in a:
            self.tests.append((a["data-test"], self.getpos()[0]))

    def handle_endtag(self, tag: str) -> None:
        line = self.getpos()[0]
        if tag == "script" and self.scripts:
            self.scripts[-1][1] = line
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                screen = self.stack[i][2]
                if screen is not None:
                    self.screens[screen][2] = line
                del self.stack[i:]
                break


def build_outline(html: str, name: str) -> str:
    parser = _Outline()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # noqa: BLE001 -- a malformed page still gets a partial outline
        pass
    lines = html.splitlines()
    out = [f"{name}: {len(html.encode('utf-8'))} bytes, {len(lines)} lines"]

    out.append(f"\nscripts ({len(parser.scripts)}):")
    for s, e, src, typ, vt in parser.scripts:
        out.append(
            f"  lines {s}-{e}"
            + (f" src={src}" if src else "")
            + (f" type={typ}" if typ else "")
            + (f" data-vt={vt}" if vt else "")
        )

    out.append(f"\nscreens ({len(parser.screens)}):")
    for sid, s, e in parser.screens:
        out.append(f"  {sid}: lines {s}-{e}")

    fn_lines: list[str] = []
    for s, e, src, typ, vt in parser.scripts:
        if src or (typ and "javascript" not in typ and "module" not in typ):
            continue
        if (
            vt in _RUNTIME_SCRIPTS
        ):  # the contract's own runtime: not the page author's code
            continue
        body = lines[
            s : max(s, e - 1)
        ]  # lines after the <script> line up to the closing line
        base = next(
            (len(m.group(1)) for ln in body if (m := re.match(r"^(\s*)\S", ln))), 0
        )
        for off, ln in enumerate(body):
            # Named function declarations at any depth (app scripts usually wrap everything in one
            # IIFE / vt:ready handler); const/let arrow helpers only up to one level below the script's base.
            fm = _FN_RE.match(ln)
            cm = None if fm else _CONST_RE.match(ln)
            if fm or (cm and len(cm.group(1)) <= base + 4):
                fn_lines.append(f"  {(fm or cm).group(2)}: line {s + 1 + off}")
    out.append(f"\nfunctions ({len(fn_lines)}):")
    out.extend(fn_lines)

    out.append(f"\ndata-test ({len(parser.tests)}):")
    out.extend(f"  {n}: line {ln}" for n, ln in parser.tests)

    text = "\n".join(out)
    if len(text) > OUTLINE_MAX_CHARS:
        text = (
            text[:OUTLINE_MAX_CHARS].rsplit("\n", 1)[0]
            + "\n... truncated (output capped at ~8k chars)"
        )
    return text


def page_outline_core(sandbox: Any, page: str = DEFAULT_PAGE) -> str:
    try:
        p = sandbox.path_for(page)
        if not p.is_file():
            return f"error: page not found in sandbox: {page}"
        return build_outline(p.read_text(encoding="utf-8", errors="replace"), page)
    except (ValueError, OSError) as exc:
        return f"error: {exc}"
    except Exception as exc:  # noqa: BLE001
        return f"error: internal error: {type(exc).__name__}: {exc}"


@tool
def page_outline(page: str = DEFAULT_PAGE) -> str:
    """Map of a large HTML page without its body text (read-only).

    Returns size, <script> blocks with line ranges, screens (<section>/[data-screen])
    with line ranges, top-level functions of the app script with their line, and every
    data-test with its line. Use it to find where to edit, then read only those lines.
    Output is capped at about 8k characters.
    """
    if _SANDBOX is None:
        return "error: no run sandbox bound"
    return page_outline_core(_SANDBOX, page)
