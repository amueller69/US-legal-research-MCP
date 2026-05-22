"""US Code tools - citation lookup and navigation."""

from legal_mcp._app import mcp


@mcp.tool(
    description="Retrieve a specific US Code section by citation",
    annotations={"readOnlyHint": True},
)
async def get_usc_section(title: str, section: str) -> dict:
    """
    Retrieve USC section with full text.

    Args:
        title: Title number (e.g., "42")
        section: Section number (e.g., "1983")

    Returns:
        {
            "citation": "42 USC § 1983",
            "heading": "Civil action for deprivation of rights",
            "text": "Every person who...",
            "chapter": "21",
            "effective_date": "1871-04-20",
        }

    Examples:
        - get_usc_section(title="42", section="1983")
        - get_usc_section(title="18", section="242")
    """
    from legal_mcp.storage import sqlite_db

    result = await sqlite_db.get_section("usc_sections", title, section)
    if not result:
        return {"error": f"Section not found: {title} USC § {section}"}

    return {
        "citation": result.get("citation") or f"{title} USC § {result.get('section', section)}",
        "heading": result.get("heading"),
        "text": result.get("text"),
        "chapter": result.get("chapter"),
        "subchapter": result.get("subchapter"),
        "effective_date": result.get("effective_date"),
    }


@mcp.tool(
    description="Get table of contents for a US Code title",
    annotations={"readOnlyHint": True},
)
async def get_title_toc(title: str) -> dict:
    """
    Get hierarchical table of contents for a USC title.

    Args:
        title: Title number (e.g., "42")

    Returns:
        {
            "title": "42",
            "chapters": [
                {
                    "number": "21",
                    "sections": [
                        {"number": "1981", "heading": "..."},
                        ...
                    ]
                },
                ...
            ]
        }

    Examples:
        - get_title_toc(title="42")
        - get_title_toc(title="26")
    """
    from legal_mcp.storage import sqlite_db

    result = await sqlite_db.get_title_toc(title)
    if not result["chapters"]:
        return {"error": f"Title {title} not found in database"}

    return result
