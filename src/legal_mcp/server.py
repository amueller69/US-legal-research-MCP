"""Legal MCP server entrypoint.

The shared FastMCP app is defined in :mod:`legal_mcp._app`. Importing
``legal_mcp.tools`` registers all tool functions via ``@mcp.tool`` decorators.
"""

from legal_mcp._app import mcp

import legal_mcp.tools  # noqa: F401 - side effect: registers all tools

# Re-export tool functions for tests and direct imports.
from legal_mcp.tools.bill_tools import get_public_law, search_bills  # noqa: F401
from legal_mcp.tools.cfr_tools import get_cfr_section, find_implementing_regulations  # noqa: F401
from legal_mcp.tools.search_tools import (  # noqa: F401
    get_database_status,
    search_cfr_semantic,
    search_fulltext,
    search_usc_semantic,
)
from legal_mcp.tools.usc_tools import get_title_toc, get_usc_section  # noqa: F401


if __name__ == "__main__":
    mcp.run()
