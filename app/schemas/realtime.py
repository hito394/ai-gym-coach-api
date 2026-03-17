"""Schemas for real-time frame-by-frame keypoint analysis."""
from typing import Dict, List, Optional

from pydantic import BaseModel, field_validator

from app.utils.exercise_key import normalize_exercise_key


class Keypoint(BaseModel):
    """Single body joint detected by pose estimation (MoveNet / BlazePose etc.)."""

    x: float  # normalised 0-1 (0 = left edge of frame)
    y: float  # normalised 0-1 (0 = top edge of frame)
    confidence: float = 1.0  # 0-1


class FormRealtimeIn(BaseModel):
    """
    One frame of keypoint data sent by the client.

    Supported joint names (MoveNet convention):
      nose, left_eye, right_eye, left_ear, right_ear,
      left_shoulder, right_shoulder,
      left_elbow, right_elbow,
      left_wrist, right_wrist,
      left_hip, right_hip,
      left_knee, right_knee,
      left_ankle, right_ankle
    """

    user_id: int
    exercise_key: str
    keypoints: Dict[str, Keypoint]
    # Optional: which camera view is active (helps with depth analysis)
    view: str = "auto"  # "front" | "side" | "auto"

    @field_validator("exercise_key")
    @classmethod
    def normalize_key(cls, v: str) -> str:
        key = normalize_exercise_key(v)
        if not key:
            raise ValueError("exercise_key must not be empty")
        return key

    @field_validator("view")
    @classmethod
    def validate_view(cls, v: str) -> str:
        if v not in ("front", "side", "auto"):
            raise ValueError("view must be 'front', 'side', or 'auto'")
        return v


class JointColor(BaseModel):
    """Color annotation for a single joint."""

    joint: str
    color: str  # "green" | "yellow" | "red"
    reason: Optional[str] = None


class BoneColor(BaseModel):
    """Color annotation for the segment connecting two joints."""

    from_joint: str
    to_joint: str
    color: str  # "green" | "yellow" | "red"


class FormRealtimeOut(BaseModel):
    """
    Per-frame response: which joints/bones to highlight and in which colour.

    The client overlays these annotations on the live skeleton.
    """

    joint_colors: List[JointColor]
    bone_colors: List[BoneColor]
    issues: List[str]
    feedback: str
    overall_score: float  # 0-100
