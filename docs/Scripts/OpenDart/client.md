# `client.py`

## 개요
OpenDART API 모듈들이 공통으로 사용하는 HTTP 클라이언트, 인증(Authentication), 에러 처리 및 기본 상수(Constants)들이 정의되어 있는 핵심 모듈입니다.

## 주요 구성 요소
1. **상수 정의**
   - API 기본 URL(`BASE_URL = "https://opendart.fss.or.kr/api"`), 데이터 저장 폴더(`DATA_DIR`).
   - 보고서 코드(1분기, 반기, 3분기, 사업보고서 등), 재무제표 구분 코드(개별/연결), 지표분류코드 등 API 호출에 필요한 기본 코드들.
   - API 상태 코드(`STATUS_MESSAGES`): '000'(정상), '010'(등록되지 않은 키) 등의 응답 메시지 매핑.

2. **커스텀 예외 클래스 (Exceptions)**
   - `OpenDartError`: 기본 에러 클래스.
   - `OpenDartNoDataError`: 조회된 데이터가 없을 때 (013).
   - `OpenDartAuthError`: 인증 실패 시 (010, 011, 012).
   - `OpenDartRateLimitError`: 요청 제한 초과 시 (020).

3. **`OpenDartClient` 클래스**
   - `requests.Session`을 통해 API와 HTTP 통신을 수행합니다.
   - 환경변수(`.env`)의 `OPEN_DART_API` 키를 자동으로 읽어와 인증에 사용합니다.
   - **주요 메서드**:
     - `request(endpoint, params)`: API를 호출하고 응답 상태 코드를 검사하여 에러가 발생하면 적절한 예외를 발생시킵니다.
     - `validate_*`: 요청 파라미터가 유효한지 검증하는 도우미 메서드 제공.
     - `save_data()`: API로 받아온 데이터 목록(list of dicts)을 `json`이나 `csv` 형태로 `data/` 디렉토리에 저장합니다.

## 역할
다른 모든 엔드포인트 모듈(`MultiCompanyAccounts`, `ReportMainInfo` 등)이 상속받거나 포함하여 사용하는 기반 구조(Base Architecture) 역할을 수행합니다. API 호출과 응답 처리, 에러 핸들링을 중앙집중화하여 코드 중복을 줄입니다.
