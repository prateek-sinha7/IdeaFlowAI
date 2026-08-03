"""Harbor agents that dispatch our REAL prototype prompts, one per stage.

Why this exists
---------------
Harbor's built-in agents are coding CLIs. Ours are prompts — composed by
`agents.factory._compose_system_prompt` from `AGENT.md` plus guardrails, skills
and any active override. To evaluate what production runs, the agent under test
must send THOSE bytes.

Why the prompt comes from a file
--------------------------------
Composition lives in the backend on python3.11; Harbor needs 3.12+. So
`eval.sh` composes with python3.11 and writes `<task>/agent/system_prompt.md`
plus its sha256. The hash becomes the agent's version string, which is how a
Harbor trial can be proven to have used the same prompt bytes as an
`evals/minimal` run.

Chaining stages
---------------
`prototype-plan` declares `consumes: [prototype-specify]`, and it is a text-only
agent — production hands it the spec IN THE MESSAGE, not as a file on disk. So
this agent reads the upstream deliverable on the host and prepends it to the
user message, mirroring `evals.minimal.run._compose_message`.

It ALSO uploads the upstream file into the container. The agent does not need
it there, but the verifier does: checking that the plan covers the pages the
spec defined requires both documents side by side. That mirrors
`_canonical_seeds`.

Where this runs
---------------
On the HOST. Harbor hands over an `environment` handle; the agent calls the
model itself and uploads results. The container needs no API key and no network.
"""

from __future__ import annotations

import os
import pathlib
import tempfile

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

HERE = pathlib.Path(__file__).resolve().parent


class VelocityAgent(BaseAgent):
    """One model call with a real composed prompt; writes one deliverable.

    Configured by environment variables rather than constructor arguments so
    that `eval.sh` can drive it without Harbor's --ak plumbing:

      VELOCITY_TASK_DIR   task folder holding agent/system_prompt.md
      VELOCITY_DELIVERABLE where to write in the container (/app/tasks.md)
      VELOCITY_UPSTREAM   optional host path to the previous stage's output
      VELOCITY_UPSTREAM_AS  filename it takes inside the container
    """

    _AGENT_NAME = "velocity"

    def __init__(self, model: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._model = model or "mistral/mistral-small-latest"
        self._task_dir = pathlib.Path(
            os.environ.get("VELOCITY_TASK_DIR", HERE / "prototype-specify"))
        self._deliverable = os.environ.get("VELOCITY_DELIVERABLE", "/app/spec.md")
        self._upstream = os.environ.get("VELOCITY_UPSTREAM") or None
        self._upstream_as = os.environ.get("VELOCITY_UPSTREAM_AS", "spec.md")

    @staticmethod
    def name() -> str:
        return "velocity"

    def version(self) -> str | None:
        sha = self._task_dir / "agent" / "system_prompt.sha"
        # The prompt hash IS the version: two trials sharing it ran identical
        # prompt bytes, and activating an override changes it visibly rather
        # than silently altering results.
        return sha.read_text(encoding="utf-8").strip()[:19] if sha.exists() else "unknown"

    async def setup(self, environment: BaseEnvironment) -> None:
        return None

    async def run(self, instruction: str, environment: BaseEnvironment,
                  context: AgentContext) -> None:
        import litellm

        system_prompt = (self._task_dir / "agent" / "system_prompt.md").read_text(encoding="utf-8")

        message = instruction
        if self._upstream:
            upstream = pathlib.Path(self._upstream)
            body = upstream.read_text(encoding="utf-8")
            # Same shape as run._compose_message: the upstream artifact is
            # labelled by the filename the downstream prompt refers to, so the
            # agent recognises it as the spec rather than as more brief.
            message = (
                f"=== {self._upstream_as} (from the previous stage) ===\n"
                f"{body}\n\n=== YOUR TASK ===\n{instruction}"
            )
            # The verifier needs it too, to check coverage of one against the other.
            await environment.upload_file(upstream, f"/app/{self._upstream_as}")

        reply = await litellm.acompletion(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            api_key=os.environ.get("MISTRAL_API_KEY"),
            # Matches settings.LLM_CALL_TIMEOUT_SECONDS. The library default is
            # far lower and truncates long generations mid-stream.
            timeout=900,
        )
        text = reply.choices[0].message.content or ""

        usage = getattr(reply, "usage", None)
        if usage is not None:
            context.n_input_tokens = getattr(usage, "prompt_tokens", 0) or 0
            context.n_output_tokens = getattr(usage, "completion_tokens", 0) or 0

        with tempfile.TemporaryDirectory() as folder:
            local = pathlib.Path(folder) / pathlib.Path(self._deliverable).name
            local.write_text(text, encoding="utf-8")
            await environment.upload_file(local, self._deliverable)


class VelocitySpecifyAgent(VelocityAgent):
    """Kept so existing commands and stored job configs still resolve."""

    @staticmethod
    def name() -> str:
        return "velocity-specify"
