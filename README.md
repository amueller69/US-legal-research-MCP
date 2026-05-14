# Legal MCP

Local MCP server for federal legal research in Claude Code. The current MVP focuses on US Code lookup and search backed by local SQLite and ChromaDB storage.

## Current Status

Phase 1 MVP is focused on US Code support:

- USC citation lookup by title and section
- USC table of contents lookup by title
- SQLite full-text search
- ChromaDB semantic search with local embeddings
- CLI setup, update, and database status commands
- FastMCP stdio server for local MCP clients

Registered but not yet implemented:

- CFR section lookup
- USC-to-CFR implementing regulation lookup
- Public law retrieval
- Bill search

Those tools currently return explicit "not yet implemented" responses.

## Fresh Setup

From a new clone:

```bash
git clone <repo-url> US-legal-research-MCP
cd US-legal-research-MCP

python3 -m venv .venv
source .venv/bin/activate

python -m pip install -e .
```

For development and tests:

```bash
python -m pip install -e ".[dev]"
```

This installs into the active virtual environment. Do not run the install commands outside the venv unless you intentionally want a global install.

## Build The Local Databases

Initial setup downloads the current US Code XML release from house.gov, parses it, stores structured data in SQLite, and indexes semantic documents in ChromaDB:

```bash
legal-mcp setup
```

This can take a while on the first run because it parses and embeds the US Code locally. Check the result with:

```bash
legal-mcp db-status
```

To check for a newer US Code release later:

```bash
legal-mcp update-db
```

To force a clean rebuild:

```bash
legal-mcp update-db --force
```

`--force` clears existing USC rows/vectors and rebuilds from the current release.

## Update Behavior

`legal-mcp update-db` uses a two-stage USC update process:

1. Compare title-level XML hashes as a cheap first-pass detector.
2. For changed title XML files, parse sections and compare normalized per-section content hashes.

Only new or changed sections are re-embedded. Removed sections are deleted from SQLite and ChromaDB. Raw XML metadata churn, generated IDs, timestamps, and whitespace should not trigger re-embedding unless the extracted indexed section content changes.

After successful non-limited setup/update runs, stale USC XML release cache folders are pruned and the current release cache is kept.

## Storage Locations

Runtime data is stored outside the repository:

```text
~/.config/legal-mcp/legal.db
~/.config/legal-mcp/chroma_db/
~/.cache/legal-mcp/usc-xml/
```

The SQLite database stores structured sections, metadata, title hashes, and section content hashes. ChromaDB stores semantic search vectors. The XML cache stores extracted house.gov USC release files used for setup/update.

## Claude Code / MCP Client Config

For local use, stdio is the intended transport. HTTP is not required.

Use the absolute path to the `legal-mcp` executable inside your venv:

```json
{
  "mcpServers": {
    "legal-mcp": {
      "command": "/absolute/path/to/US-legal-research-MCP/.venv/bin/legal-mcp",
      "args": ["serve", "--transport", "stdio"],
      "env": {}
    }
  }
}
```

Example prompts after setup:

```text
Get 42 USC 1983
Search USC for "qualified immunity for police officers"
Search full text for "equal protection"
Show the table of contents for title 42
```

## CLI Commands

```bash
legal-mcp --help
legal-mcp setup
legal-mcp update-db
legal-mcp update-db --force
legal-mcp db-status
legal-mcp serve --transport stdio
```

`legal-mcp serve --transport streamable-http --port 8000` is available for HTTP experiments, but local Claude/Claude Code usage should normally use stdio.

## Development

Run tests:

```bash
source .venv/bin/activate
python -m pytest -q
```

Current smoke coverage includes storage operations, CLI help/status behavior, and FastMCP tool registration.

## Project Structure

```text
US-legal-research-MCP/
├── src/legal_mcp/
│   ├── _app.py                # Shared FastMCP app and lifecycle
│   ├── server.py              # Server entrypoint and tool registration
│   ├── cli.py                 # setup/update/db-status/serve commands
│   ├── data/
│   │   ├── usc_parser.py      # USC XML download, parse, hash, cache helpers
│   │   ├── cfr_client.py      # Future eCFR integration
│   │   └── govinfo_wrapper.py # Future GovInfo integration
│   ├── storage/
│   │   ├── sqlite_db.py       # Structured storage and FTS
│   │   └── chroma_client.py   # Vector storage and semantic search
│   └── tools/
│       ├── usc_tools.py
│       ├── search_tools.py
│       ├── cfr_tools.py
│       └── bill_tools.py
└── tests/
```

## Reference Docs

- `LEGAL_MCP_MASTER_PLAN.md`
- `STORAGE_IMPLEMENTATION.md`

## License

MIT
