# `multi_company_indicators.py`

## 개요
다중회사 주요 재무지표 (fnlttCmpnyIndx) API 엔드포인트를 다루는 모듈입니다. 수익성, 안정성, 성장성, 활동성 등 핵심 재무지표들을 다수 회사에 대해 동시에 조회합니다. (참고: OpenDART에서 2023년 3분기부터 제공하는 데이터입니다)

## 주요 기능
- **`MultiCompanyIndicators` 클래스**
  - **`get(corp_codes, bsns_year, reprt_code, idx_cl_code)`**: 특정 지표 분류(수익성, 안정성 등)에 대한 다중회사 지표 데이터를 가져옵니다.
  - **`save_quarterly(corp_codes, bsns_years, ...)`**: 여러 회사의, 여러 해, 여러 분기, 그리고 모든 4가지 지표 분류(수익성, 안정성, 성장성, 활동성)에 대한 데이터를 순회하며 모두 수집합니다.
    - 기업들을 100개 단위로 청크 처리합니다.
    - `utils.data_processing`의 `consolidate_indicators_quarterly` 함수를 사용해 여러 지표명(`idx_nm`)을 각각의 열(Column)로 변환(Pivot)하여 가독성 좋은 단일 CSV 형태로 저장합니다.

## 역할
수익성(ROE 등), 안정성(부채비율 등)과 같은 핵심 지표값을 여러 기업에 대해 대량 수집할 때 사용됩니다. 기업별/기간별 지표 시계열 데이터를 빠르게 구성하는 데 유용합니다.
