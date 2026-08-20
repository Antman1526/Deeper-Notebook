"""Built-in chat tools (env-keyed web search, etc.)."""

from deeper_notebook.tools.add_web_source import (
    build_add_web_source_tool,
)
from deeper_notebook.tools.opencode import (
    OPENCODE_TOOL_NAME,
    build_opencode_tool,
    opencode_enabled,
)
