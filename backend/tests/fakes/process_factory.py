"""In-memory ``ProcessSpawner`` for the workflow builder's script runner.

``FakeProcessFactory`` satisfies
:class:`app.agents.workflow_builder.script_runner.ProcessSpawner`, so a test puts
it in ``ScriptContext(spawn=factory)`` and :func:`execute` runs unmodified with no
real subprocess. Each start is recorded with its ``argv``, ``env`` and ``cwd``.
What the process does is scripted by a :class:`ProcessScript`.

Scripts are consumed in order, one per start. When the queue is empty every
further start uses ``default``. A script can play back:

- an exit code (``exit_code``);
- output, as a list of byte chunks (``chunks``) that the stream returns one read
  at a time, each preceded by ``chunk_delay`` seconds;
- delays: ``start_delay`` before the spawn returns and ``exit_delay`` between the
  end of the output and the exit;
- a hang (``hang=True``): after the chunks the stream and ``wait()`` block until
  ``kill()`` is called, the way a script that never ends behaves;
- a start failure (``start_error``): the spawn raises it, like a missing
  interpreter.

``kill()`` ends a hanging or delayed process with exit code ``-9``. The factory
also counts live processes (``active``, ``max_active``) and keeps every started
process in ``processes``, so a test can check the concurrency bound and that
every process was waited for.

Nothing here asserts. Delays use ``asyncio.sleep``; keep them in milliseconds.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "KILLED_EXIT_CODE",
    "FakeProcess",
    "FakeProcessFactory",
    "FakeStream",
    "ProcessScript",
    "ProcessStart",
]

KILLED_EXIT_CODE = -9
"""Exit code of a process that ``kill()`` ended."""


@dataclass(frozen=True)
class ProcessStart:
    """One recorded spawn call.

    Attributes:
        argv: The command line, as given.
        cwd: The working directory.
        env: A copy of the environment mapping, exactly as given.
    """

    argv: tuple[str, ...]
    cwd: Path
    env: Mapping[str, str]


def _no_chunks() -> tuple[bytes, ...]:
    return ()


@dataclass(frozen=True)
class ProcessScript:
    """What one fake process does.

    Attributes:
        exit_code: Exit code once the output ends and ``exit_delay`` has passed.
        chunks: Output pieces. The stream returns one piece per ``read`` call
            (split further if the caller asks for fewer bytes).
        chunk_delay: Seconds to wait before each piece.
        start_delay: Seconds to wait inside the spawn call.
        exit_delay: Seconds between the end of the output and the exit.
        hang: When True the stream and ``wait()`` block after the chunks until
            ``kill()`` is called.
        start_error: When set, the spawn call raises it and no process exists.
    """

    exit_code: int = 0
    chunks: tuple[bytes, ...] = field(default_factory=_no_chunks)
    chunk_delay: float = 0.0
    start_delay: float = 0.0
    exit_delay: float = 0.0
    hang: bool = False
    start_error: OSError | None = None

    @classmethod
    def with_text(
        cls, text: str, *, exit_code: int = 0, hang: bool = False
    ) -> ProcessScript:
        """Return a script whose output is ``text`` encoded as UTF-8 in one chunk."""
        return cls(exit_code=exit_code, chunks=(text.encode("utf-8"),), hang=hang)


class FakeStream:
    """The merged stdout and stderr pipe of a :class:`FakeProcess`."""

    def __init__(self, process: FakeProcess) -> None:
        self._process = process
        self._pending: deque[bytes] = deque(process.script.chunks)

    # ``n`` has a default to match ``StreamLike.read(self, n=-1, /)``, which is
    # also the signature of ``asyncio.StreamReader.read``.
    async def read(self, n: int = -1) -> bytes:
        """Return up to ``n`` bytes, or ``b""`` at the end or after a kill."""
        script = self._process.script
        if self._process.killed.is_set():
            return b""
        if script.chunk_delay and self._pending:
            await asyncio.sleep(script.chunk_delay)
        if self._pending:
            chunk = self._pending.popleft()
            if 0 <= n < len(chunk):
                self._pending.appendleft(chunk[n:])
                chunk = chunk[:n]
            return chunk
        if script.hang:
            await self._process.killed.wait()
        return b""


class FakeProcess:
    """A scripted process. Satisfies ``ProcessLike``."""

    def __init__(self, script: ProcessScript, factory: FakeProcessFactory) -> None:
        self.script = script
        self.killed = asyncio.Event()
        self.kill_count = 0
        self.wait_count = 0
        self._factory = factory
        self._returncode: int | None = None
        self._stdout = FakeStream(self)

    @property
    def stdout(self) -> FakeStream:
        """The merged output pipe."""
        return self._stdout

    @property
    def returncode(self) -> int | None:
        """The exit code, or ``None`` while the process runs."""
        return self._returncode

    def kill(self) -> None:
        """End the process with :data:`KILLED_EXIT_CODE`. No effect once it exited."""
        self.kill_count += 1
        if self._returncode is None:
            self._finish(KILLED_EXIT_CODE)
        self.killed.set()

    async def wait(self) -> int:
        """Wait for the exit and return the exit code."""
        self.wait_count += 1
        if self._returncode is None:
            if self.script.hang:
                await self.killed.wait()
            elif self.script.exit_delay:
                await asyncio.sleep(self.script.exit_delay)
        if self._returncode is None:
            return self._finish(self.script.exit_code)
        return self._returncode

    def _finish(self, code: int) -> int:
        self._returncode = code
        self._factory.active -= 1
        return code


class FakeProcessFactory:
    """A ``ProcessSpawner`` that records starts and plays back scripts.

    Attributes:
        starts: Every spawn call, in order, including ones that failed.
        processes: Every process that started, in order.
        active: Processes started and not yet exited or killed.
        max_active: The highest value ``active`` reached.
    """

    def __init__(
        self, *scripts: ProcessScript, default: ProcessScript | None = None
    ) -> None:
        """Create a factory.

        Args:
            *scripts: Scripts for the first starts, in order.
            default: Script for every start after the queue is empty. Defaults
                to a process that prints nothing and exits with 0.
        """
        self._queue: deque[ProcessScript] = deque(scripts)
        self._default = default if default is not None else ProcessScript()
        self.starts: list[ProcessStart] = []
        self.processes: list[FakeProcess] = []
        self.active = 0
        self.max_active = 0

    async def __call__(
        self, argv: Sequence[str], *, cwd: Path, env: Mapping[str, str]
    ) -> FakeProcess:
        """Record the start and return the next scripted process.

        Raises:
            OSError: The script's ``start_error``.
        """
        self.starts.append(ProcessStart(tuple(argv), cwd, dict(env)))
        script = self._queue.popleft() if self._queue else self._default
        if script.start_delay:
            await asyncio.sleep(script.start_delay)
        if script.start_error is not None:
            raise script.start_error
        process = FakeProcess(script, self)
        self.processes.append(process)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        return process
