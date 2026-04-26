"""US Code XML parser - downloads and parses USC XML from house.gov.

Data source: https://uscode.house.gov/download/download.shtml
Format: XML with USLM (United States Legislative Markup) schema
"""

import re
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Iterator

import requests
from bs4 import BeautifulSoup


# Download URL and local cache
DOWNLOAD_PAGE = "https://uscode.house.gov/download/download.shtml"
CACHE_DIR = Path.home() / ".cache" / "legal-mcp" / "usc-xml"


def get_current_usc_release() -> tuple[str, str]:
    """
    Fetch current USC release point from download page.

    Uses multiple fallback strategies for resilience:
    1. Primary: <h3 class="releasepointinformation">
    2. Fallback: Regex for "Public Law XXX-XXX"
    3. Fallback: Find bulk XML link and extract from URL

    Returns:
        (release_point, bulk_xml_url)
        e.g., ("Public Law 119-84 (04/18/2026)",
               "https://uscode.house.gov/download/releasepoints/us/pl/119/84/xml_uscAll@119-84.zip")

    Raises:
        ValueError: If release point cannot be determined
    """
    try:
        response = requests.get(DOWNLOAD_PAGE, timeout=10)
        response.raise_for_status()
        html = response.text
        soup = BeautifulSoup(html, 'html.parser')

        # Strategy 1: Primary - Look for <h3 class="releasepointinformation">
        release_tag = soup.find('h3', class_='releasepointinformation')
        release_point = None
        if release_tag:
            release_point = release_tag.get_text(strip=True)
            sys.stderr.write(f"[OK] Found release point via primary method: {release_point}\n")

        # Strategy 2: Fallback - Regex search for "Public Law XXX-XXX"
        if not release_point:
            pattern = r'Public Law \d+-\d+\s*\(\d{2}/\d{2}/\d{4}\)'
            match = re.search(pattern, html)
            if match:
                release_point = match.group(0)
                sys.stderr.write(f"[WARN] Found release point via regex fallback: {release_point}\n")

        # Strategy 3: Find bulk XML download link
        bulk_xml_url = None

        # Look for link with title containing "All USC Titles in XML"
        xml_link = soup.find('a', title=re.compile(r'All USC Titles in XML', re.IGNORECASE))
        if xml_link and xml_link.get('href'):
            href = xml_link['href']
            # Make absolute URL if needed
            if href.startswith('http'):
                bulk_xml_url = href
            else:
                bulk_xml_url = f"https://uscode.house.gov/download/{href}"
            sys.stderr.write(f"[OK] Found bulk XML URL: {bulk_xml_url}\n")

        # Strategy 4: Fallback - Look for href containing "xml_uscAll"
        if not bulk_xml_url:
            for link in soup.find_all('a', href=True):
                if 'xml_uscAll' in link['href']:
                    href = link['href']
                    if href.startswith('http'):
                        bulk_xml_url = href
                    else:
                        bulk_xml_url = f"https://uscode.house.gov/download/{href}"
                    sys.stderr.write(f"[WARN] Found bulk XML URL via fallback: {bulk_xml_url}\n")
                    break

        # Strategy 5: Last resort - Extract release from URL if we have it
        if not release_point and bulk_xml_url:
            # Extract from URL like "releasepoints/us/pl/119/84/xml_uscAll@119-84.zip"
            url_match = re.search(r'/pl/(\d+)/(\d+)/', bulk_xml_url)
            if url_match:
                congress, law = url_match.groups()
                release_point = f"Public Law {congress}-{law}"
                sys.stderr.write(f"[WARN] Extracted release point from URL: {release_point}\n")

        # Validation
        if not release_point:
            raise ValueError("Could not determine USC release point from download page")
        if not bulk_xml_url:
            raise ValueError("Could not find bulk XML download URL")

        return (release_point, bulk_xml_url)

    except requests.RequestException as e:
        raise ValueError(f"Failed to fetch USC download page: {e}")
    except Exception as e:
        raise ValueError(f"Error parsing USC download page: {e}")


async def download_usc_xml(
    cache_dir: Path | None = None,
    force: bool = False
) -> tuple[Path, str]:
    """
    Download US Code XML from house.gov.

    Args:
        cache_dir: Directory to cache downloads (default: ~/.cache/legal-mcp/usc-xml)
        force: If True, re-download even if cache exists

    Returns:
        (xml_dir, release_point) - Path to extracted XML files and release point string

    Raises:
        ValueError: If download or extraction fails
    """
    cache_dir = cache_dir or CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Get current release point and download URL
    sys.stderr.write("Checking USC download page...\n")
    release_point, bulk_xml_url = get_current_usc_release()

    # Sanitize release point for directory name
    # "Public Law 119-84 (04/18/2026)" -> "119-84"
    release_match = re.search(r'Public Law (\d+-\d+)', release_point)
    if release_match:
        release_dir_name = release_match.group(1)
    else:
        # Fallback: use full release point, sanitized
        release_dir_name = re.sub(r'[^\w\-]', '_', release_point)

    # Check cache - only extracted XML is persistent
    xml_dir = cache_dir / release_dir_name

    if xml_dir.exists() and not force:
        # Check if directory has XML files
        xml_files = list(xml_dir.glob("**/*.xml"))
        if xml_files:
            sys.stderr.write(f"[OK] Using cached USC XML: {xml_dir}\n")
            sys.stderr.write(f"     Release: {release_point}\n")
            sys.stderr.write(f"     Files: {len(xml_files)} XML files\n")
            return (xml_dir, release_point)
        else:
            sys.stderr.write(f"[WARN] Cache directory exists but is empty, re-downloading\n")

    # Use temporary directory for ZIP download (auto-cleanup)
    with tempfile.TemporaryDirectory(prefix="legal-mcp-download-") as temp_dir:
        zip_file = Path(temp_dir) / f"{release_dir_name}.zip"

        # Download ZIP file to temp location
        sys.stderr.write(f"Downloading USC XML...\n")
        sys.stderr.write(f"  Release: {release_point}\n")
        sys.stderr.write(f"  URL: {bulk_xml_url}\n")
        sys.stderr.write(f"  Temp download: {zip_file}\n")

        try:
            response = requests.get(bulk_xml_url, stream=True, timeout=120)
            response.raise_for_status()

            # Get file size if available
            total_size = int(response.headers.get('content-length', 0))
            total_mb = total_size / (1024 * 1024) if total_size else 0

            # Download with progress
            downloaded = 0
            chunk_size = 1024 * 1024  # 1MB chunks

            with open(zip_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size:
                            progress = (downloaded / total_size) * 100
                            sys.stderr.write(f"\r   Progress: {progress:.1f}% ({downloaded/(1024*1024):.1f}/{total_mb:.1f} MB)")
                        else:
                            sys.stderr.write(f"\r   Downloaded: {downloaded/(1024*1024):.1f} MB")

            sys.stderr.write(f"\n[OK] Download complete: {zip_file}\n")
            sys.stderr.write(f"     Size: {zip_file.stat().st_size / (1024*1024):.1f} MB\n")

        except requests.RequestException as e:
            raise ValueError(f"Failed to download USC XML: {e}")

        # Extract ZIP file to persistent cache
        sys.stderr.write(f"Extracting ZIP archive...\n")
        sys.stderr.write(f"  Target: {xml_dir}\n")
        try:
            xml_dir.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                # Get list of XML files
                xml_members = [m for m in zip_ref.namelist() if m.endswith('.xml')]
                sys.stderr.write(f"  Found {len(xml_members)} XML files in archive\n")

                # Extract all files
                zip_ref.extractall(xml_dir)

            sys.stderr.write(f"[OK] Extraction complete\n")

            # Verify extraction
            xml_files = list(xml_dir.glob("**/*.xml"))
            if not xml_files:
                raise ValueError(f"No XML files found after extraction in {xml_dir}")

            sys.stderr.write(f"[OK] Verified {len(xml_files)} XML files in cache\n")

            # ZIP file in temp_dir will be auto-cleaned when context exits
            return (xml_dir, release_point)

        except zipfile.BadZipFile as e:
            raise ValueError(f"Downloaded file is not a valid ZIP archive: {e}")
        except Exception as e:
            raise ValueError(f"Failed to extract USC XML: {e}")


def parse_usc_xml(xml_dir: Path, limit: int | None = None) -> Iterator[dict]:
    """
    Parse USC XML files into structured sections.

    Args:
        xml_dir: Directory containing USC XML files
        limit: Maximum number of sections to parse (for testing)

    Yields:
        Section dicts with structure:
        {
            "title": "42",
            "section": "1983",
            "heading": "Civil action for deprivation of rights",
            "text": "Full text content...",
            "chapter": "21",
            "subchapter": None,
        }
    """
    from lxml import etree

    # USLM namespace
    ns = {'uslm': 'http://xml.house.gov/schemas/uslm/1.0'}

    # Find all XML files
    xml_files = sorted(xml_dir.glob("*.xml"))
    if not xml_files:
        raise ValueError(f"No XML files found in {xml_dir}")

    sys.stderr.write(f"Parsing {len(xml_files)} USC title files...\n")

    total_sections = 0

    for xml_file in xml_files:
        try:
            # Parse XML file
            tree = etree.parse(str(xml_file))
            root = tree.getroot()

            # Extract title number from <title> element
            title_elem = root.find('.//uslm:title', ns)
            if title_elem is None:
                sys.stderr.write(f"[WARN] No title element in {xml_file.name}, skipping\n")
                continue

            title_num_elem = title_elem.find('./uslm:num', ns)
            if title_num_elem is None or not title_num_elem.get('value'):
                sys.stderr.write(f"[WARN] No title number in {xml_file.name}, skipping\n")
                continue

            title_num = title_num_elem.get('value')

            # Find all sections
            sections = root.findall('.//uslm:section', ns)
            file_section_count = 0

            for section_elem in sections:
                # Extract section number
                num_elem = section_elem.find('./uslm:num', ns)
                if num_elem is None or not num_elem.get('value'):
                    continue

                section_num = num_elem.get('value')

                # Extract heading
                heading_elem = section_elem.find('./uslm:heading', ns)
                heading = heading_elem.text.strip() if heading_elem is not None and heading_elem.text else ""

                # Extract text content from <content><p> elements
                content_elem = section_elem.find('./uslm:content', ns)
                text_parts = []
                if content_elem is not None:
                    # Get all <p> elements
                    for p_elem in content_elem.findall('.//uslm:p', ns):
                        # Get all text including nested elements
                        p_text = ''.join(p_elem.itertext())
                        if p_text.strip():
                            text_parts.append(p_text.strip())

                text = '\n\n'.join(text_parts)

                # Extract miscellaneous notes (substantive statutory provisions)
                notes_parts = []
                notes_elem = section_elem.find('./uslm:notes', ns)
                if notes_elem is not None:
                    # Only capture topic="miscellaneous" notes (skip editorial, amendments, etc.)
                    for note_elem in notes_elem.findall('.//uslm:note[@topic="miscellaneous"]', ns):
                        note_text = ''.join(note_elem.itertext())
                        if note_text.strip():
                            notes_parts.append(note_text.strip())

                notes = '\n\n'.join(notes_parts) if notes_parts else None

                # Find parent chapter
                chapter_num = None
                parent = section_elem.getparent()
                while parent is not None:
                    if parent.tag == f'{{{ns["uslm"]}}}chapter':
                        chapter_num_elem = parent.find('./uslm:num', ns)
                        if chapter_num_elem is not None and chapter_num_elem.get('value'):
                            chapter_num = chapter_num_elem.get('value')
                        break
                    parent = parent.getparent()

                # Find parent subchapter (optional)
                subchapter_num = None
                parent = section_elem.getparent()
                while parent is not None:
                    if parent.tag == f'{{{ns["uslm"]}}}subchapter':
                        subchapter_num_elem = parent.find('./uslm:num', ns)
                        if subchapter_num_elem is not None and subchapter_num_elem.get('value'):
                            subchapter_num = subchapter_num_elem.get('value')
                        break
                    parent = parent.getparent()

                # Yield section dict
                yield {
                    'title': title_num,
                    'section': section_num,
                    'heading': heading,
                    'text': text,
                    'chapter': chapter_num,
                    'subchapter': subchapter_num,
                    'notes': notes,
                }

                file_section_count += 1
                total_sections += 1

                # Check limit
                if limit and total_sections >= limit:
                    sys.stderr.write(f"[OK] Reached limit of {limit} sections\n")
                    return

            sys.stderr.write(f"  {xml_file.name}: {file_section_count} sections\n")

        except Exception as e:
            sys.stderr.write(f"[WARN] Error parsing {xml_file.name}: {e}\n")
            continue

    sys.stderr.write(f"[OK] Parsed {total_sections} total sections from {len(xml_files)} files\n")


def check_for_updates(stored_release: str | None = None) -> tuple[bool, str, str]:
    """
    Check if USC XML has been updated.

    Args:
        stored_release: Previously stored release point (e.g., "Public Law 119-83")

    Returns:
        (has_update, current_release, stored_release)

    Example:
        >>> check_for_updates("Public Law 119-83")
        (True, "Public Law 119-84 (04/18/2026)", "Public Law 119-83")
    """
    try:
        current_release, _ = get_current_usc_release()

        if not stored_release:
            # No stored release, treat as update available
            return (True, current_release, stored_release or "Not initialized")

        # Normalize for comparison (strip dates if present)
        def normalize_release(release: str) -> str:
            # Extract just "Public Law XXX-XXX" part
            match = re.search(r'Public Law \d+-\d+', release)
            return match.group(0) if match else release

        current_normalized = normalize_release(current_release)
        stored_normalized = normalize_release(stored_release)

        has_update = current_normalized != stored_normalized

        return (has_update, current_release, stored_release)

    except Exception as e:
        sys.stderr.write(f"[WARN] Error checking for updates: {e}\n")
        # On error, assume no update to avoid blocking
        return (False, stored_release or "Unknown", stored_release or "Unknown")
