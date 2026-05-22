"""
Legal MCP CLI - Command-line interface for setup and maintenance.

Commands:
    legal-mcp setup       - Download USC XML and populate databases
    legal-mcp update-db   - Check for updates and update changed sections
    legal-mcp db-status   - Show database status
    legal-mcp serve       - Start MCP server (usually called by MCP client)

NOTE: Heavy imports (FastMCP, ChromaDB, sentence-transformers) are deferred to
each command handler so the CLI starts instantly.
"""

import argparse
import sys


def _usc_doc_id(section: dict) -> str:
    return f"usc-{section['title']}-{section['section']}"


async def _update_database(
    xml_dir,
    force_rebuild: bool = False,
    limit: int | None = None,
    titles: set[str] | None = None,
    sections: list[dict] | None = None,
) -> dict:
    """
    Parse USC XML and populate SQLite + ChromaDB.

    Models the Zotero-MCP update_database() pattern:
    - Stats tracking (total, processed, added, updated, skipped, errors)
    - Terminal-width-aware \r progress
    - Retry logic for failed ChromaDB batches
    - Incremental updates (skip unchanged sections via get_existing_ids)

    Args:
        xml_dir: Path to directory containing USC XML files
        force_rebuild: If True, skip incremental check and re-embed everything
        limit: Cap number of sections (for testing)
        titles: Optional USC title numbers to parse/index
        sections: Optional pre-parsed USC sections to index instead of parsing xml_dir

    Returns:
        Stats dict with keys: total, processed, added, updated, skipped, errors,
        recovered, duration
    """
    import time
    from datetime import datetime

    from legal_mcp.storage import (
        get_existing_ids,
        insert_sections,
        upsert_documents,
    )
    from legal_mcp.data.usc_parser import (
        get_usc_section_content_hash,
        get_usc_section_document,
        parse_usc_xml,
    )

    stats = {
        "total": 0,
        "processed": 0,
        "added": 0,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
        "recovered": 0,
        "duration": None,
    }
    start_time = datetime.now()
    now = datetime.now().isoformat()

    # Batch size: larger than Zotero's 25 because we use local embeddings
    # (no API token limits). ChromaDB ONNX tokenizer can still fail
    # intermittently, so we collect failures for end-of-run retry.
    BATCH_SIZE = 500

    batch_sections: list[dict] = []
    failed_batches: list[tuple] = []  # (docs, metadatas, ids) tuples for retry

    def _try_get_terminal_width() -> int:
        try:
            return __import__("os").get_terminal_size().columns
        except (OSError, ValueError):
            return 80

    def _progress(n: int, label: str = "") -> None:
        width = _try_get_terminal_width() - 1
        parts = []
        if stats["added"]:
            parts.append(f"{stats['added']} added")
        if stats["updated"]:
            parts.append(f"{stats['updated']} updated")
        if stats["skipped"]:
            parts.append(f"{stats['skipped']} skipped")
        if stats["errors"]:
            parts.append(f"{stats['errors']} errors")
        counts = f" ({', '.join(parts)})" if parts else ""
        prefix = f"  Indexing {n}{counts} — "
        remaining = width - len(prefix) - 3
        if label and remaining > 0 and len(label) > remaining:
            label = label[:remaining] + "..."
        line = f"{prefix}{label or 'working...'}"
        if len(line) > width:
            line = line[:width]
        sys.stderr.write(f"\r{line}{' ' * max(0, width - len(line))}")
        sys.stderr.flush()

    async def _flush_batch(sections: list[dict]) -> None:
        """Insert one batch into SQLite and ChromaDB; collect ChromaDB failures."""
        nonlocal failed_batches

        for s in sections:
            s.setdefault("last_updated", now)
            s.setdefault("content_hash", get_usc_section_content_hash(s))

        # SQLite — INSERT OR REPLACE handles add vs update transparently
        try:
            await insert_sections("usc_sections", sections)
        except Exception as e:
            sys.stderr.write(f"\n  [WARN] SQLite batch insert failed: {e}\n")
            stats["errors"] += len(sections)
            return

        # Build ChromaDB payload, deduplicating by doc_id within this batch.
        # The USC XML can yield the same (title, section) from appendices or
        # repeated substructures; SQLite handles this with UNIQUE(title, section)
        # + INSERT OR REPLACE, but ChromaDB rejects duplicate IDs in one upsert.
        seen: dict[str, tuple] = {}  # doc_id -> (doc_text, metadata)
        for s in sections:
            doc_text = get_usc_section_document(s)
            doc_id = _usc_doc_id(s)
            seen[doc_id] = (doc_text, {
                "source_type": "usc",
                "title": s["title"],
                "section": s["section"],
                "citation": f"{s['title']} USC § {s['section']}",
                "heading": s.get("heading") or "",
                "chapter": s.get("chapter") or "",
            })
        ids = list(seen.keys())
        docs = [seen[i][0] for i in ids]
        metadatas = [seen[i][1] for i in ids]

        # Skip sections already in ChromaDB for incremental updates
        if not force_rebuild:
            existing = get_existing_ids(ids)
            new_ids = [i for i in ids if i not in existing]
            new_docs = [d for i, d in zip(ids, docs) if i not in existing]
            new_metas = [m for i, m in zip(ids, metadatas) if i not in existing]
            update_docs = [d for i, d in zip(ids, docs) if i in existing]
            update_ids = [i for i in ids if i in existing]
            update_metas = [m for i, m in zip(ids, metadatas) if i in existing]
            stats["added"] += len(new_ids)
            stats["updated"] += len(update_ids)
            docs_to_upsert = new_docs + update_docs
            ids_to_upsert = new_ids + update_ids
            metas_to_upsert = new_metas + update_metas
        else:
            stats["added"] += len(ids)
            docs_to_upsert, ids_to_upsert, metas_to_upsert = docs, ids, metadatas

        if not docs_to_upsert:
            stats["skipped"] += len(sections)
            return

        try:
            await upsert_documents(docs_to_upsert, metas_to_upsert, ids_to_upsert)
            stats["processed"] += len(sections)
        except Exception as e:
            # Collect for end-of-run retry — ChromaDB ONNX tokenizer fails
            # intermittently; retrying after all batches usually succeeds.
            sys.stderr.write(f"\n  [WARN] ChromaDB batch failed ({e}), queued for retry\n")
            failed_batches.append((docs_to_upsert, metas_to_upsert, ids_to_upsert))
            stats["errors"] += len(docs_to_upsert)

    section_iter = sections if sections is not None else parse_usc_xml(xml_dir, limit=limit, titles=titles)

    for section in section_iter:
        stats["total"] += 1
        batch_sections.append(section)

        heading = section.get("heading") or ""
        label = f"{section['title']} USC § {section['section']} — {heading}"
        _progress(stats["total"], label)

        if len(batch_sections) >= BATCH_SIZE:
            await _flush_batch(batch_sections)
            batch_sections.clear()

    if batch_sections:
        await _flush_batch(batch_sections)
        batch_sections.clear()

    # End-of-run retry for failed ChromaDB batches
    if failed_batches:
        sys.stderr.write(f"\r{' ' * (_try_get_terminal_width() - 1)}\r")
        sys.stderr.write(f"\n  Retrying {len(failed_batches)} failed batch(es)...\n")
        import time as _time
        _time.sleep(1)
        retry_ok = 0
        retry_fail = 0
        for _docs, _metas, _ids in failed_batches:
            try:
                await upsert_documents(_docs, _metas, _ids)
                retry_ok += len(_ids)
                stats["errors"] -= len(_ids)
                stats["recovered"] += len(_ids)
            except Exception as e2:
                retry_fail += len(_ids)
                sys.stderr.write(f"  [ERROR] Retry failed: {e2}\n")
        sys.stderr.write(f"  Retry: {retry_ok} recovered, {retry_fail} still failed\n")

    # Clear progress line, print summary
    sys.stderr.write(f"\r{' ' * (_try_get_terminal_width() - 1)}\r")
    summary = (
        f"  Done: {stats['total']} total, "
        f"{stats['added']} added, "
        f"{stats['updated']} updated, "
        f"{stats['skipped']} skipped, "
        f"{stats['errors']} errors"
    )
    if stats["recovered"]:
        summary += f", {stats['recovered']} recovered"
    sys.stderr.write(summary + "\n")

    from datetime import datetime as _dt
    stats["duration"] = str(_dt.now() - start_time)
    return stats


async def _backfill_usc_section_content_hashes(
    xml_dir,
    titles: set[str] | None = None,
) -> int:
    from legal_mcp.data.usc_parser import get_usc_section_content_hash, parse_usc_xml
    from legal_mcp.storage import set_usc_section_hashes

    hashes_by_title: dict[str, dict[str, str]] = {}
    for section in parse_usc_xml(xml_dir, titles=titles):
        title = section["title"]
        section_num = section["section"]
        hashes_by_title.setdefault(title, {})[section_num] = get_usc_section_content_hash(section)

    updated_count = 0
    for title, section_hashes in hashes_by_title.items():
        updated_count += await set_usc_section_hashes(title, section_hashes)
    return updated_count


def _prune_usc_xml_cache(xml_dir) -> None:
    from legal_mcp.data.usc_parser import prune_usc_xml_cache

    removed = prune_usc_xml_cache(xml_dir)
    if removed:
        print(f"Pruned {len(removed)} stale USC XML cache entr{'y' if len(removed) == 1 else 'ies'}.")


async def _run_setup(force: bool = False, limit: int | None = None):
    from datetime import datetime

    from legal_mcp.storage import (
        clear_sections,
        clear_usc_title_hashes,
        delete_metadata,
        delete_documents_by_source,
        get_usc_title_hashes,
        initialize_chroma,
        initialize_sqlite,
        get_metadata,
        set_metadata,
        set_usc_title_hash,
    )
    from legal_mcp.data.usc_parser import download_usc_xml, get_usc_title_hashes as compute_title_hashes

    print("Legal MCP Setup")
    print("=" * 50)

    print("\nInitializing databases...")
    await initialize_sqlite()
    await initialize_chroma()
    print("  SQLite:   OK")
    print("  ChromaDB: OK")

    stored_release = await get_metadata("usc_release_point")
    if stored_release and not force:
        print(f"\nUSC already loaded: {stored_release}")
        print("Run 'legal-mcp update-db' to check for updates or 'legal-mcp update-db --rebuild' to rebuild from cache.")
        return

    print("\nFetching USC XML from house.gov...")
    xml_dir, release_point = await download_usc_xml(force=force)
    print(f"  Release: {release_point}")
    print(f"  Cache:   {xml_dir}")
    title_hashes = compute_title_hashes(xml_dir)

    if force:
        print("\nClearing existing USC data...")
        sqlite_deleted = await clear_sections("usc_sections")
        chroma_deleted = await delete_documents_by_source("usc")
        await clear_usc_title_hashes()
        await delete_metadata("usc_release_point")
        await delete_metadata("last_usc_update")
        print(f"  SQLite USC sections: {sqlite_deleted:,} deleted")
        print(f"  ChromaDB USC docs:   {chroma_deleted:,} deleted")
    else:
        stored_hashes = await get_usc_title_hashes()
        if stored_hashes:
            unchanged = sorted(t for t, h in title_hashes.items() if stored_hashes.get(t) == h)
            if unchanged:
                print(f"\nSkipping {len(unchanged)} unchanged USC title(s) based on XML hashes.")

    print("\nParsing and indexing USC sections (this will take a while)...")
    stats = await _update_database(xml_dir, force_rebuild=force, limit=limit)

    print(f"\nIndexing complete:")
    print(f"  Total sections: {stats['total']:,}")
    print(f"  Added:          {stats['added']:,}")
    print(f"  Updated:        {stats['updated']:,}")
    print(f"  Skipped:        {stats['skipped']:,}")
    print(f"  Errors:         {stats['errors']:,}")
    print(f"  Duration:       {stats['duration']}")

    if stats["errors"]:
        raise RuntimeError(
            f"USC indexing completed with {stats['errors']:,} error(s); metadata was not updated."
        )

    if limit is not None:
        print("\nLimit was used for testing; release metadata and title hashes were not updated.")
        return

    await set_metadata("usc_release_point", release_point)
    await set_metadata("last_usc_update", datetime.now().isoformat())
    for title, xml_hash in title_hashes.items():
        await set_usc_title_hash(title, xml_hash, release_point)
    _prune_usc_xml_cache(xml_dir)
    print(f"\nSaved metadata. Release: {release_point}")
    print("Setup complete.")


async def _run_update_db(force: bool = False, rebuild: bool = False, limit: int | None = None):
    from datetime import datetime

    from legal_mcp.storage import (
        clear_usc_title,
        count_usc_sections_missing_content_hash,
        delete_documents,
        delete_documents_by_source_and_title,
        delete_usc_title_hash,
        delete_usc_sections,
        get_metadata,
        get_usc_sections_for_title,
        get_usc_title_hashes,
        initialize_chroma,
        initialize_sqlite,
        set_metadata,
        set_usc_section_hashes,
        set_usc_title_hash,
    )
    from legal_mcp.data.usc_parser import (
        check_for_updates,
        download_usc_xml,
        get_usc_section_content_hash,
        get_usc_release_cache_dir,
        get_usc_title_hashes as compute_title_hashes,
        parse_usc_xml,
    )

    await initialize_sqlite()
    await initialize_chroma()

    if force and rebuild:
        raise ValueError("Use either --force or --rebuild, not both.")

    if rebuild:
        await _run_rebuild_db(limit=limit)
        return

    stored_release = await get_metadata("usc_release_point")
    has_update, current_release, stored = check_for_updates(stored_release)

    if force:
        print("Force refresh requested: downloading current USC XML, clearing USC data, and rebuilding.")
        await _run_setup(force=True, limit=limit)
        return

    if not has_update:
        stored_hashes = await get_usc_title_hashes()
        if not stored_hashes and stored_release:
            print(f"USC is up to date: {stored_release}")
            print("Backfilling USC title XML hashes for future incremental updates...")
            xml_dir, release_point = await download_usc_xml(force=False)
            current_hashes = compute_title_hashes(xml_dir)
            for title, xml_hash in current_hashes.items():
                await set_usc_title_hash(title, xml_hash, release_point)
            if limit is None:
                _prune_usc_xml_cache(xml_dir)
            print(f"  Stored {len(current_hashes)} title hash(es).")
            return

        missing_content_hashes = await count_usc_sections_missing_content_hash()
        if missing_content_hashes and stored_release:
            print(f"USC is up to date: {stored_release}")
            print(f"Backfilling {missing_content_hashes:,} USC section content hash(es)...")
            xml_dir, release_point = await download_usc_xml(force=False)
            updated_count = await _backfill_usc_section_content_hashes(xml_dir)
            print(f"  Stored {updated_count:,} section content hash(es).")
            return

        print(f"USC is up to date: {stored_release or 'not initialized'}")
        if limit is None:
            current_xml_dir = get_usc_release_cache_dir(current_release)
            if current_xml_dir.exists():
                _prune_usc_xml_cache(current_xml_dir)
        return

    if not stored_release:
        print(f"USC database not initialized. Building current release: {current_release}")
        await _run_setup(force=False, limit=limit)
        return

    if has_update:
        print(f"Update available: {stored or 'not initialized'} -> {current_release}")

    print("\nFetching USC XML from house.gov...")
    xml_dir, release_point = await download_usc_xml(force=False)
    print(f"  Release: {release_point}")
    print(f"  Cache:   {xml_dir}")

    current_hashes = compute_title_hashes(xml_dir)
    stored_hashes = await get_usc_title_hashes()

    changed_titles = {
        title
        for title, xml_hash in current_hashes.items()
        if stored_hashes.get(title) != xml_hash
    }
    removed_titles = set(stored_hashes) - set(current_hashes)
    unchanged_count = len(set(current_hashes) - changed_titles)

    print("\nUSC title hash comparison:")
    print(f"  Changed/new titles: {len(changed_titles)}")
    print(f"  Removed titles:     {len(removed_titles)}")
    print(f"  Unchanged titles:   {unchanged_count}")

    if not changed_titles and not removed_titles:
        await set_metadata("usc_release_point", release_point)
        await set_metadata("last_usc_update", datetime.now().isoformat())
        if limit is None:
            _prune_usc_xml_cache(xml_dir)
        print("\nNo title XML changes detected. Metadata updated.")
        return

    if removed_titles:
        print("\nRemoving titles no longer present in the USC XML release...")
        for title in sorted(removed_titles):
            sqlite_deleted = await clear_usc_title(title)
            chroma_deleted = await delete_documents_by_source_and_title("usc", title)
            await delete_usc_title_hash(title)
            print(f"  Title {title}: {sqlite_deleted:,} SQLite rows, {chroma_deleted:,} Chroma docs deleted")

    if changed_titles:
        print("\nParsing changed/new USC titles and comparing section hashes...")
        parsed_by_title: dict[str, dict[str, dict]] = {title: {} for title in changed_titles}
        for section in parse_usc_xml(xml_dir, limit=limit, titles=changed_titles):
            section["content_hash"] = get_usc_section_content_hash(section)
            parsed_by_title.setdefault(section["title"], {})[section["section"]] = section

        sections_to_index: list[dict] = []
        total_changed_sections = 0
        total_new_sections = 0
        total_removed_sections = 0
        total_unchanged_sections = 0

        for title in sorted(changed_titles):
            current_sections = parsed_by_title.get(title, {})
            existing_sections = await get_usc_sections_for_title(title)
            existing_hashes = {
                section: row.get("content_hash") or get_usc_section_content_hash(row)
                for section, row in existing_sections.items()
            }

            new_sections = []
            changed_sections = []
            unchanged_hashes: dict[str, str] = {}

            for section_num, section in current_sections.items():
                old_hash = existing_hashes.get(section_num)
                if old_hash is None:
                    new_sections.append(section)
                elif old_hash != section["content_hash"]:
                    changed_sections.append(section)
                else:
                    unchanged_hashes[section_num] = section["content_hash"]

            removed_sections = sorted(set(existing_sections) - set(current_sections))
            if limit is not None:
                # A limited parse is a partial test run; do not treat unseen
                # sections as removed.
                removed_sections = []

            if removed_sections:
                removed_doc_ids = [f"usc-{title}-{section}" for section in removed_sections]
                sqlite_deleted = await delete_usc_sections(title, removed_sections)
                await delete_documents(removed_doc_ids)
                total_removed_sections += sqlite_deleted

            if unchanged_hashes:
                await set_usc_section_hashes(title, unchanged_hashes)
                total_unchanged_sections += len(unchanged_hashes)

            sections_to_index.extend(new_sections)
            sections_to_index.extend(changed_sections)
            total_new_sections += len(new_sections)
            total_changed_sections += len(changed_sections)

            print(
                f"  Title {title}: "
                f"{len(new_sections):,} new, "
                f"{len(changed_sections):,} changed, "
                f"{len(removed_sections):,} removed, "
                f"{len(unchanged_hashes):,} unchanged"
            )

        print("\nUSC section hash comparison:")
        print(f"  New sections:       {total_new_sections:,}")
        print(f"  Changed sections:   {total_changed_sections:,}")
        print(f"  Removed sections:   {total_removed_sections:,}")
        print(f"  Unchanged sections: {total_unchanged_sections:,}")

        if sections_to_index:
            print("\nIndexing new/changed USC sections...")
            stats = await _update_database(
                xml_dir,
                force_rebuild=False,
                sections=sections_to_index,
            )
        else:
            stats = {
                "total": 0,
                "processed": 0,
                "added": 0,
                "updated": 0,
                "skipped": 0,
                "errors": 0,
                "recovered": 0,
                "duration": "0:00:00",
            }
            print("\nNo indexed section text changes detected; embeddings skipped.")

        print(f"\nIndexing complete:")
        print(f"  Total sections: {stats['total']:,}")
        print(f"  Added:          {stats['added']:,}")
        print(f"  Updated:        {stats['updated']:,}")
        print(f"  Skipped:        {stats['skipped']:,}")
        print(f"  Errors:         {stats['errors']:,}")
        print(f"  Duration:       {stats['duration']}")

        if stats["errors"]:
            raise RuntimeError(
                f"USC title indexing completed with {stats['errors']:,} error(s); metadata was not updated."
            )

        if limit is not None:
            print("\nLimit was used for testing; release metadata and title hashes were not updated.")
            return

        for title in sorted(changed_titles):
            await set_usc_title_hash(title, current_hashes[title], release_point)

    await set_metadata("usc_release_point", release_point)
    await set_metadata("last_usc_update", datetime.now().isoformat())
    _prune_usc_xml_cache(xml_dir)
    print(f"\nSaved metadata. Release: {release_point}")


async def _run_rebuild_db(limit: int | None = None):
    from datetime import datetime

    from legal_mcp.storage import (
        clear_sections,
        clear_usc_title_hashes,
        delete_metadata,
        delete_documents_by_source,
        get_metadata,
        initialize_chroma,
        initialize_sqlite,
        set_metadata,
        set_usc_title_hash,
    )
    from legal_mcp.data.usc_parser import (
        get_usc_release_cache_dir,
        get_usc_title_hashes as compute_title_hashes,
    )

    print("Legal MCP Rebuild")
    print("=" * 50)

    print("\nInitializing databases...")
    await initialize_sqlite()
    await initialize_chroma()
    print("  SQLite:   OK")
    print("  ChromaDB: OK")

    release_point = await get_metadata("usc_release_point")
    if not release_point:
        raise RuntimeError("USC release metadata is missing. Run 'legal-mcp setup' or 'legal-mcp update-db' first.")

    xml_dir = get_usc_release_cache_dir(release_point)
    xml_files = list(xml_dir.glob("**/*.xml")) if xml_dir.exists() else []
    if not xml_files:
        raise RuntimeError(
            f"Cached USC XML not found for {release_point} at {xml_dir}. "
            "Run 'legal-mcp update-db' to download the current release."
        )

    print("\nUsing cached USC XML:")
    print(f"  Release: {release_point}")
    print(f"  Cache:   {xml_dir}")
    print(f"  Files:   {len(xml_files)} XML files")

    title_hashes = compute_title_hashes(xml_dir)

    print("\nClearing existing USC data...")
    sqlite_deleted = await clear_sections("usc_sections")
    chroma_deleted = await delete_documents_by_source("usc")
    await clear_usc_title_hashes()
    await delete_metadata("usc_release_point")
    await delete_metadata("last_usc_update")
    print(f"  SQLite USC sections: {sqlite_deleted:,} deleted")
    print(f"  ChromaDB USC docs:   {chroma_deleted:,} deleted")

    print("\nParsing and indexing USC sections from cache (this will take a while)...")
    stats = await _update_database(xml_dir, force_rebuild=True, limit=limit)

    print(f"\nIndexing complete:")
    print(f"  Total sections: {stats['total']:,}")
    print(f"  Added:          {stats['added']:,}")
    print(f"  Updated:        {stats['updated']:,}")
    print(f"  Skipped:        {stats['skipped']:,}")
    print(f"  Errors:         {stats['errors']:,}")
    print(f"  Duration:       {stats['duration']}")

    if stats["errors"]:
        raise RuntimeError(
            f"USC rebuild completed with {stats['errors']:,} error(s); metadata was not updated."
        )

    if limit is not None:
        print("\nLimit was used for testing; release metadata and title hashes were not updated.")
        return

    await set_metadata("usc_release_point", release_point)
    await set_metadata("last_usc_update", datetime.now().isoformat())
    for title, xml_hash in title_hashes.items():
        await set_usc_title_hash(title, xml_hash, release_point)
    print(f"\nSaved metadata. Release: {release_point}")
    print("Rebuild complete.")


async def _run_db_status():
    from legal_mcp.storage import initialize_sqlite, initialize_chroma, get_metadata, get_collection_info
    from legal_mcp.storage.sqlite_db import _get_connection

    await initialize_sqlite()
    await initialize_chroma()

    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as n FROM usc_sections")
    usc_count = cursor.fetchone()["n"]
    cursor.execute("SELECT COUNT(*) as n FROM cfr_sections")
    cfr_count = cursor.fetchone()["n"]

    release_point = await get_metadata("usc_release_point")
    last_update = await get_metadata("last_usc_update")
    chroma_info = await get_collection_info()

    print("Database Status")
    print("=" * 50)
    print(f"\nSQLite:")
    print(f"  USC sections: {usc_count:,}")
    print(f"  CFR sections: {cfr_count:,}")
    print(f"  Release:      {release_point or 'not initialized'}")
    print(f"  Last updated: {last_update or 'never'}")
    print(f"\nChromaDB:")
    print(f"  Documents:    {chroma_info['count']:,}")
    print(f"  Model:        {chroma_info['embedding_model']}")
    print(f"  Persist dir:  {chroma_info['persist_directory']}")


def setup(args):
    import asyncio
    asyncio.run(_run_setup(
        force=getattr(args, "force", False),
        limit=getattr(args, "limit", None),
    ))


def update_db(args):
    import asyncio
    asyncio.run(_run_update_db(
        force=args.force,
        rebuild=args.rebuild,
        limit=getattr(args, "limit", None),
    ))


def db_status(args):
    import asyncio
    asyncio.run(_run_db_status())


def serve(args):
    from legal_mcp.server import mcp

    if args.transport == "stdio":
        mcp.run(transport="stdio", show_banner=False)
    elif args.transport == "streamable-http":
        mcp.run(transport="streamable-http", port=args.port, show_banner=False)
    else:
        print(f"Unknown transport: {args.transport}")
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Legal MCP - Federal legal research tools for Claude Code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    setup_parser = subparsers.add_parser("setup", help="Download USC XML and populate empty databases")
    setup_parser.add_argument("--limit", type=int, help="Cap sections for testing (e.g. --limit 1000)")

    update_parser = subparsers.add_parser("update-db", help="Download updates and index changed USC sections")
    update_parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild databases from cached USC XML without downloading",
    )
    update_parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-download, clear existing USC data, and rewrite databases",
    )
    update_parser.add_argument("--limit", type=int, help="Cap sections for testing")

    subparsers.add_parser("db-status", help="Show database status")

    serve_parser = subparsers.add_parser("serve", help="Start MCP server")
    serve_parser.add_argument("--transport", default="stdio", choices=["stdio", "streamable-http"])
    serve_parser.add_argument("--port", type=int, default=8000, help="Port for HTTP transport")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        raise SystemExit(1)

    if args.command == "setup":
        setup(args)
    elif args.command == "update-db":
        update_db(args)
    elif args.command == "db-status":
        db_status(args)
    elif args.command == "serve":
        serve(args)
    else:
        print(f"Unknown command: {args.command}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
