"""Storage layer - SQLite and ChromaDB."""

# SQLite exports
from .sqlite_db import (
    initialize as initialize_sqlite,
    get_section,
    insert_sections,
    search_fulltext,
    get_metadata,
    set_metadata,
    get_title_toc,
    close as close_sqlite,
)

# ChromaDB exports
from .chroma_client import (
    initialize as initialize_chroma,
    upsert_documents,
    search as search_semantic,
    delete_documents,
    get_collection_info,
    reset_collection,
    document_exists,
    get_existing_ids,
    truncate_text,
    close as close_chroma,
)

__all__ = [
    # SQLite functions
    "initialize_sqlite",
    "get_section",
    "insert_sections",
    "search_fulltext",
    "get_metadata",
    "set_metadata",
    "get_title_toc",
    "close_sqlite",
    # ChromaDB functions
    "initialize_chroma",
    "upsert_documents",
    "search_semantic",
    "delete_documents",
    "get_collection_info",
    "reset_collection",
    "document_exists",
    "get_existing_ids",
    "truncate_text",
    "close_chroma",
]
