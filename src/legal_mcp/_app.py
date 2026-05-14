"""FastMCP application instance and server lifecycle."""

import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastmcp import FastMCP


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[dict]:
    """Initialize storage when the MCP server starts."""
    from legal_mcp.storage import chroma_client, sqlite_db

    sys.stderr.write("Starting Legal MCP server...\n")
    await sqlite_db.initialize()
    await chroma_client.initialize()
    sys.stderr.write("Legal MCP storage initialized\n")

    try:
        yield {}
    finally:
        sqlite_db.close()
        sys.stderr.write("Shutting down Legal MCP server...\n")


mcp = FastMCP("Legal MCP", lifespan=server_lifespan)
