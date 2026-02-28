from fastapi import APIRouter, HTTPException
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.ai_chat import chat

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/coach", response_model=ChatResponse)
def chat_coach(payload: ChatRequest):
    if not payload.messages:
        raise HTTPException(status_code=400, detail="Messages required")

    reply = chat(payload.messages)
    return ChatResponse(reply=reply)
