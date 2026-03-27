from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.schemas.realtime import Keypoint  # re-exported for service/test use


class FormLogIn(BaseModel):
    """Log how a set felt — no pose analysis required."""
    user_id: int
    exercise_key: str = Field(..., min_length=1, max_length=100)
    feeling: int = Field(..., ge=1, le=10, description="How good was your form? 1 (terrible) – 10 (perfect)")
    note: Optional[str] = Field(default=None, max_length=500)


class FormLogOut(BaseModel):
    id: int
    exercise_key: str
    feeling: int
    note: Optional[str]
    created_at: str


class FormHistoryItemOut(BaseModel):
    id: int
    exercise_key: str
    feeling: int
    note: Optional[str]
    created_at: str


class FormHistoryOut(BaseModel):
    user_id: int
    sessions: List[FormHistoryItemOut]


class FormTrendPoint(BaseModel):
    created_at: str
    feeling: int


class FormTrendOut(BaseModel):
    user_id: int
    exercise_key: str
    points: List[FormTrendPoint]
    avg_feeling: float
    trend: str  # "improving" | "declining" | "stable"


# ---------------------------------------------------------------------------
# Internal schemas used by service layer (not exposed as API endpoints)
# ---------------------------------------------------------------------------

class FrameIn(BaseModel):
    timestamp_ms: int = Field(..., ge=0)
    keypoints: Dict[str, Keypoint]


class FormBatchIn(BaseModel):
    user_id: int
    exercise_key: str
    view: str = "auto"
    frames: List[FrameIn] = Field(..., min_length=2, max_length=600)


class RepSummary(BaseModel):
    rep_number: int
    start_ms: int
    end_ms: int
    depth_score: float
    worst_torso_angle: float
    issues: List[str]


class FormBatchOut(BaseModel):
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
    frame_count: int
    duration_ms: int
    rep_count: int
    reps: List[RepSummary]
    depth_achieved_deg: Optional[float] = None
    worst_torso_deg: Optional[float] = None
    tempo_cv: Optional[float] = None
