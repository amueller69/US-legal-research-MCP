"""Integration checks for a locally rebuilt Legal MCP database.

These tests read the runtime SQLite database in immutable mode. They are meant
to catch parser/indexing regressions against a real rebuilt USC corpus while
skipping cleanly on machines that have not run setup/rebuild.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest


DEFAULT_DB_PATH = Path.home() / ".config" / "legal-mcp" / "legal.db"
DEFAULT_CHROMA_DIR = Path.home() / ".config" / "legal-mcp" / "chroma_db"


def runtime_db_path() -> Path:
    return Path(os.environ.get("LEGAL_MCP_DB_PATH", DEFAULT_DB_PATH))


def runtime_chroma_dir() -> Path:
    return Path(os.environ.get("LEGAL_MCP_CHROMA_DIR", DEFAULT_CHROMA_DIR))


@pytest.fixture
def rebuilt_db() -> sqlite3.Connection:
    db_path = runtime_db_path()
    if not db_path.exists():
        pytest.skip(f"Local Legal MCP database not found: {db_path}")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row

    total = conn.execute("SELECT COUNT(*) FROM usc_sections").fetchone()[0]
    if total == 0:
        conn.close()
        pytest.skip(f"Local Legal MCP database has no USC sections: {db_path}")

    yield conn
    conn.close()


def get_section(conn: sqlite3.Connection, title: str, section: str) -> sqlite3.Row:
    row = conn.execute(
        """
        SELECT title, section, citation, heading, text
        FROM usc_sections
        WHERE title = ? AND section = ?
        """,
        (title, section),
    ).fetchone()
    assert row is not None, f"Missing {title} USC {section}"
    return row


def test_rebuilt_database_has_expected_corpus_shape(rebuilt_db: sqlite3.Connection):
    row = rebuilt_db.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(text = '') AS empty_text,
            SUM(length(text) > 0) AS nonempty_text,
            SUM(heading = '') AS empty_heading
        FROM usc_sections
        """
    ).fetchone()

    assert row["total"] >= 60000
    assert row["nonempty_text"] >= 50000
    assert row["empty_text"] / row["total"] < 0.20
    assert row["empty_heading"] < 500


def test_rebuilt_database_metadata_is_present(rebuilt_db: sqlite3.Connection):
    metadata = {
        row["key"]: row["value"]
        for row in rebuilt_db.execute("SELECT key, value FROM metadata")
    }

    assert metadata.get("usc_release_point", "").startswith("Public Law ")
    assert metadata.get("last_usc_update")


def test_rebuilt_chromadb_count_matches_sqlite(rebuilt_db: sqlite3.Connection):
    chroma_dir = runtime_chroma_dir()
    chroma_db_path = chroma_dir / "chroma.sqlite3"
    if not chroma_db_path.exists():
        pytest.skip(f"Local Legal MCP ChromaDB database not found: {chroma_db_path}")

    sqlite_count = rebuilt_db.execute("SELECT COUNT(*) FROM usc_sections").fetchone()[0]

    chroma = sqlite3.connect(f"file:{chroma_db_path}?mode=ro&immutable=1", uri=True)
    chroma.row_factory = sqlite3.Row
    try:
        collection = chroma.execute(
            "SELECT id FROM collections WHERE name = ?",
            ("legal_documents",),
        ).fetchone()
        assert collection is not None

        count = chroma.execute(
            """
            SELECT COUNT(*) AS n
            FROM embeddings e
            JOIN segments s ON s.id = e.segment_id
            WHERE s.collection = ? AND s.scope = 'METADATA'
            """,
            (collection["id"],),
        ).fetchone()["n"]
    finally:
        chroma.close()

    assert count == sqlite_count


@pytest.mark.parametrize(
    ("title", "section", "heading", "required_text"),
    [
        (
            "42",
            "299b",
            "Health care outcome improvement research",
            [
                "(a) Evidence rating systems",
                "In collaboration with experts from the public and private sector",
                "(b) Health care improvement research centers",
                "provider-based research networks",
            ],
        ),
        (
            "42",
            "1983",
            "Civil action for deprivation of rights",
            ["Every person who, under color of any statute", "deprivation of any rights"],
        ),
        (
            "18",
            "242",
            "Deprivation of rights under color of law",
            ["Whoever, under color of any law", "willfully subjects any person"],
        ),
        (
            "5",
            "552",
            "Public information; agency rules, opinions, orders, records, and proceedings",
            ["Each agency shall make available to the public information", "publish in the Federal Register"],
        ),
        (
            "1",
            "7",
            "Marriage",
            ["For the purposes of any Federal law", "marital status is a factor"],
        ),
    ],
)
def test_rebuilt_database_has_representative_section_text(
    rebuilt_db: sqlite3.Connection,
    title: str,
    section: str,
    heading: str,
    required_text: list[str],
):
    row = get_section(rebuilt_db, title, section)

    assert row["heading"] == heading
    assert len(row["text"]) > 200
    for expected in required_text:
        assert expected in row["text"]


def test_rebuilt_database_does_not_mix_notes_or_source_credit_into_body_text(
    rebuilt_db: sqlite3.Connection,
):
    row = get_section(rebuilt_db, "42", "299b")

    assert "July 1, 1944, ch. 373" not in row["text"]
    assert "Editorial Notes" not in row["text"]
    assert "Prior Provisions" not in row["text"]


def test_empty_text_rows_are_mostly_nonoperative_sections(rebuilt_db: sqlite3.Connection):
    rows = rebuilt_db.execute(
        """
        SELECT heading, COUNT(*) AS n
        FROM usc_sections
        WHERE text = ''
        GROUP BY heading
        ORDER BY n DESC
        LIMIT 10
        """
    ).fetchall()

    headings = {row["heading"] for row in rows}
    assert {"Omitted", "Transferred"} <= headings
    assert all(
        heading in {"Omitted", "Transferred"} or heading.startswith("Repealed.")
        for heading in headings
    )


@pytest.mark.asyncio
async def test_get_usc_section_tool_returns_rebuilt_body_text(rebuilt_db: sqlite3.Connection):
    import legal_mcp.storage.sqlite_db as sqlite_db
    from legal_mcp.tools.usc_tools import get_usc_section

    original_db_path = sqlite_db.DB_PATH
    sqlite_db.close()
    sqlite_db.DB_PATH = runtime_db_path()
    try:
        result = await get_usc_section("42", "299b")
    finally:
        sqlite_db.close()
        sqlite_db.DB_PATH = original_db_path

    assert result["citation"] == "42 USC § 299b"
    assert result["heading"] == "Health care outcome improvement research"
    assert len(result["text"]) > 1000
    assert "Evidence rating systems" in result["text"]


@pytest.mark.asyncio
async def test_get_usc_section_tool_accepts_hyphen_for_en_dash_section(
    rebuilt_db: sqlite3.Connection,
):
    import legal_mcp.storage.sqlite_db as sqlite_db
    from legal_mcp.tools.usc_tools import get_usc_section

    original_db_path = sqlite_db.DB_PATH
    sqlite_db.close()
    sqlite_db.DB_PATH = runtime_db_path()
    try:
        result = await get_usc_section("42", "299b-21")
    finally:
        sqlite_db.close()
        sqlite_db.DB_PATH = original_db_path

    assert "error" not in result
    assert result["citation"] == "42 USC § 299b–21"
    assert result["heading"] == "Definitions"
    assert "Patient safety work product" in result["text"]
