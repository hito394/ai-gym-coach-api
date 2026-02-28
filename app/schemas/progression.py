from pydantic import BaseModel, Field
from typing import Optional


class ProgressionInput(BaseModel):
    user_id: int
    exercise: str
    last_week_avg_rpe: float = Field(..., ge=0.0, le=10.0)
    last_week_volume: int = Field(..., ge=0)
    plateau_weeks: int = Field(..., ge=0)
    fatigue_score: float = Field(..., ge=0.0, le=1.0)
    readiness_score: float = Field(..., ge=0.0, le=1.0)


class ProgressionDecision(BaseModel):
    action: str
    weight_delta: float
    volume_delta_sets: int
    deload: bool
    message: str


class ReadinessInput(BaseModel):
    sleep_hours: float = Field(..., ge=0.0, le=12.0)
    soreness: int = Field(..., ge=1, le=10)
    stress: int = Field(..., ge=1, le=10)
    motivation: int = Field(..., ge=1, le=10)


class ReadinessOutput(BaseModel):
    readiness_score: float
    fatigue_score: float
    note: Optional[str] = None
