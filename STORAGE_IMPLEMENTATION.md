# Storage Layer Implementation Summary

**Date:** 2026-04-22 (updated 2026-04-26)
**Status:** ✅ Complete and Tested

## What Was Implemented

### 1. SQLite Database (`src/legal_mcp/storage/sqlite_db.py`)

**Features:**
- ✅ Complete schema implementation matching LEGAL_MCP_MASTER_PLAN.md
- ✅ Tables: usc_sections, cfr_sections, public_laws, cross_references, metadata, usc_title_hashes
- ✅ FTS5 full-text search virtual tables for USC and CFR
- ✅ Auto-sync triggers to keep FTS tables current
- ✅ Indexes for fast citation lookups (<100ms target)
- ✅ CRUD operations: insert_sections, get_section, search_fulltext
- ✅ Metadata management: get_metadata, set_metadata
- ✅ USC clean rebuild helpers: clear_sections, clear_usc_title
- ✅ USC title-level XML hash tracking plus section content hashes for incremental updates
- ✅ Table of contents generation: get_title_toc

**Key Functions:**
```python
await initialize()                      # Create schema and tables
await get_section(table, title, section)  # Retrieve by citation
await insert_sections(table, sections)   # Bulk insert/update
await clear_sections(table)             # Delete all USC/CFR section rows
await clear_usc_title(title)             # Delete one USC title from SQLite
await search_fulltext(query, table)     # FTS5 search
await get_metadata(key)                 # Get metadata
await set_metadata(key, value)          # Set metadata
await delete_metadata(key)              # Delete metadata
await get_usc_title_hashes()            # Stored title XML hashes
await set_usc_title_hash(title, hash, release_point)
await delete_usc_title_hash(title)
await clear_usc_title_hashes()
await get_usc_sections_for_title(title) # Existing sections keyed by section number
await set_usc_section_hashes(title, hashes, release_point)
await count_usc_sections_missing_content_hash()
await get_title_toc(title)              # Get table of contents
```

**Database Location:** `~/.config/legal-mcp/legal.db`

### 2. ChromaDB Client (`src/legal_mcp/storage/chroma_client.py`)

**Features:**
- ✅ Persistent vector storage using ChromaDB
- ✅ Default embedding: all-MiniLM-L6-v2 (384-dim, local, free)
- ✅ Semantic similarity search with metadata filtering
- ✅ Token-aware text truncation (8000 token default)
- ✅ Document upsert (insert/update)
- ✅ Targeted delete by source type and USC title
- ✅ Collection management and statistics

**Key Functions:**
```python
await initialize()                           # Setup ChromaDB client
await upsert_documents(docs, metadata, ids)  # Add/update documents
await search(query, n_results, where)        # Semantic search
await delete_documents(ids)                  # Remove documents
await delete_documents_by_source("usc")      # Remove all USC vectors
await delete_documents_by_source_and_title("usc", "42")  # Remove one title
await get_collection_info()                  # Get stats
await reset_collection()                     # Clear collection
get_existing_ids(ids)                        # Return subset of ids already in collection (sync)
```

`get_existing_ids()` is still available for batch-level add/update accounting. Normal USC release updates now avoid unnecessary embedding work through a two-stage comparison: unchanged title XML files are skipped entirely, while changed title XML files are parsed and compared by normalized section content hash before any ChromaDB embedding work runs.

**Storage Location:** `~/.config/legal-mcp/chroma_db/`

### 3. Storage Module Exports (`src/legal_mcp/storage/__init__.py`)

Clean API with prefixed imports:
```python
from legal_mcp.storage import (
    initialize_sqlite,
    initialize_chroma,
    insert_sections,
    get_section,
    search_fulltext,
    search_semantic,
    upsert_documents,
    # ... and more
)
```

### 4. Test Suite (`tests/test_storage.py`)

**Coverage:**
- ✅ SQLite initialization
- ✅ Section insert and retrieval
- ✅ Full-text search (FTS5)
- ✅ ChromaDB initialization
- ✅ Semantic search
- ✅ Metadata filtering

**Test Results:** All 6 tests passing

```bash
~/.venv/bin/python -m pytest tests/test_storage.py -v
# ====== 6 passed in 1.85s ======
```

## Architecture Decisions

### Dual Storage Strategy

| Storage | Use Case | Speed | Cost |
|---------|----------|-------|------|
| **SQLite** | Exact citations (42 USC § 1983) | <100ms | Free |
| **ChromaDB** | Semantic search ("qualified immunity") | ~500ms | Free |

### Why This Works

1. **Citation Lookups:** SQLite with indexes provides instant exact matches
2. **Concept Discovery:** ChromaDB finds semantically similar sections
3. **Hybrid Queries:** Tools can use both (exact lookup + related sections)
4. **No External Dependencies:** Everything runs locally, no API costs

### USC Update Strategy

USC update behavior has two modes:

| Mode | Trigger | Behavior |
|------|---------|----------|
| **Clean full rebuild** | `legal-mcp setup --force` or `legal-mcp update-db --force` | Clear all USC rows from SQLite, delete all ChromaDB docs with `source_type="usc"`, clear USC title hashes/metadata, then rebuild from the current XML release. |
| **Incremental update** | `legal-mcp update-db` when house.gov release point changes | Download/use cached XML, compute SHA-256 per USC title XML file as a coarse change detector, then parse changed/new titles and compare normalized per-section content hashes. Only new/changed sections are embedded. Removed sections/titles are deleted. Hashes and release metadata are updated after successful indexing. |

Hash storage:

```sql
CREATE TABLE usc_title_hashes (
    title TEXT PRIMARY KEY,
    xml_hash TEXT NOT NULL,
    release_point TEXT NOT NULL,
    updated_at TEXT
);
```

`usc_sections.content_hash` stores a SHA-256 hash of the same normalized text payload sent to ChromaDB: section heading, section text, and parser-extracted notes. Raw XML-only churn such as generated IDs, timestamps, publication labels, and whitespace does not force re-embedding unless it changes that indexed section content.

Normal incremental update flow:

1. Check the house.gov USC release point against `metadata.usc_release_point`.
2. If unchanged, no indexing is needed. If title XML hashes or section content hashes are missing for an existing database, backfill them from cached XML without re-embedding.
3. If changed, download or reuse cached XML under `~/.cache/legal-mcp/usc-xml/<release>/`.
4. Compute SHA-256 hashes for each title XML file.
5. Compare against `usc_title_hashes`.
6. For unchanged titles, skip SQLite and ChromaDB work entirely.
7. For changed/new titles, parse the title once and compute normalized section content hashes.
8. For unchanged sections inside changed XML titles, update hash/release metadata only.
9. For new or changed sections, upsert SQLite rows and ChromaDB documents.
10. For removed sections/titles, delete SQLite rows, ChromaDB docs, and stale title hashes.
11. Write title hashes and release metadata only after indexing completes without errors.

Metadata safety rules:

- `--force` clears `usc_release_point`, `last_usc_update`, and all title hashes before rebuilding.
- Release metadata and title hashes are not updated if indexing reports errors.
- Release metadata and title hashes are not updated when `--limit` is used, because that creates a partial test index.
- Successful non-limited setup/update runs prune stale USC XML cache directories after metadata is safely updated, keeping the current release cache under `~/.cache/legal-mcp/usc-xml/<release>/`.

## Implementation Patterns from Zotero-MCP

✅ Borrowed successfully:
- Global connection management with lazy initialization
- Persistent client pattern for ChromaDB
- Text truncation strategies
- Metadata filtering in vector search
- Cleanup functions for testing

✅ Adapted for legal domain:
- Legal citation structure (USC, CFR)
- FTS5 for legal text search
- Chapter/title hierarchy
- Cross-reference tracking
- Title-level USC XML hashes plus normalized section content hashes to avoid re-embedding unchanged USC sections

## Testing the Storage Layer

```bash
# Run all storage tests
~/.venv/bin/python -m pytest tests/test_storage.py -v

# Test specific function
~/.venv/bin/python -m pytest tests/test_storage.py::test_sqlite_fulltext_search -v

# Run with output
~/.venv/bin/python -m pytest tests/test_storage.py -v -s
```

## Example Usage

```python
from legal_mcp.storage import (
    initialize_sqlite,
    initialize_chroma,
    insert_sections,
    get_section,
    search_fulltext,
    search_semantic,
    upsert_documents,
)

# Initialize both databases
await initialize_sqlite()
await initialize_chroma()

# Insert USC section
sections = [{
    "title": "42",
    "section": "1983",
    "heading": "Civil action for deprivation of rights",
    "text": "Every person who, under color of any statute...",
    "chapter": "21"
}]
await insert_sections("usc_sections", sections)

# Add to vector search
await upsert_documents(
    documents=["42 USC 1983: Civil action for deprivation of rights..."],
    metadatas=[{"source_type": "usc", "title": "42", "citation": "42 USC § 1983"}],
    ids=["usc-42-1983"]
)

# Exact lookup
section = await get_section("usc_sections", "42", "1983")

# Full-text search
results = await search_fulltext("civil rights", "usc_sections")

# Semantic search
results = await search_semantic("qualified immunity for police", n_results=10)

# Clean one USC title for title-level incremental rebuild
await clear_usc_title("42")
await delete_documents_by_source_and_title("usc", "42")
await set_usc_title_hash("42", xml_hash, "Public Law 119-84 (04/18/2026)")
```

## Performance Characteristics

- **SQLite citation lookup:** <100ms (indexed)
- **SQLite FTS search:** 100-500ms (depends on corpus size)
- **ChromaDB semantic search:** 500-1000ms (local embeddings)
- **Disk usage:**
  - SQLite: ~500MB for full USC (estimated)
  - ChromaDB: ~400-500MB for embeddings

## Files Modified

```
US-legal-research-MCP/
├── src/legal_mcp/storage/
│   ├── __init__.py           ✅ Updated (exports)
│   ├── sqlite_db.py          ✅ Implemented
│   └── chroma_client.py      ✅ Implemented
├── tests/
│   └── test_storage.py       ✅ Created (6 tests passing)
└── STORAGE_IMPLEMENTATION.md ✅ This file
```

## References

- **Master Plan:** `LEGAL_MCP_MASTER_PLAN.md`
- **Zotero-MCP Reference:** Zotero-MCP ChromaDB/storage patterns used during development
- **SQLite Schema:** LEGAL_MCP_MASTER_PLAN.md Section 5.1
- **ChromaDB Schema:** LEGAL_MCP_MASTER_PLAN.md Section 5.1 (ChromaDB Schema)
