# findata — 프로젝트 아키텍처

> **버전**: 0.2.0  
> **최종 업데이트**: 2026-06-16

---

## 개요

`findata`는 미국 SEC EDGAR와 한국 OpenDART에서 재무 데이터를 수집·분석하는 Python 패키지입니다.

프로젝트는 **두 개의 레이어**로 명확히 분리되어 있습니다:

| 레이어 | 패키지 경로 | 역할 | 디스크 I/O |
|--------|------------|------|-----------|
| **라이브러리 레이어** | `findata.sec`, `findata.dart` | SEC/DART API를 호출 → 메모리 데이터 반환 | SEC 공개 API는 없음, DART `save_*`는 명시적 저장 |
| **서버 레이어** | `findata.server` | FastAPI + SQLite 캐싱/영속 저장 | ✅ `~/.findata/` |

```
사용자 (ipynb, 스크립트)
    │
    ├── import findata            ← 라이브러리 레이어
    │     ├── findata.sec.*       ← SEC EDGAR 데이터
    │     └── findata.dart.*      ← OpenDART 데이터
    │
    └── python -m findata.server.app  ← 서버 레이어 (FastAPI + DB)
          ├── api/                ← REST API 엔드포인트
          ├── db/                 ← SQLite 스키마 & 쿼리
          └── ingestion/          ← 배치 데이터 적재
```

---

## 디렉토리 구조

```
finData/
├── pyproject.toml                 # 패키지 빌드 설정 (setuptools)
├── requirements.txt               # ML/분석용 의존성 (패키지와 별도)
├── .env                           # API 키 (TAVILY_API_KEY, OPEN_DART_API 등)
│
├── findata/                       # ═══ 메인 패키지 ═══
│   ├── __init__.py                # 퍼블릭 API 표면 (5개 함수)
│   │
│   ├── core/                      # ── 공통 설정 ──
│   │   └── config.py              # DATA_DIR 경로 (~/.findata)
│   │
│   ├── sec/                       # ── SEC EDGAR 라이브러리 ──
│   │   ├── form4.py               # get_insider_trades()
│   │   ├── filings.py             # get_filings(), get_filing_text()
│   │   ├── financials.py          # get_financials()
│   │   ├── transcripts.py         # get_transcript()
│   │   ├── _cik.py                # Ticker → CIK 변환
│   │   ├── const.py               # 공통 상수 (HEADERS, API 키)
│   │   ├── company_data.py        # 레거시 wrapper → server.company_data
│   │   ├── company_facts/         # XBRL CompanyFacts 처리
│   │   ├── agents/                # CIO 분석 에이전트 (LangGraph)
│   │   ├── utils/                 # 파서/스크래퍼 유틸리티
│   │   │   ├── form4/             # Form 4 파싱
│   │   │   ├── sec_10kq/          # 10-K/10-Q RSS & 파싱
│   │   │   ├── sec_filings/       # 8-K, S-4, SC 13D, 144 파서
│   │   │   └── earnings_call/     # 어닝스콜 트랜스크립트 검색
│   │   └── app.py                 # 레거시 wrapper → server.app
│   │
│   ├── dart/                      # ── OpenDART 라이브러리 ──
│   │   ├── __init__.py            # 모든 클래스/상수 re-export
│   │   ├── client.py              # OpenDartClient (HTTP 클라이언트 + 인증)
│   │   ├── api_types/             # API 엔드포인트별 래퍼 클래스
│   │   │   ├── multi_company_accounts.py
│   │   │   ├── multi_company_indicators.py
│   │   │   ├── single_company_statements.py
│   │   │   └── report_main_info.py
│   │   └── utils/                 # 데이터 가공/배치 유틸리티
│   │
│   └── server/                    # ── 상용 API 서버 ──
│       ├── app.py                 # FastAPI 엔트리포인트
│       ├── api/                   # 라우터 모듈
│       │   ├── api_form4.py       # /api/trades, /api/summary, ...
│       │   ├── api_10kq.py        # /api/documents, /api/financials, ...
│       │   ├── api_earnigscall.py # /api/transcript, ...
│       │   └── api_cio_chat.py    # /api/filings/chat, ...
│       ├── db/                    # SQLite DB 스키마 & 쿼리
│       │   ├── config.py          # DB 경로 상수 & 디렉토리 helper
│       │   ├── form4_db.py        # insider_watchlist.db, insider_all.db
│       │   ├── sec_10kq_db.py     # sec_10kq.db
│       │   ├── company_facts_db.py# company_facts.db
│       │   ├── earnings_db.py     # earnings_transcripts.db
│       │   └── sec_filings_db.py  # sec_filings.db
│       ├── ingestion/             # 배치 데이터 적재
│       │   ├── sec_10kq_ingest.py # 10-K/10-Q 배치 수집
│       │   └── dart_batch.py      # OpenDART 배치 수집
│       └── company_data.py        # 서버 전용 통합 데이터 오케스트레이터
│
└── docs/                          # ═══ 문서 ═══
    ├── architecture.md            # 이 파일 (전체 아키텍처)
    ├── getting_started.md         # 설치 & 빠른 시작
    ├── library/                   # 라이브러리 레이어 문서
    ├── server/                    # 서버 레이어 문서
    └── reference/                 # 외부 API 레퍼런스 (OpenDART 스펙 등)
```

---

## 설계 원칙

### 1. 라이브러리 ↔ 서버 분리
- **라이브러리 레이어**(`findata.sec`, `findata.dart`)는 외부 API 호출과 데이터 변환을 담당합니다. SEC 공개 API는 메모리 결과만 반환하고, DART의 `save_*` 메서드는 사용자가 명시적으로 호출할 때만 파일을 저장합니다.
- **서버 레이어**(`findata.server`)는 라이브러리 레이어를 감싸서 SQLite 캐싱, REST API, 배치 수집 기능을 추가합니다.

### 2. 선택적 의존성 (Optional Dependencies)
`pyproject.toml`에서 용도별 extras로 분리:
```
pip install findata              # 기본 (SEC 라이브러리)
pip install findata[dart]        # + OpenDART
pip install findata[server]      # + 전체 FastAPI 서버 (transcript/CIO 라우터 포함)
pip install findata[transcripts] # + Tavily (어닝스콜)
pip install findata[all]         # 모두 포함
```

### 3. 데이터 디렉토리
- 기본 경로: `~/.findata/`
- 환경변수 `FINDATA_DATA_DIR`로 변경 가능
- 서버 레이어가 DB 파일 생성/관리를 담당
- `findata.server.db.config` import만으로는 디렉토리를 생성하지 않으며, 서버 startup 또는 DB 연결 직전에 생성
