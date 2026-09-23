"""The image-payload guard + the agent-error category sanitizer.

Both land from the run b0642e0f post-mortem, where ``prototype-validate`` died
with the opaque *"The model rejected this request."*

Cause: the agent took nine 1280x720 screenshots and then ``read_file``'d each PNG
back. ``playwright_take_screenshot`` returns only a PATH by design, but deepagents'
filesystem middleware turns any binary read into a base64 image CONTENT BLOCK, so
the bytes the path-return avoided came straight back in — and every image then rode
along in EVERY later turn (744KB on disk, ~1MB as base64) until the provider
refused the request.

deepagents' own eviction cannot bound this: ``_build_evicted_content`` replaces
text blocks but deliberately PRESERVES media blocks.

The bound applies to images the model has already SEEN — those followed by an AI
turn. Fixtures below end with ``AIMessage("noted")`` to say exactly that; the
last three tests cover the unseen batch after the final AI turn (run 8a992018).
"""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agents.execution_engine.engine import (
    _GENERIC_AGENT_ERROR_MESSAGE,
    _sanitize_agent_error,
)
from app.agents.deep_agent_runner import _ImagePayloadGuardMiddleware


def _image_msg(path: str, tool_call_id: str) -> ToolMessage:
    """A ToolMessage shaped like deepagents' binary ``read_file`` result."""
    return ToolMessage(
        content=[{"type": "image", "base64": "iVBORw0KGgo" + "A" * 512, "mime_type": "image/png"}],
        tool_call_id=tool_call_id,
        name="read_file",
        additional_kwargs={"read_file_path": path, "read_file_media_type": "image/png"},
    )


class _Request:
    """Minimal ModelRequest stand-in — only `messages` + `override` are used."""

    def __init__(self, messages):
        self.messages = messages
        self.overridden_with = None

    def override(self, **kw):
        self.overridden_with = kw
        return _Request(kw.get("messages", self.messages))


def _run(messages, keep=2):
    guard = _ImagePayloadGuardMiddleware(keep=keep)
    seen = {}

    def handler(req):
        seen["req"] = req
        return "response"

    assert guard.wrap_model_call(_Request(messages), handler) == "response"
    return seen["req"].messages


def _image_count(messages) -> int:
    return sum(
        1
        for m in messages
        if isinstance(m.content, list)
        and any(b.get("type") != "text" for b in m.content_blocks)
    )


def test_keeps_only_the_most_recent_images():
    """The failing shape: nine screenshots read back into one conversation."""
    msgs = [HumanMessage(content="validate the prototype")]
    for i in range(9):
        msgs.append(AIMessage(content=f"checking page {i}"))
        msgs.append(_image_msg(f"/.browser/shot{i}.png", f"call{i}"))
    msgs.append(AIMessage(content="noted"))  # an AI turn after them: the model has SEEN these

    pruned = _run(msgs, keep=2)

    assert _image_count(msgs) == 9, "fixture should start with nine image blocks"
    assert _image_count(pruned) == 2, "guard must bound the retained images"


def test_the_retained_images_are_the_newest():
    msgs = [_image_msg(f"/.browser/shot{i}.png", f"call{i}") for i in range(5)]
    msgs.append(AIMessage(content="noted"))  # an AI turn after them: the model has SEEN these
    pruned = _run(msgs, keep=2)

    kept = [
        m.additional_kwargs["read_file_path"]
        for m in pruned
        if isinstance(m.content, list)
    ]
    assert kept == ["/.browser/shot3.png", "/.browser/shot4.png"]


def test_dropped_images_leave_a_named_placeholder():
    """The agent must be able to tell WHICH file went."""
    msgs = [_image_msg(f"/.browser/shot{i}.png", f"call{i}") for i in range(4)]
    msgs.append(AIMessage(content="noted"))  # an AI turn after them: the model has SEEN these
    pruned = _run(msgs, keep=1)

    dropped = [m for m in pruned if isinstance(m, ToolMessage) and isinstance(m.content, str)]
    assert len(dropped) == 3
    assert "/.browser/shot0.png" in dropped[0].content


def test_the_placeholder_never_invites_a_re_read():
    """The run-50df89da livelock, pinned.

    The first placeholder said "re-read it if you need to look at it again". With
    keep=2 and three pages wanted, each new read evicted the oldest, the text sent
    the model back for it, and the reader cycled the same three PNGs 122 times
    until the provider rejected the request. Anything that reads as an invitation
    to fetch the file again reopens that loop.
    """
    msgs = [_image_msg(f"/.extract/pages/0{i}/image-2.png", f"call{i}") for i in range(4)]
    msgs.append(AIMessage(content="noted"))  # an AI turn after them: the model has SEEN these
    pruned = _run(msgs, keep=2)

    for placeholder in (
        m.content for m in pruned if isinstance(m, ToolMessage) and isinstance(m.content, str)
    ):
        assert "re-read" not in placeholder
        assert "read it again" not in placeholder.replace("Do NOT read it again", "")
        assert "Do NOT read it again" in placeholder


def test_repeat_reads_of_one_path_cost_one_image():
    """The dedupe half of the fix — the exact shape reader 1 produced.

    Pages 04/05/06 read over and over. Only the newest block per path survives,
    so 41 cycles cost three images rather than 123.
    """
    msgs = []
    for _ in range(41):
        for page in ("04", "05", "06"):
            msgs.append(_image_msg(f"/.extract/pages/{page}/image-2.png", f"c{len(msgs)}"))
    msgs.append(AIMessage(content="noted"))  # an AI turn after them: the model has SEEN these

    pruned = _run(msgs, keep=2)

    assert _image_count(msgs) == 123
    # keep=2 bounds it further, but the dedupe alone already caps it at 3 paths.
    assert _image_count(pruned) == 2

    kept = [
        m.additional_kwargs["read_file_path"] for m in pruned if isinstance(m.content, list)
    ]
    assert len(set(kept)) == len(kept), "a retained path must never appear twice"


def test_duplicate_older_read_is_dropped_even_within_budget():
    """A duplicate does not consume the keep budget — a DISTINCT image gets it."""
    msgs = [
        _image_msg("/a.png", "c1"),
        _image_msg("/b.png", "c2"),
        _image_msg("/a.png", "c3"),  # newer copy of a.png
    ]
    msgs.append(AIMessage(content="noted"))  # an AI turn after them: the model has SEEN these
    pruned = _run(msgs, keep=2)

    kept = [
        m.additional_kwargs["read_file_path"] for m in pruned if isinstance(m.content, list)
    ]
    assert sorted(kept) == ["/a.png", "/b.png"], "the duplicate must not evict b.png"
    assert "duplicate read" in next(m.content for m in pruned if isinstance(m.content, str))


def test_identity_fields_survive_the_rewrite():
    """A replaced ToolMessage must still answer its tool call, or the turn breaks."""
    msgs = [_image_msg("/.browser/a.png", "call-a"), _image_msg("/.browser/b.png", "call-b")]
    msgs.append(AIMessage(content="noted"))  # an AI turn after them: the model has SEEN these
    pruned = _run(msgs, keep=1)

    replaced = next(m for m in pruned if isinstance(m.content, str))
    assert replaced.tool_call_id == "call-a"
    assert replaced.name == "read_file"


def test_conversation_without_images_is_untouched():
    """DORMANT for the overwhelming majority of agents — no override at all."""
    msgs = [HumanMessage(content="hi"), ToolMessage(content="plain text", tool_call_id="c1", name="grep")]
    guard = _ImagePayloadGuardMiddleware(keep=2)
    req = _Request(msgs)

    guard.wrap_model_call(req, lambda r: None)
    assert req.overridden_with is None, "no media blocks ⇒ the request must pass through"


def test_fewer_images_than_the_cap_are_all_kept():
    msgs = [_image_msg("/.browser/only.png", "c1")]
    pruned = _run(msgs, keep=2)
    assert _image_count(pruned) == 1


# ── error categories ─────────────────────────────────────────────────────────


def test_payload_size_fault_is_named():
    msg = _sanitize_agent_error(
        "ValidationException: The request payload is too large for model xyz"
    )
    assert msg != _GENERIC_AGENT_ERROR_MESSAGE
    assert "too large" in msg


def test_throttle_and_auth_and_timeout_are_named():
    assert "rate-limited" in _sanitize_agent_error("ThrottlingException: rate limit exceeded")
    assert "credential" in _sanitize_agent_error("UnrecognizedClientException: unauthorized")
    assert "did not respond" in _sanitize_agent_error("Read timeout on endpoint URL")


def test_access_denied_and_authentication_failed_are_named():
    """A4: the literal raw text from STABILIZATION.md's 12 auth-failed runs.

    Neither ``"accessdeniedexception"`` (no space) nor ``"authentication failed"``
    matched any needle before this fix — both fell through to the generic
    message, hiding an expired-credential run behind "The model rejected this
    request."
    """
    msg = _sanitize_agent_error(
        "botocore.errorfactory.AccessDeniedException: An error occurred "
        "(AccessDeniedException) when calling the InvokeModelWithResponseStream "
        "operation: Authentication failed for the request."
    )
    assert msg != _GENERIC_AGENT_ERROR_MESSAGE
    assert "credential" in msg


def test_unrecognised_fault_keeps_the_generic_message():
    """Additive by construction — anything unmatched behaves exactly as before."""
    assert _sanitize_agent_error("something entirely new") == _GENERIC_AGENT_ERROR_MESSAGE
    assert _sanitize_agent_error("") == _GENERIC_AGENT_ERROR_MESSAGE


def test_no_provider_detail_is_ever_echoed():
    """The whole point of the sanitizer: match on raw, never reproduce it."""
    raw = (
        "ValidationException: payload too large for "
        "arn:aws:bedrock:us-east-1:123456789012:model/anthropic.claude-sonnet-5 "
        "in region us-east-1"
    )
    out = _sanitize_agent_error(raw)
    for secret in ("arn:", "123456789012", "us-east-1", "anthropic.claude"):
        assert secret not in out


def _ai_calling(paths: list[str], prefix: str) -> AIMessage:
    """An AI turn that requested one read_file per path (the parallel-batch shape)."""
    return AIMessage(
        content="",
        tool_calls=[
            {"name": "read_file", "args": {"file_path": p}, "id": f"{prefix}{k}"}
            for k, p in enumerate(paths)
        ],
    )


def test_an_unseen_batch_is_never_evicted():
    """Run 8a992018: ten PNGs read in ONE turn, two kept, eight reported as
    'already viewed' — the model had never seen them. Everything after the last
    AI turn is unseen and must reach the model whole."""
    paths = [f"/.extract/pdf/doc/pages/{k:02d}/image-1.png" for k in range(10)]
    msgs = [HumanMessage(content="read the pages"), _ai_calling(paths, "c")]
    msgs += [_image_msg(p, f"c{k}") for k, p in enumerate(paths)]

    pruned = _run(msgs, keep=2)

    assert _image_count(pruned) == 10
    assert not any(isinstance(m.content, str) and "already viewed" in m.content for m in pruned)


def test_seen_images_stay_bounded_when_a_new_batch_arrives():
    """Older turns' images still obey the cap; only the current batch is exempt."""
    msgs = [HumanMessage(content="go")]
    for k in range(4):  # four earlier single reads, each answered by an AI turn
        msgs.append(_ai_calling([f"/old{k}.png"], f"o{k}-"))
        msgs.append(_image_msg(f"/old{k}.png", f"o{k}-0"))
        msgs.append(AIMessage(content=f"noted old{k}"))
    new = ["/new0.png", "/new1.png", "/new2.png"]
    msgs.append(_ai_calling(new, "n"))
    msgs += [_image_msg(p, f"n{k}") for k, p in enumerate(new)]

    pruned = _run(msgs, keep=2)

    kept = [m.additional_kwargs["read_file_path"] for m in pruned if isinstance(m.content, list)]
    assert kept == ["/old2.png", "/old3.png", "/new0.png", "/new1.png", "/new2.png"]


def test_unseen_duplicate_of_an_older_path_still_drops_the_older_copy():
    msgs = [
        _ai_calling(["/a.png"], "x"), _image_msg("/a.png", "x0"), AIMessage(content="seen a"),
        _ai_calling(["/a.png"], "y"), _image_msg("/a.png", "y0"),
    ]
    pruned = _run(msgs, keep=2)
    assert _image_count(pruned) == 1
    assert isinstance(pruned[1].content, str) and "duplicate read" in pruned[1].content


def test_recursion_limit_names_the_step_budget_not_the_model():
    """Run 17de7ccb: the Validator drove a browser for 133 model turns and 142 tool
    nodes — 12 of them real ``edit_file`` repairs — then LangGraph's step counter
    tripped. It rendered as "The model rejected this request.", which is wrong
    twice: the model rejected nothing, and the agent was working, not looping.
    """
    raw = (
        "Recursion limit of 400 reached without hitting a stop condition. "
        "You can increase the limit by setting the `recursion_limit` config key."
    )
    msg = _sanitize_agent_error(raw)
    assert msg != _GENERIC_AGENT_ERROR_MESSAGE
    assert "ran out of steps" in msg
    assert "recursion_limit" in msg
    # The class name alone (no prose) must categorise too — that is what the
    # traceback carries when the message is wrapped.
    assert _sanitize_agent_error("langgraph.errors.GraphRecursionError") == msg
    # Never blames the model, and never echoes the raw text back.
    assert "rejected" not in msg
    assert "400" not in msg
