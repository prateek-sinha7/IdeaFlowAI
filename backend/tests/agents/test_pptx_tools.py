"""spec 017 — the three pptx tools (T2/T3).

Offline: the node subprocess is real (it is the thing under test), but nothing
here touches a model or a provider. The point of each case is the RETURN STRING,
because that string is the agent's only retry signal — a tool that failed
usefully but reported "generation failed" would leave the loop blind.
"""

from __future__ import annotations

import pathlib
import shutil

import pytest

from app.agents.tools import pptx_tools

GOOD = """
const pres = new PptxGenJS();
pres.defineLayout({ name: "W", width: 13.333, height: 7.5 });
pres.layout = "W";
const s = pres.addSlide();
s.addText("Hello", { x: 1, y: 2, w: 11, h: 1, fontSize: 40, color: "1B1B1B" });
return pres.write("nodebuffer");
"""

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is required to build a real pptx"
)


class _Sandbox:
    def __init__(self, root: pathlib.Path):
        self.root = root

    def path_for(self, name: str) -> pathlib.Path:
        return self.root / name


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(pptx_tools, "_SANDBOX", _Sandbox(tmp_path))
    return tmp_path


def test_render_pptx_writes_the_file_and_reports_its_size(sandbox):
    out = pptx_tools.render_pptx.invoke({"pptxgenjs_code": GOOD})
    assert out.startswith("ok —")
    built = sandbox / "presentation.pptx"
    assert built.is_file() and built.stat().st_size > 10_000


def test_a_compile_error_comes_back_as_text_to_act_on(sandbox):
    """The retry signal. It must name the fault, not merely report failure."""
    out = pptx_tools.render_pptx.invoke({"pptxgenjs_code": "this is not javascript ((("})
    assert out.startswith("FAILED")
    assert "SyntaxError" in out


def test_a_failed_retry_does_not_destroy_the_working_deck(sandbox):
    """A later bad attempt must leave the last good pptx intact — otherwise one
    malformed retry turns a recoverable run into a lost deliverable."""
    pptx_tools.render_pptx.invoke({"pptxgenjs_code": GOOD})
    size = (sandbox / "presentation.pptx").stat().st_size
    pptx_tools.render_pptx.invoke({"pptxgenjs_code": "still not javascript ((("})
    assert (sandbox / "presentation.pptx").stat().st_size == size


def test_verify_reports_clean_on_a_well_placed_deck(sandbox):
    pptx_tools.render_pptx.invoke({"pptxgenjs_code": GOOD})
    assert pptx_tools.verify_pptx_layout.invoke({}).startswith("clean")


def test_verify_flags_a_shape_that_crosses_the_footer_rail(sandbox):
    """Content must end above 6.70". A box at y=7.0 is over the line."""
    over = GOOD.replace('y: 2, w: 11, h: 1', 'y: 7.0, w: 11, h: 1')
    pptx_tools.render_pptx.invoke({"pptxgenjs_code": over})
    out = pptx_tools.verify_pptx_layout.invoke({})
    assert out.startswith("VIOLATIONS")


def test_the_audit_tools_refuse_before_a_deck_exists(sandbox):
    assert "call render_pptx first" in pptx_tools.verify_pptx_layout.invoke({})


def test_the_tools_are_inert_with_no_sandbox_bound(monkeypatch):
    """Unbound must never fall back to a process-relative path — that would write
    the binary outside any run."""
    monkeypatch.setattr(pptx_tools, "_SANDBOX", None)
    assert "no run sandbox" in pptx_tools.render_pptx.invoke({"pptxgenjs_code": GOOD})
    assert "no run sandbox" in pptx_tools.verify_pptx_layout.invoke({})


def test_extract_dumps_the_real_shapes(sandbox):
    pptx_tools.render_pptx.invoke({"pptxgenjs_code": GOOD})
    assert "Hello" in pptx_tools.extract_pptx_shapes.invoke({})


# ─── The binding seam (the defect that shipped) ───────────────────────────────
#
# The tools above are only useful if the factory actually BINDS them. The first
# cut looked the sandbox up as `ctx.runner.sandbox` — and `AgentContext` has no
# `runner` field: the runner does not exist when tools are resolved, because the
# tools are an input to building it. Every pptx key hit the no-sandbox branch and
# was silently skipped, so `ppt-code-generator` ran with an empty tool set,
# emitted PptxGenJS as prose, and no .pptx was ever produced. The run reported
# success. These two cases pin both halves of that seam.


def test_the_factory_binds_the_pptx_tools_when_it_has_a_sandbox(tmp_path):
    from agents.factory import AgentContext, _resolve_custom_tool_keys
    from app.agents.sandbox import RunSandbox

    sb = RunSandbox("u", "r", runs_root=str(tmp_path))
    sb.ensure()
    ctx = AgentContext(user_request="x", user_id="u", run_id="r")

    resolved = _resolve_custom_tool_keys(
        ["render_pptx", "verify_pptx_layout", "extract_pptx_shapes"], ctx, sb
    )

    assert [getattr(t, "name", None) for t in resolved] == [
        "render_pptx",
        "verify_pptx_layout",
        "extract_pptx_shapes",
    ]
    # And bound to THIS run's dir, not some ambient default.
    assert pptx_tools._SANDBOX is sb


def test_the_factory_skips_them_rather_than_writing_outside_a_run(tmp_path):
    """No sandbox → no tools. Skipping is right; the alternative is a binary
    written somewhere outside the run. What was WRONG was reaching the branch
    on every real run."""
    from agents.factory import AgentContext, _resolve_custom_tool_keys

    ctx = AgentContext(user_request="x", user_id="u", run_id="r")
    assert _resolve_custom_tool_keys(["render_pptx"], ctx, None) == []


# ─── The silent-success trap (run 4a3b4728) ───────────────────────────────────
#
# A crash in the deck code used to produce a ONE-SLIDE deck reading
# "Export error: <message>". That is a file, so every caller read it as success:
# generate_pptx_from_code returned bytes, render_pptx's except never fired, the
# layout verifier found nothing wrong with one tidy error slide, and the agent
# reported "complete and verified with zero layout violations" over a deck that
# had lost all twelve of its slides.


def test_a_crash_fails_instead_of_shipping_an_error_card(tmp_path):
    from app.services.pptx_export import generate_pptx_from_code

    crashing = """
    const pres = new PptxGenJS();
    pres.layout = "LAYOUT_16x9";
    const missing = undefined;
    pres.addSlide().addText(missing.title, { x:1, y:1, w:5, h:1 });
    return pres.write("nodebuffer");
    """
    with pytest.raises(RuntimeError) as exc:
        generate_pptx_from_code(crashing, "X")
    # The JS message survives — it is the agent's only repair signal.
    assert "title" in str(exc.value)


def test_forgetting_the_return_fails_with_the_reason(tmp_path):
    from app.services.pptx_export import generate_pptx_from_code

    with pytest.raises(RuntimeError) as exc:
        generate_pptx_from_code(
            'const pres = new PptxGenJS();\npres.addSlide().addText("Hi", {x:1,y:1,w:2,h:1});',
            "X",
        )
    assert "no buffer" in str(exc.value)


def test_render_pptx_hands_the_crash_back_to_the_agent(sandbox):
    out = pptx_tools.render_pptx.invoke({
        "pptxgenjs_code": "const pres = new PptxGenJS(); undefined.boom;",
    })
    assert out.startswith("FAILED")
    assert not (sandbox / pptx_tools.PPTX_NAME).exists()


# ─── Slide count — the rule the layout checks cannot express ─────────────────


def test_a_deck_that_lost_slides_is_not_shippable(sandbox):
    """Four slides transcribed from twelve is geometrically perfect and wrong."""
    (sandbox / pptx_tools.DECK_NAME).write_text(
        "".join(f'<section class="slide">{i}</section>' for i in range(12)),
        encoding="utf-8",
    )
    out = pptx_tools.render_pptx.invoke({"pptxgenjs_code": GOOD})   # GOOD has 1 slide
    assert "INCOMPLETE" in out
    assert "1 slide(s)" in out and "has 12" in out


def test_the_slide_counter_matches_class_tokens_not_substrings(sandbox):
    """`class="slide-body"` is not a slide. Counting the substring reported 41
    slides for a 12-slide deck, which would fail every complete transcription."""
    (sandbox / pptx_tools.DECK_NAME).write_text(
        '<section class="slide dark is-active">'
        '  <div class="slide-body"><p class="slide-note">x</p></div>'
        "</section>"
        '<section class="slide"><div class="slide-body">y</div></section>',
        encoding="utf-8",
    )
    assert pptx_tools._html_slide_count() == 2


# ─── Evidence: what the gate saw, kept where a human can look ────────────────
#
# The gate has been wrong twice, both times reporting "clean" it could not
# justify. A verdict with no artefact behind it has to be taken on trust.


def test_the_gate_writes_its_report_into_the_workspace(sandbox):
    pptx_tools.render_pptx.invoke({"pptxgenjs_code": GOOD})
    report = sandbox / pptx_tools.VERIFY_DIR / "report.txt"
    assert report.is_file()
    body = report.read_text()
    assert "SHIPPABLE" in body


def test_a_rejected_deck_leaves_the_reason_on_disk(sandbox):
    (sandbox / pptx_tools.DECK_NAME).write_text(
        "".join(f'<section class="slide">{i}</section>' for i in range(12)),
        encoding="utf-8",
    )
    pptx_tools.render_pptx.invoke({"pptxgenjs_code": GOOD})
    body = (sandbox / pptx_tools.VERIFY_DIR / "report.txt").read_text()
    assert "INCOMPLETE" in body


def test_every_attempt_s_source_is_kept(sandbox):
    """The run trace elides a 24 KB tool argument so the log stays readable. The
    source still has to exist for a post-mortem — so it lands on disk."""
    pptx_tools.render_pptx.invoke({"pptxgenjs_code": GOOD})
    pptx_tools.render_pptx.invoke({"pptxgenjs_code": GOOD})
    saved = sorted((sandbox / pptx_tools.VERIFY_DIR).glob("attempt-*.js"))
    assert [p.name for p in saved] == ["attempt-01.js", "attempt-02.js"]
    assert "PptxGenJS" in saved[0].read_text()


def test_the_evidence_never_becomes_part_of_the_deliverable(sandbox):
    """`.verify/` is engine-adjacent evidence, the same standing as `.logs/` —
    a report and a screenshot are not things the client asked for."""
    from app.agents.sandbox import serialize_sandbox_deliverable

    pptx_tools.render_pptx.invoke({"pptxgenjs_code": GOOD})
    out = serialize_sandbox_deliverable(sandbox)
    assert ".verify/" not in out
    assert "attempt-01.js" not in out
