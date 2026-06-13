# 시작 가이드

---

## 1. 로컬 노트북에서 라이브러리로 사용하기

### 설치

```bash
# 프로젝트 루트(finData/)에서 editable 모드로 설치
pip install -e "."

# 전체 기능 포함 설치
pip install -e ".[all]"

# 특정 기능만 설치
pip install -e ".[dart]"          # OpenDART만
pip install -e ".[transcripts]"   # 어닝스콜만
```

### .env 설정

프로젝트 루트에 `.env` 파일을 생성하고 필요한 API 키를 추가합니다:
```env
TAVILY_API_KEY=tvly-xxxxx         # 어닝스콜 트랜스크립트 검색 (선택)
OPEN_DART_API=xxxxxxxx            # OpenDART API 키 (선택)
```

### 기본 사용법 (SEC)

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
# (requires: pip install findata[transcripts])
transcript = findata.get_transcript("AAPL", year=2024, quarter=4)

# ── 특정 공시 텍스트 파싱 (8-K, S-4, SC 13D, 144) ──
parsed = findata.get_filing_text(
    ticker="AAPL",
    form="8-K",
    document_url="https://www.sec.gov/Archives/edgar/data/...",
)
```

### 기본 사용법 (OpenDART)

```python
from findata.dart import (
    SingleCompanyStatements,
    MultiCompanyAccounts,
    MultiCompanyIndicators,
    ReportMainInfo,
    REPORT_CODE_ANNUAL,
    FS_DIV_CONSOLIDATED,
)

# ── 단일회사 전체 재무제표 ──
stmt = SingleCompanyStatements()
df = stmt.fetch("삼성전자", bsns_year="2024", reprt_code=REPORT_CODE_ANNUAL)

# ── 다중회사 주요계정 ──
acnt = MultiCompanyAccounts()
df = acnt.fetch(
    corp_codes=["005930", "000660"],
    bsns_year="2024",
    reprt_code=REPORT_CODE_ANNUAL,
)

# ── 다중회사 재무지표 ──
idx = MultiCompanyIndicators()
df = idx.fetch(
    corp_codes=["005930"],
    bsns_year="2024",
    reprt_code=REPORT_CODE_ANNUAL,
)

# ── 정기보고서 주요정보 (30개 엔드포인트) ──
rpt = ReportMainInfo()
df = rpt.fetch_증자감자("005930", bgn_de="20240101", end_de="20241231")
```

---

## 2. 상용 API 서버로 배포하기

### 로컬 실행

```bash
# 서버 의존성 설치
pip install -e ".[server]"

# 서버 시작
python -m findata.server.app
# → FastAPI at http://0.0.0.0:8000
# → Swagger UI: http://localhost:8000/docs
```

### API 엔드포인트 요약

| 엔드포인트 | 메서드 | 설명 |
|-----------|--------|------|
| `/api/trades` | GET | Form 4 내부자 거래 목록 (필터링/페이지네이션) |
| `/api/trades/{id}` | GET | 특정 거래 상세 |
| `/api/summary` | GET | Ticker별 거래 집계 통계 |
| `/api/form4/rankings` | GET | 순매수/순매도 Ticker 랭킹 |
| `/api/watchlist` | GET | 추적 중인 Ticker 목록 |
| `/api/refresh` | POST | 수동 스크래핑 트리거 |
| `/api/documents/{ticker}/list` | GET | 10-K/10-Q 공시 목록 |
| `/api/documents/{ticker}/{accession}` | GET | 공시 상세 (파싱된 섹션) |
| `/api/financials/{ticker}/list` | GET | XBRL 재무 기간 목록 |
| `/api/financials/{ticker}/detail` | GET | 특정 기간 XBRL 팩트 |
| `/api/company-data/{ticker}` | GET | 통합 데이터 (Form 4 + 10-K/Q) |
| `/api/sec-filings/{ticker}` | GET | 다양한 Form 유형 메타데이터 |
| `/api/filing-text/{accession}` | GET | 8-K/S-4/SC13D/144 파싱 텍스트 |
| `/api/download-pdf` | GET | SEC 페이지 PDF 변환 다운로드 |
| `/api/transcript` | GET | 어닝스콜 트랜스크립트 |
| `/api/transcripts/{ticker}/list` | GET | 저장된 어닝스콜 목록 |
| `/api/filings/chat` | POST | CIO 에이전트 대화 |
| `/api/filings/chat/reset` | POST | 세션 초기화 |

### 프로덕션 배포 시 추가 작업

현재 서버는 **로컬 개발 환경**으로 구성되어 있습니다. 프로덕션 배포를 위해 아래 항목이 추가로 필요합니다:

- [ ] **인증(Authentication)**: API 키 인증, 사용량 추적
- [ ] **컨테이너화**: `Dockerfile`, `docker-compose.yml`
- [ ] **클라우드 배포**: AWS/GCP/Azure 설정, CI/CD 파이프라인
- [ ] **HTTPS**: 리버스 프록시 (nginx), SSL 인증서
- [ ] **모니터링**: 로깅, 헬스체크, 에러 트래킹 (Sentry 등)
- [ ] **과금(Billing)**: Stripe 연동, 사용량 미터링 (상용화 시)
