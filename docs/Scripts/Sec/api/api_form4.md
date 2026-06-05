# `api_form4.py`

## 개요
SEC Form 4(내부자 거래 보고서) 데이터를 조회하고 관리하는 FastAPI 라우터 모듈입니다. 두 개의 SQLite DB(`insider_watchlist.db`, `insider_all.db`)를 데이터 소스로 사용합니다.

## 주요 엔드포인트
1. **`GET /api/trades`**: 필터링 및 페이지네이션이 가능한 내부자 거래 목록 반환.
   - 필터: `ticker`, `owner`(이름 부분 일치), `code`(거래 코드), `acquired_or_disposed`, `date_from/to`, `min_value`.
   - 페이지네이션: `limit`(최대 500), `offset`.
2. **`GET /api/trades/{trade_id}`**: 특정 거래의 상세 정보 반환.
3. **`GET /api/summary`**: Ticker별 집계 통계 반환 (총 거래 수, 매수/매도 금액, 고유 내부자 수 등).
4. **`GET /api/form4/rankings`**: 순매수/순매도 기준 상위 N개 Ticker 랭킹.
   - 특정 Ticker를 지정하면 해당 Ticker의 집계 데이터만 반환.
   - `insider_all.db`와 `insider_watchlist.db`를 합산하여 중복 제거.
5. **`GET /api/watchlist`**: 현재 추적 중인 Ticker 목록 반환.
6. **`POST /api/refresh`**: 수동 스크래핑 트리거.
   - `source=watchlist`: 워치리스트 Ticker별 개별 스크래핑.
   - `source=all`: SEC RSS 피드에서 최근 100건의 Form 4 스크래핑.

## 역할
내부자 거래 데이터에 대한 다양한 조회, 분석, 관리 기능을 REST API로 제공하여 프론트엔드에서 내부자 매매 동향을 시각화하고 분석할 수 있게 합니다.
