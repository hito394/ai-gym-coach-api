from fastapi import APIRouter, HTTPException
from app.schemas.chat import ChatRequest, ChatResponse, CoachStructuredOut
from app.services.ai_chat import chat

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/coach", response_model=ChatResponse)
def chat_coach(payload: ChatRequest):
    if not payload.messages:
        raise HTTPException(status_code=400, detail="Messages required")

    reply, structured = chat(payload.messages, diagnostics=payload.diagnostics)
    structured_out = None
    if structured:
        try:
            structured_out = CoachStructuredOut.model_validate(structured)
        except Exception:
            structured_out = None

    return ChatResponse(
        reply=reply,
        structured=structured_out,
    )
