"""
Standalone SEC 10-K/10-Q PDF downloader.

Run from a terminal (NOT inside Jupyter) so you always use the current code and
a clean event loop:

    python experimental.py                # latest AAPL 10-K
    python experimental.py TSLA           # latest TSLA 10-K
    python experimental.py MSFT 10-Q      # latest MSFT 10-Q

Output PDFs (or ZIPs) are written to ./output/.
"""

import sys
from pathlib import Path

import findata
from findata.sec.pdf import SECAccessBlocked


def main() -> int:
    ticker = sys.argv[1].upper() if len(sys.argv) > 1 else "AAPL"
    form = sys.argv[2].upper() if len(sys.argv) > 2 else "10-K"

    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"{ticker}_{form.replace('-', '')}.pdf"

    print(f"Downloading latest {form} for {ticker} ...")
    try:
        data = findata.download_filing_pdf_for(
            ticker,
            form_type=form,
            output_path=str(out_path),
        )
    except SECAccessBlocked as e:
        print("\n[SEC RATE-LIMITED] SEC blocked the request:")
        print(f"  {e}")
        print("  Wait a few minutes and try again; set FINDATA_SEC_USER_AGENT.")
        return 1
    except ValueError as e:
        print(f"\n[BAD INPUT] {e}")
        return 1

    # Sanity check: make sure we saved a real PDF, not something unexpected.
    is_pdf = data[:5] == b"%PDF-"
    head = data[:2000].decode("latin-1", "ignore")
    is_block = "Undeclared Automated Tool" in head

    print(f"\nSaved: {out_path}")
    print(f"  size        : {len(data):,} bytes")
    print(f"  valid PDF   : {is_pdf}")
    print(f"  block page? : {is_block}")

    if is_pdf and not is_block:
        print("\nSUCCESS - open the file above.")
        return 0
    print("\nSomething is off - the file is not a clean PDF. Tell Claude this output.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
