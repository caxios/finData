# `company_data.py`

## 개요
Ticker 기반으로 SEC EDGAR에서 10-K/10-Q 공시 및 Form 4 내부자 거래 데이터를 조회하는 통합 오케스트레이터(Orchestrator) 모듈입니다. DB 캐시를 우선 확인하고, 데이터가 부족하거나 오래된 경우에만 SEC에서 실시간으로 스크래핑합니다.

## 주요 구성 요소
1. **Freshness Policy (신선도 정책)**
   - `TTL_10KQ_DAYS = 90`: 10-K/10-Q 데이터가 90일 이내면 캐시 사용.
   - `TTL_FORM4_DAYS = 7`: Form 4 데이터가 7일 이내면 캐시 사용.

2. **커스텀 예외 클래스**
   - `TickerNotFound`: Ticker를 CIK로 변환할 수 없을 때 발생.
   - `SECRateLimit`: SEC가 403/429 응답을 반환했을 때 발생 (Retry-After 헤더 포함).

3. **DB 조회 레이어**
   - `_select_10kq_rows(cik, limit)`: `sec_10kq.db`에서 캐시된 10-K/10-Q 행 조회.
   - `_select_form4_rows(ticker, cik, limit)`: `insider_all.db`와 `insider_watchlist.db` 양쪽에서 Form 4 거래를 중복 제거하여 조회.

4. **스크래퍼 래퍼**
   - `_scrape_10kq(cik, count)`: SEC EDGAR에서 10-K/10-Q를 가져와 파싱 후 DB에 저장.
   - `_scrape_form4(cik)`: SEC EDGAR에서 Form 4를 가져와 파싱 후 DB에 저장.

5. **`get_company_data(ticker, ...)`**: 퍼블릭 진입점 함수.
   - Ticker → CIK 변환 후, 캐시 신선도와 충분성을 검사.
   - 필요 시 SEC에서 스크래핑하여 캐시를 갱신.
   - `filings_10kq`, `form4_trades`, `cache_status`를 포함한 딕셔너리 반환.

## 역할
FastAPI 라우터(`api_10kq.py`)와 외부 스크립트에서 공통으로 사용하는 데이터 접근 레이어로서, "DB 캐시 우선, 미스 시 스크래핑" 전략을 캡슐화합니다.
