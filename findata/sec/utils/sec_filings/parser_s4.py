from findata.core.config import SEC_DB_DIR, DART_CACHE_DIR
"""
S-4 parser.

S-4 is the merger/acquisition prospectus. It's structurally similar to a
10-K (sec-parser handles it via Edgar10QParser), with sections like
"Summary", "Risk Factors", "The Merger", "The Merger Agreement".

We reuse sec-parser's TopSectionTitle traversal but with section keys
specific to S-4. Anything we can't identify lands in `full_text`.
"""

import re
import warnings
from bs4 import BeautifulSoup

try:
    import sec_parser as sp
    HAS_SEC_PARSER = True
except ImportError:
    HAS_SEC_PARSER = False


SECTION_PATTERNS = {
    "summary":          [r"\bsummary\b"],
    "risk_factors":     [r"risk\s*factors"],
    "the_merger":       [r"the\s+merger\b(?!\s+agreement)"],
    "merger_agreement": [r"the\s+merger\s+agreement"],
    "voting":           [r"the\s+special\s+meeting", r"voting\s+and\s+proxies"],
}


def _node_text(node) -> str:
    parts = []
    if hasattr(node, "text") and node.text:
        parts.append(node.text.strip())
    if hasattr(node, "children"):
        for c in node.children:
            parts.append(_node_text(c))
    return "\n".join(p for p in parts if p)


def _scan_tree(tree, patterns: list[str]) -> str | None:
    for node in tree:
        if hasattr(node, "children"):
            stype = type(getattr(node, "semantic_element", node)).__name__
            text = node.text.strip() if hasattr(node, "text") else ""
            if stype in ("TitleElement", "TopSectionTitle"):
                for p in patterns:
                    if re.search(p, text, re.IGNORECASE):
                        return _node_text(node)
            found = _scan_tree(node.children, patterns)
            if found:
                return found
    return None


def parse_s4(html: str) -> dict:
    """Parse an S-4 HTML filing into {full_text, sections: {name: text}}."""
    soup = BeautifulSoup(html, "html.parser")
    full_text = soup.get_text("\n", strip=True)

    sections: dict[str, str] = {}
    if HAS_SEC_PARSER:
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore")
                elements = sp.Edgar10QParser().parse(html)
                tree = sp.TreeBuilder().build(elements)
            for key, patterns in SECTION_PATTERNS.items():
                text = _scan_tree(tree, patterns)
                if text and len(text) > 100:
                    sections[key] = text
        except Exception as e:
            print(f"  [WARN] sec-parser failed on S-4: {e}")

    return {"full_text": full_text, "sections": sections}
