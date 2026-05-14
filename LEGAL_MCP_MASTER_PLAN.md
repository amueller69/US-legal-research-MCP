# Legal MCP Technical Reference

**Last Updated:** 2026-04-26  
**Latest:** USC end-to-end pipeline complete — all 54 titles loading into SQLite + ChromaDB ✅

---

## Table of Contents

1. [What This Is](#1-what-this-is)
2. [Core vs Extensions](#2-core-vs-extensions)
3. [Architecture Overview](#3-architecture-overview)
4. [Data Sources & Integration](#4-data-sources--integration)
5. [Implementation Details](#5-implementation-details)
6. [Reference Resources](#6-reference-resources)
7. [Quick Start (For Agents)](#7-quick-start-for-agents)

---

## 1. What This Is

MCP server providing structured + semantic access to federal legal resources for legal research in Claude Code.

**Solution:**
- **Unified access** to USC, CFR, bills, case law
- **Semantic search** ("qualified immunity for police" → relevant statutes, regulations, cases)
- **Exact citation retrieval** (42 USC § 1983 → instant text lookup)
- **Cross-reference discovery** (statute → implementing regulations → pending amendments)

**End State:**
- Integrates federal statutory law, regulations, bills, case law
- Dual search: citation-based (exact) + semantic (conceptual)
- Works across all MCP clients (CLI, desktop, web, IDE)
- Auto-updates with new legislation
- Free sources default, optional premium (PACER) with cost controls

---

## 2. Implementation Status

### ✅ MCP Scaffolding Complete (2026-04-17)

**Location:** repository root

**What's Done:**
- **FastMCP server** (`server.py`) - Tool registration, startup hooks, entry point
- **CLI structure** (`cli.py`) - Commands fully implemented: setup, update-db, db-status, serve
- **Tool contracts** (10 tools in `tools/*.py`) - Complete signatures with type hints, docstrings, MCP annotations
- **Project structure** - All directories and files created
- **Dependencies** (`pyproject.toml`) - FastMCP, ChromaDB, sentence-transformers; installed editable (`pip install -e .`)

### ✅ Storage Layer Complete (2026-04-22)

**Location:** `src/legal_mcp/storage/`

**What's Done:**
- **SQLite database** (`sqlite_db.py`) - Complete schema implementation
  - Tables: usc_sections, cfr_sections, public_laws, cross_references, metadata
  - FTS5 full-text search with auto-sync triggers
  - Indexes for fast citation lookups (<100ms)
  - Functions: initialize(), get_section(), insert_sections(), search_fulltext(), get_title_toc()
  
- **ChromaDB client** (`chroma_client.py`) - Vector search implementation
  - Persistent client with all-MiniLM-L6-v2 embeddings
  - Functions: initialize(), upsert_documents(), search(), delete_documents(), get_collection_info(), get_existing_ids()
  - Metadata filtering support
  - Text truncation (8000 tokens)
  
- **Storage module exports** (`__init__.py`) - Clean API with prefixed imports

- **Test suite** (`tests/test_storage.py`) - 6 tests, all passing

**See:** `STORAGE_IMPLEMENTATION.md` for detailed documentation

### ✅ USC Download & Parser Complete (2026-04-23)

**Location:** `src/legal_mcp/data/usc_parser.py`

**Functions Implemented:**
1. `get_current_usc_release()` - Scrapes house.gov for current release (Public Law 119-84)
2. `download_usc_xml()` - Downloads 500MB ZIP to temp, extracts to `~/.cache/legal-mcp/usc-xml/`
3. `parse_usc_xml()` - Parses USLM XML, extracts sections + miscellaneous notes only (skips editorial/amendment notes)
4. `check_for_updates()` - Compares stored vs current release

**Cache Location:** `~/.cache/legal-mcp/usc-xml/119-84/` (58 XML files, Public Law 119-84)

### ✅ CLI Commands Implemented (2026-04-26)

**Location:** `src/legal_mcp/cli.py`

**Commands:**
- `legal-mcp setup [--force] [--limit N]` - Download USC XML and populate SQLite + ChromaDB
- `legal-mcp update-db [--force] [--limit N]` - Check release point, download + rebuild if updated
- `legal-mcp db-status` - Show section counts, release point, ChromaDB document count
- `legal-mcp serve [--transport stdio|streamable-http] [--port N]` - Start MCP server

**`update-db` / `setup` implementation details** (modeled on Zotero-MCP `update_database()` pattern):
- Stats tracking: total, added, updated, skipped, errors, recovered, duration
- Terminal-width-aware `\r` progress line (shows current section being indexed)
- Batch size 500 (larger than Zotero's 25; local embeddings have no API token limits)
- Intra-batch deduplication: USC XML can yield duplicate `(title, section)` from appendices; SQLite handles via `UNIQUE + INSERT OR REPLACE`, ChromaDB payload deduped via dict keyed by doc_id before upsert
- End-of-run retry for failed ChromaDB batches (ONNX tokenizer fails intermittently)
- Incremental update support: `get_existing_ids()` used to split batch into new vs update, skipping re-embedding of unchanged sections
- Heavy imports (FastMCP, ChromaDB, sentence-transformers) deferred to command handlers — CLI starts instantly

### ✅ USC Tool Implementations Complete (2026-04-26)

**USC tools** (`tools/usc_tools.py`):
- `get_usc_section(title, section)` — queries SQLite, returns citation + full text
- `get_title_toc(title)` — returns chapter/section hierarchy for a USC title

**Search tools** (`tools/search_tools.py`):
- `search_usc_semantic(query, limit)` — ChromaDB vector search filtered to `source_type=usc`
- `search_cfr_semantic(query, limit)` — ChromaDB vector search filtered to `source_type=cfr`
- `search_fulltext(query, source, limit)` — SQLite FTS5 keyword search with boolean operators
- `get_database_status()` — returns SQLite counts + ChromaDB collection info + metadata

**CFR/bill tools** (`tools/cfr_tools.py`, `tools/bill_tools.py`):
- All return graceful error dicts (not `NotImplementedError`) so MCP server stays functional
- TODO comments preserved for Phase 2/3 implementation

### ✅ USC Fully Loaded (2026-04-26)

Full USC (Public Law 119-84, 58 XML files, ~55k sections) loaded into:
- **SQLite:** `~/.config/legal-mcp/legal.db`
- **ChromaDB:** `~/.config/legal-mcp/chroma_db/`

### 🚧 What's Not Implemented

**Data Ingestion** (`data/`):
- `cfr_client.py` - eCFR API client (Phase 2)
- `govinfo_wrapper.py` - GovInfo MCP integration (Phase 3)

**Utilities** (`utils/`):
- `citation_parser.py` - Parse legal citations (e.g., "42 USC § 1983" → {title, section})

**Testing:**
- End-to-end integration tests with real queries
- Evaluation questions (10 complex legal research queries)

---

## 3. Core vs Extensions

### Core MVP (Build First)

**What needs to work for legal research:**

1. **US Code**
   - Parse USC XML (house.gov) → SQLite + ChromaDB
   - Tools: `get_usc_section()`, `search_usc_semantic()`, `search_usc_fulltext()`, `get_title_toc()`

2. **Code of Federal Regulations**
   - eCFR API integration → same databases
   - Tools: `get_cfr_section()`, `search_cfr_semantic()`, `find_implementing_regulations(usc_citation)`
   - **Why in MVP:** Need to understand regulatory implementation of statutes

3. **Session Laws (Statutes at Large)**
   - GovInfo MCP integration
   - Tools: `get_public_law()`, `get_statutes_at_large()`, `search_bills()`
   - **Why in MVP:** Session laws are authoritative for non-positive law USC titles when they conflict with the Code

**Deliverables:**
- [ ] USC: Parse all 54 titles, build dual storage
- [ ] CFR: Integrate eCFR API, index in ChromaDB
- [ ] Session Laws: Configure GovInfo MCP, wrapper tools
- [ ] Cross-references: Link USC ↔ CFR ↔ session laws
- [ ] Test with complex legal research queries

### Extensions (Future)

**Add later if needed:**

1. **Case Law**
   - CourtListener API (free, comprehensive)
   - Semantic search over Supreme Court opinions
   - Citation network analysis

4. **PACER** (Optional)
   - Recent filings not in CourtListener
   - Cost controls: $30/quarter budget, explicit user confirmation
   - Only if needed

5. **Advanced**
   - Historical statute versions (point-in-time)
   - Citation graphs
   - Bluebook export
   - State law (ambitious)

### Extensibility Strategy

**Design core to support extensions:**

1. **Modular schema** - `source_type` field ('usc', 'cfr', 'bill', 'case')
2. **Unified search** - ChromaDB collection holds all legal docs with metadata filters
3. **Plugin tools** - New sources = new tools, don't modify core
4. **Cross-references table** - Links USC ↔ CFR ↔ bills
5. **Config-driven** - Add new sources via config, not code changes

---

## 4. Project Structure

### File/Module Layout (Status Indicators)

**Legend:** ✅ Complete | 🎯 Signature/Interface Defined | ❌ Not Started

```
US-legal-research-MCP/
├── src/
│   └── legal_mcp/
│       ├── __init__.py                 ✅ Complete
│       ├── server.py                   ✅ Complete - FastMCP server, tool registration
│       ├── cli.py                      ✅ Complete - setup, update-db, db-status, serve
│       │
│       ├── data/                       Partially complete
│       │   ├── __init__.py             ✅
│       │   ├── usc_parser.py           ✅ Complete - download, parse, update-check
│       │   ├── cfr_client.py           🎯 Stub - implement eCFR API (Phase 2)
│       │   └── govinfo_wrapper.py      🎯 Stub - implement GovInfo MCP (Phase 3)
│       │
│       ├── storage/                    ✅ Complete - SQLite + ChromaDB (2026-04-22)
│       │   ├── __init__.py             ✅ Exports all storage functions
│       │   ├── sqlite_db.py            ✅ Schema, CRUD, FTS5
│       │   └── chroma_client.py        ✅ Vector search, embeddings, get_existing_ids
│       │
│       ├── tools/                      Partially complete
│       │   ├── __init__.py             ✅
│       │   ├── usc_tools.py            ✅ 2 tools implemented
│       │   ├── cfr_tools.py            🎯 2 tools - graceful errors, TODO comments intact
│       │   ├── bill_tools.py           🎯 2 tools - graceful errors, TODO comments intact
│       │   └── search_tools.py         ✅ 4 tools implemented
│       │
│       └── utils/                      🎯 Not started
│           ├── __init__.py             ✅
│           └── citation_parser.py      🎯 Stub - implement citation parsing
│
├── tests/
│   ├── test_placeholder.py             ✅ Placeholder
│   └── test_storage.py                 ✅ Storage layer tests (6 tests passing)
│
├── pyproject.toml                      ✅ Complete - installed editable (pip install -e .)
├── README.md                           ✅ Complete
└── .gitignore                          ✅ Complete
```

### Component Responsibilities

**server.py** (✅ COMPLETE - MCP entry point)
- Registers all 9 MCP tools with FastMCP
- Startup hook initializes storage layers
- Routes tool calls to appropriate modules
- Handles MCP protocol (stdio or streamable HTTP)
- **Location:** `src/legal_mcp/server.py`

**cli.py** (✅ STRUCTURE COMPLETE - Commands defined, need implementation)
- `legal-mcp setup` - Configure embedding model, download USC XML (TODO)
- `legal-mcp update-db` - Update SQLite + ChromaDB (TODO)
- `legal-mcp db-status` - Show database info (TODO)
- `legal-mcp serve` - Start MCP server (WORKS - calls server.py)
- **Location:** `src/legal_mcp/cli.py`

**data/usc_parser.py** (USC XML parsing)
```python
# Download USC XML from house.gov
# Parse with xml.etree.ElementTree
# Extract: title, chapter, section, heading, text
# Return structured data for storage layer
```

**data/cfr_client.py** (eCFR API)
```python
# Fetch CFR sections via eCFR API
# Cache responses (CFR updates daily, not every query)
# Return structured data matching USC format
```

**data/govinfo_wrapper.py** (GovInfo integration)
```python
# Call GovInfo MCP tools (searchGovInfo, describePackageOrGranule)
# Parse responses into consistent format
# Extract session laws, public laws
```

**storage/sqlite_db.py** (Structured storage)
```python
# Create tables (usc_sections, cfr_sections, public_laws, cross_references)
# CRUD operations
# Full-text search (FTS5)
# Citation lookups (<100ms)
```

**storage/chroma_client.py** (Semantic storage)
```python
# Copied/adapted from Zotero-MCP pattern
# Embedding function selection (default, openai, gemini)
# Upsert documents with metadata
# Search with filters
# Truncation to token limits
```

**tools/\*.py** (MCP tool implementations)
```python
# Each tool is a Python function decorated with @mcp.tool()
# Tools call storage layer (sqlite_db.py, chroma_client.py)
# Return structured results (dicts, lists)
# Include annotations (readOnlyHint=True)
```

**utils/citation_parser.py** (Parse citations)
```python
# "42 USC § 1983" → {"title": "42", "section": "1983"}
# "26 CFR § 1.401(a)-1" → {"title": "26", "part": "1", "section": "401(a)-1"}
# Handle various formats, typos
```

### Data Flow

**Initial Build:**
```
1. CLI: legal-mcp update-db
2. usc_parser.py downloads/parses XML
3. sqlite_db.py stores structured data
4. chroma_client.py generates embeddings, stores vectors
5. Repeat for CFR (cfr_client.py)
```

**Query (Citation Lookup):**
```
1. User: get_usc_section("42", "1983")
2. server.py routes to usc_tools.py
3. usc_tools.py queries sqlite_db.py
4. Return result (<100ms)
```

**Query (Semantic Search):**
```
1. User: search_usc_semantic("qualified immunity")
2. server.py routes to search_tools.py
3. search_tools.py queries chroma_client.py
4. Enrich results with full data from sqlite_db.py
5. Return ranked results
```

### Key Dependencies

```toml
[project]
dependencies = [
    "mcp",                    # FastMCP
    "chromadb",               # Vector database
    "sentence-transformers",  # Local embedding model (all-MiniLM-L6-v2)
    "requests",               # HTTP for eCFR API
    "lxml",                   # XML parsing (faster than stdlib)
]
```

**Embedding model:** all-MiniLM-L6-v2 (free, local, 384-dim, proven in Zotero-MCP)

---

## 4. Architecture Overview

### 3.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Legal MCP Server                      │
│                     (Python/FastMCP)                     │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────────┐         ┌──────────────────┐     │
│  │  MCP Tools Layer │         │  Update Manager  │     │
│  │  - get_usc_*     │         │  - Periodic sync │     │
│  │  - search_*      │         │  - Version check │     │
│  │  - find_*        │         └──────────────────┘     │
│  └────────┬─────────┘                                   │
│           │                                              │
│  ┌────────▼─────────────────────────────────────┐      │
│  │         Query Router & Orchestrator          │      │
│  │  - Route exact citations → SQLite            │      │
│  │  - Route semantic queries → ChromaDB         │      │
│  │  - Combine & rank results                    │      │
│  └────────┬─────────────────────────────────────┘      │
│           │                                              │
│  ┌────────▼──────────┐       ┌─────────────────┐       │
│  │  SQLite Database  │       │   ChromaDB       │       │
│  │  (Structured)     │       │   (Semantic)     │       │
│  ├───────────────────┤       ├──────────────────┤       │
│  │ • usc_sections    │       │ • Vector embeddings│      │
│  │ • cfr_sections    │       │ • Metadata index  │      │
│  │ • public_laws     │       │ • Similarity search│      │
│  │ • citations       │       │                   │      │
│  └───────────────────┘       └──────────────────┘       │
│           │                           │                  │
└───────────┼───────────────────────────┼──────────────────┘
            │                           │
    ┌───────▼────────┐         ┌────────▼─────────┐
    │ USC XML Files  │         │ Embedding Models │
    │ (house.gov)    │         │ • Default (free) │
    │ CFR API Data   │         │ • OpenAI (opt)   │
    │ GovInfo MCP    │         │ • Gemini (opt)   │
    └────────────────┘         └──────────────────┘
```

### 3.2 Data Storage Strategy

**Why Dual Storage?**

| Storage Type | Use Case | Performance | Cost |
|-------------|----------|-------------|------|
| **SQLite** | Exact citations, structured metadata, foreign keys | <100ms lookup | Free |
| **ChromaDB** | Semantic search, concept discovery, similarity | ~500ms search | Free (default model) |

**Data Flow:**
1. **Ingest:** US Code XML → Parser → SQLite (structured) + ChromaDB (embeddings)
2. **Query:** User query → Router determines SQLite vs ChromaDB vs hybrid
3. **Update:** Periodic checks for new USC/CFR releases → incremental updates

### 3.3 Technology Stack

**Core:**
- **Language:** Python 3.10+
- **MCP Framework:** FastMCP (Python SDK for MCP servers)
- **Transport:** Streamable HTTP (stateless, scalable) + stdio fallback for local use

**Storage:**
- **Structured Data:** SQLite (built-in, no external dependencies)
- **Vector Search:** ChromaDB (lightweight, persistent, supports multiple embedding models)

**Embedding Models:**
- **Default:** all-MiniLM-L6-v2 (free, local, 384-dim vectors)
- **Optional:** OpenAI text-embedding-3-small, Gemini gemini-embedding-001

**Data Sources:**
- US Code XML (https://uscode.house.gov/download/download.shtml)
- eCFR API (https://www.ecfr.gov/developers/documentation/api/v1)
- GovInfo MCP (https://github.com/usgpo/api/blob/main/docs/mcp.md)
- CourtListener API (future)

---

## 4. Data Sources & Integration

### 4.1 US Code (Primary - Phase 1)

**Source:** Office of the Law Revision Counsel  
**URL:** https://uscode.house.gov/download/download.shtml

**Available Formats:**
- **XML** (preferred) - Structured with USLM Schema
- XHTML, PDF, PCC (not used)

**Download Options:**
- Bulk: All 54 titles in one ZIP archive (~500MB compressed)
- Individual: Single title downloads for testing

**Update Frequency:**
- Release points track public laws (currently at Public Law 119-83, 2026-04-13)
- Check for updates: Compare release point on download page

**Structure:**
```xml
<title number="42">
  <chapter number="21">
    <section number="1983">
      <heading>Civil action for deprivation of rights</heading>
      <text>Every person who, under color of any statute...</text>
    </section>
  </chapter>
</title>
```

**Implementation Plan:**
1. Download bulk XML ZIP
2. Parse with Python `xml.etree.ElementTree`
3. Extract: title, subtitle, chapter, section, heading, text
4. Store in SQLite with full citation path
5. Generate embeddings for ChromaDB (heading + text combined)

**Citation Format:**
- Standard: `42 USC § 1983`
- Internal ID: `usc-42-1983`

### 4.2 Code of Federal Regulations (Phase 2)

**Source:** eCFR (Electronic Code of Federal Regulations)  
**URL:** https://www.ecfr.gov/developers/documentation/api/v1

**API Endpoints:**
- `/v1/titles` - List all CFR titles
- `/v1/titles/{title}/parts` - List parts in a title
- `/v1/titles/{title}/parts/{part}/sections` - Get sections
- Full-text search available

**Update Frequency:**
- Updated daily (more current than annual print CFR)

**Structure:**
```
Title 26 (Internal Revenue)
  └─ Chapter I (IRS)
      └─ Part 1 (Income Taxes)
          └─ § 1.401(a)-1 (Qualified pension plans)
```

**Implementation Plan:**
1. Fetch title/part/section metadata via API
2. Store structured data in SQLite
3. Generate embeddings for semantic search
4. Link to USC sections via cross-references
5. Cache API responses (update weekly)

**Citation Format:**
- Standard: `26 CFR § 1.401(a)-1`
- Internal ID: `cfr-26-1-401a-1`

### 4.3 Bills & Legislation (Phase 3)

**Source:** GovInfo MCP (GPO)  
**GitHub:** https://github.com/usgpo/api/blob/main/docs/mcp.md  
**API Key:** Free at https://www.govinfo.gov/api-signup

**GovInfo MCP Tools:**
- `searchGovInfo` - Discovery tool (returns title, dates, links, teaser)
- `describePackageOrGranule` - Retrieval tool (HTML, PDF, XML, metadata)

**Coverage:**
- Congressional bills (current and historical)
- Public laws (session laws)
- Congressional Record
- Federal Register

**Implementation Plan:**
1. Configure GovInfo MCP as upstream dependency
2. Create wrapper tools:
   - `search_bills(query, congress)` → calls GovInfo MCP
   - `get_public_law(congress, number)` → retrieves session law
3. Index bill summaries in ChromaDB for semantic search
4. Link bills to USC sections they propose to amend

**Example Query:**
- "Find bills in 119th Congress mentioning 42 USC § 1983"
- Search GovInfo → filter by USC citation → return bills

### 4.4 Case Law (Phase 4 - Future)

**Free Source:** CourtListener (https://www.courtlistener.com/api/)
- 4M+ opinions, free API, comprehensive coverage
- Supreme Court, Circuit Courts, District Courts
- Searchable by citation, party name, docket number

**Premium Source (Optional):** PACER
- **Cost:** $0.10/page, $30/quarter budget limit
- **Use Case:** Recent filings not yet in CourtListener
- **Implementation:** Require explicit user confirmation, enforce budget caps

**Implementation Plan (Future):**
1. Start with CourtListener (free, no budget concerns)
2. Index Supreme Court opinions in ChromaDB
3. Add citation parsing (e.g., "501 U.S. 294" → case lookup)
4. PACER only if user explicitly requests and confirms cost

---

## 5. Implementation Details

### 5.1 Database Schema

#### SQLite Schema (Structured Data)

```sql
-- US Code Sections
CREATE TABLE usc_sections (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,              -- e.g., "42"
    section TEXT NOT NULL,             -- e.g., "1983"
    heading TEXT,                      -- Section heading
    text TEXT NOT NULL,                -- Full text content
    chapter TEXT,                      -- Chapter number
    subchapter TEXT,                   -- Subchapter (if any)
    effective_date TEXT,               -- Date enacted/amended
    source_law TEXT,                   -- Public Law that created/amended
    last_updated TEXT,                 -- When we last updated this
    citation TEXT GENERATED ALWAYS AS 
        (title || ' USC § ' || section) STORED,
    UNIQUE(title, section)
);

CREATE INDEX idx_usc_citation ON usc_sections(title, section);
CREATE INDEX idx_usc_chapter ON usc_sections(title, chapter);
CREATE FULL TEXT INDEX idx_usc_text ON usc_sections(text, heading);

-- CFR Sections (Phase 2)
CREATE TABLE cfr_sections (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,               -- e.g., "26"
    chapter TEXT,                      -- e.g., "I"
    part TEXT NOT NULL,                -- e.g., "1"
    section TEXT NOT NULL,             -- e.g., "401(a)-1"
    heading TEXT,
    text TEXT NOT NULL,
    effective_date TEXT,
    last_updated TEXT,
    citation TEXT GENERATED ALWAYS AS 
        (title || ' CFR § ' || section) STORED,
    UNIQUE(title, part, section)
);

-- Cross-references (USC <-> CFR)
CREATE TABLE cross_references (
    id INTEGER PRIMARY KEY,
    source_type TEXT NOT NULL,         -- 'usc' or 'cfr'
    source_id INTEGER NOT NULL,        -- Foreign key to usc_sections or cfr_sections
    target_type TEXT NOT NULL,
    target_citation TEXT NOT NULL,     -- Citation being referenced
    reference_type TEXT,               -- 'implements', 'amends', 'cites'
    FOREIGN KEY (source_id) REFERENCES usc_sections(id)
);

-- Public Laws (Phase 3)
CREATE TABLE public_laws (
    id INTEGER PRIMARY KEY,
    congress INTEGER NOT NULL,         -- e.g., 119
    law_number INTEGER NOT NULL,       -- e.g., 83
    title TEXT,                        -- Short title
    enacted_date TEXT,                 -- Date enacted
    summary TEXT,                      -- Bill summary
    sections_amended TEXT,             -- JSON array of USC sections amended
    govinfo_url TEXT,                  -- Link to GovInfo
    UNIQUE(congress, law_number)
);

-- Metadata
CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT
);
-- Store: last_usc_update, last_cfr_update, usc_release_point, etc.
```

#### ChromaDB Schema (Semantic Embeddings)

```python
# Collection: legal_documents
# Each document stored with:
{
    "id": "usc-42-1983",                    # Unique identifier
    "document": "Civil action for deprivation of rights. Every person who, under color of any statute...",  # Full text for embedding
    "metadata": {
        "source_type": "usc",               # 'usc', 'cfr', 'bill', 'case'
        "citation": "42 USC § 1983",
        "title": "42",
        "section": "1983",
        "heading": "Civil action for deprivation of rights",
        "effective_date": "1871-04-20",
        "last_updated": "2026-04-13",
        "chapter": "21",
        "word_count": 150,
        "has_cross_refs": true
    }
}
```

**Embedding Strategy:**
- **What to embed:** `heading + " " + text` (combined for context)
- **Token limit:** Truncate to 8000 tokens (text-embedding-3-small limit)
- **Model:** Default all-MiniLM-L6-v2 (384-dim), optional OpenAI/Gemini

### 5.2 MCP Tools Specification

#### Phase 1: US Code Tools

```python
@mcp.tool()
def get_usc_section(title: str, section: str) -> dict:
    """
    Retrieve a specific US Code section by citation.
    
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
            "source_law": "Public Law 119-83"
        }
    
    Annotations:
        readOnlyHint: true
    """
```

```python
@mcp.tool()
def search_usc_semantic(query: str, limit: int = 10) -> list[dict]:
    """
    Semantic search across US Code using vector similarity.
    Find sections conceptually related to your query, not just keyword matches.
    
    Args:
        query: Natural language query (e.g., "qualified immunity for police")
        limit: Maximum results to return (default 10)
    
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
    
    Annotations:
        readOnlyHint: true
    """
```

```python
@mcp.tool()
def get_title_toc(title: str) -> dict:
    """
    Get table of contents for a US Code title.
    
    Args:
        title: Title number (e.g., "42")
    
    Returns:
        {
            "title": "42",
            "name": "The Public Health and Welfare",
            "chapters": [
                {
                    "number": "21",
                    "name": "Civil Rights",
                    "sections": ["1981", "1982", "1983", ...]
                },
                ...
            ]
        }
    
    Annotations:
        readOnlyHint: true
    """
```

```python
@mcp.tool()
def search_usc_fulltext(query: str, limit: int = 20) -> list[dict]:
    """
    Traditional keyword search using SQLite FTS (full-text search).
    Faster than semantic search for exact phrase matches.
    
    Args:
        query: Search terms (supports AND, OR, NOT, "exact phrases")
        limit: Maximum results (default 20)
    
    Returns:
        List of matching sections with highlighted snippets
    
    Examples:
        - "due process"
        - "commerce AND interstate"
        - '"equal protection" NOT state'
    
    Annotations:
        readOnlyHint: true
    """
```

```python
@mcp.tool()
def get_database_status() -> dict:
    """
    Get status of Legal MCP databases and indexes.
    
    Returns:
        {
            "sqlite": {
                "usc_sections": 55000,
                "last_updated": "2026-04-13",
                "release_point": "Public Law 119-83"
            },
            "chromadb": {
                "documents": 55000,
                "embedding_model": "all-MiniLM-L6-v2",
                "collection_size_mb": 450
            },
            "update_config": {
                "auto_update": true,
                "check_frequency": "weekly"
            }
        }
    
    Annotations:
        readOnlyHint: true
    """
```

#### Phase 2: CFR Tools (Add Later)

```python
@mcp.tool()
def get_cfr_section(title: str, part: str, section: str) -> dict:
    """Retrieve CFR section by citation."""
    
@mcp.tool()
def search_cfr_semantic(query: str, limit: int = 10) -> list[dict]:
    """Semantic search across Code of Federal Regulations."""
    
@mcp.tool()
def find_implementing_regulations(usc_citation: str) -> list[dict]:
    """Find CFR regulations that implement a USC section."""
```

#### Phase 3: Legislative Tracking (Add Later)

```python
@mcp.tool()
def search_bills(query: str, congress: int = 119, limit: int = 10) -> list[dict]:
    """Search bills and legislation (uses GovInfo MCP)."""
    
@mcp.tool()
def track_amendments(usc_citation: str, congress: int = 119) -> list[dict]:
    """Find bills proposing to amend a specific USC section."""
```

### 5.3 Embedding Strategy

**Model Selection:**

| Model | Dimensions | Cost | Speed | Quality |
|-------|-----------|------|-------|---------|
| all-MiniLM-L6-v2 (default) | 384 | Free | Fast (local) | Good |
| text-embedding-3-small | 1536 | $0.02/1M tokens | API call | Better |
| gemini-embedding-001 | 768 | Free (quota limits) | API call | Better |

**Default:** all-MiniLM-L6-v2 (proven in Zotero-MCP, no API costs)

**Text Preparation:**
```python
def create_document_text(section: dict) -> str:
    """Combine heading and text for embedding."""
    heading = section.get('heading', '')
    text = section.get('text', '')
    
    # Combine for context
    combined = f"{heading}\n\n{text}"
    
    # Truncate to model's token limit (8000 for most models)
    truncated = truncate_to_tokens(combined, max_tokens=8000)
    
    return truncated
```

**Metadata Storage:**
Store alongside embeddings for filtering:
- `source_type`: 'usc', 'cfr', 'bill', 'case'
- `title`, `section`, `citation`
- `effective_date`, `last_updated`
- `chapter`, `subchapter` (for hierarchical filtering)

**Query-time:**
```python
# Semantic search with metadata filter
results = chroma_client.search(
    query="qualified immunity",
    n_results=10,
    where={"source_type": "usc", "title": "42"}  # Optional filter
)
```

### 5.4 Update Mechanisms

**US Code Updates:**
```python
# Check for updates
async def check_usc_updates():
    """
    1. Fetch current release point from house.gov download page
    2. Compare to stored metadata.usc_release_point
    3. If different, download new XML and trigger incremental update
    """
    
# Incremental update strategy
async def update_usc_incremental():
    """
    1. Parse new XML
    2. For each section:
       - If new: INSERT into SQLite + add to ChromaDB
       - If modified: UPDATE SQLite + upsert ChromaDB
       - If deleted: DELETE from both
    3. Update metadata.last_usc_update
    """
```

**Update Schedule:**
- **Default:** Weekly checks for USC/CFR updates
- **Manual:** `legal-mcp update-db --force` command
- **Auto:** Configurable via setup (daily, weekly, monthly)

**Configuration:**
```json
{
  "semantic_search": {
    "embedding_model": "default",
    "update_config": {
      "auto_update": true,
      "update_frequency": "weekly",
      "last_update": "2026-04-13T10:30:00"
    }
  }
}
```

---

## 6. Reference Resources

### 6.1 Key APIs & Data Sources

**US Code:**
- Download: https://uscode.house.gov/download/download.shtml
- Format: XML with USLM Schema
- Documentation: User Guide included in download
- Update frequency: Release points track public laws

**eCFR API:**
- Base URL: https://www.ecfr.gov/api/versioner/v1
- Documentation: https://www.ecfr.gov/developers/documentation/api/v1
- No API key required
- Rate limits: Reasonable (undocumented, monitor)

**GovInfo MCP:**
- GitHub: https://github.com/usgpo/api/blob/main/docs/mcp.md
- API Key: Free at https://www.govinfo.gov/api-signup
- Tools: `searchGovInfo`, `describePackageOrGranule`
- Configuration:
  ```json
  {
    "mcpServers": {
      "mcp-govinfo": {
        "url": "https://api.govinfo.gov/mcp",
        "headers": {
          "x-api-key": "YOUR_GOVINFO_API_KEY"
        }
      }
    }
  }
  ```

**CourtListener (Future):**
- API: https://www.courtlistener.com/api/rest-info/
- Free tier: 5000 requests/day
- Coverage: 4M+ opinions

### 6.2 MCP Development Resources

**Essential Reading:**
- MCP Sitemap: https://modelcontextprotocol.io/sitemap.xml
- Fetch specific pages with `.md` suffix: https://modelcontextprotocol.io/specification/draft.md

**MCP Best Practices:**
Stored in the local MCP builder reference materials used during development.

Key points:
- Use descriptive tool names (action-oriented)
- Return concise, focused results
- Implement pagination for large result sets
- Provide actionable error messages
- Use annotations: `readOnlyHint`, `destructiveHint`, `idempotentHint`

**Python/FastMCP:**
- SDK README: https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/README.md
- Guide: local MCP builder Python server reference

**TypeScript (Alternative):**
- SDK README: https://raw.githubusercontent.com/modelcontextprotocol/typescript-sdk/main/README.md
- Guide: local MCP builder Node server reference

### 6.3 Example: Zotero-MCP Patterns

**Location:** external Zotero-MCP reference implementation

**Key files to reference:**
- `src/zotero_mcp/semantic_search.py` - Semantic search implementation
- `src/zotero_mcp/chroma_client.py` - ChromaDB integration patterns
- `src/zotero_mcp/server.py` - MCP tool definitions

**Proven patterns from Zotero-MCP:**

1. **Dual Storage:**
   - SQLite for structured metadata
   - ChromaDB for semantic embeddings
   - Pattern works at scale (tested with 10k+ documents)

2. **Embedding Models:**
   - Default: all-MiniLM-L6-v2 (free, local)
   - Optional: OpenAI, Gemini (API-based)
   - Config-driven selection

3. **Update Strategy:**
   - Manual: `zotero-mcp update-db`
   - Auto: Configurable frequency (startup, daily, weekly)
   - Incremental updates (don't rebuild everything)

4. **Tool Annotations:**
   ```python
   @mcp.tool(readOnlyHint=True)
   def search_tool(...):
       """Clear description with examples."""
   ```

5. **Testing:**
   - 294 unit tests
   - Integration test plan in `docs/integration-test-plan.md`

**Do NOT copy verbatim** - adapt patterns to legal domain.

---

---

## 8. Quick Start (For Implementation Agents)

**Current status (2026-04-26):**
- ✅ MCP scaffolding complete
- ✅ Storage layer complete (SQLite + ChromaDB)
- ✅ USC download & parser complete
- ✅ CLI commands fully implemented (setup, update-db, db-status, serve)
- ✅ USC tool implementations complete (get_usc_section, get_title_toc, all search tools)
- ✅ USC fully loaded into databases (~55k sections, Public Law 119-84)
- 🚧 CFR client (Phase 2)
- 🚧 GovInfo wrapper (Phase 3)
- 🚧 Citation parser utility
- 🚧 Integration tests and evaluation queries

### What's Already Done — Don't Rebuild

- `server.py` — MCP server, tool registration, startup hooks
- `cli.py` — All 4 commands fully implemented
- `storage/sqlite_db.py` — Schema, CRUD, FTS5
- `storage/chroma_client.py` — Vector search, embeddings, incremental update helpers
- `data/usc_parser.py` — Download, extract, parse USLM XML
- `tools/usc_tools.py` — `get_usc_section`, `get_title_toc` implemented
- `tools/search_tools.py` — `search_usc_semantic`, `search_cfr_semantic`, `search_fulltext`, `get_database_status` implemented
- Databases populated: `~/.config/legal-mcp/legal.db` and `~/.config/legal-mcp/chroma_db/`

### What Still Needs Implementation

**Phase 2 — CFR (`data/cfr_client.py`):**
1. `get_cfr_section(title, part, section)` - fetch from eCFR API, cache in SQLite
2. `fetch_all_cfr_sections(title)` - bulk fetch for a CFR title, populate SQLite + ChromaDB
3. Wire into `tools/cfr_tools.py` — `get_cfr_section` and `find_implementing_regulations`
4. Add `legal-mcp setup --cfr` or extend `update-db` to include CFR ingestion

eCFR API base: `https://www.ecfr.gov/api/versioner/v1` — no key required.

**Phase 3 — GovInfo (`data/govinfo_wrapper.py`):**
1. `search_govinfo(query, congress)` - call GovInfo MCP `searchGovInfo` tool
2. `get_public_law(congress, law_number)` - call GovInfo MCP `describePackageOrGranule`
3. Wire into `tools/bill_tools.py`

Requires GovInfo MCP configured in Claude Code with API key from govinfo.gov.

**Phase 4 — Utilities & Testing:**
1. `utils/citation_parser.py` - parse "42 USC § 1983" → `{title: "42", section: "1983"}`, "26 CFR § 1.401(a)-1" → `{title: "26", part: "1", section: "401(a)-1"}`
2. Integration test suite with real queries against populated databases
3. 10 complex legal research evaluation questions

### Update Strategy (Already Implemented)

`legal-mcp update-db` workflow:
1. Calls `check_for_updates(stored_release)` — scrapes house.gov, compares release points
2. If update available (or `--force`): re-runs `setup` with `force=True`
3. Incremental ChromaDB update: `get_existing_ids()` splits batch into new vs update
4. Stores new release point in SQLite metadata table after completion

Notify-only at server startup is not yet wired — the startup hook in `server.py` currently just initializes storage. To add: call `check_for_updates()` and print to stderr if new release available.

### Key Decisions (Already Made)

- **Python + FastMCP** (legal domain has strong Python ecosystem)
- **SQLite + ChromaDB** (citations need <100ms exact match, semantic needs vectors)
- **house.gov XML** (official source, bulk download, no rate limits, structured USLM)
- **Local embeddings only** (sentence-transformers/all-MiniLM-L6-v2, no OpenAI/Gemini)
- **USC XML note filtering** - only `<note topic="miscellaneous">` included; editorial/amendment notes excluded
- **Intra-batch deduplication** - USC XML yields duplicate `(title, section)` from appendices; deduped via dict before ChromaDB upsert; SQLite handles via `UNIQUE + INSERT OR REPLACE`

---

## Glossary

**USC** - United States Code  
**CFR** - Code of Federal Regulations  
**USLM** - US Legislative Markup (XML schema)  
**MCP** - Model Context Protocol  
**ChromaDB** - Vector database for semantic search  
**Embedding** - Vector representation of text  
**eCFR** - Electronic CFR  
**GovInfo** - Government Publishing Office API  
**PACER** - Public Access to Court Electronic Records ($$$)  
**CourtListener** - Free case law database
