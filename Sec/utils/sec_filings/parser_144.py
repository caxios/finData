"""
Form 144 parser.

Form 144 is filed when an insider plans to sell restricted/control
securities. EDGAR's primary document for newer 144s is XML with tagged
fields; older 144s are paper-style HTML. We try the XML path first and
fall back to a tolerant text scan.
"""

import re
from xml.etree import ElementTree as ET
from bs4 import BeautifulSoup


def _xml_text(root, tag: str) -> str | None:
    """Find the first tag (any namespace) and return its stripped text."""
    for el in root.iter():
        local = el.tag.split("}", 1)[-1]
        if local.lower() == tag.lower() and el.text:
            return el.text.strip()
    return None


def parse_144(content: str) -> dict:
    """Parse Form 144. `content` may be XML or HTML."""
    stripped = content.lstrip()
    if stripped.startswith("<?xml") or stripped.startswith("<edgar"):
        return _parse_xml(content)
    return _parse_html(content)


def _parse_xml(xml: str) -> dict:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return _parse_html(xml)

    return {
        "full_text": xml,
        "issuer_name":       _xml_text(root, "issuerName"),
        "shares_to_be_sold": _xml_text(root, "noOfShares") or _xml_text(root, "amountOfSecurities"),
        "aggregate_value":   _xml_text(root, "aggregateMarketValue") or _xml_text(root, "marketValue"),
        "broker":            _xml_text(root, "brokerName") or _xml_text(root, "firmName"),
        "sale_date":         _xml_text(root, "approximateDateOfSale") or _xml_text(root, "dateOfSale"),
    }


def _grab(label: str, text: str) -> str | None:
    m = re.search(rf"{label}[^\n:]*[:\n]+\s*([^\n]{{2,120}})", text, re.IGNORECASE)
    return " ".join(m.group(1).split()) if m else None


def _parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    return {
        "full_text": text,
        "issuer_name":       _grab(r"name\s+of\s+issuer", text),
        "shares_to_be_sold": _grab(r"number\s+of\s+shares|amount\s+of\s+securities", text),
        "aggregate_value":   _grab(r"aggregate\s+market\s+value", text),
        "broker":            _grab(r"name\s+(?:and\s+address\s+)?of\s+broker", text),
        "sale_date":         _grab(r"approximate\s+date\s+of\s+sale", text),
    }
