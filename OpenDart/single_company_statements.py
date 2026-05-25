"""
단일회사 전체 재무제표 (Single Company Full Financial Statements)

API endpoint: fnlttSinglAcntAll.json
Docs section: ## 단일회사 전체 재무제표
"""

from pathlib import Path
from typing import Optional

from .client import (
    OpenDartClient,
    REPORT_CODE_ANNUAL,
    FS_DIV_CONSOLIDATED,
    SJ_DIV_BS,
    SJ_DIV_IS,
    SJ_DIV_CIS,
    SJ_DIV_CF,
    SJ_DIV_SCE,
)


class SingleCompanyStatements:
    """단일회사 전체 재무제표 조회 (fnlttSinglAcntAll).

    Retrieves the **full financial statements** for a single company,
    including Balance Sheet (BS), Income Statement (IS),
    Comprehensive Income Statement (CIS), Cash Flow (CF),
    and Statement of Changes in Equity (SCE).

    Usage::

        from OpenDart.single_company_statements import SingleCompanyStatements

        api = SingleCompanyStatements()  # reads OPEN_DART_API from .env

        # Just fetch data
        items = api.get(
            corp_code="00126380",
            bsns_year="2024",
            reprt_code="11011",
            fs_div="CFS",
        )

        # Fetch AND save to data/ folder
        filepath = api.save(
            corp_code="00126380",
            bsns_year="2024",
            fmt="csv",
        )
    """

    def __init__(self, client: OpenDartClient | None = None):
        """Initialize with an existing client or create a new one.

        Args:
            client: An ``OpenDartClient`` instance. If ``None``, a new
                    client is created (reads API key from ``.env``).
        """
        self._client = client or OpenDartClient()

    # ------------------------------------------------------------------
    # Core method
    # ------------------------------------------------------------------
    def get(
        self,
        corp_code: str,
        bsns_year: str,
        reprt_code: str = REPORT_CODE_ANNUAL,
        fs_div: str = FS_DIV_CONSOLIDATED,
    ) -> list[dict]:
        """Fetch the full financial statements for a single company.

        Args:
            corp_code:  8-digit corp_code (고유번호).
            bsns_year:  4-digit fiscal year, e.g. ``"2024"``.
            reprt_code: Report type code. Defaults to annual (``"11011"``).
                - ``"11013"`` – Q1 (1분기보고서)
                - ``"11012"`` – Half-year (반기보고서)
                - ``"11014"`` – Q3 (3분기보고서)
                - ``"11011"`` – Annual (사업보고서)
            fs_div: Financial statement division. Defaults to ``"CFS"``
                    (consolidated).
                - ``"OFS"`` – 재무제표 (개별/별도)
                - ``"CFS"`` – 연결재무제표

        Returns:
            A list of dicts with keys:

            =============================  ==========================================
            Key                            Description
            =============================  ==========================================
            ``rcept_no``                   접수번호 (14자리)
            ``reprt_code``                 보고서 코드
            ``bsns_year``                  사업연도
            ``corp_code``                  고유번호
            ``sj_div``                     재무제표구분 (BS/IS/CIS/CF/SCE)
            ``sj_nm``                      재무제표명
            ``account_id``                 계정ID (IFRS/DART 표준코드)
            ``account_nm``                 계정명
            ``account_detail``             계정상세
            ``thstrm_nm``                  당기명
            ``thstrm_amount``              당기금액
            ``thstrm_add_amount``          당기누적금액 (IS/CIS만 해당)
            ``frmtrm_nm``                  전기명
            ``frmtrm_amount``              전기금액
            ``frmtrm_add_amount``          전기누적금액 (IS/CIS만 해당)
            ``bfefrmtrm_nm``               전전기명 (사업보고서만)
            ``bfefrmtrm_amount``           전전기금액 (사업보고서만)
            ``ord``                        계정과목 정렬순서
            ``currency``                   통화 단위
            =============================  ==========================================

        Raises:
            ValueError: If inputs are invalid.
            OpenDartNoDataError: If no data is found.
            OpenDartError: For other API errors.

        Example::

            items = api.get(
                corp_code="00126380",
                bsns_year="2018",
                reprt_code="11011",
                fs_div="OFS",
            )
            for item in items:
                print(item["sj_nm"], item["account_nm"], item["thstrm_amount"])
        """
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

    # ------------------------------------------------------------------
    # Save – full statements
    # ------------------------------------------------------------------
    def save(
        self,
        corp_code: str,
        bsns_year: str,
        reprt_code: str = REPORT_CODE_ANNUAL,
        fs_div: str = FS_DIV_CONSOLIDATED,
        fmt: str = "json",
        filename: Optional[str] = None,
        data_dir: Path | str | None = None,
    ) -> Path:
        """Fetch full financial statements and save to ``data/single_company_statements/``.

        Args:
            corp_code:  8-digit corp_code.
            bsns_year:  4-digit fiscal year.
            reprt_code: Report type code. Defaults to annual.
            fs_div:     ``"CFS"`` (consolidated) or ``"OFS"`` (separate).
            fmt:        ``"json"`` (default) or ``"csv"``.
            filename:   Custom filename (without extension). Auto-generated
                        if ``None``.
            data_dir:   Override the output root directory.

        Returns:
            The ``Path`` of the saved file.

        Example::

            path = api.save(
                corp_code="00126380",
                bsns_year="2018",
                fmt="csv",
            )
            print(f"Saved to {path}")
        """
        items = self.get(corp_code, bsns_year, reprt_code, fs_div)

        if filename is None:
            filename = f"single_all_{corp_code}_{bsns_year}_{reprt_code}_{fs_div}"

        return self._client.save_data(
            items,
            filename=filename,
            sub_dir="single_company_statements",
            fmt=fmt,
            data_dir=data_dir,
        )

    # ------------------------------------------------------------------
    # Convenience filters (get only)
    # ------------------------------------------------------------------
    def get_balance_sheet(
        self,
        corp_code: str,
        bsns_year: str,
        reprt_code: str = REPORT_CODE_ANNUAL,
        fs_div: str = FS_DIV_CONSOLIDATED,
    ) -> list[dict]:
        """재무상태표만 조회 (Balance Sheet only)."""
        items = self.get(corp_code, bsns_year, reprt_code, fs_div)
        return [i for i in items if i.get("sj_div") == SJ_DIV_BS]

    def get_income_statement(
        self,
        corp_code: str,
        bsns_year: str,
        reprt_code: str = REPORT_CODE_ANNUAL,
        fs_div: str = FS_DIV_CONSOLIDATED,
    ) -> list[dict]:
        """손익계산서만 조회 (Income Statement only)."""
        items = self.get(corp_code, bsns_year, reprt_code, fs_div)
        return [i for i in items if i.get("sj_div") == SJ_DIV_IS]

    def get_comprehensive_income(
        self,
        corp_code: str,
        bsns_year: str,
        reprt_code: str = REPORT_CODE_ANNUAL,
        fs_div: str = FS_DIV_CONSOLIDATED,
    ) -> list[dict]:
        """포괄손익계산서만 조회 (Comprehensive Income Statement only)."""
        items = self.get(corp_code, bsns_year, reprt_code, fs_div)
        return [i for i in items if i.get("sj_div") == SJ_DIV_CIS]

    def get_cash_flow(
        self,
        corp_code: str,
        bsns_year: str,
        reprt_code: str = REPORT_CODE_ANNUAL,
        fs_div: str = FS_DIV_CONSOLIDATED,
    ) -> list[dict]:
        """현금흐름표만 조회 (Cash Flow Statement only)."""
        items = self.get(corp_code, bsns_year, reprt_code, fs_div)
        return [i for i in items if i.get("sj_div") == SJ_DIV_CF]

    def get_equity_changes(
        self,
        corp_code: str,
        bsns_year: str,
        reprt_code: str = REPORT_CODE_ANNUAL,
        fs_div: str = FS_DIV_CONSOLIDATED,
    ) -> list[dict]:
        """자본변동표만 조회 (Statement of Changes in Equity only)."""
        items = self.get(corp_code, bsns_year, reprt_code, fs_div)
        return [i for i in items if i.get("sj_div") == SJ_DIV_SCE]

    # ------------------------------------------------------------------
    # Convenience filters (save)
    # ------------------------------------------------------------------
    def save_balance_sheet(
        self,
        corp_code: str,
        bsns_year: str,
        reprt_code: str = REPORT_CODE_ANNUAL,
        fs_div: str = FS_DIV_CONSOLIDATED,
        fmt: str = "json",
        data_dir: Path | str | None = None,
    ) -> Path:
        """재무상태표 저장 (Balance Sheet → file)."""
        items = self.get_balance_sheet(corp_code, bsns_year, reprt_code, fs_div)
        filename = f"BS_{corp_code}_{bsns_year}_{reprt_code}_{fs_div}"
        return self._client.save_data(
            items, filename=filename,
            sub_dir="single_company_statements", fmt=fmt, data_dir=data_dir,
        )

    def save_income_statement(
        self,
        corp_code: str,
        bsns_year: str,
        reprt_code: str = REPORT_CODE_ANNUAL,
        fs_div: str = FS_DIV_CONSOLIDATED,
        fmt: str = "json",
        data_dir: Path | str | None = None,
    ) -> Path:
        """손익계산서 저장 (Income Statement → file)."""
        items = self.get_income_statement(corp_code, bsns_year, reprt_code, fs_div)
        filename = f"IS_{corp_code}_{bsns_year}_{reprt_code}_{fs_div}"
        return self._client.save_data(
            items, filename=filename,
            sub_dir="single_company_statements", fmt=fmt, data_dir=data_dir,
        )

    def save_comprehensive_income(
        self,
        corp_code: str,
        bsns_year: str,
        reprt_code: str = REPORT_CODE_ANNUAL,
        fs_div: str = FS_DIV_CONSOLIDATED,
        fmt: str = "json",
        data_dir: Path | str | None = None,
    ) -> Path:
        """포괄손익계산서 저장 (Comprehensive Income → file)."""
        items = self.get_comprehensive_income(corp_code, bsns_year, reprt_code, fs_div)
        filename = f"CIS_{corp_code}_{bsns_year}_{reprt_code}_{fs_div}"
        return self._client.save_data(
            items, filename=filename,
            sub_dir="single_company_statements", fmt=fmt, data_dir=data_dir,
        )

    def save_cash_flow(
        self,
        corp_code: str,
        bsns_year: str,
        reprt_code: str = REPORT_CODE_ANNUAL,
        fs_div: str = FS_DIV_CONSOLIDATED,
        fmt: str = "json",
        data_dir: Path | str | None = None,
    ) -> Path:
        """현금흐름표 저장 (Cash Flow → file)."""
        items = self.get_cash_flow(corp_code, bsns_year, reprt_code, fs_div)
        filename = f"CF_{corp_code}_{bsns_year}_{reprt_code}_{fs_div}"
        return self._client.save_data(
            items, filename=filename,
            sub_dir="single_company_statements", fmt=fmt, data_dir=data_dir,
        )

    def save_equity_changes(
        self,
        corp_code: str,
        bsns_year: str,
        reprt_code: str = REPORT_CODE_ANNUAL,
        fs_div: str = FS_DIV_CONSOLIDATED,
        fmt: str = "json",
        data_dir: Path | str | None = None,
    ) -> Path:
        """자본변동표 저장 (Equity Changes → file)."""
        items = self.get_equity_changes(corp_code, bsns_year, reprt_code, fs_div)
        filename = f"SCE_{corp_code}_{bsns_year}_{reprt_code}_{fs_div}"
        return self._client.save_data(
            items, filename=filename,
            sub_dir="single_company_statements", fmt=fmt, data_dir=data_dir,
        )

