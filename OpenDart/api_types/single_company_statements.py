"""
단일회사 전체 재무제표 (Single Company Full Financial Statements)

API endpoint: fnlttSinglAcntAll.json
"""

from pathlib import Path
from typing import Optional

from ..client import (
    DATA_DIR,
    OpenDartClient,
    OpenDartNoDataError,
    REPORT_CODE_Q1,
    REPORT_CODE_HALF,
    REPORT_CODE_Q3,
    REPORT_CODE_ANNUAL,
    FS_DIV_CONSOLIDATED,
)
from ..utils.data_processing import consolidate_quarterly

_QUARTERLY_CODES = [REPORT_CODE_Q1, REPORT_CODE_HALF, REPORT_CODE_Q3, REPORT_CODE_ANNUAL]


def _year_range_str(years: list[str]) -> str:
    if len(years) == 1:
        return years[0]
    s = sorted(years)
    return f"{s[0]}-{s[-1]}"


class SingleCompanyStatements:
    """단일회사 전체 재무제표 조회 (fnlttSinglAcntAll).

    Retrieves the **full financial statements** for a single company,
    spanning Balance Sheet (BS), Income Statement (IS), Comprehensive
    Income (CIS), Cash Flow (CF), and Statement of Changes in Equity (SCE).
    """

    def __init__(self, client: OpenDartClient | None = None):
        self._client = client or OpenDartClient()

    def get(
        self,
        corp_code: str,
        bsns_year: str,
        reprt_code: str = REPORT_CODE_ANNUAL,
        fs_div: str = FS_DIV_CONSOLIDATED,
    ) -> list[dict]:
        """Fetch full financial statements for one (year, report)."""
        self._client.validate_reprt_code(reprt_code)
        self._client.validate_fs_div(fs_div)

        params = {
            "corp_code": corp_code,
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
            "fs_div": fs_div,
        }
        data = self._client.request("fnlttSinglAcntAll.json", params)
        return data.get("list", [])

    def save_quarterly(
        self,
        corp_code: str,
        bsns_years: list[str],
        fs_div: str = FS_DIV_CONSOLIDATED,
        filename: Optional[str] = None,
        data_dir: Path | str | None = None,
    ) -> Path:
        """Fetch every quarter of every year, pivot, and save as one CSV.

        Produces a single CSV at ``data/single_company_statements/<filename>.csv``
        with one row per (corp_code, sj_div, period) — account names become
        columns. Sorted by statement type then chronologically by period.
        """
        if not bsns_years:
            raise ValueError("bsns_years must contain at least one year.")

        items: list[dict] = []
        for year in bsns_years:
            for code in _QUARTERLY_CODES:
                try:
                    items.extend(self.get(corp_code, year, code, fs_div))
                except OpenDartNoDataError:
                    continue

        if not items:
            raise ValueError("No data returned for the given company/years.")

        # API response omits corp_code in some payloads — inject it so the
        # pivot index is always well-defined.
        for it in items:
            it.setdefault("corp_code", corp_code)

        df = consolidate_quarterly(items)

        if filename is None:
            filename = (
                f"single_quarterly_{corp_code}_{_year_range_str(bsns_years)}_{fs_div}"
            )

        root = Path(data_dir) if data_dir else DATA_DIR
        out_dir = root / "single_company_statements"
        out_dir.mkdir(parents=True, exist_ok=True)
        filepath = out_dir / f"{filename}.csv"
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
        return filepath

