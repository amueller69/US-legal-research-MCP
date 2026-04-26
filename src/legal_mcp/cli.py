"""
Legal MCP CLI - Command-line interface for setup and maintenance.

Commands:
    legal-mcp setup       - Configure embedding model, download USC XML
    legal-mcp update-db   - Update SQLite + ChromaDB databases
    legal-mcp db-status   - Show database status
    legal-mcp serve       - Start MCP server (usually called by MCP client)
"""

import argparse
import asyncio
import sys


def setup():
    """Configure Legal MCP - embedding model, data sources, etc."""
    print("Legal MCP Setup")
    print("=" * 50)
    print("\nThis will configure:")
    print("  - Embedding model (default: all-MiniLM-L6-v2)")
    print("  - Download USC XML from house.gov")
    print("  - Initialize databases")
    print("\nNOTE: Setup functionality to be implemented")
    print("See LEGAL_MCP_MASTER_PLAN.md for implementation details")


def update_db(args):
    """Update databases with latest legal data."""
    print(f"Updating databases...")
    print(f"  Force rebuild: {args.force}")
    print(f"  Include fulltext: {args.fulltext}")

    print("\nNOTE: Database update functionality to be implemented")
    print("Will update:")
    print("  - US Code from house.gov XML")
    print("  - CFR from eCFR API")
    print("  - Session laws from GovInfo MCP")


def db_status():
    """Show database status and statistics."""
    print("Database Status")
    print("=" * 50)
    print("\nNOTE: Status check functionality to be implemented")
    print("Will show:")
    print("  - SQLite: table counts, last update, release point")
    print("  - ChromaDB: document count, embedding model, collection size")


def serve(args):
    """Start MCP server."""
    print(f"Starting Legal MCP server on {args.transport}...")
    from legal_mcp.server import mcp

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    elif args.transport == "streamable-http":
        mcp.run(transport="streamable-http", port=args.port)
    else:
        print(f"Unknown transport: {args.transport}")
        sys.exit(1)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Legal MCP - Federal legal research tools for Claude Code",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Setup command
    subparsers.add_parser("setup", help="Configure Legal MCP")

    # Update database command
    update_parser = subparsers.add_parser("update-db", help="Update databases")
    update_parser.add_argument("--force", action="store_true", help="Force full rebuild")
    update_parser.add_argument("--fulltext", action="store_true", help="Include fulltext extraction")

    # Database status command
    subparsers.add_parser("db-status", help="Show database status")

    # Serve command
    serve_parser = subparsers.add_parser("serve", help="Start MCP server")
    serve_parser.add_argument("--transport", default="stdio", choices=["stdio", "streamable-http"])
    serve_parser.add_argument("--port", type=int, default=8000, help="Port for HTTP transport")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Dispatch to command handlers
    if args.command == "setup":
        setup()
    elif args.command == "update-db":
        update_db(args)
    elif args.command == "db-status":
        db_status()
    elif args.command == "serve":
        serve(args)
    else:
        print(f"Unknown command: {args.command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
