# `company_specific_fin.py`

## 개요
SEC EDGAR의 CompanyFacts API에서 단일 기업의 XBRL 재무 팩트를 가져와 SQLite에 저장하는 모듈입니다.

## 주요 기능
- **`_resolve_cik(ticker)`**: SEC의 `company_tickers.json`에서 Ticker를 CIK 번호(10자리 zero-padded)로 변환합니다.
- **`get_company_facts(ticker)`**: `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json` 에서 XBRL 팩트 원본 JSON을 가져옵니다.
- **`fetch_and_save(ticker, db_path)`**: 위 함수로 데이터를 가져온 후 `company_facts_db.save_company_facts()`를 호출하여 SQLite에 저장합니다. 삽입된 행 수를 반환합니다.

## 역할
XBRL 재무 데이터(매출, 순이익, EPS, 자산, 부채 등 수백 개 항목)를 SEC에서 로컬 DB로 가져오는 데이터 수집(Ingestion) 파이프라인 역할을 합니다. `api_10kq.py`의 `/api/financials/` 엔드포인트에서 DB 미스 시 호출됩니다.
