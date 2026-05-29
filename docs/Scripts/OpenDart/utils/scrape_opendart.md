# `scrape_opendart.py`

## 개요
오픈다트(OpenDART) 공식 웹사이트의 API 개발 가이드(문서) 페이지를 웹 스크래핑(크롤링)하여, 각 API에 대한 요약 문서를 텍스트(`docs/opendarts/main_info.txt`) 형태로 자동 생성해주는 스크립트입니다.

## 주요 기능
- **기존 파일 백업 및 초기화**: `main_info.txt` 파일의 상단 1~41줄(아마도 기본 소개나 인트로 부분)만을 남겨두고 하단 내용을 덮어쓰기 위해 초기화합니다.
- **BeautifulSoup을 활용한 웹 스크래핑**:
  - 정기보고서 주요정보에 해당하는 API ID 대역(`2020018` ~ `2020053`, 총 36개)을 순회하며 OpenDART 가이드 웹페이지(HTML)를 요청합니다.
  - 가져온 HTML 문서에서 API의 **제목(Title)**, **요청 URL (json endpoint)**, **요청 인자(Request Params)** 표, 그리고 **응답 결과(Response Result)** 표를 파싱(추출)해냅니다.
- **문서 포매팅 (Formatting)**:
  - 추출된 정보를 마크다운(Markdown)과 유사한 구조로 깔끔하게 정리합니다.
  - 제목(`##`), API 주소, 가상의 요청 URL 예시(example of api request url), 요청/응답 파라미터 테이블을 탭(\t) 구분자로 정리하여 리스트업합니다.
  - 수집된 텍스트 청크들을 `main_info.txt` 파일에 덧붙여서(append) 최종 가이드 문서를 완성합니다.

## 역할
API에 대한 스펙이 변경되거나 전체 API 종류와 파라미터를 한눈에 확인할 수 있는 통합 문서 텍스트(Documentation Text)를 사람이 일일이 복사하지 않고도 자동으로 최신화 구축할 수 있게 도와줍니다.
