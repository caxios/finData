"""
OpenDart Base Client

Shared HTTP client, authentication, error handling, and constants
used by all OpenDART API modules.
"""

import csv
import json
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_URL = "https://opendart.fss.or.kr/api"

# Default data output directory (project_root/data/)
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Report type codes (보고서 코드)
REPORT_CODE_Q1 = "11013"      # 1분기보고서
REPORT_CODE_HALF = "11012"    # 반기보고서
REPORT_CODE_Q3 = "11014"     # 3분기보고서
REPORT_CODE_ANNUAL = "11011"  # 사업보고서

# Financial statement division (개별/연결 구분)
FS_DIV_SEPARATE = "OFS"       # 재무제표 (개별)
FS_DIV_CONSOLIDATED = "CFS"   # 연결재무제표

# Statement type division (재무제표 구분)
SJ_DIV_BS = "BS"    # 재무상태표 (Balance Sheet)
SJ_DIV_IS = "IS"    # 손익계산서 (Income Statement)
SJ_DIV_CIS = "CIS"  # 포괄손익계산서 (Comprehensive Income Statement)
SJ_DIV_CF = "CF"    # 현금흐름표 (Cash Flow Statement)
SJ_DIV_SCE = "SCE"  # 자본변동표 (Statement of Changes in Equity)

# API status codes
STATUS_SUCCESS = "000"
STATUS_MESSAGES = {
    "000": "정상",
    "010": "등록되지 않은 키입니다.",
    "011": "사용할 수 없는 키입니다.",
    "012": "접근할 수 없는 IP입니다.",
    "013": "조회된 데이타가 없습니다.",
    "020": "요청 제한을 초과하였습니다.",
    "100": "필드의 부적절한 값입니다.",
    "800": "원활한 공시서비스를 위하여 오픈API 서비스가 일시 중지 중입니다.",
    "900": "정의되지 않은 오류가 발생하였습니다.",
}

_VALID_REPRT_CODES = {REPORT_CODE_Q1, REPORT_CODE_HALF, REPORT_CODE_Q3, REPORT_CODE_ANNUAL}
_VALID_FS_DIVS = {FS_DIV_SEPARATE, FS_DIV_CONSOLIDATED}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class OpenDartError(Exception):
    """Base exception for OpenDART API errors."""

    def __init__(self, status: str, message: str):
        self.status = status
        self.message = message
        super().__init__(f"[{status}] {message}")


class OpenDartNoDataError(OpenDartError):
    """Raised when the API returns no data (status 013)."""
    pass


class OpenDartAuthError(OpenDartError):
    """Raised for authentication-related errors (status 010, 011, 012)."""
    pass


class OpenDartRateLimitError(OpenDartError):
    """Raised when request limit is exceeded (status 020)."""
    pass


# ---------------------------------------------------------------------------
# Base Client
# ---------------------------------------------------------------------------
class OpenDartClient:
    """Low-level HTTP client for OpenDART APIs.

    Handles authentication, request dispatch, and error mapping.
    All endpoint-specific modules inherit or compose this client.

    The API key is read from the ``OPEN_DART_API`` variable in ``.env``
    unless explicitly provided.
    """

    def __init__(self, api_key: Optional[str] = None):
        if api_key is None:
            load_dotenv()
            api_key = os.getenv("OPEN_DART_API")

        if not api_key:
            raise ValueError(
                "OpenDART API key is required. "
                "Pass it directly or set the OPEN_DART_API environment variable in .env."
            )

        self.api_key: str = api_key
        self._session = requests.Session()

    def request(self, endpoint: str, params: dict) -> dict:
        """Send a GET request and return the parsed JSON response.

        Raises:
            OpenDartAuthError: For authentication failures.
            OpenDartNoDataError: When no data matches the query.
            OpenDartRateLimitError: When the rate limit is exceeded.
            OpenDartError: For any other API error.
            requests.HTTPError: For HTTP-level errors.
        """
        params["crtfc_key"] = self.api_key
        url = f"{BASE_URL}/{endpoint}"

        logger.debug(
            "GET %s  params=%s",
            url,
            {k: v for k, v in params.items() if k != "crtfc_key"},
        )

        response = self._session.get(url, params=params, timeout=30)
        response.raise_for_status()

        data = response.json()
        status = data.get("status", "")
        message = data.get("message", STATUS_MESSAGES.get(status, "알 수 없는 오류"))

        if status != STATUS_SUCCESS:
            if status in ("010", "011", "012"):
                raise OpenDartAuthError(status, message)
            if status == "013":
                raise OpenDartNoDataError(status, message)
            if status == "020":
                raise OpenDartRateLimitError(status, message)
            raise OpenDartError(status, message)

        return data

    # ------------------------------------------------------------------
    # Validation helpers (used by endpoint modules)
    # ------------------------------------------------------------------
    @staticmethod
    def validate_reprt_code(reprt_code: str) -> None:
        if reprt_code not in _VALID_REPRT_CODES:
            raise ValueError(
                f"Invalid reprt_code '{reprt_code}'. Must be one of: {_VALID_REPRT_CODES}"
            )

    @staticmethod
    def validate_fs_div(fs_div: str) -> None:
        if fs_div not in _VALID_FS_DIVS:
            raise ValueError(
                f"Invalid fs_div '{fs_div}'. Must be one of: {_VALID_FS_DIVS}"
            )

    # ------------------------------------------------------------------
    # File save helpers
    # ------------------------------------------------------------------
    @staticmethod
    def save_data(
        items: list[dict],
        filename: str,
        sub_dir: str = "",
        fmt: str = "json",
        data_dir: Path | str | None = None,
    ) -> Path:
        """Save a list of dicts to a file inside the ``data/`` directory.

        Args:
            items:    The data list returned by an API ``get()`` call.
            filename: Base filename **without** extension.
                      e.g. ``"samsung_2024_annual"``.
            sub_dir:  Optional subdirectory under ``data/``.
                      e.g. ``"multi_accounts"`` → ``data/multi_accounts/``.
            fmt:      Output format — ``"json"`` (default) or ``"csv"``.
            data_dir: Override the output root directory.
                      Defaults to ``<project_root>/data/``.

        Returns:
            The ``Path`` of the saved file.

        Raises:
            ValueError: If *fmt* is not ``"json"`` or ``"csv"``.
            ValueError: If *items* is empty.
        """
        if fmt not in ("json", "csv"):
            raise ValueError(f"Unsupported format '{fmt}'. Use 'json' or 'csv'.")
        if not items:
            raise ValueError("No data to save (items list is empty).")

        root = Path(data_dir) if data_dir else DATA_DIR
        out_dir = root / sub_dir if sub_dir else root
        out_dir.mkdir(parents=True, exist_ok=True)

        filepath = out_dir / f"{filename}.{fmt}"

        if fmt == "json":
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
        else:  # csv
            fieldnames = list(items[0].keys())
            with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(items)
            
            # Apply CSV manipulation for financial statements
            try:
                from .data_processing import clean_financial_data
                clean_financial_data(str(filepath), str(filepath))
            except Exception as e:
                logger.warning("Failed to process CSV with data_processing: %s", e)

        logger.info("Saved %d records → %s", len(items), filepath)
        return filepath
