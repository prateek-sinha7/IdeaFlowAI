"""EXPERIMENT ONLY: record every PLANNER.md the engine writes + the composed first message."""
import pytest

CAPTURE = []


@pytest.fixture(autouse=True)
def _capture_planner_md(monkeypatch):
    from app.agents.sandbox import RunSandbox

    orig = RunSandbox.write

    def spy(self, relpath, content):
        if str(relpath).endswith("PLANNER.md"):
            CAPTURE.append((str(self.root), content))
        return orig(self, relpath, content)

    monkeypatch.setattr(RunSandbox, "write", spy)
    yield


def pytest_terminal_summary(terminalreporter):
    for root, content in CAPTURE:
        import pathlib as _pl
        ondisk = _pl.Path(root, "PLANNER.md")
        terminalreporter.write_line("=== PLANNER.md written @ " + root)
        terminalreporter.write_line("    on disk after the test: " + str(ondisk.exists()) + (" | contains SPINNAKER-SENTINEL: " + str("SPINNAKER-SENTINEL" in ondisk.read_text()) if ondisk.exists() else ""))
        for ln in content.splitlines():
            terminalreporter.write_line("    | " + ln)
