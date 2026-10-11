"""conftest.py for agents test suite.

Fixtures are provided by the shared agents_fixtures plugin in tests/plugins/.
This file re-exports them for backward compatibility during migration.
"""

from __future__ import annotations

# Re-export all fixtures from the plugin module
from tests.plugins.agents_fixtures import (  # noqa: F401
    create_agent_file,
    in_process_checkpointer,
    local_git_fixture,
    make_agent_md,
    tmp_agent_dir,
)
