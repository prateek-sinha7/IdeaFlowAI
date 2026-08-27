"""Live progress on the terminal while the suite runs.

A single dot per test tells you nothing while a run sits for minutes on a cold
Next.js compile or a Bedrock call.

The important detail: a step is announced when it STARTS, not when it finishes.
Printing only on completion means a slow step shows nothing at all while it is
the very thing you are waiting on — which looks exactly like a hang. The line is
written without a newline, then completed with its timing when the step returns.

Everything goes through pytest's own `terminalreporter`. A plain `print()` is
swallowed by output capture unless the run passes `-s`, which would also dump
every stray library log into the same stream.
"""

from __future__ import annotations

from contextlib import contextmanager

WIDTH = 56


class Reporter:
    def __init__(self, config):
        # None when the terminal plugin is disabled (`-p no:terminal`), which is
        # legitimate — the suite should still run, just silently.
        self._tr = config.pluginmanager.get_plugin("terminalreporter")
        # Global output capture is ACTIVE during setup and the test call, and it
        # swallows terminal writes made there. Without suspending it, everything
        # below appears only under `-s` — which is exactly the case that matters,
        # since a slow step is the one you need to watch.
        self._capman = config.pluginmanager.get_plugin("capturemanager")

    # ── plumbing ─────────────────────────────────────────────────────────────

    @contextmanager
    def _uncaptured(self):
        if self._capman is not None and hasattr(self._capman, "global_and_fixture_disabled"):
            with self._capman.global_and_fixture_disabled():
                yield
        else:
            yield

    def _write(self, text: str, **markup) -> None:
        if self._tr is None:
            return
        with self._uncaptured():
            self._tr.write(text, **markup)
            self._flush()

    def _line(self, text: str = "", **markup) -> None:
        if self._tr is None:
            return
        with self._uncaptured():
            self._tr.write_line(text, **markup)
            self._flush()

    def _flush(self) -> None:
        # Without this a half-written step line sits in the buffer — which is
        # the whole failure mode this class exists to prevent.
        tw = getattr(self._tr, "_tw", None)
        if tw is not None and hasattr(tw, "flush"):
            tw.flush()

    # ── session ──────────────────────────────────────────────────────────────

    def session(self, count: int, base_url: str) -> None:
        self._line("")
        self._line(f"  {count} scenario{'' if count == 1 else 's'} against {base_url}", bold=True)
        self._line("  The first navigation can take a while — the dev server compiles on demand.")

    # ── scenario ─────────────────────────────────────────────────────────────

    def scenario(self, i: int, total: int, scenario_id: str, title: str) -> None:
        self._line("")
        self._line(f"  [{i}/{total}]  {scenario_id}  {title}", bold=True)

    def outcome(self, passed: bool, shots: int, seconds: float) -> None:
        mark = "PASS" if passed else "FAIL"
        self._line(
            f"     {mark}  {shots} shot{'' if shots == 1 else 's'}  {seconds:.1f}s",
            green=passed,
            red=not passed,
            bold=True,
        )

    # ── step ─────────────────────────────────────────────────────────────────

    def step_start(self, n: int, slug: str, gherkin: str) -> None:
        """Announce a step BEFORE running it, so a slow one is visible."""
        # The Gherkin line is the useful half — it says what the step was for,
        # not just what it was called.
        text = gherkin or slug
        if len(text) > WIDTH:
            text = text[: WIDTH - 1] + "…"
        self._write(f"     {n:>2}  {text:<{WIDTH}} ")

    def step_end(self, ok: bool, ms: int) -> None:
        """Complete the line opened by `step_start`."""
        self._line(f"{ms / 1000:>6.1f}s  {'ok' if ok else 'FAILED'}", red=not ok)

    def note(self, text: str, warn: bool = True) -> None:
        """A detail under the step it belongs to — a console error, a retry."""
        self._line(f"         {text}", yellow=warn)
