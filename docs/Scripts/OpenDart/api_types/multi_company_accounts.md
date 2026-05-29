# `multi_company_accounts.py`

## 개요
다중회사 주요계정 (fnlttMultiAcnt) API 엔드포인트를 호출하기 위한 모듈입니다. 여러 회사의 주요 재무 계정 정보를 동시에 조회하고 저장하는 기능을 제공합니다.

## 주요 기능
- **`MultiCompanyAccounts` 클래스**
  - **`get(corp_codes, bsns_year, reprt_code)`**: 주어진 여러 회사의 고유번호 리스트, 사업연도, 보고서 코드를 사용해 다중회사의 주요 계정 정보를 가져옵니다. OpenDART API의 한계(한 번에 최대 100개 기업 조회 가능)를 고려하여 설계되었습니다.
  - **`save_quarterly(corp_codes, bsns_years, filename, data_dir)`**: 여러 회사의 다년간 4개 분기 데이터를 모두 가져와 하나의 CSV 파일로 정리하여 저장합니다. 
    - 내부적으로 최대 100개씩 청크(Chunk) 단위로 분할하여 API를 호출합니다.
    - 데이터 병합 시 `utils.data_processing` 모듈의 `consolidate_quarterly` 함수를 사용하여 재무계정명(`account_nm`)을 열(Column)로 하는 넓은 형태(Wide Format)로 데이터를 피벗(Pivot)합니다.

## 역할
주로 다수 기업에 대한 횡단면 데이터(Cross-sectional data) 혹은 패널 데이터(Panel data) 구축을 위해 특정 재무 계정을 일괄로 가져오고 변환하는 역할을 합니다.
