from typing import List, Dict, Optional
from pydantic import BaseModel, Field


class ExerciseSet(BaseModel):
    reps: int
    weight: float
    rpe: Optional[float] = None


class ExercisePrescription(BaseModel):
    name: str
    sets: int
    rep_range: str
    rpe_target: float
    rest_seconds: int
    notes: Optional[str] = None


class WorkoutDayOut(BaseModel):
    day_index: int
    focus: str
    exercises: List[ExercisePrescription]


class WorkoutPlanOut(BaseModel):
    plan_name: str
    split: str
    week_index: int
    block_index: int
    days: List[WorkoutDayOut]
    volume_landmarks: Dict[str, int]
    readiness_score: float
    fatigue_score: float


class GenerateWorkoutIn(BaseModel):
    profile_id: int
    split: str = Field(..., pattern="^(ppl|upper_lower|full_body)$")
    week_index: int = 1
    block_index: int = 1
    readiness_score: float = Field(default=0.7, ge=0.0, le=1.0)


class SetLogIn(BaseModel):
    user_id: int
    exercise: str
    reps: int
    weight: float
    rpe: Optional[float] = None


class SetLogOut(SetLogIn):
    id: int


class ProgressSummaryOut(BaseModel):
    user_id: int
    total_volume: float
    prs: Dict[str, float]
