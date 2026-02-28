from pydantic import BaseModel, Field
from typing import List


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(system|user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    user_id: int
    messages: List[ChatMessage]


class ChatResponse(BaseModel):
    reply: str
