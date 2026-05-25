"""
다중회사 주요계정 (Multi-Company Key Accounts)

API endpoint: fnlttMultiAcnt.json
Docs section: ## 다중회사 주요계정
"""

from pathlib import Path
from typing import Optional

from .client import (
    OpenDartClient,
    REPORT_CODE_ANNUAL,
)


class MultiCompanyAccounts:
    """다중회사 주요계정 조회 (fnlttMultiAcnt).

    Retrieves key financial account data for **multiple** companies
    in a single request.

    Usage::

        from OpenDart.multi_company_accounts import MultiCompanyAccounts

        api = MultiCompanyAccounts()  # reads OPEN_DART_API from .env

        # Just fetch data
        items = api.get(
            corp_codes=["00126380", "00334624"],
            bsns_year="2024",
            reprt_code="11011",
        )

        # Fetch AND save to data/ folder
        filepath = api.save(
            corp_codes=["00126380", "00334624"],
            bsns_year="2024",
            reprt_code="11011",
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

    def get(
        self,
        corp_codes: list[str],
        bsns_year: str,
        reprt_code: str = REPORT_CODE_ANNUAL,
    ) -> list[dict]:
        """Fetch key accounts for multiple companies.

        Args:
            corp_codes: List of 8-digit corp_code strings (고유번호).
            bsns_year:  4-digit fiscal year, e.g. ``"2024"``.
            reprt_code: Report type code. Defaults to annual (``"11011"``).
                - ``"11013"`` – Q1 (1분기보고서)
                - ``"11012"`` – Half-year (반기보고서)
                - ``"11014"`` – Q3 (3분기보고서)
                - ``"11011"`` – Annual (사업보고서)

        Returns:
            A list of dicts, each containing account-level data with keys:

            =============================  ==========================================
            Key                            Description
            =============================  ==========================================
            ``rcept_no``                   접수번호 (14자리)
            ``reprt_code``                 보고서 코드
            ``bsns_year``                  사업연도
            ``corp_code``                  고유번호
            ``stock_code``                 종목코드 (6자리)
            ``fs_div``                     개별/연결구분 (OFS / CFS)
            ``fs_nm``                      개별/연결명
            ``sj_div``                     재무제표구분 (BS / IS)
            ``sj_nm``                      재무제표명
            ``account_nm``                 계정명
            ``thstrm_nm``                  당기명
            ``thstrm_dt``                  당기일자
            ``thstrm_amount``              당기금액
            ``thstrm_add_amount``          당기누적금액
            ``frmtrm_nm``                  전기명
            ``frmtrm_dt``                  전기일자
            ``frmtrm_amount``              전기금액
            ``frmtrm_add_amount``          전기누적금액
            ``bfefrmtrm_nm``               전전기명 (사업보고서만)
            ``bfefrmtrm_dt``               전전기일자 (사업보고서만)
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
                corp_codes=["00126380", "00334624"],
                bsns_year="2018",
                reprt_code="11011",
            )
            for item in items:
                print(item["corp_code"], item["account_nm"], item["thstrm_amount"])
        """
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

    def save(
        self,
        corp_codes: list[str],
        bsns_year: str,
        reprt_code: str = REPORT_CODE_ANNUAL,
        fmt: str = "json",
        filename: Optional[str] = None,
        data_dir: Path | str | None = None,
    ) -> Path:
        """Fetch key accounts and save the result to ``data/multi_company_accounts/``.

        Args:
            corp_codes: List of 8-digit corp_code strings.
            bsns_year:  4-digit fiscal year.
            reprt_code: Report type code. Defaults to annual.
            fmt:        ``"json"`` (default) or ``"csv"``.
            filename:   Custom filename (without extension). If ``None``,
                        auto-generated as
                        ``multi_acnt_{corp_codes}_{year}_{reprt_code}``.
            data_dir:   Override the output root directory.

        Returns:
            The ``Path`` of the saved file.

        Example::

            path = api.save(
                corp_codes=["00126380", "00334624"],
                bsns_year="2018",
                fmt="csv",
            )
            print(f"Saved to {path}")
        """
        items = self.get(corp_codes, bsns_year, reprt_code)

        if filename is None:
            codes_str = "_".join(corp_codes[:5])  # cap at 5 to avoid crazy names
            if len(corp_codes) > 5:
                codes_str += f"_and{len(corp_codes) - 5}more"
            filename = f"multi_acnt_{codes_str}_{bsns_year}_{reprt_code}"

        return self._client.save_data(
            items,
            filename=filename,
            sub_dir="multi_company_accounts",
            fmt=fmt,
            data_dir=data_dir,
        )

