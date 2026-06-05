"""
FastAPI backend for the Insider Trading Tracker.

Serves insider trade data from two SQLite databases:
  - insider_watchlist.db  (per-ticker watchlist scraping)
  - insider_all.db        (latest Form 4 filings from SEC RSS)

Run:
    uvicorn app:app --reload --port 8000
"""
import sys
import asyncio
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api import api_form4, api_earnigscall, api_10kq, api_cio_chat


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATHS = {
    "watchlist": os.path.join(BASE_DIR, "db", "insider_watchlist.db"),
    "all":       os.path.join(BASE_DIR, "db", "insider_all.db"),
}


COMPANY_FACTS_DB = os.path.join(BASE_DIR, "db", "company_facts.db")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
# [에러 해결 핵심 코드] 윈도우 환경일 경우 Proactor 이벤트 루프 정책을 강제로 설정합니다.
if sys.platform == "win32" or "win64":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

app = FastAPI(title="Insider Trading Tracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 쪼개둔 미니 앱(라우터)들을 메인 앱에 부착
app.include_router(api_form4.router)
app.include_router(api_earnigscall.router)
app.include_router(api_10kq.router)
app.include_router(api_cio_chat.router)
