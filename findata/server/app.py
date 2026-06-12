"""
FastAPI server for the findata commercial API.

Serves data from SQLite databases with caching and lazy-loading.

Run:
    python -m findata.server.app
    # or
    uvicorn findata.server.app:app --reload --port 8000
"""
import sys
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from findata.server.api import api_form4, api_earnigscall, api_10kq, api_cio_chat


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
# Windows event loop policy
if sys.platform == "win32" or "win64":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

app = FastAPI(title="findata API Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Attach route modules
app.include_router(api_form4.router)
app.include_router(api_earnigscall.router)
app.include_router(api_10kq.router)
app.include_router(api_cio_chat.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("findata.server.app:app", host="0.0.0.0", port=8000, reload=True)
