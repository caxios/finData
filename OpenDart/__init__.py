"""
OpenDart — Python wrapper for OpenDART financial data APIs.

Modules:
    client                    – Shared base client, errors, and constants
    multi_company_accounts    – 다중회사 주요계정 (fnlttMultiAcnt)
    single_company_statements – 단일회사 전체 재무제표 (fnlttSinglAcntAll)
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
)

# Endpoint modules
from .multi_company_accounts import MultiCompanyAccounts
from .single_company_statements import SingleCompanyStatements

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
    # Endpoint classes
    "MultiCompanyAccounts",
    "SingleCompanyStatements",
]
