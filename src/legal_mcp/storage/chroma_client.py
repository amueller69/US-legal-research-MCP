"""ChromaDB client for semantic search - adapted from Zotero-MCP pattern.

Handles:
- Embedding generation (sentence-transformers/all-MiniLM-L6-v2)
- Vector storage and indexing
- Semantic similarity search
- Metadata filtering

Reference: /home/alex/Repos/Zotero-MCP-fork/src/zotero_mcp/chroma_client.py
"""

import logging
from pathlib import Path
from typing import Optional, Any

logger = logging.getLogger(__name__)

# ChromaDB imports
try:
    import chromadb
    from chromadb.config import Settings
except ImportError as e:
    raise ImportError(
        "chromadb is required for semantic search. "
        "Install it with: pip install chromadb sentence-transformers"
    ) from e


# Collection name and persist directory
COLLECTION_NAME = "legal_documents"
PERSIST_DIR = Path.home() / ".config" / "legal-mcp" / "chroma_db"

# Module-level client and collection (initialized on first use)
_client: Optional[chromadb.PersistentClient] = None
_collection: Optional[chromadb.Collection] = None
_embedding_function: Optional[Any] = None


def _get_client() -> chromadb.PersistentClient:
    """Get or create ChromaDB client."""
    global _client
    if _client is None:
        PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(PERSIST_DIR),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
    return _client


def _get_embedding_function():
    """Get or create embedding function (all-MiniLM-L6-v2 by default)."""
    global _embedding_function
    if _embedding_function is None:
        # Use ChromaDB's default embedding function (all-MiniLM-L6-v2)
        _embedding_function = chromadb.utils.embedding_functions.DefaultEmbeddingFunction()
    return _embedding_function


def _get_collection() -> chromadb.Collection:
    """Get or create collection."""
    global _collection
    if _collection is None:
        client = _get_client()
        embedding_fn = _get_embedding_function()

        try:
            _collection = client.get_or_create_collection(
                name=COLLECTION_NAME,
                embedding_function=embedding_fn
            )
            logger.info(f"Using ChromaDB collection: {COLLECTION_NAME}")
        except Exception as e:
            logger.error(f"Error creating collection: {e}")
            raise

    return _collection


async def initialize():
    """
    Initialize ChromaDB client and collection.

    Sets up:
    - Persistent ChromaDB client
    - Default embedding function (all-MiniLM-L6-v2)
    - Legal documents collection
    """
    logger.info(f"Initializing ChromaDB at {PERSIST_DIR}")

    # Force initialization by getting collection
    collection = _get_collection()

    logger.info(f"ChromaDB initialized with {collection.count()} documents")


async def upsert_documents(documents: list[str], metadatas: list[dict], ids: list[str]):
    """
    Add or update documents in ChromaDB.

    Args:
        documents: List of text content to embed
        metadatas: List of metadata dicts (source_type, citation, etc.)
        ids: List of unique IDs (e.g., 'usc-42-1983')
    """
    if not documents:
        return

    if len(documents) != len(metadatas) or len(documents) != len(ids):
        raise ValueError("documents, metadatas, and ids must have the same length")

    collection = _get_collection()

    # Truncate documents to token limit
    truncated_docs = [truncate_text(doc) for doc in documents]

    try:
        collection.upsert(
            documents=truncated_docs,
            metadatas=metadatas,
            ids=ids
        )
        logger.info(f"Upserted {len(documents)} documents to ChromaDB")
    except Exception as e:
        logger.error(f"Error upserting documents: {e}")
        raise


async def search(query: str, n_results: int = 10, where: Optional[dict] = None) -> dict:
    """
    Semantic search using vector similarity.

    Args:
        query: Natural language query
        n_results: Number of results to return
        where: Metadata filter (e.g., {"source_type": "usc"})

    Returns:
        {
            "ids": [["usc-42-1983", ...]],
            "distances": [[0.13, ...]],
            "documents": [["Civil action for...", ...]],
            "metadatas": [[{...}, ...]]
        }
    """
    collection = _get_collection()

    try:
        query_kwargs = {
            "query_texts": [query],
            "n_results": n_results,
        }

        if where:
            query_kwargs["where"] = where

        results = collection.query(**query_kwargs)

        logger.info(f"Semantic search for '{query}' returned {len(results.get('ids', [[]])[0])} results")
        return results

    except Exception as e:
        logger.error(f"Error performing semantic search: {e}")
        raise


async def delete_documents(ids: list[str]):
    """
    Delete documents from the collection.

    Args:
        ids: List of document IDs to delete
    """
    if not ids:
        return

    collection = _get_collection()

    try:
        collection.delete(ids=ids)
        logger.info(f"Deleted {len(ids)} documents from ChromaDB")
    except Exception as e:
        logger.error(f"Error deleting documents: {e}")
        raise


async def get_collection_info() -> dict:
    """Get collection statistics."""
    try:
        collection = _get_collection()
        count = collection.count()

        return {
            "name": COLLECTION_NAME,
            "count": count,
            "embedding_model": "all-MiniLM-L6-v2",
            "persist_directory": str(PERSIST_DIR)
        }
    except Exception as e:
        logger.error(f"Error getting collection info: {e}")
        return {
            "name": COLLECTION_NAME,
            "count": 0,
            "embedding_model": "all-MiniLM-L6-v2",
            "persist_directory": str(PERSIST_DIR),
            "error": str(e)
        }


async def reset_collection():
    """Reset (clear) the collection."""
    global _collection

    try:
        client = _get_client()
        client.delete_collection(name=COLLECTION_NAME)
        _collection = None  # Force recreation

        # Recreate collection
        _get_collection()

        logger.info(f"Reset ChromaDB collection '{COLLECTION_NAME}'")
    except Exception as e:
        logger.error(f"Error resetting collection: {e}")
        raise


def document_exists(doc_id: str) -> bool:
    """Check if a document exists in the collection."""
    try:
        collection = _get_collection()
        result = collection.get(ids=[doc_id])
        return len(result['ids']) > 0
    except Exception:
        return False


def get_existing_ids(ids: list[str]) -> set[str]:
    """Return the subset of ids that already exist in the collection."""
    if not ids:
        return set()

    try:
        collection = _get_collection()
        result = collection.get(ids=ids, include=[])
        return set(result.get("ids", []))
    except Exception:
        return set()


def truncate_text(text: str, max_tokens: int = 8000) -> str:
    """
    Truncate text to fit within embedding model token limit.

    Uses character-based approximation (~4 chars/token for all-MiniLM-L6-v2).
    For more accurate truncation, could use tiktoken with cl100k_base encoding.

    Args:
        text: Input text
        max_tokens: Maximum tokens (default: 8000, conservative for most models)

    Returns:
        Truncated text
    """
    # all-MiniLM-L6-v2 has max_seq_length of 256 tokens, but we use a conservative
    # limit here. The actual model will truncate at its limit anyway.
    # For legal documents, we want to preserve as much context as possible.

    # Character-based approximation: ~4 chars per token
    max_chars = max_tokens * 4

    if len(text) <= max_chars:
        return text

    # Truncate and add indicator
    return text[:max_chars]


def close():
    """Close ChromaDB client (cleanup)."""
    global _client, _collection
    _client = None
    _collection = None
