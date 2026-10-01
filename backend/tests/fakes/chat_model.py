"""In-memory chat model for tests that build a real runner but never need a real reply."""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class FakeStaticChatModel(BaseChatModel):
    """Answers every call with ``reply`` and accepts ``bind_tools``. No network.

    ``create_runner`` binds the agent's tools to whatever model it is handed, so a
    fake has to tolerate ``bind_tools``; the stock LangChain fakes raise there.
    """

    reply: str = "ok"

    @property
    def _llm_type(self) -> str:
        return "fake-static-chat-model"

    def bind_tools(self, tools: Any, **kwargs: Any) -> FakeStaticChatModel:
        return self

    def _generate(
        self,
        messages: list[Any],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.reply))])
