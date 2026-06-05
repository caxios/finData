# `data_loader.py`

## 개요
3개의 분석 에이전트(재무/사업/감성)가 필요로 하는 모든 입력 데이터를 SQLite에서 사전 조회하여 구성하는 데이터 로더 모듈입니다. SEC EDGAR에 직접 호출하지 않고 로컬 DB(`company_facts.db`, `sec_10kq.db`, `earnings_transcripts.db`, `insider_*.db`)만을 사용합니다.

## 주요 구성 요소
1. **DB 경로 상수**: `COMPANY_FACTS_DB`, `SEC_10KQ_DB`, `EARNINGS_DB`, `INSIDER_WATCHLIST_DB`, `INSIDER_ALL_DB`.

2. **XBRL 개념(Concept) 목록**
   - `INCOME_STATEMENT_CONCEPTS`: 매출(Revenues), 매출원가, 영업이익, 순이익, EPS 등 15개 항목.
   - `BALANCE_SHEET_CONCEPTS`: 총자산, 유동자산, 현금, 매출채권, 재고, 부채, 자본 등 15개 항목.
   - `CASH_FLOW_CONCEPTS`: 영업/투자/재무 활동 현금흐름, 감가상각, 자사주매입, 배당 등 7개 항목.

3. **핵심 함수**
   - `_lookup_cik(ticker)`: Ticker → CIK 변환. `company_facts.db`를 우선 조회하고, 없으면 `sec_cik_mapper` 패키지로 폴백.
   - `_query_facts(cik, concepts, forms, limit)`: 특정 XBRL 개념들의 최근 관측값을 조회.
   - `_latest_filing_row(cik)`: 가장 최근 10-K(또는 10-Q) 공시의 전체 행 반환.
   - `_notes_for_filing(accession_number)`: 특정 공시의 재무제표 주석(Notes) 조회.
   - `_insider_trades(ticker, limit)`: Form 4 내부자 거래 최대 60건 조회.
   - `_latest_transcript(ticker)`: 가장 최근 어닝스콜 트랜스크립트 조회.

4. **`load_company_data(ticker, max_chars)`**: 퍼블릭 진입점.
   - 3가지 블록을 구성하여 반환: `financial_inputs`, `business_inputs`, `sentiment_inputs`.
   - 각 블록에 `_missing` 리스트가 포함되어 데이터 부재 시 에러 없이 원인을 기록합니다.
   - 긴 텍스트는 `max_chars`로 잘라냅니다 (기본 80,000자).

## 역할
CIO 에이전트 시스템의 핵심 데이터 레이어로서, 3개의 분석 에이전트(Financial Analyst, Risk Analyst, Sentiment Analyst)에게 필요한 입력 데이터를 표준화된 형태로 제공합니다.
