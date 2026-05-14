"""Semantic and full-text search tools."""

from legal_mcp._app import mcp


@mcp.tool(
    description="Semantic search across US Code using vector similarity",
    annotations={"readOnlyHint": True},
)
async def search_usc_semantic(query: str, limit: int = 10) -> list[dict]:
    """
    Semantic search for USC sections conceptually related to query.

    Args:
        query: Natural language query (e.g., "qualified immunity for police")
        limit: Maximum results to return (default: 10)

    Returns:
        [
            {
                "citation": "42 USC § 1983",
                "heading": "Civil action for deprivation of rights",
                "similarity_score": 0.87,
                "excerpt": "Every person who, under color of...",
                "chapter": "21"
            },
            ...
        ]

    Examples:
        - "qualified immunity for government officials"
        - "civil rights violations by law enforcement"
        - "employment discrimination remedies"
    """
    from legal_mcp.storage import chroma_client

    results = await chroma_client.search(
        query, n_results=limit, where={"source_type": "usc"}
    )

    ids = results.get("ids", [[]])[0]
    distances = results.get("distances", [[]])[0]
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]

    output = []
    for i, doc_id in enumerate(ids):
        meta = metadatas[i] if i < len(metadatas) else {}
        distance = distances[i] if i < len(distances) else 1.0
        doc = documents[i] if i < len(documents) else ""

        output.append({
            "citation": meta.get("citation"),
            "heading": meta.get("heading"),
            "similarity_score": round(1 - distance, 4),
            "excerpt": doc[:500] if doc else "",
            "title": meta.get("title"),
            "section": meta.get("section"),
            "chapter": meta.get("chapter"),
        })

    return output


@mcp.tool(
    description="Semantic search across Code of Federal Regulations",
    annotations={"readOnlyHint": True},
)
async def search_cfr_semantic(query: str, limit: int = 10) -> list[dict]:
    """
    Semantic search for CFR sections conceptually related to query.

    Args:
        query: Natural language query
        limit: Maximum results (default: 10)

    Returns:
        List of CFR sections with similarity scores

    Examples:
        - "tax-exempt retirement plans"
        - "environmental impact assessments"
    """
    from legal_mcp.storage import chroma_client

    results = await chroma_client.search(
        query, n_results=limit, where={"source_type": "cfr"}
    )

    ids = results.get("ids", [[]])[0]
    if not ids:
        return [{"message": "CFR data not yet loaded. Run 'legal-mcp setup' and CFR indexing when available."}]

    distances = results.get("distances", [[]])[0]
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]

    output = []
    for i, doc_id in enumerate(ids):
        meta = metadatas[i] if i < len(metadatas) else {}
        distance = distances[i] if i < len(distances) else 1.0
        doc = documents[i] if i < len(documents) else ""

        output.append({
            "citation": meta.get("citation"),
            "heading": meta.get("heading"),
            "similarity_score": round(1 - distance, 4),
            "excerpt": doc[:500] if doc else "",
            "title": meta.get("title"),
            "section": meta.get("section"),
        })

    return output


@mcp.tool(
    description="Full-text keyword search using SQLite FTS",
    annotations={"readOnlyHint": True},
)
async def search_fulltext(query: str, source: str = "usc", limit: int = 20) -> list[dict]:
    """
    Traditional keyword search with boolean operators.

    Args:
        query: Search terms (supports AND, OR, NOT, "exact phrases")
        source: Data source to search ('usc' or 'cfr')
        limit: Maximum results (default: 20)

    Returns:
        List of matching sections with highlighted snippets

    Examples:
        - search_fulltext("due process", source="usc")
        - search_fulltext("commerce AND interstate", source="usc")
        - search_fulltext('"equal protection" NOT state', source="usc")
    """
    from legal_mcp.storage import sqlite_db

    if source not in ("usc", "cfr"):
        return [{"error": f"Invalid source '{source}'. Use 'usc' or 'cfr'."}]

    table = f"{source}_sections"
    results = await sqlite_db.search_fulltext(query, table, limit)

    return [
        {
            "citation": r.get("citation"),
            "heading": r.get("heading"),
            "snippet": r.get("snippet"),
            "title": r.get("title"),
            "section": r.get("section"),
            "chapter": r.get("chapter"),
        }
        for r in results
    ]


@mcp.tool(
    description="Get status of Legal MCP databases",
    annotations={"readOnlyHint": True},
)
async def get_database_status() -> dict:
    """
    Show database status and statistics.

    Returns:
        {
            "sqlite": {
                "usc_sections": 55000,
                "cfr_sections": 0,
                "release_point": "Public Law 119-84",
                "last_updated": "2026-04-25T..."
            },
            "chromadb": {
                "count": 55000,
                "embedding_model": "all-MiniLM-L6-v2",
                ...
            }
        }
    """
    from legal_mcp.storage import sqlite_db, chroma_client, get_metadata, get_collection_info

    conn = sqlite_db._get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as n FROM usc_sections")
    usc_count = cursor.fetchone()["n"]

    cursor.execute("SELECT COUNT(*) as n FROM cfr_sections")
    cfr_count = cursor.fetchone()["n"]

    release_point = await get_metadata("usc_release_point")
    last_update = await get_metadata("last_usc_update")
    chroma_info = await get_collection_info()

    return {
        "sqlite": {
            "usc_sections": usc_count,
            "cfr_sections": cfr_count,
            "release_point": release_point or "not initialized",
            "last_updated": last_update,
        },
        "chromadb": chroma_info,
    }
