# `build_corp_codes.py`

## 개요
기업 목록(JSON) 데이터를 읽어와, 기존에 만들어둔 전체 기업 고유번호 캐시 파일(`auto_corp_cache.json`)과 대조하여 필요한 기업들의 고유번호 정보만을 필터링 및 매핑해주는 유틸리티 스크립트입니다.

## 주요 기능
- **`process(file_path, out_file, cache)` 함수**: 
  - 특정 산업군 등의 기업명 목록이 담긴 JSON 파일(`file_path`)을 읽습니다.
  - 사전에 다운로드 받아둔 `auto_corp_cache.json`(기업명 -> 고유번호 딕셔너리 캐시)을 참조하여 해당 기업들의 OpenDART 고유번호(corp_code)를 찾습니다.
  - 매핑된 결과를 새로운 JSON 파일(`out_file`)로 추출하여 저장합니다.
  - 만약 캐시에 존재하지 않는 기업이 있다면 `missing` 목록에 추가하여 사용자에게 경고 메시지(Warning)를 출력합니다.
- **`main()` 함수**: 자동차(car), 반도체(semi), 조선(ship) 3가지 산업군별 기업 리스트에 대해 일괄적으로 `process`를 수행합니다.

## 역할
이름만 알고 있는 기업 리스트(예: 관심 종목 리스트)를 OpenDART API 호출에 필수적인 8자리 고유번호(corp_code)로 변환해주는 전처리 파이프라인 역할을 합니다.
