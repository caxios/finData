# SEC 라이브러리 레이어

> **패키지 경로**: `findata.sec`  
> **설계 원칙**: 순수 함수, 디스크 I/O 없음, `list[dict]` 반환

---

## 로컬 환경 설치 및 설정 (프로토타이핑/테스트용)

아직 PyPI에 배포하지 않은 상태에서 Jupyter Notebook(`.ipynb`)이나 로컬 스크립트에서 패키지를 사용하려면, 소스 코드가 있는 디렉토리에서 **Editable 모드(`-e`)**로 로컬 설치해야 합니다. 이렇게 설치하면 파이썬이 `pyproject.toml`에 명시된 필수 외부 라이브러리(`sec-cik-mapper`, `requests`, `beautifulsoup4` 등)를 알아서 한 번에 설치해 주고, 패키지 내부 코드 변경 사항도 실시간으로 반영됩니다.

**터미널에서 다음 명령어 실행:**

```bash
# 1. findata 폴더(프로젝트 루트)로 이동
cd c:\finData

# 2. 로컬 설치 (의존성 자동 설치 포함)
pip install -e .

# 3. 만약 PDF 다운로드나 어닝스콜 기능이 추가로 필요하다면 아래 명령어로 설치
pip install -e .[server,transcripts]
playwright install chromium
```

이제 `.ipynb` 파일이나 파이썬 스크립트 어디에서든 `sys.path` 조작 없이 깔끔하게 `import findata`만 적어주면 바로 패키지를 사용할 수 있습니다!

### 💡 팁: 불러온 데이터를 파일(Excel, TXT)로 추출하기 (Jupyter Notebook 활용)

`findata` 패키지의 데이터 수집 함수들은 결과를 파이썬 기본 딕셔너리 리스트(`list[dict]`)로 반환합니다. 이를 `pandas` 라이브러리를 활용해 DataFrame으로 변환하면 아주 쉽게 데이터 파일로 저장할 수 있습니다.

```python
import pandas as pd
import findata

# 1. 패키지 함수로 데이터 불러오기
facts = findata.get_financials("AAPL")

# 2. DataFrame으로 변환
facts_df = pd.DataFrame(facts)

# 3. Excel (.xlsx) 파일로 저장
excel_filename = "AAPL_financial_facts.xlsx"
facts_df.to_excel(excel_filename, index=False)
print(f"데이터를 '{excel_filename}' 파일로 저장했습니다.")

# 4. Text (.txt) 파일로 저장 (탭으로 구분)
txt_filename = "AAPL_financial_facts.txt"
facts_df.to_csv(txt_filename, sep='\t', index=False)
print(f"데이터를 '{txt_filename}' 파일로 저장했습니다.")
```

---

## 퍼블릭 API

`findata.__init__.py`에서 아래 6개 함수를 최상위로 re-export합니다:

```python
import findata

findata.get_insider_trades(ticker)       # → Form 4 내부자 거래
findata.get_filings(ticker, ...)         # → 10-K/10-Q 공시 + 파싱
findata.get_filing_text(ticker, ...)     # → 8-K/S-4/SC13D/144 텍스트
findata.get_financials(ticker)           # → XBRL 재무 팩트
findata.get_transcript(ticker, ...)      # → 어닝스콜 트랜스크립트
findata.download_filing_pdf(url, ...)    # → SEC 공시 PDF 다운로드
```

---

## 모듈별 상세

### `form4.py` — 내부자 거래 (Form 4)

#### `get_insider_trades(ticker, count, delay)`

SEC EDGAR에서 Form 4 XML을 수집·파싱하여 내부자 거래 데이터를 반환합니다.
각 (owner × transaction) 조합이 하나의 dict으로 평탄화됩니다.

**파라미터:**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|:----:|--------|------|
| `ticker` | `str` | ✔ | — | 주식 심볼 (예: `"AAPL"`) |
| `count` | `int` | ✗ | `5` | 가져올 최근 Form 4 공시 수 |
| `delay` | `float` | ✗ | `0.2` | SEC 요청 사이의 대기 시간(초). SEC Fair Access 정책 준수용 |

**반환값:** `list[dict[str, Any]]` — `transaction_date` 기준 내림차순 정렬

반환되는 dict의 주요 키:

| 키 | 설명 |
|----|------|
| `ticker` | 주식 심볼 |
| `owner_name` | 내부자 이름 |
| `officer_title` | 직책 (예: `"CEO"`, `"CFO"`) |
| `is_director` | 이사 여부 |
| `is_officer` | 임원 여부 |
| `is_ten_pct_owner` | 10% 이상 주주 여부 |
| `transaction_date` | 거래일 |
| `transaction_code` | 거래 유형 코드 (`P` = 매수, `S` = 매도 등) |
| `security_title` | 증권 종류 |
| `shares` | 거래 주식 수 |
| `price_per_share` | 주당 가격 |
| `transaction_value` | 총 거래 금액 |
| `source_url` | 원본 Form 4 문서 URL |
| `period_of_report` | 보고 기간 |
| `issuer_name` | 발행사 이름 |
| `issuer_cik` | 발행사 CIK |

**예외:** `ValueError` — 티커가 CIK로 변환될 수 없는 경우

**예시:**

```python
import findata

# 기본 사용: 최근 5건의 Form 4
trades = findata.get_insider_trades("AAPL")
for t in trades:
    print(f"{t['owner_name']} | {t['transaction_code']} | "
          f"{t.get('shares', 'N/A')} shares @ ${t.get('price_per_share', 'N/A')}")

# 더 많은 공시 가져오기 (SEC 레이트리밋 주의)
trades = findata.get_insider_trades("NVDA", count=20, delay=0.3)

# 매수(P)만 필터링
buys = [t for t in trades if t.get("transaction_code") == "P"]
print(f"최근 매수 건수: {len(buys)}")

# 특정 기간의 대규모 거래만 추출
big_trades = [
    t for t in trades
    if t.get("transaction_value") and t["transaction_value"] > 1_000_000
]
```

---

### `filings.py` — 10-K/10-Q 공시

#### `get_filings(ticker, form_type, count, include_archive, parse_sections, delay)`

SEC EDGAR의 submissions JSON에서 공시 메타데이터를 수집하고, 선택적으로
각 공시의 HTML을 다운로드하여 Business, Risk Factors, MD&A, Financial Notes
섹션을 파싱합니다.

**파라미터:**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|:----:|--------|------|
| `ticker` | `str` | ✔ | — | 주식 심볼 (예: `"AAPL"`) |
| `form_type` | `str` | ✗ | `"10-K,10-Q"` | 쉼표로 구분된 Form 유형 |
| `count` | `int` | ✗ | `4` | 반환할 공시 수 |
| `include_archive` | `bool` | ✗ | `False` | `True`면 오래된 공시 아카이브까지 순회하여 전체 이력 포함 |
| `parse_sections` | `bool` | ✗ | `True` | `True`면 HTML을 다운로드하여 섹션 추출. `False`면 메타데이터만 반환 (훨씬 빠름) |
| `delay` | `float` | ✗ | `0.2` | SEC 요청 사이의 대기 시간(초) |

**반환값:** `list[dict[str, Any]]` — `filing_date` 기준 내림차순 정렬

`parse_sections=True` 시 반환 dict의 주요 키:

| 키 | 설명 |
|----|------|
| `accession_number` | SEC accession number |
| `form_type` | 공시 유형 (`"10-K"`, `"10-Q"`) |
| `filing_date` | 제출일 |
| `company_name` | 회사명 |
| `document_url` | 원본 문서 URL |
| `business` | 사업 개요 섹션 (Item 1) |
| `risk_factors` | 위험 요인 섹션 (Item 1A) |
| `mda` | 경영진 토의 및 분석 섹션 (Item 7) |
| `financial_notes` | 재무제표 주석 목록 |

**예외:** `ValueError` — 티커가 CIK로 변환될 수 없는 경우

**예시:**

```python
import findata

# 최근 10-K/10-Q 4건 가져오기 (파싱 포함)
filings = findata.get_filings("AAPL")
for f in filings:
    print(f"{f['form_type']} | {f['filing_date']}")
    if f.get("risk_factors"):
        print(f"  Risk Factors: {f['risk_factors'][:200]}...")

# 10-K만 가져오기
annual = findata.get_filings("MSFT", form_type="10-K", count=3)

# 메타데이터만 빠르게 조회 (파싱 없이)
meta_only = findata.get_filings("GOOGL", parse_sections=False, count=10)
for m in meta_only:
    print(f"{m['form_type']} | {m['filing_date']} | {m['accession_number']}")

# 전체 이력 포함
full_history = findata.get_filings(
    "TSLA", count=20, include_archive=True, parse_sections=False
)
```

---

#### `get_filing_text(ticker, form, document_url, accession_number, filing_date)`

8-K, S-4, SC 13D, SC 13G, Form 144 등 특정 공시 문서를 다운로드하여
Form별 전용 파서로 텍스트 섹션을 추출합니다.

**파라미터:**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|:----:|--------|------|
| `ticker` | `str` | ✔ | — | 주식 심볼 |
| `form` | `str` | ✔ | — | Form 유형. 지원: `"8-K"`, `"S-4"`, `"SC 13D"`, `"SC 13G"`, `"144"` |
| `document_url` | `str` | ✔ | — | 원본 문서의 SEC URL |
| `accession_number` | `str` | ✗ | `""` | SEC accession number (메타데이터용) |
| `filing_date` | `str \| None` | ✗ | `None` | 제출일 (YYYY-MM-DD, 메타데이터용) |

**반환값:** `dict[str, Any] | None` — 파싱된 공시 dict, 실패 시 `None`

반환 dict에 자동 추가되는 키: `cik`, `accession_number`, `form_type`, `filing_date`, `document_url`  
나머지 키는 Form 유형별 파서에 따라 다릅니다.

**예외:** `ValueError` — 지원하지 않는 Form 유형인 경우

**예시:**

```python
import findata

# 8-K 공시 텍스트 파싱
parsed = findata.get_filing_text(
    ticker="AAPL",
    form="8-K",
    document_url="https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/form8k.htm",
    accession_number="0000320193-24-000123",
    filing_date="2024-05-01",
)
if parsed:
    print(f"Form: {parsed['form_type']}")
    print(f"Date: {parsed['filing_date']}")
    # 파싱된 섹션은 Form 유형에 따라 다름
    for key, value in parsed.items():
        if isinstance(value, str) and len(value) > 100:
            print(f"  {key}: {value[:150]}...")

# get_filings와 조합하여 사용
filings = findata.get_filings("NVDA", form_type="10-K", parse_sections=False)
# sec-filings 엔드포인트 등에서 얻은 8-K URL로 텍스트 파싱
```

---

### `financials.py` — XBRL 재무 팩트

#### `get_financials(ticker)`

SEC CompanyFacts API (`data.sec.gov/api/xbrl/companyfacts/`)에서 XBRL 데이터를
가져와 중첩된 JSON 구조를 1차원 `list[dict]`로 평탄화합니다.

**파라미터:**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|:----:|--------|------|
| `ticker` | `str` | ✔ | — | 주식 심볼 (예: `"AAPL"`) |

**반환값:** `list[dict[str, Any]]`

반환 dict의 키:

| 키 | 타입 | 설명 |
|----|------|------|
| `cik` | `str` | 10자리 zero-padded CIK |
| `taxonomy` | `str` | XBRL 택소노미 (예: `"us-gaap"`, `"dei"`) |
| `concept` | `str` | 개념명 (예: `"Revenue"`, `"Assets"`) |
| `label` | `str` | 사람이 읽을 수 있는 라벨 |
| `unit` | `str` | 단위 (예: `"USD"`, `"shares"`) |
| `period_start` | `str \| None` | 기간 시작일 |
| `period_end` | `str` | 기간 종료일 |
| `val` | `float \| int` | 값 |
| `accn` | `str \| None` | accession number |
| `fy` | `int \| None` | 회계연도 |
| `fp` | `str \| None` | 회계분기 (예: `"Q1"`, `"FY"`) |
| `form` | `str \| None` | 공시 유형 (예: `"10-K"`) |
| `filed` | `str \| None` | 제출일 |
| `frame` | `str \| None` | XBRL 프레임 (예: `"CY2024Q1I"`) |

**예외:**
- `ValueError` — 티커가 CIK로 변환될 수 없거나 데이터가 없는 경우

**예시:**

```python
import findata

# 전체 XBRL 팩트 가져오기
facts = findata.get_financials("AAPL")
print(f"총 {len(facts)}개의 XBRL 관측값")

# 매출(Revenue) 데이터만 추출
revenue = [
    f for f in facts
    if f["concept"] == "Revenues" and f["form"] == "10-K"
]
for r in revenue:
    print(f"FY{r['fy']} | {r['unit']} {r['val']:,.0f} | filed: {r['filed']}")

# 특정 분기 데이터 필터링
q1_2024 = [
    f for f in facts
    if f["fy"] == 2024 and f["fp"] == "Q1"
]
print(f"2024 Q1: {len(q1_2024)}개의 팩트")

# 택소노미별 그룹핑
from collections import Counter
taxonomies = Counter(f["taxonomy"] for f in facts)
for tax, cnt in taxonomies.most_common():
    print(f"  {tax}: {cnt}개")
```

---

### `transcripts.py` — 어닝스콜 트랜스크립트

#### `get_transcript(ticker, year, quarter)`

Tavily API를 통해 여러 소스(Motley Fool, Rev.com, Seeking Alpha 등)에서
어닝스콜 트랜스크립트를 검색하고, 도메인 우선순위 + 키워드 매칭 점수로
최적의 결과를 선택하여 반환합니다.

> ⚠️ 호출할 때마다 Tavily API 크레딧이 소비됩니다 (라이브러리 계층은 캐시가 없습니다).

**사전 요구사항:**
- `pip install findata[transcripts]` (또는 `pip install findata[all]`)
- 환경변수 `TAVILY_API_KEY=tvly-xxxxx` 설정

**파라미터:**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|:----:|--------|------|
| `ticker` | `str` | ✔ | — | 주식 심볼 (예: `"AAPL"`) |
| `year` | `int` | ✔ | — | 회계연도 (예: `2024`) |
| `quarter` | `int` | ✔ | — | 회계분기 (`1`–`4`) |

**반환값:** `dict[str, Any] | None` — 트랜스크립트를 찾지 못하면 `None`

반환 dict의 키:

| 키 | 타입 | 설명 |
|----|------|------|
| `ticker` | `str` | 주식 심볼 (대문자) |
| `fiscal_year` | `int` | 회계연도 |
| `fiscal_quarter` | `int` | 회계분기 |
| `source_url` | `str` | 트랜스크립트 원본 URL |
| `source_domain` | `str` | 소스 도메인 (예: `"fool.com"`) |
| `title` | `str` | 페이지 제목 |
| `transcript_text` | `str` | 트랜스크립트 전문 (최소 2,000자 이상) |

**예외:**
- `ValueError` — `quarter`가 1–4 범위를 벗어난 경우
- `RuntimeError` — `TAVILY_API_KEY`가 설정되지 않은 경우

**검색 우선순위 도메인:**

| 도메인 | 우선순위 점수 |
|--------|:----------:|
| `fool.com` (Motley Fool) | 100 |
| `rev.com` | 80 |
| `insidermonkey.com` | 60 |
| `investing.com` | 50 |
| `seekingalpha.com` | 40 |

**예시:**

```python
import findata

# 기본 사용
transcript = findata.get_transcript("AAPL", year=2024, quarter=4)
if transcript:
    print(f"소스: {transcript['source_domain']}")
    print(f"제목: {transcript['title']}")
    print(f"분량: {len(transcript['transcript_text']):,}자")
    print(f"URL: {transcript['source_url']}")
    print(f"\n--- 트랜스크립트 시작 ---\n")
    print(transcript["transcript_text"][:500])
else:
    print("트랜스크립트를 찾을 수 없습니다.")

# 여러 분기 순회
for q in range(1, 5):
    result = findata.get_transcript("MSFT", year=2024, quarter=q)
    status = f"{len(result['transcript_text']):,}자" if result else "없음"
    print(f"MSFT 2024 Q{q}: {status}")
```

---

### `pdf.py` — SEC 공시 PDF 다운로드

#### `download_filing_pdf(url, output_path, page_format, wait_ms)`

SEC 공시 페이지를 Playwright(headless Chromium)로 렌더링하여 PDF로 변환합니다.
서버 API의 `GET /v1/api/download-pdf` 엔드포인트와 동일한 기능을 라이브러리
계층에서 제공합니다.

> ⚠️ 이 함수는 Playwright가 필요합니다:
> ```bash
> pip install "findata[server]"
> python -m playwright install chromium
> ```

**파라미터:**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|:----:|--------|------|
| `url` | `str \| list[str]` | ✔ | — | PDF로 렌더링할 SEC 공시 페이지의 전체 URL. 리스트 형태로 여러 URL을 전달하면 ZIP 파일로 묶어서 반환합니다. |
| `output_path` | `str \| Path \| None` | ✗ | `None` | 지정 시 해당 경로에 결과(PDF 또는 ZIP) 저장. 상위 디렉토리는 자동 생성 |
| `page_format` | `str` | ✗ | `"A4"` | PDF 페이지 포맷. `"Letter"`, `"Legal"` 등도 가능 |
| `wait_ms` | `int` | ✗ | `1500` | 페이지 로드 후 PDF 생성까지 대기 시간(ms). SEC 방화벽 체크 통과용 |

**반환값:** `bytes` — 단일 URL일 경우 PDF 바이트, 여러 URL일 경우 ZIP 바이트. `output_path` 지정 시 파일에도 동시에 저장됩니다.

**예외:**
- `RuntimeError` — Playwright가 설치되어 있지 않은 경우
- 기타 Playwright/브라우저 관련 오류는 그대로 전파됩니다

**예시:**

```python
import findata

# ── 단일 URL: PDF 바이트만 가져오기 ──
pdf_bytes = findata.download_filing_pdf(
    "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240928.htm"
)
print(f"PDF 크기: {len(pdf_bytes):,} bytes")

# ── 여러 URL: 한 번에 ZIP 파일로 다운로드 ──
# 여러 URL을 리스트로 넘기면 브라우저를 한 번만 띄워 처리하므로 속도가 빠릅니다.
urls = [
    "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240928.htm",
    "https://www.sec.gov/Archives/edgar/data/320193/000032019324000069/aapl-20240629.htm"
]
zip_bytes = findata.download_filing_pdf(
    urls,
    output_path="output/aapl_recent_filings.zip",
)
print(f"ZIP 저장 완료. 크기: {len(zip_bytes):,} bytes")

# ── get_filings와 조합하여 여러 공시 한 번에 받기 ──
filings = findata.get_filings("AAPL", form_type="10-Q", count=3, parse_sections=False)
target_urls = [f["document_url"] for f in filings if f.get("document_url")]

if target_urls:
    findata.download_filing_pdf(
        target_urls,
        output_path="aapl_10q_bundle.zip",
    )
```

---

### `_cik.py` — Ticker → CIK 변환

#### `lookup_cik(ticker)`

`sec-cik-mapper` 패키지의 오프라인 JSON 매핑을 사용하여 티커 심볼을
SEC CIK 번호로 변환합니다. 네트워크 호출이나 DB 접근 없이 동작합니다.

**파라미터:**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|:----:|--------|------|
| `ticker` | `str` | ✔ | — | 주식 심볼 (대소문자 무관) |

**반환값:** `tuple[str | None, str | None]` — `(CIK zero-padded, entity_name)`  
티커를 찾을 수 없으면 `(None, None)` 반환.

**예시:**

```python
from findata.sec._cik import lookup_cik

# 정상 조회
cik, name = lookup_cik("AAPL")
print(f"CIK: {cik}, Name: {name}")
# → CIK: 0000320193, Name: AAPL

# 대소문자 무관
cik, _ = lookup_cik("aapl")   # 동일 결과

# 미등록 티커
cik, name = lookup_cik("INVALID_TICKER")
print(cik, name)
# → None None
```

---

### `const.py` — 공통 상수

| 상수 | 타입 | 설명 |
|------|------|------|
| `HEADERS` | `dict` | SEC Fair Access 정책 준수를 위한 `User-Agent` 헤더. 환경변수 `FINDATA_SEC_USER_AGENT`로 오버라이드 가능 |
| `TAVILY_API_KEY` | `str \| None` | 환경변수 `TAVILY_API_KEY`에서 읽은 Tavily API 키 |

**예시:**

```python
from findata.sec.const import HEADERS, TAVILY_API_KEY

# SEC API 직접 호출 시 헤더 사용
import requests
resp = requests.get(
    "https://efts.sec.gov/LATEST/search-index?q=AAPL",
    headers=HEADERS,
)

# Tavily 키 확인
if TAVILY_API_KEY:
    print("Tavily API 키가 설정되어 있습니다.")
```

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
