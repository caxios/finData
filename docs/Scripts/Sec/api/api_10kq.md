# `api_10kq.py`

## 개요
SEC EDGAR의 10-K(사업보고서) 및 10-Q(분기보고서) 공시 데이터와 XBRL 재무 팩트(Company Facts)를 제공하는 FastAPI 라우터 모듈입니다. DB 캐시 우선 전략을 사용하며, 데이터가 없을 경우 SEC EDGAR에서 실시간으로 가져옵니다.

## 주요 엔드포인트
1. **`GET /api/documents/{ticker}/list`**: 특정 Ticker의 10-K/10-Q 공시 목록을 반환합니다.
2. **`GET /api/documents/{ticker}/{accession_number}`**: 특정 공시의 세부 내용 (Business, Risk Factors, MD&A, Financial Notes) 반환.
3. **`GET /api/financials/{ticker}/list`**: XBRL 기반 재무 기간(Fiscal Year/Quarter) 목록 반환. DB에 없으면 SEC companyfacts API에서 가져와 저장 후 재조회.
4. **`GET /api/financials/{ticker}/detail`**: 특정 기간의 모든 XBRL 팩트를 반환.
5. **`GET /api/company-data/{ticker}`**: Form 4 + 10-K/10-Q 통합 데이터 반환 (`company_data.get_company_data()` 호출).
6. **`GET /api/sec-filings/{ticker}`**: 다양한 Form 유형(10-K, 10-Q, 8-K, S-4, SC 13D 등)의 공시 메타데이터 목록 반환.
7. **`GET /api/filing-text/{accession_number}`**: 10-K/10-Q 이외 Form(8-K, S-4, SC 13D, 144)의 파싱된 텍스트 반환.
8. **`GET /api/download-pdf`**: Playwright를 사용하여 SEC 페이지를 PDF로 변환하여 다운로드.

## 역할
SEC EDGAR의 핵심 공시 데이터(10-K/10-Q 텍스트 섹션, XBRL 재무제표, 다양한 Form 유형)에 대한 통합 REST API 인터페이스를 제공합니다.
