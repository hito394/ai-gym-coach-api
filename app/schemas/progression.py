from pydantic import BaseModel, Field, model_validator
from typing import Optional
from app.utils.exercise_key import normalize_exercise_key


class ProgressionInput(BaseModel):
    user_id: int
    exercise_key: Optional[str] = None
    exercise_name: Optional[str] = None
    exercise: Optional[str] = None
    last_week_avg_rpe: float = Field(..., ge=0.0, le=10.0)
    last_week_volume: int = Field(..., ge=0)
    plateau_weeks: int = Field(..., ge=0)
    fatigue_score: float = Field(..., ge=0.0, le=1.0)
    readiness_score: float = Field(..., ge=0.0, le=1.0)

    @model_validator(mode="after")
    def normalize_fields(self):
        exercise_key = (self.exercise_key or "").strip()
        exercise_name = (self.exercise_name or self.exercise or "").strip()
        if exercise_key:
            self.exercise_key = exercise_key
            if not exercise_name:
                self.exercise_name = exercise_key
            return self
        if not exercise_name:
            raise ValueError("exercise_key or exercise_name is required")
        self.exercise_name = exercise_name
        self.exercise_key = normalize_exercise_key(exercise_name)
        return self


class ProgressionDecision(BaseModel):
    action: str
    weight_delta: float
    volume_delta_sets: int
    deload: bool
    message: str
    recommendation_id: Optional[int] = None
    recommendation_accuracy: float = 0.0
    exercise_key: Optional[str] = None
    exercise_name: Optional[str] = None


class ReadinessInput(BaseModel):
    sleep_hours: float = Field(..., ge=0.0, le=12.0)
    soreness: int = Field(..., ge=1, le=10)
    stress: int = Field(..., ge=1, le=10)
    motivation: int = Field(..., ge=1, le=10)


class ReadinessOutput(BaseModel):
    readiness_score: float
    fatigue_score: float
    note: Optional[str] = None
