"""
sec_10kq_parser.py
──────────────────
Stage 2-5 of the 10-K / 10-Q pipeline.

Downloads raw HTML from a filing URL, parses it with sec-parser
into a semantic tree, and extracts target sections as clean text.

Includes a TOC-based fallback for filings where sec-parser cannot
identify a section.
"""

import re
import time
import logging
import warnings
import requests
from bs4 import BeautifulSoup

try:
    import sec_parser as sp
    HAS_SEC_PARSER = True
except ImportError:
    HAS_SEC_PARSER = False
    print("[WARN] sec-parser not installed. Only TOC fallback will be used.")

import sys
import os
# Ensure parent directory is in path so we can import const
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from const import HEADERS

logger = logging.getLogger(__name__)

# SEC rate-limit safe delay
REQUEST_DELAY = 0.15


# ============================================================
# Section Mapping: which Items to target per form type
# ============================================================

# sec-parser's TopSectionTitle text is often heavily truncated.
# Real examples from MSFT 10-Q:
#   "Item 1", "Item 2", "Item 1, 1A", "ITEM 1A. RI", "ITEM 4. CONTROLS"
# We need patterns flexible enough to match these truncated forms.

# For 10-Q:
#   PART I  > Item 1 = Financial Statements (contains notes)
#   PART I  > Item 2 = MD&A
#   PART II > Item 1A = Risk Factors
#
# For 10-K:
#   PART I  > Item 1  = Business
#   PART I  > Item 1A = Risk Factors
#   PART I  > Item 7  = MD&A
#   PART II > Item 8  = Financial Statements (contains notes)

# We define lookup configs that specify:
#   - which PART to look in
#   - which Item pattern(s) to match

SECTION_LOOKUP_10K = {
    "business": {
        "part_pattern": r"PART\s*I\b",
        "item_patterns": [
            r"^item\s*1\s*$",                          # exact "Item 1"
            r"^item\s*1[.\s]",                          # "Item 1." or "Item 1 "
            r"item\s*1[.\s]*bus",                       # "Item 1. Bus..."
        ],
        "exclude_patterns": [r"1a", r"1b"],             # don't match 1A, 1B
    },
    "risk_factors": {
        "part_pattern": r"PART\s*I\b",
        "item_patterns": [
            r"item\s*1\s*a",                            # "Item 1A" or "Item 1a"
            r"item\s*1,\s*1\s*a",                       # "Item 1, 1A"  (combined TOC)
            r"item\s*1a[.\s]*ri",                       # "ITEM 1A. RI..." (truncated)
            r"risk\s*factors",
        ],
    },
    "mda": {
        "part_pattern": r"PART\s*(I\b|II\b)",
        "item_patterns": [
            r"^item\s*7\s*$",
            r"^item\s*7[.\s]",
            r"item\s*7[.\s]*man",
            r"management.{0,5}s?\s+discussion",
        ],
        "exclude_patterns": [r"7a"],
    },
}

SECTION_LOOKUP_10Q = {
    "risk_factors": {
        "part_pattern": r"PART\s*II\b",
        "item_patterns": [
            r"item\s*1\s*a",
            r"item\s*1,\s*1\s*a",
            r"item\s*1a[.\s]*ri",
            r"risk\s*factors",
        ],
    },
    "mda": {
        "part_pattern": r"PART\s*I\b",
        "item_patterns": [
            r"^item\s*2\s*$",
            r"^item\s*2[.\s]",
            r"item\s*2[.\s]*man",
            r"management.{0,5}s?\s+discussion",
        ],
        "exclude_patterns": [r"2a"],
    },
}


# ============================================================
# Document Fetching
# ============================================================

def fetch_document_html(url: str) -> str | None:
    """Download the raw HTML of a 10-K / 10-Q filing."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=60)
        resp.raise_for_status()
        time.sleep(REQUEST_DELAY)
        return resp.text
    except Exception as e:
        logger.error(f"Failed to download {url}: {e}")
        return None


# ============================================================
# sec-parser Tree Helpers
# ============================================================

def _get_semantic_type(node) -> str:
    """Get the semantic element type name from a TreeNode."""
    if hasattr(node, "semantic_element"):
        return type(node.semantic_element).__name__
    return type(node).__name__


def _collect_node_text(node) -> str:
    """Recursively collect all text from a tree node and its children."""
    parts = []
    if hasattr(node, "text") and node.text:
        parts.append(node.text.strip())
    if hasattr(node, "children"):
        for child in node.children:
            parts.append(_collect_node_text(child))
    return "\n".join(p for p in parts if p)


def _build_tree(html: str):
    """Parse HTML with sec-parser and return the semantic tree."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore")
        elements = sp.Edgar10QParser().parse(html)
        tree = sp.TreeBuilder().build(elements)
    return tree


# ============================================================
# sec-parser Section Extraction (Primary Strategy)
# ============================================================

def _find_part_node(tree, part_pattern: str):
    """
    Find the PART-level TopSectionTitle node (e.g., PART I, PART II)
    at the top level of the tree.
    """
    for node in tree:
        stype = _get_semantic_type(node)
        if stype == "TopSectionTitle":
            text = node.text.strip() if hasattr(node, "text") else ""
            if re.search(part_pattern, text, re.IGNORECASE):
                return node
    return None


def _find_item_in_children(parent_node, item_patterns: list[str],
                            exclude_patterns: list[str] = None) -> str | None:
    """
    Search a PART node's direct children for the matching Item section.
    Returns the full text of that section (node + descendants).
    
    Some filings combine items like "Item 1, 1A" in a single TOC entry.
    If we match such a combined node, we try to find the specific sub-item
    among its children first.
    """
    if not hasattr(parent_node, "children"):
        return None

    for child in parent_node.children:
        stype = _get_semantic_type(child)
        if stype != "TopSectionTitle":
            continue

        child_text = child.text.strip() if hasattr(child, "text") else ""

        # Check exclude patterns first
        if exclude_patterns:
            excluded = any(re.search(ep, child_text, re.IGNORECASE) for ep in exclude_patterns)
            if excluded:
                continue

        # Check if any item pattern matches
        matched = any(re.search(p, child_text, re.IGNORECASE) for p in item_patterns)
        if matched:
            return _collect_node_text(child)

    return None


def _extract_section(tree, lookup_config: dict) -> str | None:
    """
    Extract a section from the tree using a lookup config dict.
    """
    part_pattern = lookup_config.get("part_pattern", "") # section의 제목이 PART 이렇게 시작하는 부분의 section 이름을 가져온다.
    item_patterns = lookup_config.get("item_patterns", [])
    exclude_patterns = lookup_config.get("exclude_patterns", [])

    # SEC filings can split PART I into multiple matches (e.g., PART I, PART I (continued))
    # Try both specific PART and fallback to any PART
    parts_to_try = [part_pattern]

    for pp in parts_to_try:
        part_node = _find_part_node(tree, pp)
        if part_node:
            result = _find_item_in_children(part_node, item_patterns, exclude_patterns)
            if result:
                return result

    # Fallback: search ALL top-level nodes and their children (some filings
    # don't have a proper PART structure)
    for node in tree:
        if hasattr(node, "children") and node.children:
            result = _find_item_in_children(node, item_patterns, exclude_patterns)
            if result:
                return result

    return None


def _extract_all_notes_from_tree(tree) -> dict:
    """
    Find every numbered note (NOTE 1, NOTE 2, etc.) anywhere in the tree
    and return its full text.

    Notes can appear as:
    - TitleElement children under Item 1 (10-Q) or Item 8 (10-K)
    - Sometimes nested under a TextElement that starts with "NOTES TO..."
    """
    extracted = {}

    def _scan_for_notes(nodes):
        for node in nodes:
            stype = _get_semantic_type(node)
            node_text = node.text.strip() if hasattr(node, "text") else ""

            # Match "Note 1 — Title", "Note 1. Title", "1. Title", or "1 — Title".
            # Some filers (e.g. BE) drop the "Note" word and just number the entries.
            if stype == "TitleElement" and re.match(
                r"(note\s*)?\d+\s*[.\-–—:)]", node_text, re.IGNORECASE
            ):
                key = re.sub(r"[^a-z0-9]+", "_", node_text.lower()).strip("_")
                if len(key) > 60:
                    key = key[:60]
                extracted[key] = _collect_node_text(node)

            if hasattr(node, "children") and node.children:
                _scan_for_notes(node.children)

    _scan_for_notes(tree)
    return extracted


def extract_sections_secparser(html: str, form_type: str) -> dict:
    """
    Parse filing HTML with sec-parser and extract target sections.

    Args:
        html:      Raw HTML string of the filing.
        form_type: "10-K" or "10-Q".

    Returns:
        Dict with section keys → extracted text (or None).
    """
    if not HAS_SEC_PARSER:
        return {}

    section_lookup = SECTION_LOOKUP_10K if form_type == "10-K" else SECTION_LOOKUP_10Q

    try:
        tree = _build_tree(html)
    except Exception as e:
        logger.error(f"sec-parser failed to parse document: {e}")
        return {}

    sections = {}

    # Extract named sections (business, risk_factors, mda)
    for section_key, config in section_lookup.items():
        try:
            text = _extract_section(tree, config) # 여기에서 business, risk_factors, mda의 section을 추출한다.
            sections[section_key] = text
        except Exception as e:
            logger.warning(f"Failed to extract {section_key} via sec-parser: {e}")
            sections[section_key] = None

    # Extract all numbered financial notes
    try:
        notes = _extract_all_notes_from_tree(tree)
        sections["financial_notes"] = notes if notes else None
    except Exception as e:
        logger.warning(f"Failed to extract financial_notes via sec-parser: {e}")
        sections["financial_notes"] = None

    return sections


# ============================================================
# Unified Extraction Entry Point
# ============================================================

def extract_filing_sections(html: str, form_type: str) -> dict:
    """
    Extract target sections from a 10-K or 10-Q HTML filing.
    Uses sec-parser as primary strategy, with TOC fallback.

    Args:
        html:      Raw HTML string.
        form_type: "10-K" or "10-Q".

    Returns:
        Dict of section_key -> extracted text (str or dict for notes).
        Missing sections are None.
    """
    # Expected keys depend on form type
    if form_type == "10-K":
        expected_keys = {"business", "risk_factors", "mda", "financial_notes"}
    else:
        expected_keys = {"risk_factors", "mda", "financial_notes"}

    # --- Primary: sec-parser ---
    sections = extract_sections_secparser(html, form_type)

    # --- Fallback: fill in any missing sections via TOC ---
    missing = [k for k in expected_keys if k not in sections or sections.get(k) is None]
    # Don't try TOC fallback for financial_notes (they need structured parsing)
    missing_for_toc = [k for k in missing if k != "financial_notes"]

    if missing_for_toc:
        logger.info(f"sec-parser missed {len(missing_for_toc)} section(s), trying TOC fallback: {missing_for_toc}")
        fallback = extract_sections_toc_fallback(html, form_type)
        for k in missing_for_toc:
            if k in fallback and fallback[k]:
                sections[k] = fallback[k]

    # Ensure all expected keys exist
    for k in expected_keys:
        sections.setdefault(k, None)

    return sections


# ============================================================
# Full single-filing pipeline
# ============================================================

def parse_single_filing(filing_meta: dict) -> dict:
    """
    Given a filing metadata dict (from sec_10kq_rss),
    download, parse, and return the structured result.

    Args:
        filing_meta: Dict with keys:
            cik, form_type, filing_date, document_url, accession_number, title

    Returns:
        Dict with all metadata + extracted sections.
    """
    doc_url = filing_meta.get("document_url")
    form_type = filing_meta.get("form_type", "10-K")

    if not doc_url:
        logger.warning(f"No document URL for filing {filing_meta.get('accession_number')}")
        return {**filing_meta, "sections": None, "parse_method": None}

    print(f"    Downloading {form_type}: {doc_url}")
    html = fetch_document_html(doc_url)

    if not html:
        return {**filing_meta, "sections": None, "parse_method": "download_failed"}

    print(f"    Parsing sections ({len(html):,} chars)...")
    sections = extract_filing_sections(html, form_type)

    # Determine which method(s) succeeded
    found = [k for k, v in sections.items() if v is not None]
    print(f"    Extracted: {found}")

    return {
        **filing_meta,
        "sections": sections,
        "parse_method": "sec-parser+toc_fallback",
    }



# ============================================================
# TOC Anchor-Tracing Fallback
# ============================================================

# TOC patterns for finding sections in the HTML anchor links
TOC_PATTERNS = {
    "business": [
        r"item\s*1[.\s]*business",
        r"item\s*1[.\s]*$",
    ],
    "risk_factors": [
        r"item\s*1\s*a",
        r"risk\s*factors",
    ],
    "mda": [
        r"item\s*7[.\s]*management",
        r"item\s*2[.\s]*management",
        r"management.{0,10}discussion",
        r"item\s*7[.\s]*$",
        r"item\s*2[.\s]*$",
    ],
}


def _find_toc_anchors(soup: BeautifulSoup) -> list[tuple[str, str]]:
    """
    Scan the document for a Table of Contents and extract
    (anchor_id, title) pairs preserving order.
    """
    toc_entries = []
    seen_ids = set()

    # html anchor 태그를 찾는다
    all_links = soup.find_all("a", href=True) 

    for link in all_links:
        href = link.get("href", "")
        if href.startswith("#"):
            anchor_id = href[1:] # anchor id
            text = link.get_text(strip=True) # anchor text
            if text and len(text) > 3 and anchor_id not in seen_ids:
                toc_entries.append((anchor_id, text))
                seen_ids.add(anchor_id)

    return toc_entries


def _extract_between_anchors(soup: BeautifulSoup, start_id: str, end_id: str | None) -> str:
    """Extract all text between two anchor IDs in the document."""
    start_elem = soup.find(id=start_id) or soup.find("a", {"name": start_id})
    if not start_elem:
        return ""

    parts = []
    current = start_elem

    while current:
        current = current.find_next()
        if current is None:
            break

        # Stop at the next section
        if end_id:
            elem_id = current.get("id", "") if hasattr(current, "get") else ""
            elem_name = current.get("name", "") if hasattr(current, "get") else ""
            if elem_id == end_id or elem_name == end_id:
                break

        if hasattr(current, "get_text"):
            text = current.get_text(strip=True)
            if text:
                parts.append(text)

    return "\n".join(parts)


def extract_sections_toc_fallback(html: str, form_type: str) -> dict:
    """
    Fallback: use TOC anchor tracing to extract sections.
    Only used when sec-parser cannot find a given section.
    """
    soup = BeautifulSoup(html, "html.parser")
    toc_entries = _find_toc_anchors(soup)

    if not toc_entries:
        return {}

    # Choose appropriate patterns based on form type
    patterns_map = {}
    if form_type == "10-K":
        patterns_map = TOC_PATTERNS
    else:
        # 10-Q: no "business" section, different item numbers for mda
        patterns_map = {
            "risk_factors": TOC_PATTERNS["risk_factors"],
            "mda": TOC_PATTERNS["mda"],
        }

    sections = {}
    for section_key, patterns in patterns_map.items():
        for i, (anchor_id, title) in enumerate(toc_entries):
            matched = any(re.search(p, title, re.IGNORECASE) for p in patterns)
            if matched:
                next_id = toc_entries[i + 1][0] if i + 1 < len(toc_entries) else None
                text = _extract_between_anchors(soup, anchor_id, next_id)
                if text and len(text) > 50:  # skip trivially short matches
                    sections[section_key] = text
                break

    return sections



# ============================================================
# Quick test
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("sec_10kq_parser.py loaded successfully.")
    print(f"sec-parser available: {HAS_SEC_PARSER}")
    print(f"Target sections (10-K): {list(SECTION_LOOKUP_10K.keys())} + financial_notes")
    print(f"Target sections (10-Q): {list(SECTION_LOOKUP_10Q.keys())} + financial_notes")
    print("Financial notes: extracting all numbered notes")
