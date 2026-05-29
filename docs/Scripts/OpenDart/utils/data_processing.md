# `data_processing.py`

## 개요
OpenDART API로부터 반환받은 원시 재무제표(Financial Statements) JSON 데이터를 Pandas를 활용하여 시계열 분석에 용이한 넓은 형태(Wide format)로 재구성해주는 헬퍼(Helper) 모듈입니다.

## 주요 기능
- **보고서 코드 변환**: 내부의 `_REPRT_CODE_TO_QUARTER` 딕셔너리를 사용하여 OpenDART의 보고서 코드(예: '11013', '11011')를 사람이 읽기 쉬운 분기 숫자(1, 2, 3, 4)로 변환합니다.
- **`consolidate_quarterly(items)`**: 
  - `MultiCompanyAccounts` 및 `SingleCompanyStatements` 등에서 반환된 계정 데이터 목록을 입력으로 받습니다.
  - 연도(bsns_year)와 분기 숫자를 조합하여 '2023Q1' 형태의 시계열 `period` 컬럼을 생성합니다.
  - 재무제표 종류 구분(개별/연결) 중 기본적으로 **연결재무제표(CFS) 데이터만 필터링**하여 활용합니다.
  - Pandas의 `pivot_table`을 이용해 길게 늘어진 데이터를 피벗(Pivot)하여, 각 재무계정명(`account_nm`)들이 고유한 열(Column)이 되도록 넓게 펼칩니다.
- **`consolidate_indicators_quarterly(items)`**:
  - 다중회사 주요 재무지표 데이터를 변환하기 위한 별도의 피벗 함수입니다.
  - 위와 동일하게 시계열 `period`를 만들고, 지표명(`idx_nm`)들을 고유한 열(Column)로 변환합니다.

## 역할
복잡하고 중첩된 형태의 API JSON 응답(Long format)을 우리가 흔히 아는 형태의 시계열 재무 모델 엑셀/CSV 데이터(Wide format)로 1차 정제 및 변환하는 핵심 역할을 담당합니다.
