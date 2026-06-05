from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional
from agents.conversational_cio import chat as cio_chat, reset_session as cio_reset
import uuid
from fastapi import FastAPI, Query, HTTPException

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
router = APIRouter(prefix="/api/filings", tags=["Filings"])

# ---------------------------------------------------------------------------
# POST /chat — conversational CIO ReAct agent
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    user_message: str = Field(..., min_length=1, description="The user's chat message.")
    session_id: Optional[str] = Field(
        None,
        description="Conversation thread id. If omitted, a new one is generated and returned.",
    )


class ChatResponse(BaseModel):
    session_id: str
    reply: str


@router.post("/chat", response_model=ChatResponse)
def chat_with_cio(req: ChatRequest):
    """
    Talk to the conversational Chief Investment Officer agent.

    The CIO has tools to query the insider-trades SQLite DB and to consult the
    Financial / Risk / Sentiment subordinate analysts. Conversation memory is
    keyed by `session_id`; reuse the same id across turns to continue a thread.
    """
    session_id = req.session_id or uuid.uuid4().hex
    try:
        reply = cio_chat(req.user_message, session_id=session_id)
    except RuntimeError as e:
        # Surfaces missing GOOGLE_API_KEY etc. as 500.
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CIO agent error: {e!r}")
    return ChatResponse(session_id=session_id, reply=reply)


@router.post("/chat/reset")
def chat_reset(session_id: str = Query(..., description="Session id to clear")):
    """Drop the memory buffer for a single conversation thread."""
    cio_reset(session_id)
    return {"status": "ok", "session_id": session_id}