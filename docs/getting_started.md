# 시작 가이드

---

## 1. 로컬 노트북에서 라이브러리로 사용하기

`findata` 라이브러리 계층은 SEC EDGAR 공개 API에서 데이터를 가져와 메모리에
`list[dict]` 형태로 반환합니다. 디스크에는 아무것도 저장하지 않습니다.

### 설치

```bash
# 프로젝트 루트(finData/)에서 editable 모드로 설치
pip install -e "."

# 전체 기능 포함 설치 (server + sec-parser)
pip install -e ".[all]"

# 특정 기능만 설치
pip install -e ".[server]"        # 상용 API 서버 (FastAPI, uvicorn, playwright, tavily, psycopg2)
pip install -e ".[transcripts]"   # 어닝스콜 트랜스크립트 (Tavily)
pip install -e ".[sec-parser]"    # 10-K/10-Q 섹션 파서(sec-parser) 사용
pip install -e ".[dev]"           # 테스트 (pytest)
```

> ℹ️ 기본 설치만으로 Form 4 / 10-K·10-Q / XBRL 재무 조회가 동작합니다.
> `get_transcript`는 Tavily가 필요하므로 `[transcripts]`(또는 `[server]`)를 함께 설치하세요.

### .env 설정

프로젝트 루트에 `.env` 파일을 생성하고 필요한 값을 추가합니다. 라이브러리
계층에서 필요한 것은 어닝스콜 검색용 Tavily 키뿐입니다:

```env
TAVILY_API_KEY=tvly-xxxxx         # 어닝스콜 트랜스크립트 검색 (get_transcript 사용 시)
```

> 서버 배포용 환경변수(`DATABASE_URL`, `FINDATA_GATEWAY_SECRET` 등)는 아래
> [2. 상용 API 서버로 배포하기](#2-상용-api-서버로-배포하기)의 환경변수 표를 참고하세요.

### 기본 사용법

```python
import findata

# ── SEC 내부자 거래 (Form 4) ──
trades = findata.get_insider_trades("AAPL")
# → list[dict] with keys: owner, title, date, code, shares, price, value, ...

# ── SEC 10-K/10-Q 공시 (파싱된 섹션 포함) ──
filings = findata.get_filings("AAPL", form_type="10-K", count=2)
# → list[dict] with keys: filing_date, form_type, business, risk_factors, mda, ...

# ── 빠른 메타데이터만 조회 (파싱 없이) ──
filings_meta = findata.get_filings("AAPL", parse_sections=False)

# ── XBRL 재무 팩트 ──
facts = findata.get_financials("AAPL")
# → list[dict] with keys: taxonomy, concept, label, unit, val, period_end, ...

# ── 어닝스콜 트랜스크립트 ──
# (requires: pip install "findata[transcripts]" + TAVILY_API_KEY)
transcript = findata.get_transcript("AAPL", year=2024, quarter=4)

# ── 특정 공시 텍스트 파싱 (8-K, S-4, SC 13D, 144) ──
parsed = findata.get_filing_text(
    ticker="AAPL",
    form="8-K",
    document_url="https://www.sec.gov/Archives/edgar/data/...",
)
```

공개 함수는 `findata` 최상위에 노출됩니다:
`get_insider_trades`, `get_filings`, `get_filing_text`, `get_financials`, `get_transcript`.

> ⚠️ 이전 버전에 있던 OpenDART(`findata.dart`) 라이브러리 계층은 현재 코드베이스에서
> 제거되었습니다. 지금 findata는 **SEC EDGAR 전용**입니다.

---

## 2. 상용 API 서버로 배포하기

서버 계층(`findata.server`)은 SEC 데이터를 로컬 DB에 캐싱해 제공하는 FastAPI
애플리케이션입니다. **모든 데이터 엔드포인트는 API 키 인증이 필요하고, 크레딧
단위로 과금·미터링**됩니다.

### 저장소 백엔드

연결은 `DATABASE_URL` 환경변수로 런타임에 선택됩니다:

- **미설정 (기본값)** → `FINDATA_DATA_DIR`(기본 `~/.findata`) 아래 파일별 SQLite.
  별도 DB 프로세스가 없어 단일 서버 프로토타입에 적합합니다.
- **`postgres://...` 설정** → PostgreSQL(psycopg2).

코드는 Postgres 방언(`%s` 플레이스홀더, `SERIAL` 등)으로 작성되어 있고, SQLite
백엔드에서는 엔진 래퍼가 자동으로 변환합니다.

### 로컬 실행

```bash
# 1) 서버 의존성 설치
pip install -e ".[server]"

# 2) 최초 1회: 계정 스키마 초기화 + API 키 발급 (아래 참고)
python -m findata.server.tools.issue_key --email me@example.com --plan owner

# 3) 서버 시작
python -m findata.server.app
# → FastAPI at http://0.0.0.0:8000
# → Swagger UI: http://localhost:8000/docs
```

시작 시 데이터 디렉터리와 계정/사용량/업스트림 비용 스키마가 자동으로 준비됩니다.

### API 키 발급 (관리자)

키 발급·조회는 `issue_key` CLI로 합니다. 발급된 `fd_live_...` 키는 **화면에 한
번만** 표시되므로 즉시 복사하세요.

```bash
# 소유자(owner) 계정 + 키 생성 — 무제한, 과금 게이트웨이 우회
python -m findata.server.tools.issue_key --email me@example.com --plan owner

# 무료(free) 사용자 키 생성
python -m findata.server.tools.issue_key --email user@example.com

# 라벨 지정 / 특정 사용자 키 목록 조회
python -m findata.server.tools.issue_key --email user@example.com --label "production"
python -m findata.server.tools.issue_key --email user@example.com --list
```

플랜(`--plan owner|free|pro`)에 따라 월 크레딧 한도와 레이트리밋이 정해집니다:

| 플랜 | 월 크레딧 | 레이트리밋(req/s, burst) | 월 요금 |
|------|-----------|--------------------------|---------|
| `owner` | 무제한 | 100 / 200 | $0 (개발자 전용) |
| `free`  | 1,000  | 2 / 10   | $0 |
| `pro`   | 50,000 | 10 / 30  | $49 |

### 인증 방식

데이터 요청 시 아래 헤더 중 하나로 API 키를 전달합니다:

```
X-API-Key: fd_live_xxxxx
# 또는
Authorization: Bearer fd_live_xxxxx
```

```python
import requests

resp = requests.get(
    "http://localhost:8000/v1/api/trades",
    params={"ticker": "NVDA", "limit": 10},
    headers={"X-API-Key": "fd_live_xxxxx"},
)
print(resp.json())
```

> 팀원(클라이언트) 관점의 상세 호출 예시는 [api_usage_guide.md](api_usage_guide.md)를 참고하세요.

### 크레딧 과금 모델

각 호출은 실제 비용에 비례한 **크레딧**을 소비합니다. 캐시 읽기는 저렴하고
(1 크레딧), 업스트림(EDGAR/Tavily) 호출을 유발하는 엔드포인트는 가중치가 높습니다.
캐시 미스로 온디맨드 페치가 발생하면 기본 비용 위에 추가 크레딧이 붙습니다.
정확한 가중치는 [`findata/server/billing/costs.py`](../findata/server/billing/costs.py)가
단일 진실 공급원입니다.

### API 엔드포인트 요약

모든 데이터 엔드포인트는 `/v1` 프리픽스 아래에 있으며 인증이 필요합니다.

| 엔드포인트 | 메서드 | 크레딧 | 설명 |
|-----------|--------|:-----:|------|
| `/v1/api/trades` | GET | 1 (+3 페치 시) | Form 4 내부자 거래 목록 (필터/페이지네이션, 온디맨드 백필) |
| `/v1/api/trades/{id}` | GET | 1 | 특정 거래 상세 |
| `/v1/api/summary` | GET | 1 | Ticker별 거래 집계 통계 |
| `/v1/api/form4/rankings` | GET | 1 | 순매수/순매도 Ticker 랭킹 |
| `/v1/api/watchlist` | GET | 1 | 추적 중인 Ticker 목록 |
| `/v1/api/refresh` | POST | 5 | 수동 스크래핑 트리거 |
| `/v1/api/documents/{ticker}/list` | GET | 1 | 10-K/10-Q 공시 목록 (DB-first, 미스 시 페치) |
| `/v1/api/documents/{ticker}/{accession}` | GET | 1 | 공시 상세 (파싱된 섹션 + 재무 노트) |
| `/v1/api/financials/{ticker}/list` | GET | 1 | XBRL 재무 기간 목록 |
| `/v1/api/financials/{ticker}/detail` | GET | 1 | 특정 기간 XBRL 팩트 |
| `/v1/api/company-data/{ticker}` | GET | 3 | 통합 데이터 (Form 4 + 10-K/Q, 오케스트레이터) |
| `/v1/api/sec-filings/{ticker}` | GET | 2 | 다양한 Form 유형 메타데이터 (라이브 submissions.json) |
| `/v1/api/filing-text/{accession}` | GET | 3 | 8-K/S-4/SC13D/144 파싱 텍스트 |
| `/v1/api/download-pdf` | GET | 5 | SEC 페이지 PDF 변환 (기본 비활성, `ENABLE_PDF_DOWNLOAD=1` 필요) |
| `/v1/api/transcript` | GET | 10 | 어닝스콜 트랜스크립트 (Tavily 업스트림) |
| `/v1/api/transcripts/{ticker}/list` | GET | 1 | 저장된 어닝스콜 목록 |

시스템/관리 엔드포인트:

| 엔드포인트 | 메서드 | 인증 | 설명 |
|-----------|--------|------|------|
| `/health` | GET | 없음 | 헬스체크 |
| `/v1/api/health/poller` | GET | 없음 | Form 4 백그라운드 폴러 상태 |
| `/v1/api/usage` | GET | API 키 | 호출자 본인의 이번 청구 기간 크레딧 사용량 |
| `/v1/api/admin/upstream-costs` | GET | owner | 엔드포인트별 업스트림 비용 요약 (크레딧 가중치 보정용) |

> ⚠️ 이전 버전의 CIO 채팅 엔드포인트(`/api/filings/chat`, `/api/filings/chat/reset`)는
> 현재 서버 앱에 라우터로 등록되어 있지 않습니다.

### 엔드포인트별 파라미터 레퍼런스 및 사용 예시

아래는 각 엔드포인트가 받을 수 있는 **모든 파라미터**에 대한 상세 설명과
코드 예시입니다. 공통 설정을 먼저 정의해 두고 재사용합니다.

```python
import requests

BASE = "http://localhost:8000"          # 배포 주소로 교체
HEADERS = {"X-API-Key": "fd_live_xxxxx"}  # 발급받은 키로 교체


def get(path, **params):
    r = requests.get(f"{BASE}{path}", params=params, headers=HEADERS)
    r.raise_for_status()
    return r.json()


def post(path, **params):
    r = requests.post(f"{BASE}{path}", params=params, headers=HEADERS)
    r.raise_for_status()
    return r.json()
```

---

#### Form 4 (내부자 거래)

##### `GET /v1/api/trades` — 내부자 거래 목록 (필터 + 페이지네이션)

캐시에 데이터가 없을 경우 SEC EDGAR에서 온디맨드로 백필합니다.

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|:----:|--------|------|
| `source` | `string` | ✗ | `"watchlist"` | DB 소스. `"watchlist"` 또는 `"all"` |
| `ticker` | `string[]` | ✗ | — | 필터링할 티커. 반복 파라미터로 여러 개 지정 가능 (`?ticker=NVDA&ticker=AAPL`) |
| `owner` | `string` | ✗ | — | 내부자 이름으로 필터링 |
| `code` | `string` | ✗ | — | 거래 유형 코드. `"P"` = 매수, `"S"` = 매도 |
| `acquired_or_disposed` | `string` | ✗ | — | `"A"` = 취득, `"D"` = 처분 |
| `date_from` | `string` | ✗ | — | 시작일 (YYYY-MM-DD). 기간 범위 필터용 |
| `date_to` | `string` | ✗ | — | 종료일 (YYYY-MM-DD). 기간 범위 필터용 |
| `min_value` | `float` | ✗ | — | 최소 거래 금액 (USD) 필터 |
| `limit` | `int` | ✗ | `100` | 반환할 최대 건수 (1–500) |
| `offset` | `int` | ✗ | `0` | 페이지네이션 오프셋 (0 이상) |
| `auto_refresh` | `bool` | ✗ | `true` | `true`면 캐시 미스 시 SEC에서 자동 페치. `false`면 읽기 전용 |
| `count` | `int` | ✗ | `5` | 캐시 미스 시 티커당 가져올 Form 4 공시 수 (1–100) |

**응답 형식**: `{"total": int, "limit": int, "offset": int, "trades": [...]}`

```python
trades = get(
    "/v1/api/trades",
    source="watchlist",
    ticker=["NVDA", "AAPL"],   # requests 가 ?ticker=NVDA&ticker=AAPL 로 전개
    code="P",                  # P=매수, S=매도
    date_from="2024-01-01",
    date_to="2024-12-31",
    min_value=1_000_000,
    limit=50,
    offset=0,
    auto_refresh=True,
    count=5,
)
```

##### `GET /v1/api/trades/{trade_id}` — 단일 거래 상세

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|:----:|--------|------|
| `trade_id` | `int` (path) | ✔ | — | 조회할 거래의 DB row ID |
| `source` | `string` | ✗ | `"watchlist"` | DB 소스. `"watchlist"` 또는 `"all"` |

**응답 형식**: 거래 상세 정보 dict (모든 컬럼 포함)

```python
trade = get("/v1/api/trades/123", source="watchlist")
```

##### `GET /v1/api/summary` — Ticker별 집계 통계

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|:----:|--------|------|
| `source` | `string` | ✗ | `"watchlist"` | DB 소스. `"watchlist"` 또는 `"all"` |

**응답 형식**: `{"summary": [...]}`  — 티커별 거래 건수, 총 금액, 내부자 수 등

```python
summary = get("/v1/api/summary", source="watchlist")
```

##### `GET /v1/api/form4/rankings` — 순매수/순매도 랭킹

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|:----:|--------|------|
| `source` | `string` | ✗ | `"watchlist"` | DB 소스. `"watchlist"` 또는 `"all"` |
| `n` | `int` | ✗ | `10` | 상위 N개 티커 반환 (1–50) |
| `ticker` | `string` | ✗ | — | 특정 티커 지정 시 해당 티커의 단일 집계 객체 반환 |
| `date_from` | `string` | ✗ | — | 시작일 (YYYY-MM-DD) |
| `date_to` | `string` | ✗ | — | 종료일 (YYYY-MM-DD) |

**응답 형식**:
- `ticker` 미지정: `{"n": int, "top_net_buying": [...], "top_net_selling": [...]}`
- `ticker` 지정: 해당 티커의 단일 집계 객체

```python
# Top 10 랭킹
rankings = get("/v1/api/form4/rankings", source="watchlist", n=10,
               date_from="2024-01-01", date_to="2024-12-31")

# 특정 티커 집계
nvda_rank = get("/v1/api/form4/rankings", ticker="NVDA")
```

##### `GET /v1/api/watchlist` — 추적 중인 Ticker 목록

파라미터 없음.

**응답 형식**: `{"watchlist": ["AAPL", "NVDA", ...]}`

```python
watchlist = get("/v1/api/watchlist")
```

##### `POST /v1/api/refresh` — 수동 스크래핑 트리거

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|:----:|--------|------|
| `source` | `string` | ✗ | `"watchlist"` | `"watchlist"` → 티커별 스크래핑, `"all"` → RSS 최신 100건 |
| `count` | `int` | ✗ | `5` | 티커당 가져올 공시 수 (1–40, watchlist 모드 전용) |

**응답 형식**: `{"status": "ok", "source": "...", "inserted": int, "skipped": int}`

```python
result = post("/v1/api/refresh", source="watchlist", count=5)
```

---

#### 10-K / 10-Q · XBRL 재무 · 공시

##### `GET /v1/api/documents/{ticker}/list` — 10-K/10-Q 공시 목록

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|:----:|--------|------|
| `ticker` | `string` (path) | ✔ | — | 주식 심볼 (예: `"AAPL"`) |

DB에 캐시가 없으면 SEC EDGAR에서 자동으로 페치 후 저장합니다.

**응답 형식**: `{"filings": [{"accession_number", "form_type", "filing_date", "company_name"}, ...]}`

```python
docs = get("/v1/api/documents/AAPL/list")
```

##### `GET /v1/api/documents/{ticker}/{accession_number}` — 공시 상세

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|:----:|--------|------|
| `ticker` | `string` (path) | ✔ | — | 주식 심볼 |
| `accession_number` | `string` (path) | ✔ | — | SEC accession number |

**응답 형식**: `{"company_name", "form_type", "filing_date", "business", "risk_factors", "mda", "financial_notes": [{"note_key", "note_text"}, ...]}`

```python
acc = docs["filings"][0]["accession_number"]
detail = get(f"/v1/api/documents/AAPL/{acc}")
```

##### `GET /v1/api/financials/{ticker}/list` — XBRL 재무 기간 목록

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|:----:|--------|------|
| `ticker` | `string` (path) | ✔ | — | 주식 심볼 |

DB에 캐시가 없으면 SEC CompanyFacts API에서 자동 페치 후 저장합니다.

**응답 형식**: `{"periods": [{"fy", "fp", "form", "filed", "fact_count"}, ...]}`

```python
periods = get("/v1/api/financials/AAPL/list")
```

##### `GET /v1/api/financials/{ticker}/detail` — 특정 기간 XBRL 팩트

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|:----:|--------|------|
| `ticker` | `string` (path) | ✔ | — | 주식 심볼 |
| `fy` | `int` | ✔ | — | 회계연도 (예: `2024`). `/list` 결과에서 사용 |
| `fp` | `string` | ✔ | — | 회계분기 (예: `"Q1"`, `"FY"`). `/list` 결과에서 사용 |
| `form` | `string` | ✔ | — | 공시 유형 (예: `"10-K"`). `/list` 결과에서 사용 |
| `filed` | `string` | ✔ | — | 제출일 (YYYY-MM-DD). `/list` 결과에서 사용 |

**응답 형식**: `{"facts": [{"concept", "label", "val", "unit", "fy", "fp", "form", "period_end", "filed"}, ...]}`

```python
p = periods["periods"][0]
facts = get("/v1/api/financials/AAPL/detail",
            fy=p["fy"], fp=p["fp"], form=p["form"], filed=p["filed"])
```

##### `GET /v1/api/company-data/{ticker}` — 통합 데이터 (Form 4 + 10-K/Q)

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|:----:|--------|------|
| `ticker` | `string` (path) | ✔ | — | 주식 심볼 |
| `limit` | `int` | ✗ | `4` | 반환할 10-K/10-Q 수 (1–1000). DB에 부족하면 SEC에서 추가 스크래핑 |
| `limit_form4` | `int` | ✗ | `30` | 반환할 Form 4 내부자 거래 수 (1–1000) |
| `include_archive` | `bool` | ✗ | `false` | `true`면 오래된 공시 아카이브까지 순회하여 전체 이력 포함 |

**에러 코드**: `404` (미확인 티커), `503` (SEC 레이트리밋, `Retry-After` 헤더 포함), `502` (업스트림 오류)

```python
company = get("/v1/api/company-data/NVDA",
              limit=4,
              limit_form4=30,
              include_archive=False)
```

##### `GET /v1/api/sec-filings/{ticker}` — 다양한 Form 메타데이터 (라이브)

EDGAR `submissions.json`에서 실시간으로 가져옵니다 (DB 캐시 없음, 섹션 파싱 없음).

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|:----:|--------|------|
| `ticker` | `string` (path) | ✔ | — | 주식 심볼 |
| `forms` | `string` | ✗ | `"10-K,10-Q"` | 쉼표로 구분된 Form 유형. 지원: `10-K`, `10-Q`, `8-K`, `S-4`, `SC 13D`, `SC 13G`, `144`, `4` |
| `limit` | `int` | ✗ | `20` | 반환할 최대 공시 수 (1–1000) |
| `include_archive` | `bool` | ✗ | `false` | `true`면 오래된 공시 아카이브까지 순회 |

**응답 형식**: `{"ticker": "AAPL", "cik": "...", "filings": [{...}, ...]}`  
— 10-K/10-Q 항목에는 `has_business`, `has_risk_factors`, `has_mda` 캐시 플래그가 추가됩니다.

```python
sec_filings = get("/v1/api/sec-filings/AAPL",
                  forms="10-K,10-Q,8-K",
                  limit=20,
                  include_archive=False)
```

##### `GET /v1/api/filing-text/{accession_number}` — 파싱된 공시 텍스트

8-K, S-4, SC 13D, SC 13G, 144 공시의 파싱된 텍스트 섹션을 반환합니다.

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|:----:|--------|------|
| `accession_number` | `string` (path) | ✔ | — | SEC accession number |
| `form` | `string` | ✔ | — | Form 유형 (`"8-K"`, `"S-4"`, `"SC 13D"`, `"SC 13G"`, `"144"`) |
| `document_url` | `string` | ✔ | — | 원본 문서 URL |
| `ticker` | `string` | ✗ | — | CIK 해석용 티커 (신규 파싱 시 유용) |
| `filing_date` | `string` | ✗ | — | 제출일 (YYYY-MM-DD) |

> 10-K/10-Q는 이 엔드포인트가 아닌 `/api/documents/*` 를 사용하세요.

```python
text = get(
    "/v1/api/filing-text/0000320193-24-000123",
    form="8-K",
    document_url="https://www.sec.gov/Archives/edgar/data/320193/.../form8k.htm",
    ticker="AAPL",
    filing_date="2024-05-01",
)
```

##### `GET /v1/api/download-pdf` — SEC 페이지 PDF 변환

서버에 `ENABLE_PDF_DOWNLOAD=1` 환경변수가 설정되어 있어야 합니다 (Playwright + Chromium 필요).  
응답은 JSON이 아닌 `application/pdf` 바이트입니다.

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|:----:|--------|------|
| `url` | `string` | ✔ | — | PDF로 변환할 SEC 페이지 URL |

```python
r = requests.get(f"{BASE}/v1/api/download-pdf",
                 params={"url": "https://www.sec.gov/Archives/edgar/data/..."},
                 headers=HEADERS)
r.raise_for_status()
with open("filing.pdf", "wb") as f:
    f.write(r.content)
```

---

#### 어닝스콜 트랜스크립트

##### `GET /v1/api/transcript` — 어닝스콜 트랜스크립트 조회

첫 호출 시 Tavily API를 통해 검색·캐시합니다. 이후 호출은 DB에서 반환합니다.

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|:----:|--------|------|
| `ticker` | `string` | ✔ | — | 주식 심볼 (예: `"AAPL"`) |
| `year` | `int` | ✔ | — | 회계연도 (예: `2024`) |
| `quarter` | `int` | ✔ | — | 회계분기 (1–4) |
| `force_refresh` | `bool` | ✗ | `false` | `true`면 캐시를 무시하고 Tavily에서 재검색 |

> ⚠️ 캐시 미스 또는 `force_refresh=true` 시 Tavily API 호출이 발생하며, 크레딧 소비가 높습니다 (10 크레딧).

```python
transcript = get("/v1/api/transcript",
                 ticker="AAPL", year=2024, quarter=4,
                 force_refresh=False)
```

##### `GET /v1/api/transcripts/{ticker}/list` — 저장된 트랜스크립트 목록

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|:----:|--------|------|
| `ticker` | `string` (path) | ✔ | — | 주식 심볼 |

**응답 형식**: `{"transcripts": [{"fiscal_year", "fiscal_quarter", "call_date", "title"}, ...]}`

```python
tx_list = get("/v1/api/transcripts/AAPL/list")
```

#### 시스템 · 관리

```python
# GET /health — 헬스체크 (인증 불필요)
requests.get(f"{BASE}/health").json()          # → {"status": "ok"}

# GET /v1/api/health/poller — Form 4 폴러 상태 (인증 불필요)
requests.get(f"{BASE}/v1/api/health/poller").json()

# GET /v1/api/usage — 본인의 이번 청구 기간 크레딧 사용량 (API 키 필요)
usage = get("/v1/api/usage")
# → {..., "plan": "free", "credits_limit": 1000}

# GET /v1/api/admin/upstream-costs — 엔드포인트별 업스트림 비용 (owner 플랜 전용)
costs = get("/v1/api/admin/upstream-costs")
```

> 💡 `X-API-Key` 헤더 대신 `Authorization: Bearer fd_live_xxxxx` 형식도 동일하게 동작합니다.

### 주요 환경변수

| 변수 | 기본값 | 용도 |
|------|--------|------|
| `DATABASE_URL` | (미설정) | 설정 시 Postgres 사용, 미설정 시 SQLite |
| `FINDATA_DATA_DIR` | `~/.findata` | SQLite DB/데이터 저장 위치 |
| `TAVILY_API_KEY` | — | 어닝스콜 트랜스크립트 검색 |
| `FINDATA_GATEWAY_SECRET` | (미설정) | 설정 시 과금 게이트웨이 경유 강제 (owner는 우회) |
| `FINDATA_CORS_ORIGINS` | `*` | 허용 CORS 오리진 (쉼표 구분) |
| `ENABLE_FORM4_POLLER` | `0` | `1`이면 Form 4 실시간 폴러 시작 (단일 인스턴스만) |
| `FORM4_POLL_INTERVAL` | (폴러 기본값) | 폴링 주기(초) |
| `ENABLE_SCHEDULED_INGESTION` | `0` | `1`이면 재무/공시 예약 인제스션 시작 (단일 인스턴스만) |
| `ENABLE_PDF_DOWNLOAD` | `0` | `1`이면 Playwright PDF 렌더 활성화 (Chromium 필요) |

> 폴러/스케줄러는 쓰기 경합 방지를 위해 **한 프로세스에서만** 켜야 합니다.
> 멀티 인스턴스 배포에서는 별도 워커(`findata.server.worker`)로 실행하세요.

### 프로덕션 배포 시 추가 작업

인증·미터링·과금·레이트리밋은 이미 서버에 구현되어 있습니다. 프로덕션 배포를
위해 추가로 필요한 인프라 항목은 다음과 같습니다:

- [x] **인증(Authentication)**: API 키 인증 + 사용량 미터링 (구현됨)
- [x] **과금/쿼터**: 크레딧 기반 미터링, 플랜별 월 한도·레이트리밋 (구현됨)
- [ ] **컨테이너화**: `Dockerfile`, `docker-compose.yml`
- [ ] **클라우드 배포**: AWS/GCP/Azure 설정, CI/CD 파이프라인
- [ ] **HTTPS**: 리버스 프록시 (nginx), SSL 인증서
- [ ] **모니터링**: 로깅, 헬스체크, 에러 트래킹 (Sentry 등)
- [ ] **과금 게이트웨이**: 외부 게이트웨이(예: RapidAPI) 연동 시 `FINDATA_GATEWAY_SECRET` 구성
