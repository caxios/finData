"""
OpenDart — Python wrapper for OpenDART financial data APIs.

Modules:
    client                    – Shared base client, errors, and constants
    multi_company_accounts    – 다중회사 주요계정 (fnlttMultiAcnt)
    multi_company_indicators  – 다중회사 주요 재무지표 (fnlttCmpnyIndx)
    single_company_statements – 단일회사 전체 재무제표 (fnlttSinglAcntAll)
    report_main_info          – 정기보고서 주요정보 (30 endpoints)
"""

# Base client & errors
from .client import (
    OpenDartClient,
    OpenDartError,
    OpenDartNoDataError,
    OpenDartAuthError,
    OpenDartRateLimitError,
    REPORT_CODE_Q1,
    REPORT_CODE_HALF,
    REPORT_CODE_Q3,
    REPORT_CODE_ANNUAL,
    FS_DIV_SEPARATE,
    FS_DIV_CONSOLIDATED,
    SJ_DIV_BS,
    SJ_DIV_IS,
    SJ_DIV_CIS,
    SJ_DIV_CF,
    SJ_DIV_SCE,
    IDX_PROFITABILITY,
    IDX_STABILITY,
    IDX_GROWTH,
    IDX_ACTIVITY,
)

# Endpoint modules
from .multi_company_accounts import MultiCompanyAccounts
from .multi_company_indicators import MultiCompanyIndicators
from .single_company_statements import SingleCompanyStatements
from .report_main_info import ReportMainInfo

__all__ = [
    # Client & errors
    "OpenDartClient",
    "OpenDartError",
    "OpenDartNoDataError",
    "OpenDartAuthError",
    "OpenDartRateLimitError",
    # Constants
    "REPORT_CODE_Q1",
    "REPORT_CODE_HALF",
    "REPORT_CODE_Q3",
    "REPORT_CODE_ANNUAL",
    "FS_DIV_SEPARATE",
    "FS_DIV_CONSOLIDATED",
    "SJ_DIV_BS",
    "SJ_DIV_IS",
    "SJ_DIV_CIS",
    "SJ_DIV_CF",
    "SJ_DIV_SCE",
    "IDX_PROFITABILITY",
    "IDX_STABILITY",
    "IDX_GROWTH",
    "IDX_ACTIVITY",
    # Endpoint classes
    "MultiCompanyAccounts",
    "MultiCompanyIndicators",
    "SingleCompanyStatements",
    "ReportMainInfo",
]
