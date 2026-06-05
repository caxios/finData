# `app.py`

## 개요
SEC EDGAR 데이터를 서빙하는 FastAPI 백엔드 애플리케이션의 메인 엔트리포인트입니다. 모든 API 라우터(Router)를 결합하고, CORS 미들웨어를 설정하며, 서버 실행을 위한 기본 구성을 제공합니다.

## 주요 구성 요소
1. **FastAPI 앱 인스턴스**: `title="Insider Trading Tracker API"`로 생성.
2. **CORS 미들웨어**: 모든 출처(Origin)의 요청을 허용(`allow_origins=["*"]`).
3. **라우터 등록**: 4개의 API 라우터를 메인 앱에 부착합니다.
   - `api_form4.router` — Form 4 내부자 거래 데이터
   - `api_earnigscall.router` — 어닝스콜 트랜스크립트
   - `api_10kq.router` — 10-K/10-Q 공시 및 재무 데이터
   - `api_cio_chat.router` — 대화형 CIO 에이전트
4. **Windows 호환성**: Windows 환경에서 `asyncio.WindowsProactorEventLoopPolicy()`를 설정하여 이벤트 루프 오류를 방지합니다.

## 실행 방법
```bash
uvicorn app:app --reload --port 8000
```

## 역할
모든 SEC 관련 API 엔드포인트들을 하나의 FastAPI 서버로 통합하여 프론트엔드 또는 외부 클라이언트가 일관된 REST API를 통해 데이터에 접근할 수 있게 합니다.
