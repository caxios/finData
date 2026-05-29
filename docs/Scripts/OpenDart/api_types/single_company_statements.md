# `single_company_statements.py`

## 개요
단일회사 전체 재무제표 (fnlttSinglAcntAll) API 엔드포인트를 다루는 모듈입니다. 

## 주요 기능
- **`SingleCompanyStatements` 클래스**
  - 단일 기업의 5대 주요 재무제표(재무상태표, 손익계산서, 포괄손익계산서, 현금흐름표, 자본변동표)의 모든 계정 과목 데이터를 가져옵니다.
  - **`get(corp_code, bsns_year, reprt_code, fs_div)`**: 주어진 기업 고유번호에 대해 지정된 사업연도 및 분기의 전체 재무제표 데이터를 반환합니다. 기본값으로 연결재무제표(CFS) 데이터를 우선 요청합니다.
  - **`save_quarterly(corp_code, bsns_years, ...)`**: 단일 회사에 대해 여러 연도와 여러 분기 데이터를 모두 요청하여 하나의 CSV로 병합 및 변환(Pivot)하여 저장합니다. 
    - `utils.data_processing` 모듈의 `consolidate_quarterly`를 통해 계정명(`account_nm`)들이 열(Column)로 전개되는 넓은 형태(Wide Format)의 데이터를 구성합니다.
    - 재무제표 종류별(`sj_div`), 기간별(`period`)로 정렬되어 시계열 분석을 용이하게 합니다.

## 역할
특정 단일 기업에 대해 모든 계정과목의 상세한 재무 데이터를 얻어 시계열 재무 모델을 만들거나 깊이 있는 개별 기업 분석을 진행하고자 할 때 필수적인 모듈입니다.
