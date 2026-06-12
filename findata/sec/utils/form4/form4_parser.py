from findata.core.config import SEC_DB_DIR, DART_CACHE_DIR
import re
import requests
import xml.etree.ElementTree as ET
from sec_cik_mapper import StockMapper
import yfinance as yf

HEADERS = {
    "User-Agent": "YourName your.email@example.com",  # Replace with real info
    "Accept-Encoding": "gzip, deflate",
}
mapper = StockMapper()


def _index_to_txt_url(index_url: str) -> str:
    """Convert -index.htm URL to the full submission .txt URL."""
    # e.g. .../0001193125-26-162571-index.htm -> .../0001193125-26-162571.txt
    return re.sub(r"-index\.htm$", ".txt", index_url, flags=re.IGNORECASE)


def _get_text(elem, tag: str) -> str:
    child = elem.find(tag)
    return child.text.strip() if child is not None and child.text else ""


def _get_value(elem, path: str) -> str:
    """Read the <value> child under a nested path (e.g. 'transactionDate')."""
    if elem is None:
        return ""
    target = elem.find(path)
    if target is None:
        return ""
    return _get_text(target, "value")


_TRANSACTION_CODE_DESC = {
    "P": "Open market or private purchase of non-derivative or derivative security",
    "S": "Open market or private sale of non-derivative or derivative security",
    "V": "Transaction voluntarily reported earlier than required",
    "A": "Grant, award or other acquisition pursuant to Rule 16b-3(d)",
    "D": "Disposition to the issuer of issuer equity securities pursuant to Rule 16b-3(e)",
    "F": "Payment of exercise price or tax liability by delivering or withholding securities incident to the receipt, exercise or vesting of a security issued in accordance with Rule 16b-3",
    "I": "Discretionary transaction in accordance with Rule 16b-3(f) resulting in acquisition or disposition of issuer securities",
    "M": "Exercise or conversion of derivative security exempted pursuant to Rule 16b-3",
    "C": "Conversion of derivative security",
    "E": "Expiration of short derivative position",
    "H": "Expiration (or cancellation) of long derivative position with value received",
    "O": "Exercise of out-of-the-money derivative security",
    "X": "Exercise of in-the-money or at-the-money derivative security",
    "G": "Bona fide gift",
    "L": "Small acquisition under Rule 16a-6",
    "W": "Acquisition or disposition by will or laws of descent and distribution",
    "Z": "Deposit into or withdrawal from voting trust",
    "J": "Other acquisition or disposition (describe transaction)",
    "K": "Transaction in equity swap or instrument with similar characteristics",
    "U": "Disposition pursuant to a tender of shares in a change of control transaction",
}


_ROW_SOURCES = [
    ("nonDerivativeTable/nonDerivativeTransaction", "nonDerivativeTransaction", "non-derivative"),
    ("nonDerivativeTable/nonDerivativeHolding",     "nonDerivativeHolding",     "non-derivative"),
    ("derivativeTable/derivativeTransaction",       "derivativeTransaction",    "derivative"),
    ("derivativeTable/derivativeHolding",           "derivativeHolding",        "derivative"),
]


def _extract_row(elem, row_type: str, security_category: str, ticker: str) -> dict:
    """Extract a single transaction/holding row in a unified shape."""
    amounts = elem.find("transactionAmounts")
    ownership = elem.find("ownershipNature")
    coding = elem.find("transactionCoding")
    transaction_code = _get_text(coding, "transactionCode") if coding is not None else ""
    transaction_code_desc = _TRANSACTION_CODE_DESC.get(transaction_code, "")
    footnote_refs = [
        fn.get("id") for fn in elem.iter("footnoteId") if fn.get("id")
    ]

    amount_str = _get_value(amounts, "transactionShares") # 거래 수량
    amount = float(amount_str) if amount_str else 0.0 # 거래수량

    # price = yf.Ticker(ticker).history(period="1d")["Close"].iloc[-1] # 최신가격
    # market_cap = yf.Ticker(ticker).info["marketCap"] if yf.Ticker(ticker).info["marketCap"] is not None else 0
    price = 0
    market_cap = 0

    post_amounts = elem.find("postTransactionAmounts")
    shares_after_str = _get_value(post_amounts, "sharesOwnedFollowingTransaction") if post_amounts is not None else ""
    shares_after = float(shares_after_str) if shares_after_str else 0.0

    a_or_d = _get_value(amounts, "transactionAcquiredDisposedCode")

    if a_or_d == 'D':
        # 매도 비중
        ratio = amount / (shares_after + amount) if (shares_after + amount) > 0 else 0
    elif a_or_d == 'A':
        # 매수 비중 (기존 보유량이 0이었다면 신규 진입이므로 100%로 처리)
        before_shares = shares_after - amount
        ratio = amount / before_shares if before_shares > 0 else 1.0 
    else:
        ratio = 0

    return {
        "row_type":              row_type,
        "security_category":     security_category,
        "security_title":        _get_value(elem, "securityTitle"),
        "transaction_date":      _get_value(elem, "transactionDate"),
        "transaction_code":            transaction_code,
        "transaction_code_description": transaction_code_desc,
        "amount":                _get_value(amounts, "transactionShares"),
        "acquired_or_disposed":  _get_value(amounts, "transactionAcquiredDisposedCode"),
        "price_per_share":       _get_value(amounts, "transactionPricePerShare"),
        "shares_owned_after":    _get_value(elem.find("postTransactionAmounts"),
                                            "sharesOwnedFollowingTransaction")
                                    if elem.find("postTransactionAmounts") is not None else "",
        "ownership_form":        _get_value(ownership, "directOrIndirectOwnership"),
        "nature_of_ownership":   _get_value(ownership, "natureOfOwnership"),
        # "footnote_refs":         footnote_refs,
        "trade_ratio_pct":       round(ratio * 100, 2),
        "transaction_value":     round(float(_get_value(amounts, "transactionPricePerShare") or 0) * float(_get_value(amounts, "transactionShares") or 0), 2),
        "market_value_after":    round(float(_get_value(elem.find("postTransactionAmounts"), "sharesOwnedFollowingTransaction") or 0) * price if elem.find("postTransactionAmounts") is not None else 0, 2),
        "market_cap":            market_cap,
        
    }


def _extract_reporting_owner(rp) -> dict:
    rp_id = rp.find("reportingOwnerId")
    rp_addr = rp.find("reportingOwnerAddress")
    rp_rel = rp.find("reportingOwnerRelationship")

    return {
        "name": _get_text(rp_id, "rptOwnerName") if rp_id is not None else "",
        # "address": {
        #     "street1": _get_text(rp_addr, "rptOwnerStreet1") if rp_addr is not None else "",
        #     "street2": _get_text(rp_addr, "rptOwnerStreet2") if rp_addr is not None else "",
        #     "city":    _get_text(rp_addr, "rptOwnerCity")    if rp_addr is not None else "",
        #     "state":   _get_text(rp_addr, "rptOwnerState")   if rp_addr is not None else "",
        #     "zip":     _get_text(rp_addr, "rptOwnerZipCode") if rp_addr is not None else "",
        # },
        "relationship": {
            "is_director":      _get_text(rp_rel, "isDirector")        if rp_rel is not None else "",
            "is_officer":       _get_text(rp_rel, "isOfficer")         if rp_rel is not None else "",
            "is_ten_pct_owner": _get_text(rp_rel, "isTenPercentOwner") if rp_rel is not None else "",
            "is_other":         _get_text(rp_rel, "isOther")           if rp_rel is not None else "",
            "officer_title":    _get_text(rp_rel, "officerTitle")      if rp_rel is not None else "",
            "other_text":       _get_text(rp_rel, "otherText")         if rp_rel is not None else "",
        },
    }


def _parse_form4_xml(xml_text: str, source_url: str = "") -> dict:
    """Parse the raw Form 4 XML string into the structured dict."""
    root = ET.fromstring(xml_text)

    issuer_elem = root.find("issuer")
    issuer = {
        "name":           _get_text(issuer_elem, "issuerName")           if issuer_elem is not None else "",
        "cik":            _get_text(issuer_elem, "issuerCik")            if issuer_elem is not None else "",
        "trading_symbol": _get_text(issuer_elem, "issuerTradingSymbol") if issuer_elem is not None else "",
    }
    tickers = mapper.cik_to_tickers.get(issuer['cik'], set())
    ticker = next(iter(tickers)) if tickers else issuer.get('trading_symbol', '')
    reporting_owners = [_extract_reporting_owner(rp) for rp in root.findall("reportingOwner")]

    transactions = []
    for xpath, row_type, category in _ROW_SOURCES:
        for elem in root.findall(xpath):
            transactions.append(_extract_row(elem, row_type, category, ticker))

    footnotes = {}
    for fn in root.findall("footnotes/footnote"):
        fn_id = fn.get("id")
        if fn_id:
            footnotes[fn_id] = (fn.text or "").strip()

    return {
        "source_url":       source_url,
        "document_type":    _get_text(root, "documentType"),
        "period_of_report": _get_text(root, "periodOfReport"),
        "issuer":           issuer,
        "reporting_owners": reporting_owners,
        "transactions":     transactions,
        # "footnotes":        footnotes,
        "ticker":                ticker,
    }


def parse_form4(index_url: str) -> dict:
    """
    Fetch a Form 4 submission and parse it into a structured dict.

    Args:
        index_url: The -index.htm URL from the SEC RSS feed.

    Returns:
        A dict with issuer, reporting_owners (list), transactions (list of all
        row types tagged by row_type), and footnotes. See plan for full shape.
    """
    txt_url = _index_to_txt_url(index_url)
    response = requests.get(txt_url, headers=HEADERS, timeout=15)
    response.raise_for_status()

    match = re.search(r"<XML>(.*?)</XML>", response.text, re.DOTALL)
    if not match:
        raise ValueError(f"No <XML> block found in {txt_url}")

    return _parse_form4_xml(match.group(1).strip(), source_url=txt_url)


def parse_all_from_rss(delay: float = 0.2) -> list:
    """
    Pull the latest Form 4 filings via fetch_form4() and parse every one.

    Args:
        delay: Seconds to sleep between requests (SEC fair-access: ≤10 req/s).

    Returns:
        List of parsed Form 4 dicts. Each dict also carries the original
        RSS metadata (title, form_type, updated) under 'rss_meta'.
    """
    import time
    from findata.sec.utils.form4.sec_form4_rss import fetch_form4

    filings = fetch_form4()
    results = []

    for item in filings:
        link = item.get("link")
        if not link:
            continue
        try:
            parsed = parse_form4(link)
            parsed["rss_meta"] = {
                "title":     item.get("title"),
                "form_type": item.get("form_type"),
                "updated":   item.get("updated"),
            }
            results.append(parsed)
        except Exception as e:
            print(f"[WARN] Failed to parse {link}: {e}")
        time.sleep(delay)

    return results
