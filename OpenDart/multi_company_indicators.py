"""
다중회사 주요 재무지표 (Multi-Company Key Financial Indicators)

API endpoint: fnlttCmpnyIndx.json
Data is only provided from 2023 Q3 onward.
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
    IDX_PROFITABILITY,
    IDX_STABILITY,
    IDX_GROWTH,
    IDX_ACTIVITY,
)
from .data_processing import consolidate_indicators_quarterly

_QUARTERLY_CODES = [REPORT_CODE_Q1, REPORT_CODE_HALF, REPORT_CODE_Q3, REPORT_CODE_ANNUAL]
_IDX_CODES = [IDX_PROFITABILITY, IDX_STABILITY, IDX_GROWTH, IDX_ACTIVITY]


def _year_range_str(years: list[str]) -> str:
    if len(years) == 1:
        return years[0]
    s = sorted(years)
    return f"{s[0]}-{s[-1]}"


class MultiCompanyIndicators:
    """다중회사 주요 재무지표 조회 (fnlttCmpnyIndx)."""

    def __init__(self, client: OpenDartClient | None = None):
        self._client = client or OpenDartClient()

    def get(
        self,
        corp_codes: list[str],
        bsns_year: str,
        reprt_code: str,
        idx_cl_code: str,
    ) -> list[dict]:
        """Fetch one indicator category for multiple companies (one year, one report)."""
        if not corp_codes:
            raise ValueError("corp_codes must contain at least one corp_code.")
        self._client.validate_reprt_code(reprt_code)
        self._client.validate_idx_cl_code(idx_cl_code)

        params = {
            "corp_code": ",".join(corp_codes),
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
            "idx_cl_code": idx_cl_code,
        }
        data = self._client.request("fnlttCmpnyIndx.json", params)
        return data.get("list", [])

    def save_quarterly(
        self,
        corp_codes: list[str],
        bsns_years: list[str],
        filename: Optional[str] = None,
        data_dir: Path | str | None = None,
    ) -> Path:
        """Fetch every quarter × every indicator category for every company, pivot, and save.

        Produces a single CSV at ``data/multi_company_indicators/<filename>.csv``
        with one row per (corp_code, period) — indicator names (``idx_nm``)
        become columns, spanning all four 지표분류 categories (수익성/안정성/
        성장성/활동성).
        """
        if not corp_codes:
            raise ValueError("corp_codes must contain at least one corp_code.")
        if not bsns_years:
            raise ValueError("bsns_years must contain at least one year.")

        items: list[dict] = []
        for year in bsns_years:
            for reprt in _QUARTERLY_CODES:
                for idx in _IDX_CODES:
                    try:
                        items.extend(self.get(corp_codes, year, reprt, idx))
                    except OpenDartNoDataError:
                        continue

        if not items:
            raise ValueError("No data returned for the given companies/years.")

        df = consolidate_indicators_quarterly(items)

        if filename is None:
            codes_str = "_".join(corp_codes[:5])
            if len(corp_codes) > 5:
                codes_str += f"_and{len(corp_codes) - 5}more"
            filename = f"multi_indx_quarterly_{codes_str}_{_year_range_str(bsns_years)}"

        root = Path(data_dir) if data_dir else DATA_DIR
        out_dir = root / "multi_company_indicators"
        out_dir.mkdir(parents=True, exist_ok=True)
        filepath = out_dir / f"{filename}.csv"
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
        return filepath
