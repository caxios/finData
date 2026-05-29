"""
정기보고서 주요정보 (Periodic Report Key Information)

Wraps the 30 OpenDART endpoints that expose data extracted from
periodic reports (annual / half / quarterly). All endpoints share the
same request signature ``(corp_code, bsns_year, reprt_code)`` and
differ only in URL path and response fields.

Docs section: docs/opendarts/report_main_info.txt
"""

from pathlib import Path
from typing import Optional

from ..client import (
    DATA_DIR,
    OpenDartClient,
    OpenDartNoDataError,
    REPORT_CODE_ANNUAL,
)
from ..utils.report_processing import consolidate_report_main_info


def _year_range_str(years: list[str]) -> str:
    """Build a filename-safe label for a list of years."""
    if len(years) == 1:
        return years[0]
    s = sorted(years)
    return f"{s[0]}-{s[-1]}"

# ---------------------------------------------------------------------------
# Endpoint registry: snake_case English key → API filename
# ---------------------------------------------------------------------------
_ENDPOINTS: dict[str, str] = {
    "capital_change":                  "irdsSttus.json",
    "dividend":                        "alotMatter.json",
    "treasury_stock":                  "tesstkAcqsDspsSttus.json",
    "major_shareholder":               "hyslrSttus.json",
    "major_shareholder_change":        "hyslrChgSttus.json",
    "minority_shareholders":           "mrhlSttus.json",
    "executives":                      "exctvSttus.json",
    "employees":                       "empSttus.json",
    "director_individual_pay":         "hmvAuditIndvdlBySttus.json",
    "director_total_pay":              "hmvAuditAllSttus.json",
    "top5_individual_pay":             "indvdlByPay.json",
    "other_corp_investment":           "otrCprInvstmntSttus.json",
    "total_stock":                     "stockTotqySttus.json",
    "debt_securities_issued":          "detScritsIsuAcmslt.json",
    "commercial_paper_outstanding":    "entrprsBilScritsNrdmpBlce.json",
    "short_term_bond_outstanding":     "srtpdPsndbtNrdmpBlce.json",
    "corporate_bond_outstanding":      "cprndNrdmpBlce.json",
    "hybrid_securities_outstanding":   "newCaplScritsNrdmpBlce.json",
    "conditional_capital_outstanding": "cndlCaplScritsNrdmpBlce.json",
    "auditor_opinion":                 "accnutAdtorNmNdAdtOpinion.json",
    "audit_service_contract":          "adtServcCnclsSttus.json",
    "non_audit_service_contract":      "accnutAdtorNonAdtServcCnclsSttus.json",
    "outside_director":                "outcmpnyDrctrNdChangeSttus.json",
    "unregistered_executive_pay":      "unrstExctvMendngSttus.json",
    "director_total_pay_approved":     "drctrAdtAllMendngSttusGmtsckConfmAmount.json",
    "director_total_pay_by_type":      "drctrAdtAllMendngSttusMendngPymntamtTyCl.json",
    "public_offering_fund_usage":      "pssrpCptalUseDtls.json",
    "private_placement_fund_usage":    "prvsrpCptalUseDtls.json",
    "director_individual_pay_v2":      "hmvAuditIndvdlBySttusV2.json",
    "top5_individual_pay_v2":          "indvdlByPayV2.json",
}


class ReportMainInfo:
    """정기보고서 주요정보 조회 (30 endpoints).

    All endpoints accept the same arguments::

        corp_code:  8-digit 고유번호
        bsns_year:  4-digit 사업연도 (>= 2015)
        reprt_code: "11013" Q1 / "11012" Half / "11014" Q3 / "11011" Annual

    Usage::

        from OpenDart import ReportMainInfo

        api = ReportMainInfo()  # reads OPEN_DART_API from .env

        # Named wrapper (recommended for discoverability)
        items = api.get_dividend("00126380", "2024", "11011")

        # Generic form
        items = api.get("dividend", "00126380", "2024", "11011")

        # Fetch and save
        path = api.save_dividend("00126380", "2024", fmt="csv")

    Available endpoint keys are listed in ``ReportMainInfo.endpoints()``.
    """

    def __init__(self, client: OpenDartClient | None = None):
        self._client = client or OpenDartClient()

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------
    @staticmethod
    def endpoints() -> list[str]:
        """Return the list of supported endpoint keys."""
        return list(_ENDPOINTS.keys())

    # ------------------------------------------------------------------
    # Generic core
    # ------------------------------------------------------------------
    def get(
        self,
        endpoint_key: str,
        corp_code: str,
        bsns_year: str,
        reprt_code: str = REPORT_CODE_ANNUAL,
    ) -> list[dict]:
        """Fetch the ``list`` payload for an endpoint identified by ``endpoint_key``.

        Args:
            endpoint_key: Key from ``_ENDPOINTS`` (see ``endpoints()``).
            corp_code:    8-digit 고유번호.
            bsns_year:    4-digit 사업연도.
            reprt_code:   Report type code. Defaults to annual ("11011").

        Raises:
            ValueError: If ``endpoint_key`` is unknown or ``reprt_code`` invalid.
            OpenDartNoDataError: If the API returns no data.
            OpenDartError: For other API errors.
        """
        endpoint = _ENDPOINTS.get(endpoint_key)
        if endpoint is None:
            raise ValueError(
                f"Unknown endpoint_key '{endpoint_key}'. "
                f"Available: {sorted(_ENDPOINTS)}"
            )
        self._client.validate_reprt_code(reprt_code)

        params = {
            "corp_code": corp_code,
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
        }
        data = self._client.request(endpoint, params)
        return data.get("list", [])

    def save(
        self,
        endpoint_key: str,
        corp_code: str,
        bsns_year: str,
        reprt_code: str = REPORT_CODE_ANNUAL,
        fmt: str = "json",
        filename: Optional[str] = None,
        data_dir: Path | str | None = None,
    ) -> Path:
        """Fetch and save to ``data/report_main_info/``.

        Filename defaults to ``{endpoint_key}_{corp_code}_{bsns_year}_{reprt_code}``.
        """
        items = self.get(endpoint_key, corp_code, bsns_year, reprt_code)

        if filename is None:
            filename = f"{endpoint_key}_{corp_code}_{bsns_year}_{reprt_code}"

        return self._client.save_data(
            items,
            filename=filename,
            sub_dir="report_main_info",
            fmt=fmt,
            data_dir=data_dir,
        )

    # ------------------------------------------------------------------
    # Multi-year (generic)
    # ------------------------------------------------------------------
    def get_years(
        self,
        endpoint_key: str,
        corp_code: str,
        bsns_years: list[str],
        reprt_code: str = REPORT_CODE_ANNUAL,
    ) -> list[dict]:
        """Fetch one endpoint across multiple fiscal years and return merged list.

        Years with no data are skipped silently. ``bsns_year`` is injected
        into each item if the response doesn't already include it, so years
        remain distinguishable after merging.
        """
        if not bsns_years:
            raise ValueError("bsns_years must contain at least one year.")

        merged: list[dict] = []
        for year in bsns_years:
            try:
                items = self.get(endpoint_key, corp_code, year, reprt_code)
            except OpenDartNoDataError:
                continue
            for it in items:
                it.setdefault("bsns_year", year)
            merged.extend(items)
        return merged

    def save_years(
        self,
        endpoint_key: str,
        corp_code: str,
        bsns_years: list[str],
        reprt_code: str = REPORT_CODE_ANNUAL,
        fmt: str = "json",
        filename: Optional[str] = None,
        data_dir: Path | str | None = None,
    ) -> Path:
        """Fetch multi-year data for one endpoint and save as one combined file.

        Filename defaults to
        ``{endpoint_key}_{corp_code}_{minYear}-{maxYear}_{reprt_code}``.
        """
        items = self.get_years(endpoint_key, corp_code, bsns_years, reprt_code)

        if filename is None:
            filename = (
                f"{endpoint_key}_{corp_code}_{_year_range_str(bsns_years)}_{reprt_code}"
            )

        return self._client.save_data(
            items,
            filename=filename,
            sub_dir="report_main_info",
            fmt=fmt,
            data_dir=data_dir,
        )

    # ------------------------------------------------------------------
    # Consolidated dump (all endpoints → one file)
    # ------------------------------------------------------------------
    def save_all(
        self,
        corp_code: str,
        bsns_years: list[str],
        reprt_code: str = REPORT_CODE_ANNUAL,
        filename: Optional[str] = None,
        data_dir: Path | str | None = None,
    ) -> Path:
        """Fetch every endpoint across all years and stack into one CSV.

        Each row carries an ``endpoint`` column labeling its origin. Endpoints
        have heterogeneous schemas, so the output is the column-wise union;
        cells that don't apply to a row's endpoint are left empty.

        Sorted by endpoint, then bsns_year.
        """
        if not bsns_years:
            raise ValueError("bsns_years must contain at least one year.")

        rows: list[dict] = []
        for endpoint_key in self.endpoints():
            for year in bsns_years:
                try:
                    items = self.get(endpoint_key, corp_code, year, reprt_code)
                except OpenDartNoDataError:
                    continue
                for it in items:
                    # Force-override: the API sometimes returns Korean
                    # term-number strings (e.g. "제55기(감사위원)") in this
                    # field, which would corrupt sorting and filtering.
                    it["bsns_year"] = int(year)
                    it["endpoint"] = endpoint_key
                rows.extend(items)

        if not rows:
            raise ValueError("No data returned across any endpoint.")

        df = consolidate_report_main_info(rows)

        if filename is None:
            years_sorted = sorted(bsns_years)
            year_label = years_sorted[0] if len(years_sorted) == 1 else f"{years_sorted[0]}-{years_sorted[-1]}"
            filename = f"report_main_info_all_{corp_code}_{year_label}_{reprt_code}"

        root = Path(data_dir) if data_dir else DATA_DIR
        out_dir = root / "report_main_info"
        out_dir.mkdir(parents=True, exist_ok=True)
        filepath = out_dir / f"{filename}.csv"
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
        return filepath

    # ------------------------------------------------------------------
    # Named wrappers (one per endpoint)
    # ------------------------------------------------------------------
    def get_capital_change(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL) -> list[dict]:
        """증자(감자) 현황 (irdsSttus)."""
        return self.get("capital_change", corp_code, bsns_year, reprt_code)

    def get_dividend(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL) -> list[dict]:
        """배당에 관한 사항 (alotMatter)."""
        return self.get("dividend", corp_code, bsns_year, reprt_code)

    def get_treasury_stock(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL) -> list[dict]:
        """자기주식 취득 및 처분 현황 (tesstkAcqsDspsSttus)."""
        return self.get("treasury_stock", corp_code, bsns_year, reprt_code)

    def get_major_shareholder(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL) -> list[dict]:
        """최대주주 현황 (hyslrSttus)."""
        return self.get("major_shareholder", corp_code, bsns_year, reprt_code)

    def get_major_shareholder_change(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL) -> list[dict]:
        """최대주주 변동현황 (hyslrChgSttus)."""
        return self.get("major_shareholder_change", corp_code, bsns_year, reprt_code)

    def get_minority_shareholders(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL) -> list[dict]:
        """소액주주 현황 (mrhlSttus)."""
        return self.get("minority_shareholders", corp_code, bsns_year, reprt_code)

    def get_executives(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL) -> list[dict]:
        """임원 현황 (exctvSttus)."""
        return self.get("executives", corp_code, bsns_year, reprt_code)

    def get_employees(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL) -> list[dict]:
        """직원 현황 (empSttus)."""
        return self.get("employees", corp_code, bsns_year, reprt_code)

    def get_director_individual_pay(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL) -> list[dict]:
        """이사·감사의 개인별 보수현황 5억원 이상 (hmvAuditIndvdlBySttus). 2026년 4월까지 제출분."""
        return self.get("director_individual_pay", corp_code, bsns_year, reprt_code)

    def get_director_total_pay(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL) -> list[dict]:
        """이사·감사 전체의 보수현황 - 보수지급금액 (hmvAuditAllSttus)."""
        return self.get("director_total_pay", corp_code, bsns_year, reprt_code)

    def get_top5_individual_pay(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL) -> list[dict]:
        """개인별 보수지급 금액 5억이상 상위5인 (indvdlByPay). 2026년 4월까지 제출분."""
        return self.get("top5_individual_pay", corp_code, bsns_year, reprt_code)

    def get_other_corp_investment(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL) -> list[dict]:
        """타법인 출자현황 (otrCprInvstmntSttus)."""
        return self.get("other_corp_investment", corp_code, bsns_year, reprt_code)

    def get_total_stock(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL) -> list[dict]:
        """주식의 총수 현황 (stockTotqySttus)."""
        return self.get("total_stock", corp_code, bsns_year, reprt_code)

    def get_debt_securities_issued(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL) -> list[dict]:
        """채무증권 발행실적 (detScritsIsuAcmslt)."""
        return self.get("debt_securities_issued", corp_code, bsns_year, reprt_code)

    def get_commercial_paper_outstanding(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL) -> list[dict]:
        """기업어음증권 미상환 잔액 (entrprsBilScritsNrdmpBlce)."""
        return self.get("commercial_paper_outstanding", corp_code, bsns_year, reprt_code)

    def get_short_term_bond_outstanding(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL) -> list[dict]:
        """단기사채 미상환 잔액 (srtpdPsndbtNrdmpBlce)."""
        return self.get("short_term_bond_outstanding", corp_code, bsns_year, reprt_code)

    def get_corporate_bond_outstanding(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL) -> list[dict]:
        """회사채 미상환 잔액 (cprndNrdmpBlce)."""
        return self.get("corporate_bond_outstanding", corp_code, bsns_year, reprt_code)

    def get_hybrid_securities_outstanding(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL) -> list[dict]:
        """신종자본증권 미상환 잔액 (newCaplScritsNrdmpBlce)."""
        return self.get("hybrid_securities_outstanding", corp_code, bsns_year, reprt_code)

    def get_conditional_capital_outstanding(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL) -> list[dict]:
        """조건부 자본증권 미상환 잔액 (cndlCaplScritsNrdmpBlce)."""
        return self.get("conditional_capital_outstanding", corp_code, bsns_year, reprt_code)

    def get_auditor_opinion(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL) -> list[dict]:
        """회계감사인의 명칭 및 감사의견 (accnutAdtorNmNdAdtOpinion)."""
        return self.get("auditor_opinion", corp_code, bsns_year, reprt_code)

    def get_audit_service_contract(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL) -> list[dict]:
        """감사용역체결현황 (adtServcCnclsSttus)."""
        return self.get("audit_service_contract", corp_code, bsns_year, reprt_code)

    def get_non_audit_service_contract(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL) -> list[dict]:
        """회계감사인과의 비감사용역 계약체결 현황 (accnutAdtorNonAdtServcCnclsSttus)."""
        return self.get("non_audit_service_contract", corp_code, bsns_year, reprt_code)

    def get_outside_director(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL) -> list[dict]:
        """사외이사 및 그 변동현황 (outcmpnyDrctrNdChangeSttus)."""
        return self.get("outside_director", corp_code, bsns_year, reprt_code)

    def get_unregistered_executive_pay(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL) -> list[dict]:
        """미등기임원 보수현황 (unrstExctvMendngSttus)."""
        return self.get("unregistered_executive_pay", corp_code, bsns_year, reprt_code)

    def get_director_total_pay_approved(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL) -> list[dict]:
        """이사·감사 전체의 보수현황 - 주주총회 승인금액 (drctrAdtAllMendngSttusGmtsckConfmAmount)."""
        return self.get("director_total_pay_approved", corp_code, bsns_year, reprt_code)

    def get_director_total_pay_by_type(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL) -> list[dict]:
        """이사·감사 전체의 보수현황 - 유형별 (drctrAdtAllMendngSttusMendngPymntamtTyCl)."""
        return self.get("director_total_pay_by_type", corp_code, bsns_year, reprt_code)

    def get_public_offering_fund_usage(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL) -> list[dict]:
        """공모자금의 사용내역 (pssrpCptalUseDtls)."""
        return self.get("public_offering_fund_usage", corp_code, bsns_year, reprt_code)

    def get_private_placement_fund_usage(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL) -> list[dict]:
        """사모자금의 사용내역 (prvsrpCptalUseDtls)."""
        return self.get("private_placement_fund_usage", corp_code, bsns_year, reprt_code)

    def get_director_individual_pay_v2(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL) -> list[dict]:
        """이사·감사의 개인별 보수현황 5억원 이상 Ver 2.0 (hmvAuditIndvdlBySttusV2). 2026년 5월 이후 제출분."""
        return self.get("director_individual_pay_v2", corp_code, bsns_year, reprt_code)

    def get_top5_individual_pay_v2(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL) -> list[dict]:
        """개인별 보수지급 금액 5억이상 상위5인 Ver 2.0 (indvdlByPayV2). 2026년 5월 이후 제출분."""
        return self.get("top5_individual_pay_v2", corp_code, bsns_year, reprt_code)

    # ------------------------------------------------------------------
    # Named save wrappers
    # ------------------------------------------------------------------
    def save_capital_change(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL, fmt: str = "json", data_dir: Path | str | None = None) -> Path:
        return self.save("capital_change", corp_code, bsns_year, reprt_code, fmt=fmt, data_dir=data_dir)

    def save_dividend(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL, fmt: str = "json", data_dir: Path | str | None = None) -> Path:
        return self.save("dividend", corp_code, bsns_year, reprt_code, fmt=fmt, data_dir=data_dir)

    def save_treasury_stock(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL, fmt: str = "json", data_dir: Path | str | None = None) -> Path:
        return self.save("treasury_stock", corp_code, bsns_year, reprt_code, fmt=fmt, data_dir=data_dir)

    def save_major_shareholder(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL, fmt: str = "json", data_dir: Path | str | None = None) -> Path:
        return self.save("major_shareholder", corp_code, bsns_year, reprt_code, fmt=fmt, data_dir=data_dir)

    def save_major_shareholder_change(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL, fmt: str = "json", data_dir: Path | str | None = None) -> Path:
        return self.save("major_shareholder_change", corp_code, bsns_year, reprt_code, fmt=fmt, data_dir=data_dir)

    def save_minority_shareholders(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL, fmt: str = "json", data_dir: Path | str | None = None) -> Path:
        return self.save("minority_shareholders", corp_code, bsns_year, reprt_code, fmt=fmt, data_dir=data_dir)

    def save_executives(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL, fmt: str = "json", data_dir: Path | str | None = None) -> Path:
        return self.save("executives", corp_code, bsns_year, reprt_code, fmt=fmt, data_dir=data_dir)

    def save_employees(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL, fmt: str = "json", data_dir: Path | str | None = None) -> Path:
        return self.save("employees", corp_code, bsns_year, reprt_code, fmt=fmt, data_dir=data_dir)

    def save_director_individual_pay(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL, fmt: str = "json", data_dir: Path | str | None = None) -> Path:
        return self.save("director_individual_pay", corp_code, bsns_year, reprt_code, fmt=fmt, data_dir=data_dir)

    def save_director_total_pay(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL, fmt: str = "json", data_dir: Path | str | None = None) -> Path:
        return self.save("director_total_pay", corp_code, bsns_year, reprt_code, fmt=fmt, data_dir=data_dir)

    def save_top5_individual_pay(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL, fmt: str = "json", data_dir: Path | str | None = None) -> Path:
        return self.save("top5_individual_pay", corp_code, bsns_year, reprt_code, fmt=fmt, data_dir=data_dir)

    def save_other_corp_investment(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL, fmt: str = "json", data_dir: Path | str | None = None) -> Path:
        return self.save("other_corp_investment", corp_code, bsns_year, reprt_code, fmt=fmt, data_dir=data_dir)

    def save_total_stock(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL, fmt: str = "json", data_dir: Path | str | None = None) -> Path:
        return self.save("total_stock", corp_code, bsns_year, reprt_code, fmt=fmt, data_dir=data_dir)

    def save_debt_securities_issued(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL, fmt: str = "json", data_dir: Path | str | None = None) -> Path:
        return self.save("debt_securities_issued", corp_code, bsns_year, reprt_code, fmt=fmt, data_dir=data_dir)

    def save_commercial_paper_outstanding(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL, fmt: str = "json", data_dir: Path | str | None = None) -> Path:
        return self.save("commercial_paper_outstanding", corp_code, bsns_year, reprt_code, fmt=fmt, data_dir=data_dir)

    def save_short_term_bond_outstanding(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL, fmt: str = "json", data_dir: Path | str | None = None) -> Path:
        return self.save("short_term_bond_outstanding", corp_code, bsns_year, reprt_code, fmt=fmt, data_dir=data_dir)

    def save_corporate_bond_outstanding(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL, fmt: str = "json", data_dir: Path | str | None = None) -> Path:
        return self.save("corporate_bond_outstanding", corp_code, bsns_year, reprt_code, fmt=fmt, data_dir=data_dir)

    def save_hybrid_securities_outstanding(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL, fmt: str = "json", data_dir: Path | str | None = None) -> Path:
        return self.save("hybrid_securities_outstanding", corp_code, bsns_year, reprt_code, fmt=fmt, data_dir=data_dir)

    def save_conditional_capital_outstanding(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL, fmt: str = "json", data_dir: Path | str | None = None) -> Path:
        return self.save("conditional_capital_outstanding", corp_code, bsns_year, reprt_code, fmt=fmt, data_dir=data_dir)

    def save_auditor_opinion(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL, fmt: str = "json", data_dir: Path | str | None = None) -> Path:
        return self.save("auditor_opinion", corp_code, bsns_year, reprt_code, fmt=fmt, data_dir=data_dir)

    def save_audit_service_contract(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL, fmt: str = "json", data_dir: Path | str | None = None) -> Path:
        return self.save("audit_service_contract", corp_code, bsns_year, reprt_code, fmt=fmt, data_dir=data_dir)

    def save_non_audit_service_contract(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL, fmt: str = "json", data_dir: Path | str | None = None) -> Path:
        return self.save("non_audit_service_contract", corp_code, bsns_year, reprt_code, fmt=fmt, data_dir=data_dir)

    def save_outside_director(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL, fmt: str = "json", data_dir: Path | str | None = None) -> Path:
        return self.save("outside_director", corp_code, bsns_year, reprt_code, fmt=fmt, data_dir=data_dir)

    def save_unregistered_executive_pay(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL, fmt: str = "json", data_dir: Path | str | None = None) -> Path:
        return self.save("unregistered_executive_pay", corp_code, bsns_year, reprt_code, fmt=fmt, data_dir=data_dir)

    def save_director_total_pay_approved(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL, fmt: str = "json", data_dir: Path | str | None = None) -> Path:
        return self.save("director_total_pay_approved", corp_code, bsns_year, reprt_code, fmt=fmt, data_dir=data_dir)

    def save_director_total_pay_by_type(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL, fmt: str = "json", data_dir: Path | str | None = None) -> Path:
        return self.save("director_total_pay_by_type", corp_code, bsns_year, reprt_code, fmt=fmt, data_dir=data_dir)

    def save_public_offering_fund_usage(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL, fmt: str = "json", data_dir: Path | str | None = None) -> Path:
        return self.save("public_offering_fund_usage", corp_code, bsns_year, reprt_code, fmt=fmt, data_dir=data_dir)

    def save_private_placement_fund_usage(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL, fmt: str = "json", data_dir: Path | str | None = None) -> Path:
        return self.save("private_placement_fund_usage", corp_code, bsns_year, reprt_code, fmt=fmt, data_dir=data_dir)

    def save_director_individual_pay_v2(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL, fmt: str = "json", data_dir: Path | str | None = None) -> Path:
        return self.save("director_individual_pay_v2", corp_code, bsns_year, reprt_code, fmt=fmt, data_dir=data_dir)

    def save_top5_individual_pay_v2(self, corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL, fmt: str = "json", data_dir: Path | str | None = None) -> Path:
        return self.save("top5_individual_pay_v2", corp_code, bsns_year, reprt_code, fmt=fmt, data_dir=data_dir)
