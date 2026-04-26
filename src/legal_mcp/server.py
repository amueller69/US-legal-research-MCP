"""
Legal MCP Server - FastMCP server with tool registration.

This module sets up the MCP server and registers all legal research tools.
Tools are implemented in the tools/ subdirectory.
"""

from mcp import FastMCP
from legal_mcp.tools import usc_tools, cfr_tools, bill_tools, search_tools

# Initialize FastMCP server
mcp = FastMCP("legal-mcp")


@mcp.on_startup()
async def startup():
    """Initialize database connections and resources on server startup."""
    from legal_mcp.storage import sqlite_db, chroma_client

    # Initialize storage layers
    await sqlite_db.initialize()
    await chroma_client.initialize()

    print("Legal MCP server initialized")


# Register USC tools
mcp.tool()(usc_tools.get_usc_section)
mcp.tool()(usc_tools.get_title_toc)

# Register CFR tools
mcp.tool()(cfr_tools.get_cfr_section)
mcp.tool()(cfr_tools.find_implementing_regulations)

# Register bill/session law tools
mcp.tool()(bill_tools.get_public_law)
mcp.tool()(bill_tools.search_bills)

# Register search tools
mcp.tool()(search_tools.search_usc_semantic)
mcp.tool()(search_tools.search_cfr_semantic)
mcp.tool()(search_tools.search_fulltext)
mcp.tool()(search_tools.get_database_status)


# Entry point for MCP clients
if __name__ == "__main__":
    mcp.run()
