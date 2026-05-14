"""MCP tools for legal research.

Importing this package registers all tool modules with the shared FastMCP app.
"""

from legal_mcp.tools import bill_tools, cfr_tools, search_tools, usc_tools  # noqa: F401

__all__ = [
    "bill_tools",
    "cfr_tools",
    "search_tools",
    "usc_tools",
]
