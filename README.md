# Legal MCP

MCP server providing structured and semantic access to federal legal resources (US Code, CFR, bills, session laws) for legal research in Claude Code.

## Status: 🚧 In Development

**Current Phase:** MCP scaffolding complete, functionality implementation in progress

See [`LEGAL_MCP_MASTER_PLAN.md`](../LEGAL_MCP_MASTER_PLAN.md) for complete technical reference.

## Features (Planned)

### Core MVP
- **US Code**: Citation lookup, semantic search, full-text search, navigation
- **CFR**: Regulatory lookup, cross-references to USC
- **Session Laws**: Public laws (Statutes at Large) - authoritative for non-positive law USC

### Search Capabilities
- **Semantic**: Find conceptually related sections ("qualified immunity" → 42 USC § 1983)
- **Citation**: Instant lookup by citation (<100ms)
- **Full-text**: Keyword search with boolean operators

## Installation (WIP)

```bash
cd legal-mcp
pip install -e .

# Configure (TODO: implement setup)
legal-mcp setup

# Build databases (TODO: implement update-db)
legal-mcp update-db

# Check status
legal-mcp db-status
```

## Usage with Claude Code

Add to your MCP client config (e.g., Claude Desktop):

```json
{
  "mcpServers": {
    "legal-mcp": {
      "command": "legal-mcp",
      "args": ["serve"],
      "env": {}
    }
  }
}
```

Then use in Claude Code:
```
Search USC for "qualified immunity for police officers"
Get 42 USC § 1983
Find CFR regulations implementing 26 USC § 401
```

## Architecture

**Dual Storage:**
- **SQLite**: Structured data (citations, cross-references, metadata) - fast exact lookup
- **ChromaDB**: Vector embeddings (semantic search) - conceptual discovery

**Data Sources:**
- US Code XML from house.gov (bulk download)
- eCFR API for regulations
- GovInfo MCP for bills/session laws

**Embedding Model:** sentence-transformers/all-MiniLM-L6-v2 (free, local, proven)

## Project Structure

```
legal-mcp/
├── src/legal_mcp/
│   ├── server.py              # FastMCP server (COMPLETE)
│   ├── cli.py                 # CLI commands (SCAFFOLDING)
│   ├── data/                  # Data ingestion (TODO)
│   │   ├── usc_parser.py      # Parse USC XML
│   │   ├── cfr_client.py      # eCFR API
│   │   └── govinfo_wrapper.py # GovInfo MCP integration
│   ├── storage/               # Storage layer (TODO)
│   │   ├── sqlite_db.py       # SQLite operations
│   │   └── chroma_client.py   # ChromaDB wrapper
│   ├── tools/                 # MCP tools (SIGNATURES DEFINED)
│   │   ├── usc_tools.py       # USC tools
│   │   ├── cfr_tools.py       # CFR tools
│   │   ├── bill_tools.py      # Bill/session law tools
│   │   └── search_tools.py    # Search tools
│   └── utils/                 # Utilities (TODO)
│       └── citation_parser.py # Parse legal citations
└── tests/                     # Tests (TODO)
```

## Implementation Status

✅ **Complete:**
- Project structure
- FastMCP server setup
- MCP tool signatures and contracts
- Database schema (documented in master plan)

🚧 **In Progress:**
- USC XML parser
- SQLite database implementation
- ChromaDB integration
- Tool implementations

❌ **Not Started:**
- CFR integration
- GovInfo MCP wrapper
- Testing suite
- Evaluation questions

## Development

See [`LEGAL_MCP_MASTER_PLAN.md`](../LEGAL_MCP_MASTER_PLAN.md) for:
- Complete architecture details
- Database schemas
- Data source specifications
- Implementation patterns
- Reference resources

## License

MIT
