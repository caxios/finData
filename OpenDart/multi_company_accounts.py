"""
다중회사 주요계정 (Multi-Company Key Accounts)

API endpoint: fnlttMultiAcnt.json
"""

from pathlib import Path
from typing import Optional

from .client import (
    DATA_DIR,
    OpenDartClient,
    OpenDartNoDataError,
    REPORT_CODE_Q1,
    REPORT_CODE_HALF,
    REPORT_CODE_Q3,
    REPORT_CODE_ANNUAL,
)
from .data_processing import consolidate_quarterly

_QUARTERLY_CODES = [REPORT_CODE_Q1, REPORT_CODE_HALF, REPORT_CODE_Q3, REPORT_CODE_ANNUAL]
_CORP_CHUNK = 100  # OpenDART caps fnlttMultiAcnt at 100 corp_codes per request.


def _year_range_str(years: list[str]) -> str:
    if len(years) == 1:
        return years[0]
    s = sorted(years)
    return f"{s[0]}-{s[-1]}"


class MultiCompanyAccounts:
    """다중회사 주요계정 조회 (fnlttMultiAcnt)."""

    def __init__(self, client: OpenDartClient | None = None):
        self._client = client or OpenDartClient()

    def get(
        self,
        corp_codes: list[str],
        bsns_year: str,
        reprt_code: str = REPORT_CODE_ANNUAL,
    ) -> list[dict]:
        """Fetch key accounts for multiple companies for one (year, report)."""
        if not corp_codes:
            raise ValueError("corp_codes must contain at least one corp_code.")
        self._client.validate_reprt_code(reprt_code)

        params = {
            "corp_code": ",".join(corp_codes),
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
        }
        data = self._client.request("fnlttMultiAcnt.json", params)
        return data.get("list", [])

    def save_quarterly(
        self,
        corp_codes: list[str],
        bsns_years: list[str],
        filename: Optional[str] = None,
        data_dir: Path | str | None = None,
    ) -> Path:
        """Fetch every quarter of every year for every company, pivot, and save.

        Produces a single CSV at ``data/multi_company_accounts/<filename>.csv``
        with one row per (corp_code, fs_div, period) — account names become
        columns. Rows are sorted by company, then chronologically by period,
        so all of Company A's quarters appear before Company B's.
        """
        if not corp_codes:
            raise ValueError("corp_codes must contain at least one corp_code.")
        if not bsns_years:
            raise ValueError("bsns_years must contain at least one year.")

        items: list[dict] = []
        for year in bsns_years:
            for code in _QUARTERLY_CODES:
                for i in range(0, len(corp_codes), _CORP_CHUNK):
                    chunk = corp_codes[i : i + _CORP_CHUNK]
                    try:
                        items.extend(self.get(chunk, year, code))
                    except OpenDartNoDataError:
                        continue

        if not items:
            raise ValueError("No data returned for the given companies/years.")

        df = consolidate_quarterly(items)

        if filename is None:
            codes_str = "_".join(corp_codes[:5])
            if len(corp_codes) > 5:
                codes_str += f"_and{len(corp_codes) - 5}more"
            filename = f"multi_acnt_quarterly_{codes_str}_{_year_range_str(bsns_years)}"

        root = Path(data_dir) if data_dir else DATA_DIR
        out_dir = root / "multi_company_accounts"
        out_dir.mkdir(parents=True, exist_ok=True)
        filepath = out_dir / f"{filename}.csv"
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
        return filepath
