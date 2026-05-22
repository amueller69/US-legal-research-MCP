"""Tests for storage layer (SQLite and ChromaDB)."""

import pytest
import asyncio
from pathlib import Path
import tempfile
import shutil

# Import storage functions
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from legal_mcp.storage import (
    initialize_sqlite,
    initialize_chroma,
    insert_sections,
    get_section,
    search_fulltext,
    upsert_documents,
    search_semantic,
    get_collection_info,
)


@pytest.fixture
def temp_config_dir():
    """Create temporary config directory for tests."""
    temp_dir = tempfile.mkdtemp()

    # Mock the config directory
    import legal_mcp.storage.sqlite_db as sqlite_db
    import legal_mcp.storage.chroma_client as chroma_client

    original_db_path = sqlite_db.DB_PATH
    original_persist_dir = chroma_client.PERSIST_DIR

    test_db_path = Path(temp_dir) / "legal.db"
    test_chroma_dir = Path(temp_dir) / "chroma_db"

    sqlite_db.DB_PATH = test_db_path
    chroma_client.PERSIST_DIR = test_chroma_dir

    # Reset global state
    sqlite_db._connection = None
    chroma_client._client = None
    chroma_client._collection = None
    chroma_client._embedding_function = None

    yield temp_dir

    # Cleanup connections
    sqlite_db.close()
    chroma_client.close()

    # Restore original paths
    sqlite_db.DB_PATH = original_db_path
    chroma_client.PERSIST_DIR = original_persist_dir

    # Remove temp directory
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_sqlite_initialization(temp_config_dir):
    """Test SQLite database initialization."""
    await initialize_sqlite()

    # Check that database file was created
    import legal_mcp.storage.sqlite_db as sqlite_db
    assert sqlite_db.DB_PATH.exists()


@pytest.mark.asyncio
async def test_sqlite_insert_and_retrieve(temp_config_dir):
    """Test inserting and retrieving USC sections."""
    await initialize_sqlite()

    # Insert test section
    test_sections = [
        {
            "title": "42",
            "section": "1983",
            "heading": "Civil action for deprivation of rights",
            "text": "Every person who, under color of any statute...",
            "chapter": "21",
        }
    ]

    count = await insert_sections("usc_sections", test_sections)
    assert count == 1

    # Retrieve the section
    section = await get_section("usc_sections", "42", "1983")
    assert section is not None
    assert section["title"] == "42"
    assert section["section"] == "1983"
    assert section["heading"] == "Civil action for deprivation of rights"


@pytest.mark.asyncio
async def test_sqlite_usc_lookup_normalizes_section_dashes(temp_config_dir):
    """USC lookups should accept regular hyphens for sections stored with en dashes."""
    await initialize_sqlite()

    await insert_sections(
        "usc_sections",
        [
            {
                "title": "42",
                "section": "299b–21",
                "heading": "Definitions",
                "text": "The term patient safety work product means...",
                "chapter": "6A",
            }
        ],
    )

    section = await get_section("usc_sections", "42", "299b-21")

    assert section is not None
    assert section["section"] == "299b–21"
    assert section["citation"] == "42 USC § 299b–21"


@pytest.mark.asyncio
async def test_sqlite_fulltext_search(temp_config_dir):
    """Test full-text search."""
    await initialize_sqlite()

    # Insert test sections
    test_sections = [
        {
            "title": "42",
            "section": "1983",
            "heading": "Civil action for deprivation of rights",
            "text": "Every person who, under color of any statute, ordinance, regulation, custom, or usage...",
            "chapter": "21",
        },
        {
            "title": "42",
            "section": "1985",
            "heading": "Conspiracy to interfere with civil rights",
            "text": "If two or more persons conspire to prevent by force, intimidation...",
            "chapter": "21",
        }
    ]

    await insert_sections("usc_sections", test_sections)

    # Search for "civil rights"
    results = await search_fulltext("civil rights", "usc_sections", limit=10)
    assert len(results) > 0
    assert any("civil" in r["heading"].lower() for r in results)


@pytest.mark.asyncio
async def test_chromadb_initialization(temp_config_dir):
    """Test ChromaDB initialization."""
    await initialize_chroma()

    info = await get_collection_info()
    assert info["name"] == "legal_documents"
    assert info["count"] == 0  # Should be empty initially


@pytest.mark.asyncio
async def test_chromadb_upsert_and_search(temp_config_dir):
    """Test upserting documents and semantic search."""
    await initialize_chroma()

    # Upsert test documents
    documents = [
        "42 USC 1983: Civil action for deprivation of rights. Every person who, under color of statute...",
        "42 USC 1985: Conspiracy to interfere with civil rights. If two or more persons conspire..."
    ]
    metadatas = [
        {
            "source_type": "usc",
            "title": "42",
            "section": "1983",
            "citation": "42 USC § 1983",
            "heading": "Civil action for deprivation of rights"
        },
        {
            "source_type": "usc",
            "title": "42",
            "section": "1985",
            "citation": "42 USC § 1985",
            "heading": "Conspiracy to interfere with civil rights"
        }
    ]
    ids = ["usc-42-1983", "usc-42-1985"]

    await upsert_documents(documents, metadatas, ids)

    # Verify documents were added
    info = await get_collection_info()
    assert info["count"] == 2

    # Perform semantic search
    results = await search_semantic("civil rights violations", n_results=2)
    assert len(results["ids"][0]) == 2
    assert "usc-42-1983" in results["ids"][0] or "usc-42-1985" in results["ids"][0]


@pytest.mark.asyncio
async def test_chromadb_metadata_filtering(temp_config_dir):
    """Test semantic search with metadata filters."""
    await initialize_chroma()

    # Add documents from different sources
    documents = [
        "42 USC 1983: Civil rights statute",
        "26 CFR 1.401: Qualified pension plan regulation"
    ]
    metadatas = [
        {"source_type": "usc", "title": "42"},
        {"source_type": "cfr", "title": "26"}
    ]
    ids = ["usc-42-1983", "cfr-26-1-401"]

    await upsert_documents(documents, metadatas, ids)

    # Search with filter for USC only
    results = await search_semantic(
        "civil rights",
        n_results=10,
        where={"source_type": "usc"}
    )

    assert len(results["ids"][0]) == 1
    assert results["ids"][0][0] == "usc-42-1983"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
