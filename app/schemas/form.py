from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator

from app.utils.exercise_key import normalize_exercise_key
from app.utils.exercise_registry import is_gym_exercise
from app.schemas.realtime import Keypoint


def _validate_gym_exercise_key(v: str) -> str:
    """Normalise and assert the key is a recognised gym exercise."""
    key = normalize_exercise_key(v)
    if not key:
        raise ValueError("exercise_key must not be empty")
    if not is_gym_exercise(key):
        raise ValueError(
            f"'{key}' is not a supported gym exercise. "
            "Only weight-training exercises are accepted."
        )
    return key


class FormAnalyzeIn(BaseModel):
    user_id: int
    exercise_key: str
    diagnostics: Dict[str, Any]

    @field_validator("exercise_key")
    @classmethod
    def normalize_and_validate_key(cls, v: str) -> str:
        return _validate_gym_exercise_key(v)


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


# ---------------------------------------------------------------------------
# Multi-frame batch analysis schemas
# ---------------------------------------------------------------------------

class FrameIn(BaseModel):
    """
    One video frame from the client.

    timestamp_ms: milliseconds since recording started (monotonically increasing).
    keypoints:    MoveNet-style joint dict (same format as FormRealtimeIn).
    """
    timestamp_ms: int = Field(..., ge=0, description="ms offset from clip start")
    keypoints: Dict[str, Keypoint]


class FormBatchIn(BaseModel):
    """
    Multi-frame batch submitted after recording a set.

    Clients should down-sample to ≤ 60 fps before sending (150 frames max
    keeps payloads under ~200 KB even for a 5-second clip).
    """
    user_id: int
    exercise_key: str
    view: str = "auto"   # "front" | "side" | "auto"
    frames: List[FrameIn] = Field(..., min_length=2, max_length=600)

    @field_validator("exercise_key")
    @classmethod
    def normalize_and_validate_key(cls, v: str) -> str:
        return _validate_gym_exercise_key(v)

    @field_validator("view")
    @classmethod
    def validate_view(cls, v: str) -> str:
        if v not in ("front", "side", "auto"):
            raise ValueError("view must be 'front', 'side', or 'auto'")
        return v


class RepSummary(BaseModel):
    """Per-rep breakdown within the batch."""
    rep_number: int
    start_ms: int
    end_ms: int
    depth_score: float       # best depth reached this rep (0–100)
    worst_torso_angle: float # degrees – the peak lean during the rep
    issues: List[str]        # issues fired for this rep


class FormBatchOut(FormAnalyzeOut):
    """
    Aggregated result of analysing all frames in the submitted clip.

    Extends FormAnalyzeOut with multi-frame specific fields.
    """
    frame_count: int
    duration_ms: int
    rep_count: int
    reps: List[RepSummary]
    depth_achieved_deg: Optional[float] = None  # minimum knee angle seen (smaller = deeper)
    worst_torso_deg: Optional[float] = None     # peak torso lean angle (degrees)
    tempo_cv: Optional[float] = None            # coefficient of variation of rep durations
