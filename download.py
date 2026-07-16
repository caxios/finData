"""
Data-download headquarters — standalone CLI over the ``findata`` package.

Run from a terminal (NOT inside Jupyter) so you always use the current code and
a clean event loop. Output is written to ./output/.

SEC filings → PDF (default command; the leading "filing" token is optional).
One or more tickers may be given; multiple tickers → a single combined ZIP with
every file prefixed by its ticker:

    python download.py                                      # latest AAPL 10-K
    python download.py TSLA                                 # latest TSLA 10-K
    python download.py MSFT 10-Q                            # latest MSFT 10-Q
    python download.py AAPL 10-K 2019-01-01 2024-12-31      # range -> ZIP of PDFs
    python download.py TSLA AAPL 10-Q 2020-01-01 2026-06-30 # both -> one ZIP
    python download.py filing AAPL 4 2020-01-01 2026-06-30

Earnings call transcripts → TXT (Tavily search; needs TAVILY_API_KEY). Multiple
tickers → one combined ZIP, ticker-prefixed:

    python download.py transcript AAPL 2024 4              # one quarter  -> one .txt
    python download.py transcript AAPL 2020 1 2026 2       # quarter range -> ZIP of .txt
    python download.py transcript AAPL MSFT 2020 1 2026 2  # both -> one ZIP

files that are essential to download the data :

    download.py                                    the CLI you run
    findata/__init__.py                            package entry (import findata)
    findata/sec/pdf.py                             download_filing_pdf_for → render/subprocess logic + SECAccessBlocked
    findata/sec/_pdf_worker.py                     the subprocess that runs Chromium
    findata/sec/transcripts.py                     get_transcript / download_transcripts_for (Tavily search+extract)
    findata/sec/filings.py                         find_filings (ticker+form+dates → rows)
    findata/sec/_cik.py                            lookup_cik (ticker → CIK)
    findata/sec/utils/sec_submissions.py           fetch_and_resolve (submissions.json → document_url)
    findata/sec/const.py                           HEADERS / SEC_USER_AGENT

"""

import io
import re
import sys
import zipfile
from pathlib import Path

import findata
from findata.sec.pdf import SECAccessBlocked

ZIP_MAGIC = b"PK\x03\x04"

OUT_DIR = Path(__file__).parent / "output"

# A ticker is pure letters (optionally with '.'/'-', e.g. BRK.B) and no digits.
# Every SEC form token carries a digit (10-K, 10-Q, 8-K, 4, S-1), and dates are
# YYYY-MM-DD, so "leading letter-only tokens = tickers" splits the args cleanly.
_TICKER_RE = re.compile(r"^[A-Za-z][A-Za-z.\-]*$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ── Shared ZIP helpers ──────────────────────────────────────────────

def _writestr_unique(zf: zipfile.ZipFile, name: str, data: bytes,
                     seen: dict[str, int]) -> None:
    """Write *data* into *zf* under *name*, disambiguating collisions."""
    if name in seen:
        seen[name] += 1
        stem, dot, ext = name.rpartition(".")
        name = f"{stem}_{seen[name]}.{ext}" if dot else f"{name}_{seen[name]}"
    else:
        seen[name] = 0
    zf.writestr(name, data)


def _add_to_zip(zf: zipfile.ZipFile, ticker: str, data: bytes,
                fallback_name: str, seen: dict[str, int]) -> None:
    """Add one ticker's download result into *zf*, prefixed with the ticker.

    ``data`` is either raw PDF/TXT bytes (a single match) or ZIP bytes (many
    matches). A ZIP is flattened — each member is re-added as ``TICKER_member``;
    single bytes become ``TICKER_<fallback_name>``.
    """
    if data[:4] == ZIP_MAGIC:
        src = zipfile.ZipFile(io.BytesIO(data))
        for info in src.infolist():
            if info.is_dir():
                continue
            member = info.filename.rsplit("/", 1)[-1]
            _writestr_unique(zf, f"{ticker}_{member}", src.read(info), seen)
    else:
        _writestr_unique(zf, f"{ticker}_{fallback_name}", data, seen)


def _download_multi(tickers, fetch_fn, fallback_name, out_stem, noun) -> int:
    """Fetch each ticker, merge results into one ticker-prefixed ZIP, report.

    ``fetch_fn(ticker)`` returns PDF/TXT/ZIP bytes. Per-ticker failures are
    caught so one bad ticker never sinks the rest (continue-and-report).
    """
    buf = io.BytesIO()
    seen: dict[str, int] = {}
    succeeded: list[str] = []
    failed: list[tuple[str, str]] = []

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for t in tickers:
            print(f"  - {t} ...", end=" ", flush=True)
            try:
                data = fetch_fn(t)
            except SECAccessBlocked as e:
                print("SEC RATE-LIMITED")
                failed.append((t, f"SEC rate-limited: {e}"))
                continue
            except (ValueError, RuntimeError) as e:
                print("skipped")
                failed.append((t, str(e)))
                continue
            except Exception as e:  # noqa: BLE001 - keep going, record the reason
                print("error")
                failed.append((t, f"{type(e).__name__}: {e}"))
                continue

            before = len(zf.namelist())
            _add_to_zip(zf, t, data, fallback_name, seen)
            added = len(zf.namelist()) - before
            print(f"ok ({added} file{'' if added == 1 else 's'})")
            succeeded.append(t)

    if not succeeded:
        print(f"\n[FAILED] No {noun} downloaded for any ticker:")
        for t, why in failed:
            print(f"  - {t}: {why}")
        return 1

    out_path = OUT_DIR / f"{out_stem}.zip"
    payload = buf.getvalue()
    out_path.write_bytes(payload)

    names = zipfile.ZipFile(io.BytesIO(payload)).namelist()
    print(f"\nSaved: {out_path}")
    print(f"  size : {len(payload):,} bytes")
    print(f"  type : ZIP with {len(names)} {noun} from {len(succeeded)} ticker(s)")
    for n in names:
        print(f"           - {n}")
    if failed:
        print(f"\n  {len(failed)} ticker(s) failed:")
        for t, why in failed:
            print(f"           - {t}: {why}")
    print("\nSUCCESS - unzip the file above.")
    return 0


def _ticker_stem(tickers: list[str]) -> str:
    """Short filename stem for a group of tickers."""
    return "_".join(tickers) if len(tickers) <= 4 else f"{len(tickers)}tickers"


# ── Filings ─────────────────────────────────────────────────────────

def _split_filing_args(args: list[str]):
    """Parse ``[TICKER...] [FORM] [DATE_FROM] [DATE_TO]``.

    Returns ``(tickers, form, date_from, date_to)``.
    """
    tickers: list[str] = []
    idx = 0
    while idx < len(args) and _TICKER_RE.match(args[idx]):
        tickers.append(args[idx].upper())
        idx += 1

    form = None
    dates: list[str] = []
    for tok in args[idx:]:
        if _DATE_RE.match(tok):
            dates.append(tok)
        else:
            form = tok.upper()  # last non-date token wins as the form

    if not tickers:
        tickers = ["AAPL"]
    form = form or "10-K"
    date_from = dates[0] if dates else None
    date_to = dates[1] if len(dates) > 1 else None
    return tickers, form, date_from, date_to


def _run_filing_single(ticker, form, date_from, date_to) -> int:
    """Download SEC filing(s) as PDF for a single ticker."""
    if date_from or date_to:
        print(f"Downloading all {form} for {ticker} in [{date_from} .. {date_to}] ...")
    else:
        print(f"Downloading latest {form} for {ticker} ...")

    try:
        # No output_path here: we inspect the bytes first to pick .pdf vs .zip,
        # then write with the correct extension.
        data = findata.download_filing_pdf_for(
            ticker,
            form_type=form,
            date_from=date_from,
            date_to=date_to,
        )
    except SECAccessBlocked as e:
        print("\n[SEC RATE-LIMITED] SEC blocked the request:")
        print(f"  {e}")
        print("  Wait a few minutes and try again; set FINDATA_SEC_USER_AGENT.")
        return 1
    except ValueError as e:
        print(f"\n[BAD INPUT] {e}")
        return 1

    is_zip = data[:4] == ZIP_MAGIC
    is_pdf = data[:5] == b"%PDF-"

    suffix = f"_{date_from}_{date_to}" if (date_from or date_to) else ""
    ext = "zip" if is_zip else "pdf"
    out_path = OUT_DIR / f"{ticker}_{form.replace('-', '')}{suffix}.{ext}"
    out_path.write_bytes(data)

    print(f"\nSaved: {out_path}")
    print(f"  size : {len(data):,} bytes")
    if is_zip:
        names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        print(f"  type : ZIP with {len(names)} filing(s)")
        for n in names:
            print(f"           - {n}")
        print("\nSUCCESS - unzip the file above.")
        return 0
    if is_pdf:
        print("  type : single PDF")
        print("\nSUCCESS - open the file above.")
        return 0

    print("\nSomething is off - not a clean PDF/ZIP. Tell Claude this output.")
    return 1


def _run_filing(args: list[str]) -> int:
    """Download SEC filing(s) as PDF for one or more tickers."""
    tickers, form, date_from, date_to = _split_filing_args(args)

    if len(tickers) == 1:
        return _run_filing_single(tickers[0], form, date_from, date_to)

    if date_from or date_to:
        print(f"Downloading all {form} for {', '.join(tickers)} "
              f"in [{date_from} .. {date_to}] ...")
    else:
        print(f"Downloading latest {form} for {', '.join(tickers)} ...")

    suffix = f"_{date_from}_{date_to}" if (date_from or date_to) else ""
    fallback = f"{form.replace('-', '')}{suffix}.pdf"
    out_stem = f"{_ticker_stem(tickers)}_{form.replace('-', '')}{suffix}"

    def fetch(ticker: str) -> bytes:
        return findata.download_filing_pdf_for(
            ticker, form_type=form, date_from=date_from, date_to=date_to,
        )

    return _download_multi(tickers, fetch, fallback, out_stem, "filing(s)")


# ── Transcripts ─────────────────────────────────────────────────────

def _split_transcript_args(args: list[str]):
    """Parse ``[TICKER...] YEAR_FROM Q_FROM [YEAR_TO Q_TO]``.

    Returns ``(tickers, nums)`` where nums are the trailing (non-ticker) tokens.
    """
    tickers: list[str] = []
    idx = 0
    while idx < len(args) and _TICKER_RE.match(args[idx]):
        tickers.append(args[idx].upper())
        idx += 1
    return tickers, args[idx:]


def _run_transcript_single(ticker, year_from, quarter_from, year_to,
                           quarter_to) -> int:
    """Download earnings call transcript(s) as TXT for a single ticker."""
    windowed = year_to is not None or quarter_to is not None
    if windowed:
        print(f"Downloading transcripts for {ticker} from "
              f"{year_from} Q{quarter_from} to {year_to} Q{quarter_to} ...")
    else:
        print(f"Downloading transcript for {ticker} {year_from} Q{quarter_from} ...")

    try:
        # No output_path here: inspect the bytes to pick .txt vs .zip.
        data = findata.download_transcripts_for(
            ticker,
            year_from,
            quarter_from,
            year_to=year_to,
            quarter_to=quarter_to,
        )
    except ValueError as e:
        print(f"\n[BAD INPUT] {e}")
        return 1
    except RuntimeError as e:
        print(f"\n[CONFIG] {e}")
        print("  Set TAVILY_API_KEY (in your environment or a .env file).")
        return 1

    is_zip = data[:4] == ZIP_MAGIC

    if windowed:
        suffix = f"_{year_from}Q{quarter_from}_{year_to}Q{quarter_to}"
    else:
        suffix = f"_{year_from}Q{quarter_from}"
    ext = "zip" if is_zip else "txt"
    out_path = OUT_DIR / f"{ticker}_transcript{suffix}.{ext}"
    out_path.write_bytes(data)

    print(f"\nSaved: {out_path}")
    print(f"  size : {len(data):,} bytes")
    if is_zip:
        names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        print(f"  type : ZIP with {len(names)} transcript(s)")
        for n in names:
            print(f"           - {n}")
        print("\nSUCCESS - unzip the file above.")
    else:
        print("  type : single TXT")
        print("\nSUCCESS - open the file above.")
    return 0


def _run_transcript(args: list[str]) -> int:
    """Download earnings call transcript(s) as TXT for one or more tickers.

    args = [ticker..., year_from, quarter_from, (year_to), (quarter_to)]
    """
    tickers, nums = _split_transcript_args(args)

    if not tickers or len(nums) < 2:
        print("Usage: python download.py transcript TICKER [TICKER...] YEAR_FROM "
              "Q_FROM [YEAR_TO Q_TO]")
        print("  e.g. python download.py transcript AAPL 2024 4")
        print("       python download.py transcript AAPL MSFT 2020 1 2026 2")
        return 1

    try:
        year_from = int(nums[0])
        quarter_from = int(nums[1])
        year_to = int(nums[2]) if len(nums) > 2 else None
        quarter_to = int(nums[3]) if len(nums) > 3 else None
    except ValueError:
        print("\n[BAD INPUT] year and quarter must be integers.")
        return 1

    if len(tickers) == 1:
        return _run_transcript_single(
            tickers[0], year_from, quarter_from, year_to, quarter_to
        )

    windowed = year_to is not None or quarter_to is not None
    if windowed:
        print(f"Downloading transcripts for {', '.join(tickers)} from "
              f"{year_from} Q{quarter_from} to {year_to} Q{quarter_to} ...")
        suffix = f"_{year_from}Q{quarter_from}_{year_to}Q{quarter_to}"
    else:
        print(f"Downloading transcripts for {', '.join(tickers)} "
              f"{year_from} Q{quarter_from} ...")
        suffix = f"_{year_from}Q{quarter_from}"

    fallback = f"transcript{suffix}.txt"
    out_stem = f"{_ticker_stem(tickers)}_transcript{suffix}"

    def fetch(ticker: str) -> bytes:
        return findata.download_transcripts_for(
            ticker, year_from, quarter_from,
            year_to=year_to, quarter_to=quarter_to,
        )

    return _download_multi(tickers, fetch, fallback, out_stem, "transcript(s)")


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)

    argv = sys.argv[1:]
    command = argv[0].lower() if argv else ""

    if command == "transcript":
        return _run_transcript(argv[1:])
    if command == "filing":
        return _run_filing(argv[1:])
    # Backward-compatible default: no command token → treat args as a filing
    # request (python download.py TICKER... FORM DATE_FROM DATE_TO).
    return _run_filing(argv)


if __name__ == "__main__":
    raise SystemExit(main())
