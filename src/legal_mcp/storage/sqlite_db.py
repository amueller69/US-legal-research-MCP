"""SQLite database for structured legal data storage.

Handles:
- USC sections
- CFR sections
- Public laws
- Cross-references
- Metadata

Schema defined in LEGAL_MCP_MASTER_PLAN.md section 5.1
"""

import sqlite3
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Database path
DB_PATH = Path.home() / ".config" / "legal-mcp" / "legal.db"

# Module-level connection (initialized on first use)
_connection: Optional[sqlite3.Connection] = None


def _get_connection() -> sqlite3.Connection:
    """Get or create database connection."""
    global _connection
    if _connection is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _connection = sqlite3.connect(str(DB_PATH))
        _connection.row_factory = sqlite3.Row
    return _connection


async def initialize():
    """
    Initialize SQLite database with schema.

    Creates tables if they don't exist:
    - usc_sections
    - cfr_sections
    - public_laws
    - cross_references
    - metadata
    """
    conn = _get_connection()
    cursor = conn.cursor()

    logger.info(f"Initializing SQLite database at {DB_PATH}")

    # US Code Sections table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usc_sections (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            section TEXT NOT NULL,
            heading TEXT,
            text TEXT NOT NULL,
            chapter TEXT,
            subchapter TEXT,
            effective_date TEXT,
            source_law TEXT,
            last_updated TEXT,
            citation TEXT GENERATED ALWAYS AS
                (title || ' USC § ' || section) STORED,
            UNIQUE(title, section)
        )
    """)

    # CFR Sections table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cfr_sections (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            chapter TEXT,
            part TEXT NOT NULL,
            section TEXT NOT NULL,
            heading TEXT,
            text TEXT NOT NULL,
            effective_date TEXT,
            last_updated TEXT,
            citation TEXT GENERATED ALWAYS AS
                (title || ' CFR § ' || section) STORED,
            UNIQUE(title, part, section)
        )
    """)

    # Cross-references table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cross_references (
            id INTEGER PRIMARY KEY,
            source_type TEXT NOT NULL,
            source_id INTEGER NOT NULL,
            target_type TEXT NOT NULL,
            target_citation TEXT NOT NULL,
            reference_type TEXT
        )
    """)

    # Public Laws table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS public_laws (
            id INTEGER PRIMARY KEY,
            congress INTEGER NOT NULL,
            law_number INTEGER NOT NULL,
            title TEXT,
            enacted_date TEXT,
            summary TEXT,
            sections_amended TEXT,
            govinfo_url TEXT,
            UNIQUE(congress, law_number)
        )
    """)

    # Metadata table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT
        )
    """)

    # Create indexes for USC
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usc_citation ON usc_sections(title, section)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usc_chapter ON usc_sections(title, chapter)")

    # Create indexes for CFR
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cfr_citation ON cfr_sections(title, part, section)")

    # Create FTS5 virtual tables for full-text search
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS usc_sections_fts USING fts5(
            title, section, heading, text,
            content='usc_sections',
            content_rowid='id'
        )
    """)

    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS cfr_sections_fts USING fts5(
            title, section, heading, text,
            content='cfr_sections',
            content_rowid='id'
        )
    """)

    # Create triggers to keep FTS tables in sync
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS usc_sections_ai AFTER INSERT ON usc_sections BEGIN
            INSERT INTO usc_sections_fts(rowid, title, section, heading, text)
            VALUES (new.id, new.title, new.section, new.heading, new.text);
        END
    """)

    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS usc_sections_ad AFTER DELETE ON usc_sections BEGIN
            INSERT INTO usc_sections_fts(usc_sections_fts, rowid, title, section, heading, text)
            VALUES('delete', old.id, old.title, old.section, old.heading, old.text);
        END
    """)

    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS usc_sections_au AFTER UPDATE ON usc_sections BEGIN
            INSERT INTO usc_sections_fts(usc_sections_fts, rowid, title, section, heading, text)
            VALUES('delete', old.id, old.title, old.section, old.heading, old.text);
            INSERT INTO usc_sections_fts(rowid, title, section, heading, text)
            VALUES (new.id, new.title, new.section, new.heading, new.text);
        END
    """)

    conn.commit()
    logger.info("Database schema initialized successfully")


async def get_section(table: str, title: str, section: str) -> Optional[dict]:
    """
    Retrieve a section from USC or CFR tables.

    Args:
        table: Table name ('usc_sections' or 'cfr_sections')
        title: Title number
        section: Section number

    Returns:
        Section data as dict or None if not found
    """
    if table not in ("usc_sections", "cfr_sections"):
        raise ValueError(f"Invalid table: {table}")

    conn = _get_connection()
    cursor = conn.cursor()

    query = f"SELECT * FROM {table} WHERE title = ? AND section = ?"
    cursor.execute(query, (title, section))

    row = cursor.fetchone()
    if row:
        return dict(row)
    return None


async def insert_sections(table: str, sections: list[dict]) -> int:
    """
    Bulk insert sections into database.

    Args:
        table: Table name ('usc_sections' or 'cfr_sections')
        sections: List of section dicts to insert

    Returns:
        Number of rows inserted
    """
    if table not in ("usc_sections", "cfr_sections"):
        raise ValueError(f"Invalid table: {table}")

    if not sections:
        return 0

    conn = _get_connection()
    cursor = conn.cursor()

    # Determine columns based on table
    if table == "usc_sections":
        columns = ["title", "section", "heading", "text", "chapter", "subchapter",
                   "effective_date", "source_law", "last_updated"]
        placeholders = ", ".join(["?"] * len(columns))

        query = f"""
            INSERT OR REPLACE INTO {table}
            ({", ".join(columns)})
            VALUES ({placeholders})
        """

        data = [
            (
                s.get("title"),
                s.get("section"),
                s.get("heading"),
                s.get("text"),
                s.get("chapter"),
                s.get("subchapter"),
                s.get("effective_date"),
                s.get("source_law"),
                s.get("last_updated", datetime.now().isoformat())
            )
            for s in sections
        ]
    else:  # cfr_sections
        columns = ["title", "chapter", "part", "section", "heading", "text",
                   "effective_date", "last_updated"]
        placeholders = ", ".join(["?"] * len(columns))

        query = f"""
            INSERT OR REPLACE INTO {table}
            ({", ".join(columns)})
            VALUES ({placeholders})
        """

        data = [
            (
                s.get("title"),
                s.get("chapter"),
                s.get("part"),
                s.get("section"),
                s.get("heading"),
                s.get("text"),
                s.get("effective_date"),
                s.get("last_updated", datetime.now().isoformat())
            )
            for s in sections
        ]

    cursor.executemany(query, data)
    conn.commit()

    inserted_count = cursor.rowcount
    logger.info(f"Inserted {inserted_count} sections into {table}")
    return inserted_count


async def search_fulltext(query: str, table: str = "usc_sections", limit: int = 20) -> list[dict]:
    """
    Full-text search using SQLite FTS5.

    Args:
        query: FTS query (supports AND, OR, NOT, "phrases")
        table: Table to search ('usc_sections' or 'cfr_sections')
        limit: Maximum results

    Returns:
        List of matching sections with snippets
    """
    if table not in ("usc_sections", "cfr_sections"):
        raise ValueError(f"Invalid table: {table}")

    fts_table = f"{table}_fts"
    conn = _get_connection()
    cursor = conn.cursor()

    # Query FTS table and join with main table for full data
    fts_query = f"""
        SELECT
            t.*,
            snippet({fts_table}, 3, '<b>', '</b>', '...', 64) as snippet,
            rank
        FROM {fts_table} f
        JOIN {table} t ON f.rowid = t.id
        WHERE {fts_table} MATCH ?
        ORDER BY rank
        LIMIT ?
    """

    cursor.execute(fts_query, (query, limit))

    results = []
    for row in cursor.fetchall():
        results.append(dict(row))

    logger.info(f"Full-text search for '{query}' returned {len(results)} results")
    return results


async def get_metadata(key: str) -> Optional[str]:
    """Get metadata value by key."""
    conn = _get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT value FROM metadata WHERE key = ?", (key,))
    row = cursor.fetchone()

    if row:
        return row["value"]
    return None


async def set_metadata(key: str, value: str):
    """Set metadata key-value pair."""
    conn = _get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT OR REPLACE INTO metadata (key, value, updated_at)
        VALUES (?, ?, ?)
        """,
        (key, value, datetime.now().isoformat())
    )
    conn.commit()


async def get_title_toc(title: str, table: str = "usc_sections") -> dict:
    """
    Get table of contents for a title.

    Args:
        title: Title number
        table: Table to query ('usc_sections' or 'cfr_sections')

    Returns:
        Dictionary with title info and chapter/section structure
    """
    if table not in ("usc_sections", "cfr_sections"):
        raise ValueError(f"Invalid table: {table}")

    conn = _get_connection()
    cursor = conn.cursor()

    # Get all sections for this title, grouped by chapter
    query = f"""
        SELECT chapter, section, heading
        FROM {table}
        WHERE title = ?
        ORDER BY CAST(chapter AS INTEGER), CAST(section AS INTEGER)
    """

    cursor.execute(query, (title,))
    rows = cursor.fetchall()

    # Group by chapter
    chapters = {}
    for row in rows:
        chapter = row["chapter"] or "Unknown"
        if chapter not in chapters:
            chapters[chapter] = {
                "number": chapter,
                "sections": []
            }
        chapters[chapter]["sections"].append({
            "number": row["section"],
            "heading": row["heading"]
        })

    return {
        "title": title,
        "chapters": list(chapters.values())
    }


def close():
    """Close database connection."""
    global _connection
    if _connection:
        _connection.close()
        _connection = None
