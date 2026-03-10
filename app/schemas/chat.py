from pydantic import BaseModel, Field
from typing import List, Optional


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(system|user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    user_id: int
    messages: List[ChatMessage]
    diagnostics: Optional[dict] = None


class NextSessionAdjustment(BaseModel):
    exercise: str
    recommended_weight_delta: float
    sets_delta: int
    reps_target: int
    rpe_target: float
    rest_seconds: int
    notes: str
    confidence: float


class SessionSummaryOut(BaseModel):
    wins: List[str]
    risks: List[str]
    pr_events: List[str]
    volume: float
    fatigue: float
    next_actions: List[str]


class SubstitutionOut(BaseModel):
    original: str
    alternative: str
    reason: str
    equipment_required: List[str]


class CoachStructuredOut(BaseModel):
    next_session_adjustment: Optional[NextSessionAdjustment] = None
    session_summary: Optional[SessionSummaryOut] = None
    substitutions: List[SubstitutionOut] = []


class ChatResponse(BaseModel):
    reply: str
    structured: Optional[CoachStructuredOut] = None
