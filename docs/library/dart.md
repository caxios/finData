# OpenDART 라이브러리 레이어

> **패키지 경로**: `findata.dart`  
> **설계 원칙**: 클래스 기반 API 래퍼, OpenDART REST API 호출 → `list[dict]` 또는 `DataFrame` 반환

---

## 개요

`findata.dart`는 한국 금융감독원의 OpenDART API를 래핑하는 모듈입니다. 모든 클래스는 `OpenDartClient`를 상속받아 인증, 에러 처리, 파라미터 검증을 공통으로 사용합니다.

```python
from findata.dart import (
    OpenDartClient,
    SingleCompanyStatements,
    MultiCompanyAccounts,
    MultiCompanyIndicators,
    ReportMainInfo,
)
```

---

## 핵심 클라이언트 (`client.py`)

### `OpenDartClient`

모든 API 모듈이 상속받는 기반 클래스입니다.

| 기능 | 설명 |
|------|------|
| **인증** | `.env`의 `OPEN_DART_API` 키를 자동 로드 |
| **HTTP 통신** | `requests.Session` 기반 |
| **에러 처리** | API 응답 코드별 커스텀 예외 발생 |
| **파라미터 검증** | 보고서 코드, 재무제표 구분 등의 유효성 검사 |

### 커스텀 예외

| 예외 | 설명 |
|------|------|
| `OpenDartError` | 기본 에러 클래스 |
| `OpenDartNoDataError` | 조회된 데이터 없음 (응답 코드 013) |
| `OpenDartAuthError` | 인증 실패 (응답 코드 010, 011, 012) |
| `OpenDartRateLimitError` | 요청 제한 초과 (응답 코드 020) |

### 상수

**보고서 코드**:

| 상수 | 값 | 설명 |
|------|----|------|
| `REPORT_CODE_Q1` | `"11013"` | 1분기 보고서 |
| `REPORT_CODE_HALF` | `"11012"` | 반기 보고서 |
| `REPORT_CODE_Q3` | `"11014"` | 3분기 보고서 |
| `REPORT_CODE_ANNUAL` | `"11011"` | 사업보고서 |

**재무제표 구분**:

| 상수 | 값 | 설명 |
|------|----|------|
| `FS_DIV_SEPARATE` | `"OFS"` | 개별 재무제표 |
| `FS_DIV_CONSOLIDATED` | `"CFS"` | 연결 재무제표 |

**재무제표 종류 (`sj_div`)**:

| 상수 | 설명 |
|------|------|
| `SJ_DIV_BS` | 재무상태표 (Balance Sheet) |
| `SJ_DIV_IS` | 손익계산서 (Income Statement) |
| `SJ_DIV_CIS` | 포괄손익계산서 |
| `SJ_DIV_CF` | 현금흐름표 (Cash Flow) |
| `SJ_DIV_SCE` | 자본변동표 |

**재무지표 분류**:

| 상수 | 설명 |
|------|------|
| `IDX_PROFITABILITY` | 수익성 지표 |
| `IDX_STABILITY` | 안정성 지표 |
| `IDX_GROWTH` | 성장성 지표 |
| `IDX_ACTIVITY` | 활동성 지표 |

---

## API 엔드포인트 클래스 (`api_types/`)

### `MultiCompanyAccounts` — 다중회사 주요계정

OpenDART `fnlttMultiAcnt` API 래퍼입니다.

```python
acnt = MultiCompanyAccounts()
df = acnt.fetch(
    corp_codes=["005930", "000660"],
    bsns_year="2024",
    reprt_code=REPORT_CODE_ANNUAL,
)
```

여러 기업의 주요 재무계정(매출, 영업이익, 당기순이익 등)을 한 번에 조회합니다.

---

### `MultiCompanyIndicators` — 다중회사 주요 재무지표

OpenDART `fnlttCmpnyIndx` API 래퍼입니다.

```python
idx = MultiCompanyIndicators()
df = idx.fetch(
    corp_codes=["005930"],
    bsns_year="2024",
    reprt_code=REPORT_CODE_ANNUAL,
    idx_cl_code=IDX_PROFITABILITY,  # 수익성 지표만
)
```

ROE, ROA, PER 등 주요 재무지표를 조회합니다.

---

### `SingleCompanyStatements` — 단일회사 전체 재무제표

OpenDART `fnlttSinglAcntAll` API 래퍼입니다.

```python
stmt = SingleCompanyStatements()
df = stmt.fetch(
    "삼성전자",
    bsns_year="2024",
    reprt_code=REPORT_CODE_ANNUAL,
    fs_div=FS_DIV_CONSOLIDATED,  # 연결 재무제표
)
```

특정 기업의 전체 재무제표 (재무상태표, 손익계산서, 현금흐름표 등)를 조회합니다. 기업명 또는 고유번호(corp_code)로 조회할 수 있습니다.

---

### `ReportMainInfo` — 정기보고서 주요정보

OpenDART 주요사항보고서 관련 **30개 엔드포인트**를 래핑합니다.

```python
rpt = ReportMainInfo()

# 유상증자 결정 조회
df = rpt.fetch_piicDecsn(corp_code="005930", bgn_de="20240101", end_de="20241231")

# 전환사채 발행결정 조회
df = rpt.fetch_cvbdIsDecsn(corp_code="005930", bgn_de="20240101", end_de="20241231")
```

지원되는 주요 보고서 유형:
- 유상증자/무상증자/감자 결정
- 전환사채/신주인수권부사채/교환사채 발행결정
- 영업양수도/유형자산 양수도/타법인 주식 양수도 결정
- 회사합병/분할/주식교환 결정
- 자기주식 취득/처분 결정
- 부도발생/영업정지/회생절차/해산사유 등

---

## 유틸리티 (`dart/utils/`)

OpenDART 데이터를 가공하기 위한 유틸리티 모듈입니다.

| 모듈 | 역할 |
|------|------|
| `build_corp_codes.py` | 기업 고유번호 매핑 JSON 빌드 |
| `calculate_ratios.py` | 재무 비율 계산 (유동비율, 부채비율 등 30개 지표) |
| `data_processing.py` | 재무 데이터 전처리/가공 |
| `report_processing.py` | 보고서 데이터 후처리 |
| `scrape_opendart.py` | OpenDART 배치 스크래핑 |
| `get_companies.py` | 기업 목록 관리 |
| `fetch_quarterly_returns.py` | 분기별 주식 수익률 계산 |
