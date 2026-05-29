# `__init__.py`

## 개요
`OpenDart` 패키지의 초기화 파일입니다. OpenDART 재무 데이터 API를 사용하기 위한 주요 클래스, 예외 처리(Error) 클래스, 그리고 공통적으로 사용되는 상수(Constants)들을 외부에서 쉽게 임포트(import)할 수 있도록 노출합니다.

## 주요 내용
- **Base Client 및 Error**: `OpenDartClient`, `OpenDartError` 등 API 연결 및 에러 처리를 위한 클래스 임포트.
- **상수(Constants)**:
  - 보고서 코드: `REPORT_CODE_Q1`(1분기), `REPORT_CODE_HALF`(반기), `REPORT_CODE_Q3`(3분기), `REPORT_CODE_ANNUAL`(사업보고서).
  - 재무제표 구분: `FS_DIV_SEPARATE`(개별), `FS_DIV_CONSOLIDATED`(연결).
  - 재무제표 종류: `SJ_DIV_BS`(재무상태표), `SJ_DIV_IS`(손익계산서), `SJ_DIV_CIS`(포괄손익계산서), `SJ_DIV_CF`(현금흐름표), `SJ_DIV_SCE`(자본변동표).
  - 지표 분류 코드: 수익성(`IDX_PROFITABILITY`), 안정성(`IDX_STABILITY`), 성장성(`IDX_GROWTH`), 활동성(`IDX_ACTIVITY`).
- **Endpoint 모듈**: 
  - `MultiCompanyAccounts`: 다중회사 주요계정
  - `MultiCompanyIndicators`: 다중회사 주요 재무지표
  - `SingleCompanyStatements`: 단일회사 전체 재무제표
  - `ReportMainInfo`: 정기보고서 주요정보

## 역할
사용자가 패키지 내의 복잡한 경로를 알 필요 없이 `from OpenDart import OpenDartClient, MultiCompanyAccounts`와 같은 형태로 직관적으로 모듈을 사용할 수 있게 해줍니다.
