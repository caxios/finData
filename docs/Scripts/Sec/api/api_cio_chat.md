# `api_cio_chat.py`

## 개요
대화형 CIO(Chief Investment Officer) ReAct 에이전트와의 채팅 인터페이스를 제공하는 FastAPI 라우터 모듈입니다.

## 주요 엔드포인트
1. **`POST /api/filings/chat`**: CIO 에이전트에게 메시지를 보내고 답변을 받습니다.
   - 요청: `ChatRequest` (user_message, session_id).
   - 응답: `ChatResponse` (session_id, reply).
   - `session_id`를 재사용하여 대화 맥락(Context)을 유지할 수 있습니다. 생략 시 새 세션이 자동 생성됩니다.
   - CIO 에이전트는 내부자 거래 SQLite DB를 조회하고, 재무/리스크/감성 분석 하위 에이전트를 활용하는 도구(Tool)를 가지고 있습니다.
2. **`POST /api/filings/chat/reset`**: 특정 세션의 대화 메모리를 초기화합니다.

## 역할
LLM 기반 금융 분석 에이전트에 대한 대화형 REST API 인터페이스를 제공하여, 사용자가 자연어로 기업 분석을 요청할 수 있게 합니다.
