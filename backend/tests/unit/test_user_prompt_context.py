"""The user's request is persisted to .context/user-prompt.md for any agent to read."""

from agents.execution_engine.user_prompt import (
    RUN_ID_PATH,
    USER_PROMPT_PATH,
    write_run_id_to_sandbox,
    write_user_prompt_to_sandbox,
)
from app.agents.sandbox import AGENT_READABLE_RESERVED, RESERVED_PATHS


class _FakeSandbox:
    def __init__(self):
        self.files: dict[str, str] = {}

    def write(self, path: str, content: str) -> None:
        self.files[path] = content


def test_writes_request_to_user_prompt_md():
    sb = _FakeSandbox()
    write_user_prompt_to_sandbox(sb, "Halo, Hoe gaat het?")
    assert sb.files == {".context/user-prompt.md": "Halo, Hoe gaat het?\n"}


def test_strips_inherited_pipeline_context():
    sb = _FakeSandbox()
    msg = "Make it blue\n\n=== CONTEXT FROM PREVIOUS PIPELINE ===\nold stuff"
    write_user_prompt_to_sandbox(sb, msg)
    assert sb.files[USER_PROMPT_PATH] == "Make it blue\n"


def test_empty_message_writes_nothing():
    sb = _FakeSandbox()
    write_user_prompt_to_sandbox(sb, "")
    assert sb.files == {}


def test_write_failure_never_raises():
    class _Broken:
        def write(self, path, content):
            raise OSError("disk full")

    write_user_prompt_to_sandbox(_Broken(), "hi")
    write_user_prompt_to_sandbox(None, "hi")


def test_writes_run_id_with_newline():
    sb = _FakeSandbox()
    write_run_id_to_sandbox(sb, "3f2a9c1e-0000-4000-8000-000000000001")
    assert sb.files == {".context/run-id.txt": "3f2a9c1e-0000-4000-8000-000000000001\n"}
    assert sb.files[RUN_ID_PATH].endswith("\n")


def test_empty_run_id_writes_nothing():
    sb = _FakeSandbox()
    write_run_id_to_sandbox(sb, "")
    write_run_id_to_sandbox(sb, None)
    assert sb.files == {}


def test_run_id_write_failure_never_raises():
    class _Broken:
        def write(self, path, content):
            raise OSError("disk full")

    write_run_id_to_sandbox(_Broken(), "abc")
    write_run_id_to_sandbox(None, "abc")


def test_path_is_reserved_and_agent_readable():
    # Agents may read it but never overwrite it.
    assert USER_PROMPT_PATH.startswith(".context/")
    assert ".context/" in RESERVED_PATHS
    assert ".context/" in AGENT_READABLE_RESERVED


def test_strip_inline_attachments_keeps_brief_and_names():
    from agents.execution_engine.user_prompt import strip_inline_attachments

    msg = (
        "Please create prototype"
        "\n\n=== Attached: a.pdf ===\nPAGE TEXT A\n=== End: a.pdf ==="
        "\n\n=== Attached: b.json ===\n[1, 2]\n=== End: b.json ==="
    )
    out = strip_inline_attachments(msg)
    assert out.startswith("Please create prototype\n\n")
    assert "PAGE TEXT A" not in out and "[1, 2]" not in out
    assert "- .uploads/a.pdf" in out and "- .uploads/b.json" in out


def test_strip_inline_attachments_noop_without_blocks():
    from agents.execution_engine.user_prompt import strip_inline_attachments

    assert strip_inline_attachments("just a brief") == "just a brief"
