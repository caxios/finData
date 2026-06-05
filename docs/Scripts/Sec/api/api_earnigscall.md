# `api_earnigscall.py`

## 개요
어닝스콜(Earnings Call) 트랜스크립트를 조회하는 FastAPI 라우터 모듈입니다. Tavily 검색 API를 통해 트랜스크립트를 가져오고 SQLite에 캐싱합니다.

## 주요 엔드포인트
1. **`GET /api/transcript`**: 특정 Ticker/연도/분기의 어닝스콜 트랜스크립트를 반환.
   - 파라미터: `ticker`, `year`(회계연도), `quarter`(1~4분기), `force_refresh`(캐시 무시).
   - 첫 호출 시 Tavily API로 검색 후 `earnings_transcripts.db`에 캐싱.
   - 이후 호출에서는 캐시된 결과를 반환.
2. **`GET /api/transcripts/{ticker}/list`**: 특정 Ticker의 저장된 어닝스콜 목록을 반환 (회계연도, 분기, 날짜, 제목).

## 역할
어닝스콜 트랜스크립트에 대한 온디맨드(On-demand) 조회 API를 제공하며, 감성 분석 에이전트의 입력 데이터로 활용됩니다.
