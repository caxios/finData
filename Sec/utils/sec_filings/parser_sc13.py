"""
SC 13D / SC 13G parser.

These filings disclose beneficial ownership. The cover page contains a
short, predictable set of fields (name of reporting person, aggregate
shares, percent of class). We extract those by regex from plain text and
keep the full text as a fallback for the UI.
"""

import re
from bs4 import BeautifulSoup


def _first_match(patterns: list[str], text: str) -> str | None:
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE | re.DOTALL)
        if m:
            return " ".join(m.group(1).split())[:200]
    return None


def parse_sc13(html: str) -> dict:
    """Parse SC 13D/G HTML into structured cover-page fields + full_text."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)

    # "Names of Reporting Persons" → next non-empty line is the name.
    owner = _first_match(
        [
            r"name(?:s)?\s+of\s+reporting\s+person[^\n]*\n+([^\n]{2,150})",
        ],
        text,
    )

    shares = _first_match(
        [
            r"aggregate\s+amount\s+beneficially\s+owned[^\n]*\n+([^\n]{2,80})",
            r"\b11[\.\s)]*aggregate[^\n]*\n+([^\n]{2,80})",
        ],
        text,
    )

    percent = _first_match(
        [
            r"percent\s+of\s+class\s+represented[^\n]*\n+([^\n]{2,30})",
            r"\b13[\.\s)]*percent[^\n]*\n+([^\n]{2,30})",
        ],
        text,
    )

    return {
        "full_text": text,
        "beneficial_owner": owner,
        "shares_owned": shares,
        "percent_owned": percent,
    }
