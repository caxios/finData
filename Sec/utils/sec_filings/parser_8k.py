"""
8-K parser.

8-Ks are event-driven filings organized by numbered "Items" (e.g. Item 1.01,
Item 2.02, Item 5.02). We split the body on those headers and return a list
of {code, title, text} blocks.
"""

import re
from bs4 import BeautifulSoup

# Matches "Item 1.01" / "ITEM 1.01" / "Item 1.01." optionally followed by a title.
ITEM_PATTERN = re.compile(
    r"(?im)^\s*item\s+(\d+\.\d{2})\s*[\.\-:]?\s*(.*)$"
)


def parse_8k(html: str) -> dict:
    """Parse 8-K HTML into {full_text, items: [{code, title, text}]}."""
    soup = BeautifulSoup(html, "html.parser")
    full_text = soup.get_text("\n", strip=True)

    matches = list(ITEM_PATTERN.finditer(full_text))
    items: list[dict] = []
    for i, m in enumerate(matches):
        code = m.group(1)
        title = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        body = full_text[start:end].strip()
        # Skip TOC-style hits where the "body" is just the next item header.
        if len(body) < 30:
            continue
        items.append({"code": code, "title": title, "text": body})

    # De-dupe consecutive entries with the same code (TOC + actual body) —
    # keep the longer body.
    deduped: dict[str, dict] = {}
    for it in items:
        prev = deduped.get(it["code"])
        if prev is None or len(it["text"]) > len(prev["text"]):
            deduped[it["code"]] = it
    items = sorted(deduped.values(), key=lambda x: tuple(int(p) for p in x["code"].split(".")))

    return {"full_text": full_text, "items": items}
