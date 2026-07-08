"""
Standalone SEC 10-K/10-Q PDF downloader.

Run from a terminal (NOT inside Jupyter) so you always use the current code and
a clean event loop.

Single filing (latest) -> one PDF:
    python experimental.py                       # latest AAPL 10-K
    python experimental.py TSLA                  # latest TSLA 10-K
    python experimental.py MSFT 10-Q             # latest MSFT 10-Q

Multiple filings in a date range -> one ZIP (one PDF per filing):
    python experimental.py AAPL 10-K 2019-01-01 2024-12-31
    python experimental.py MSFT 10-Q 2022-01-01 2023-12-31

Output is written to ./output/.

files that are essential to download the filings : 

experimental.py	the CLI you run
findata/init.py	package entry (import findata)
findata/sec/pdf.py	download_filing_pdf_for → download_filing_pdf → render/subprocess logic + SECAccessBlocked
findata/sec/_pdf_worker.py	the subprocess that runs Chromium (doesn't show in the trace because it's a separate process)
findata/sec/filings.py	find_filings (ticker+form+dates → rows)
findata/sec/_cik.py	lookup_cik (ticker → CIK)
findata/sec/utils/sec_submissions.py	fetch_and_resolve (submissions.json → document_url)
findata/sec/const.py	HEADERS / SEC_USER_AGENT

"""

import io
import sys
import zipfile
from pathlib import Path

import findata
from findata.sec.pdf import SECAccessBlocked

ZIP_MAGIC = b"PK\x03\x04"


def main() -> int:
    ticker = sys.argv[1].upper() if len(sys.argv) > 1 else "AAPL"
    form = sys.argv[2].upper() if len(sys.argv) > 2 else "10-K"
    date_from = sys.argv[3] if len(sys.argv) > 3 else None
    date_to = sys.argv[4] if len(sys.argv) > 4 else None

    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)

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
    out_path = out_dir / f"{ticker}_{form.replace('-', '')}{suffix}.{ext}"
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


if __name__ == "__main__":
    raise SystemExit(main())
