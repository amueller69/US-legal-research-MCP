"""Bills and session laws tools - integrates with GovInfo MCP."""

from legal_mcp._app import mcp


@mcp.tool(
    description="Retrieve a public law (session law) by citation",
    annotations={"readOnlyHint": True},
)
async def get_public_law(congress: int, law_number: int) -> dict:
    """
    Retrieve public law (Statutes at Large) by citation.

    Args:
        congress: Congress number (e.g., 119)
        law_number: Public law number (e.g., 83)

    Returns:
        {
            "citation": "Public Law 119-83",
            "title": "...",
            "enacted_date": "2026-04-13",
            "summary": "...",
            "full_text_url": "https://www.govinfo.gov/...",
            "sections_amended": ["42 USC § 1983", ...]
        }

    Examples:
        - get_public_law(congress=119, law_number=83)

    Note: Critical for non-positive law USC titles where session law
    is authoritative when it conflicts with the Code.
    """
    # TODO: Implement public law retrieval
    # 1. Query SQLite cache first
    # 2. If not cached, call GovInfo MCP
    # 3. Parse and return result
    return {"error": "Public law retrieval not yet implemented. GovInfo MCP integration is planned for Phase 3."}


@mcp.tool(
    description="Search for bills and legislation",
    annotations={"readOnlyHint": True},
)
async def search_bills(query: str, congress: int = 119, limit: int = 10) -> list[dict]:
    """
    Search for bills and legislation via GovInfo MCP.

    Args:
        query: Search query (e.g., "qualified immunity" or "42 USC § 1983")
        congress: Congress number to search (default: 119)
        limit: Maximum results (default: 10)

    Returns:
        [
            {
                "bill_number": "H.R. 1234",
                "title": "...",
                "sponsor": "...",
                "status": "Introduced",
                "summary": "...",
                "url": "https://www.govinfo.gov/..."
            },
            ...
        ]

    Examples:
        - search_bills("qualified immunity", congress=119)
        - search_bills("42 USC § 1983")
    """
    # TODO: Implement bill search
    # 1. Call GovInfo MCP searchGovInfo tool
    # 2. Filter results by congress
    # 3. Parse and format results
    return [{"error": "Bill search not yet implemented. GovInfo MCP integration is planned for Phase 3."}]
