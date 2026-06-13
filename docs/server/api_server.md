# 서버 레이어 — 상용 API

> **패키지 경로**: `findata.server`  
> **역할**: 라이브러리 레이어를 감싸서 FastAPI REST API + SQLite 캐싱을 제공

---

## 개요

서버 레이어는 라이브러리의 순수 함수들 위에 아래 기능을 추가합니다:

1. **SQLite 캐싱**: 한 번 수집한 데이터를 로컬 DB에 저장하여 반복 호출 방지
2. **REST API**: FastAPI 기반 RESTful 엔드포인트
3. **캐시 신선도 관리**: TTL 기반으로 캐시 갱신 여부 판단
4. **배치 수집**: 다량의 데이터를 한 번에 수집하는 파이프라인

---

## 서버 시작 (`app.py`)

```bash
# 방법 1: 모듈로 실행
python -m findata.server.app

# 방법 2: uvicorn 직접 실행 (개발 모드)
uvicorn findata.server.app:app --reload --port 8000
```

- FastAPI 앱 인스턴스: `title="findata API Server"`
- CORS: 모든 출처 허용 (`allow_origins=["*"]`)
- Windows 호환: `asyncio.WindowsProactorEventLoopPolicy()` 자동 설정
- 4개 라우터 모듈 등록

---

## API 라우터 (`server/api/`)

### `api_form4.py` — 내부자 거래

| 엔드포인트 | 메서드 | 설명 |
|-----------|--------|------|
| `/api/trades` | GET | 내부자 거래 목록 (필터: ticker, owner, code, date, min_value) |
| `/api/trades/{trade_id}` | GET | 특정 거래 상세 정보 |
| `/api/summary` | GET | Ticker별 집계 통계 (총 거래 수, 매수/매도 금액, 고유 내부자 수) |
| `/api/form4/rankings` | GET | 순매수/순매도 기준 상위 N개 Ticker 랭킹 |
| `/api/watchlist` | GET | 추적 중인 Ticker 목록 |
| `/api/refresh` | POST | 수동 스크래핑 트리거 (`source=watchlist` 또는 `source=all`) |

**데이터 소스**: `insider_watchlist.db` + `insider_all.db` (중복 제거하여 합산)

---

### `api_10kq.py` — 공시 & 재무 데이터

| 엔드포인트 | 메서드 | 설명 |
|-----------|--------|------|
| `/api/documents/{ticker}/list` | GET | 10-K/10-Q 공시 목록 |
| `/api/documents/{ticker}/{accession}` | GET | 공시 상세 (Business, Risk Factors, MD&A, Notes) |
| `/api/financials/{ticker}/list` | GET | XBRL 재무 기간(FY/FQ) 목록 |
| `/api/financials/{ticker}/detail` | GET | 특정 기간의 모든 XBRL 팩트 |
| `/api/company-data/{ticker}` | GET | Form 4 + 10-K/Q 통합 데이터 |
| `/api/sec-filings/{ticker}` | GET | 다양한 Form 유형 메타데이터 |
| `/api/filing-text/{accession}` | GET | 8-K/S-4/SC13D/144 파싱 텍스트 |
| `/api/download-pdf` | GET | Playwright로 SEC 페이지 → PDF 변환 |

**캐시 전략**: DB에서 먼저 조회, 없으면 SEC EDGAR에서 실시간 수집 후 DB 저장

---

### `api_earnigscall.py` — 어닝스콜 트랜스크립트

| 엔드포인트 | 메서드 | 설명 |
|-----------|--------|------|
| `/api/transcript` | GET | 특정 Ticker/연도/분기의 트랜스크립트 (params: ticker, year, quarter, force_refresh) |
| `/api/transcripts/{ticker}/list` | GET | 저장된 어닝스콜 목록 |

**캐시 전략**: 첫 호출 시 Tavily API로 검색 → `earnings_transcripts.db`에 저장 → 이후 캐시 반환

---

### `api_cio_chat.py` — CIO 에이전트 대화

| 엔드포인트 | 메서드 | 설명 |
|-----------|--------|------|
| `/api/filings/chat` | POST | CIO 에이전트에게 메시지 전송 (body: `{user_message, session_id}`) |
| `/api/filings/chat/reset` | POST | 세션 대화 메모리 초기화 |

CIO 에이전트는 3개의 하위 분석 에이전트(재무/리스크/감성)를 조율하며, SQLite DB에서 데이터를 조회합니다.

---

## 데이터베이스 레이어 (`server/db/`)

### 경로 설정 (`config.py`)

모든 DB는 `~/.findata/` 하위에 생성됩니다 (`FINDATA_DATA_DIR` 환경변수로 변경 가능):

```
~/.findata/
├── sec_db/
│   ├── insider_watchlist.db       # 워치리스트 기반 Form 4
│   ├── insider_all.db             # RSS 피드 기반 Form 4
│   ├── sec_10kq.db                # 10-K/10-Q 파싱 결과
│   ├── company_facts.db           # XBRL CompanyFacts
│   └── earnings_transcripts.db   # 어닝스콜 트랜스크립트
├── dart_cache/                    # OpenDART 캐시
└── data/                          # 범용 데이터
```

### DB 모듈

| 모듈 | DB 파일 | 역할 |
|------|--------|------|
| `form4_db.py` | `insider_watchlist.db`, `insider_all.db` | Form 4 거래 저장/조회/집계 |
| `sec_10kq_db.py` | `sec_10kq.db` | 10-K/10-Q 파싱 결과 저장/조회 |
| `company_facts_db.py` | `company_facts.db` | XBRL 팩트 평탄화 저장 (UNIQUE 제약으로 중복 방지) |
| `earnings_db.py` | `earnings_transcripts.db` | 어닝스콜 트랜스크립트 캐싱 |
| `sec_filings_db.py` | (공용) | 다양한 Form 유형 메타데이터 |

---

## 통합 오케스트레이터 (`company_data.py`)

서버 전용 모듈로, DB 캐시와 SEC 스크래핑을 조합합니다.

### 캐시 신선도 정책
| 데이터 유형 | TTL | 설명 |
|------------|-----|------|
| 10-K/10-Q | 90일 | 분기마다 갱신 |
| Form 4 | 7일 | 내부자 거래는 빈번 |

### 동작 흐름
```
1. Ticker → CIK 변환
2. DB에서 캐시된 데이터 조회
3. 캐시 신선도/충분성 검사
4. 부족 시 SEC에서 실시간 스크래핑
5. 스크래핑 결과를 DB에 저장
6. 통합 결과 반환 (filings_10kq, form4_trades, cache_status)
```

---

## 배치 수집 (`server/ingestion/`)

대량의 데이터를 일괄 수집하기 위한 파이프라인입니다.

| 모듈 | 역할 |
|------|------|
| `sec_10kq_ingest.py` | 여러 Ticker의 10-K/10-Q를 배치로 수집하여 DB에 적재 |
| `dart_batch.py` | OpenDART 데이터를 배치로 수집하여 캐시에 적재 |

---

## 레거시 코드

> ⚠️ **`findata/sec/app.py`는 레거시 파일입니다.**  
> 리팩토링 이전의 FastAPI 엔트리포인트로, 상대 임포트(`from api import ...`)를 사용합니다.  
> 현재 정상 엔트리포인트는 `findata/server/app.py`입니다.  
> 향후 삭제 예정입니다.
