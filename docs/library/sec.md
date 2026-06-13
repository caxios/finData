# SEC 라이브러리 레이어

> **패키지 경로**: `findata.sec`  
> **설계 원칙**: 순수 함수, 디스크 I/O 없음, `list[dict]` 반환

---

## 퍼블릭 API

`findata.__init__.py`에서 아래 4개 함수를 최상위로 re-export합니다:

```python
import findata

findata.get_insider_trades(ticker)    # → Form 4 내부자 거래
findata.get_filings(ticker, ...)      # → 10-K/10-Q 공시 + 파싱
findata.get_filing_text(ticker, ...)  # → 8-K/S-4/SC13D/144 텍스트
findata.get_financials(ticker)        # → XBRL 재무 팩트
findata.get_transcript(ticker, ...)   # → 어닝스콜 트랜스크립트
```

---

## 모듈별 상세

### `form4.py` — 내부자 거래 (Form 4)

| 함수 | 설명 |
|------|------|
| `get_insider_trades(ticker, count)` | SEC EDGAR에서 Form 4 데이터를 수집하여 반환 |

- SEC의 최근 Form 4 RSS 피드 또는 개별 Ticker 페이지에서 데이터를 가져옵니다.
- `findata.sec.utils.form4` 모듈의 파서를 사용합니다.

---

### `filings.py` — 10-K/10-Q 공시

| 함수 | 설명 |
|------|------|
| `get_filings(ticker, form_type, count, parse_sections, ...)` | 10-K/10-Q 공시 메타데이터 + 파싱된 섹션 반환 |
| `get_filing_text(ticker, form, document_url, ...)` | 특정 공시(8-K, S-4, SC 13D, 144)의 텍스트 파싱 |

**`get_filings()` 파라미터**:
- `form_type`: 쉼표로 구분된 Form 유형 (기본값: `"10-K,10-Q"`)
- `count`: 반환할 공시 수 (기본값: `4`)
- `parse_sections`: `True`면 HTML을 다운로드하여 Business, Risk Factors, MD&A, Financial Notes 섹션을 추출. `False`면 메타데이터만 반환 (훨씬 빠름).
- `include_archive`: `True`면 오래된 공시 아카이브까지 포함.

**`get_filing_text()` 지원 Form 유형**: `8-K`, `S-4`, `SC 13D`, `SC 13G`, `144`

**의존 모듈**:
- `findata.sec.utils.sec_10kq.sec_10kq_rss` — EDGAR submissions JSON에서 공시 메타데이터 추출
- `findata.sec.utils.sec_10kq.sec_10kq_parser` — 10-K/10-Q HTML 파싱
- `findata.sec.utils.sec_filings.parser_8k` — 8-K 파서
- `findata.sec.utils.sec_filings.parser_s4` — S-4 파서
- `findata.sec.utils.sec_filings.parser_sc13` — SC 13D/G 파서
- `findata.sec.utils.sec_filings.parser_144` — Form 144 파서

---

### `financials.py` — XBRL 재무 팩트

| 함수 | 설명 |
|------|------|
| `get_financials(ticker)` | SEC CompanyFacts API에서 XBRL 관측값을 평탄화하여 반환 |

- `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json`에서 원본 JSON을 가져옵니다.
- 중첩된 JSON 구조 (`facts → taxonomy → concept → units → observations`)를 1차원 `list[dict]`로 변환합니다.
- 반환되는 키: `cik`, `taxonomy`, `concept`, `label`, `unit`, `period_start`, `period_end`, `val`, `accn`, `fy`, `fp`, `form`, `filed`, `frame`

---

### `transcripts.py` — 어닝스콜 트랜스크립트

| 함수 | 설명 |
|------|------|
| `get_transcript(ticker, year, quarter)` | Tavily API를 통해 어닝스콜 트랜스크립트 검색 |

- `pip install findata[transcripts]` 필요 (Tavily 의존성).
- 환경변수 `TAVILY_API_KEY` 필요.

---

### `_cik.py` — Ticker → CIK 변환

| 함수 | 설명 |
|------|------|
| `lookup_cik(ticker)` | Ticker 심볼을 SEC CIK 번호로 변환 |

- `sec-cik-mapper` 패키지를 사용합니다.
- `(cik: str, company_name: str)` 튜플을 반환합니다.

---

### `const.py` — 공통 상수

| 상수 | 설명 |
|------|------|
| `HEADERS` | SEC Fair Access 정책 준수를 위한 `User-Agent` 헤더 |
| `TAVILY_API_KEY` | 환경변수에서 읽은 Tavily API 키 |

---

## 유틸리티 모듈 (`findata.sec.utils/`)

라이브러리 함수들이 내부적으로 사용하는 파서와 스크래퍼입니다.

| 디렉토리 | 역할 |
|----------|------|
| `utils/form4/` | Form 4 XML 파싱, 워치리스트 기반 스크래핑 |
| `utils/sec_10kq/` | 10-K/10-Q RSS 피드 조회, HTML 파싱 (섹션 추출) |
| `utils/sec_filings/` | 8-K, S-4, SC 13D/G, 144 Form별 파서 |
| `utils/earnings_call/` | Tavily 기반 어닝스콜 트랜스크립트 검색 |

---

## CIO 분석 에이전트 (`findata.sec.agents/`)

LangGraph 기반의 금융 분석 에이전트 시스템입니다. 서버 레이어의 `/api/filings/chat` 엔드포인트에서 사용됩니다.

| 모듈 | 역할 |
|------|------|
| `conversational_cio.py` | CIO(Chief Investment Officer) ReAct 에이전트 |
| `data_loader.py` | 3개 분석 에이전트를 위한 데이터 로더 (DB → 구조화된 입력) |
| `run_analysis.py` | 재무/리스크/감성 분석 실행기 |
| `prompts.py` | 에이전트 프롬프트 템플릿 |
| `schemas.py` | Pydantic 스키마 (입출력 타입) |
| `tools.py` | 에이전트 도구 정의 (DB 조회, 분석 호출) |
| `graph.py` | LangGraph 그래프 정의 |
| `nodes.py` | 그래프 노드 구현 |
| `state.py` | 에이전트 상태 스키마 |
| `llm.py` | LLM 클라이언트 설정 |
| `persistence.py` | 대화 메모리 영속 저장 |
