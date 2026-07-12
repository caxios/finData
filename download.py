"""
Data-download headquarters — standalone CLI over the ``findata`` package.

Run from a terminal (NOT inside Jupyter) so you always use the current code and
a clean event loop. Output is written to ./output/.

SEC filings → PDF (default command; the leading "filing" token is optional):

    python download.py                                 # latest AAPL 10-K
    python download.py TSLA                             # latest TSLA 10-K
    python download.py MSFT 10-Q                        # latest MSFT 10-Q
    python download.py AAPL 10-K 2019-01-01 2024-12-31  # range -> ZIP of PDFs
    python download.py filing AAPL 4 2020-01-01 2026-06-30

Earnings call transcripts → TXT (Tavily search; needs TAVILY_API_KEY):

    python download.py transcript AAPL 2024 4          # one quarter  -> one .txt
    python download.py transcript AAPL 2020 1 2026 2   # quarter range -> ZIP of .txt

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
import sys
import zipfile
from pathlib import Path

import findata
from findata.sec.pdf import SECAccessBlocked

ZIP_MAGIC = b"PK\x03\x04"

OUT_DIR = Path(__file__).parent / "output"


def _run_filing(args: list[str]) -> int:
    """Download SEC filing(s) as PDF. args = [ticker, form, date_from, date_to]."""
    ticker = args[0].upper() if len(args) > 0 else "AAPL"
    form = args[1].upper() if len(args) > 1 else "10-K"
    date_from = args[2] if len(args) > 2 else None
    date_to = args[3] if len(args) > 3 else None

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


def _run_transcript(args: list[str]) -> int:
    """Download earnings call transcript(s) as TXT.

    args = [ticker, year_from, quarter_from, (year_to), (quarter_to)]
    """
    if len(args) < 3:
        print("Usage: python download.py transcript TICKER YEAR_FROM Q_FROM "
              "[YEAR_TO Q_TO]")
        print("  e.g. python download.py transcript AAPL 2024 4")
        print("       python download.py transcript AAPL 2020 1 2026 2")
        return 1

    ticker = args[0].upper()
    try:
        year_from = int(args[1])
        quarter_from = int(args[2])
        year_to = int(args[3]) if len(args) > 3 else None
        quarter_to = int(args[4]) if len(args) > 4 else None
    except ValueError:
        print("\n[BAD INPUT] year and quarter must be integers.")
        return 1

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


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)

    argv = sys.argv[1:]
    command = argv[0].lower() if argv else ""

    if command == "transcript":
        return _run_transcript(argv[1:])
    if command == "filing":
        return _run_filing(argv[1:])
    # Backward-compatible default: no command token → treat args as a filing
    # request (python download.py TICKER FORM DATE_FROM DATE_TO).
    return _run_filing(argv)


if __name__ == "__main__":
    raise SystemExit(main())
