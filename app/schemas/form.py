from typing import Any, Dict, List, Optional
from pydantic import BaseModel, field_validator

from app.utils.exercise_key import normalize_exercise_key


class FormAnalyzeIn(BaseModel):
    user_id: int
    exercise_key: str
    diagnostics: Dict[str, Any]

    @field_validator("exercise_key")
    @classmethod
    def normalize_key(cls, v: str) -> str:
        key = normalize_exercise_key(v)
        if not key:
            raise ValueError("exercise_key must not be empty")
        return key


class FormAnalyzeOut(BaseModel):
    overall_score: float
    depth_score: float
    torso_angle_score: float
    symmetry_score: float
    tempo_score: float
    bar_path_score: float
    issues: List[str]
    feedback: str
    diagnostics: Dict[str, Any]
    model_name: Optional[str] = None
    model_version: Optional[str] = None


class FormHistoryItemOut(BaseModel):
    id: int
    exercise_key: str
    overall_score: float
    depth_score: float
    torso_angle_score: float
    symmetry_score: float
    tempo_score: float
    bar_path_score: float
    issues: List[str]
    feedback: str
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    created_at: str


class FormHistoryOut(BaseModel):
    user_id: int
    sessions: List[FormHistoryItemOut]


class FormTrendPoint(BaseModel):
    created_at: str
    overall_score: float


class FormTrendOut(BaseModel):
    user_id: int
    exercise_key: str
    points: List[FormTrendPoint]
    avg_score: float
    trend: str  # "improving" | "declining" | "stable"
