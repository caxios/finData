# `const.py`

## 개요
SEC EDGAR API 호출 시 필요한 공통 상수들을 정의하는 모듈입니다.

## 주요 내용
- **`HEADERS`**: SEC EDGAR의 Fair Access 정책을 준수하기 위한 `User-Agent` 헤더. SEC는 모든 요청에 이메일 주소가 포함된 User-Agent를 요구합니다.
- **`TAVILY_API_KEY`**: 어닝스콜 트랜스크립트 검색에 사용되는 Tavily API 키 (환경변수에서 읽음).

## 역할
SEC API를 호출하는 모든 모듈(`company_specific_fin.py`, `sec_10kq_rss.py` 등)이 공통으로 참조하는 설정값을 중앙에서 관리합니다.
