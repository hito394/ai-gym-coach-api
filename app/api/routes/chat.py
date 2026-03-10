from fastapi import APIRouter, HTTPException
from app.schemas.chat import ChatRequest, ChatResponse, CoachStructuredOut
from app.services.ai_chat import chat

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/coach", response_model=ChatResponse)
def chat_coach(payload: ChatRequest):
    if not payload.messages:
        raise HTTPException(status_code=400, detail="Messages required")

    reply, structured = chat(payload.messages, diagnostics=payload.diagnostics)
    return ChatResponse(
        reply=reply,
        structured=CoachStructuredOut.model_validate(structured)
        if structured
        else None,
    )
