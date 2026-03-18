from typing import List, Dict, Optional
from pydantic import BaseModel, Field, model_validator
from app.utils.exercise_key import normalize_exercise_key


class ExerciseSet(BaseModel):
    reps: int
    weight: float
    rpe: Optional[float] = None


class ExercisePrescription(BaseModel):
    name: str
    exercise_key: Optional[str] = None
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
    client_id: Optional[str] = None
    exercise_key: Optional[str] = None
    exercise_name: Optional[str] = None
    exercise: Optional[str] = None
    reps: int
    weight: float
    rpe: Optional[float] = None
    rest_seconds: Optional[int] = None
    session_id: Optional[str] = None

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


class SetLogOut(BaseModel):
    id: int
    user_id: int
    client_id: Optional[str] = None
    exercise: str
    exercise_key: str
    reps: int
    weight: float
    rpe: Optional[float] = None
    rest_seconds: Optional[int] = None
    session_id: Optional[str] = None


class WorkoutHistorySetOut(BaseModel):
    exercise: str
    exercise_key: str
    reps: int
    weight: float
    rpe: Optional[float] = None
    rest_seconds: Optional[int] = None
    performed_at: str


class WorkoutHistorySessionOut(BaseModel):
    session_id: str
    performed_at: str
    total_sets: int
    total_volume: float
    entries: List[WorkoutHistorySetOut]


class WorkoutHistoryOut(BaseModel):
    user_id: int
    sessions: List[WorkoutHistorySessionOut]


class ProgressSummaryOut(BaseModel):
    user_id: int
    total_volume: float
    weekly_volume_by_muscle_group: Dict[str, float]
    rep_prs: Dict[str, int]
    one_rm_prs: Dict[str, float]
    strength_index: float
    strength_index_by_lift: Dict[str, float]


# ---------------------------------------------------------------------------
# AI menu generation
# ---------------------------------------------------------------------------

class GenerateAIMenuIn(BaseModel):
    profile_id: int
    split: str = Field(..., pattern="^(ppl|upper_lower|full_body)$")
    week_index: int = Field(default=1, ge=1)
    block_index: int = Field(default=1, ge=1)
    readiness_score: float = Field(default=0.7, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

class SessionStartIn(BaseModel):
    user_id: int
    plan_id: Optional[int] = None          # link to a WorkoutPlan if available
    notes: Optional[str] = None


class SessionLogSetIn(BaseModel):
    exercise_key: str
    exercise_name: Optional[str] = None
    reps: int = Field(..., ge=1)
    weight: float = Field(..., ge=0)       # 0 = bodyweight
    rpe: Optional[float] = Field(default=None, ge=1.0, le=10.0)
    rest_seconds: Optional[int] = None
    form_session_id: Optional[int] = None  # link to FormAnalysisSession


class SessionSetOut(BaseModel):
    id: int
    exercise: str
    exercise_key: str
    reps: int
    weight: float
    rpe: Optional[float] = None
    rest_seconds: Optional[int] = None
    form_session_id: Optional[int] = None
    performed_at: str


class SessionOut(BaseModel):
    id: int
    session_key: str
    user_id: int
    plan_id: Optional[int] = None
    notes: Optional[str] = None
    started_at: str
    finished_at: Optional[str] = None
    is_active: bool
    total_sets: int
    total_volume: float
    sets: List[SessionSetOut] = []


class SessionFinishIn(BaseModel):
    notes: Optional[str] = None
