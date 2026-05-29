# `report_main_info.py`

## 개요
정기보고서 주요정보(Periodic Report Key Information)에 속하는 30개의 오픈다트(OpenDART) 엔드포인트들을 감싸(Wrapper) 쉽게 호출할 수 있도록 해주는 모듈입니다.

## 주요 기능
- **30개 엔드포인트 통합 관리**: 증자(감자)현황, 배당현황, 임원현황, 타법인출자현황 등 30개에 이르는 정기보고서 내 주요 정보 데이터 엔드포인트가 내부 `_ENDPOINTS` 딕셔너리로 관리됩니다.
- **`ReportMainInfo` 클래스**
  - 모든 엔드포인트는 `(corp_code, bsns_year, reprt_code)` 형태의 동일한 파라미터 구조를 가집니다.
  - **`get(endpoint_key, ...)` / `save(...)`**: 범용 메서드로, 키 값(예: 'dividend', 'executives')을 통해 원하는 엔드포인트의 데이터를 가져오거나 저장합니다.
  - **`get_years(...)` / `save_years(...)`**: 단일 기업에 대해 여러 사업연도(bsns_years)의 데이터를 하나로 합쳐서 조회하거나 저장하는 편의 기능입니다.
  - **`save_all(corp_code, bsns_years, ...)`**: 특정 기업의 여러 사업연도에 걸쳐 **30개 전체 엔드포인트의 데이터**를 한 번에 가져와 단일 CSV에 모아서 저장(Consolidated dump)하는 강력한 기능입니다. 이 때 반환되는 스키마(컬럼 형태)가 제각각인 점을 고려하여 `utils.report_processing`의 도움을 받아 깔끔하게 병합합니다.
  - **개별 명명된 래퍼(Named wrappers)**: 
    - `get_dividend()`, `save_executives()` 처럼 메서드명을 명시적으로 제공하여 코드 자동완성 및 가독성을 높입니다.

## 역할
기업의 비재무적(혹은 계정과목 외) 정기보고서 내 세부 정보들을 수집할 때 사용되는 핵심 인터페이스입니다. 다양한 형태의 데이터를 일관성 있게 관리합니다.
