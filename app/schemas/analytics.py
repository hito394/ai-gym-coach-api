from typing import Dict, List, Optional
from pydantic import BaseModel


class TrendPoint(BaseModel):
    label: str
    value: float


class ProgressScoreOut(BaseModel):
    user_id: int
    progress_score: float
    strength_component: float
    consistency_component: float
    volume_quality_component: float


class AnalyticsSummaryOut(BaseModel):
    user_id: int
    weekly_volume: float
    workout_frequency: int
    progress_score: float
    strongest_exercise: Optional[str] = None
    fastest_improving_lift: Optional[str] = None
    weakest_muscle_group: Optional[str] = None
    plateau_exercise: Optional[str] = None
    insights: List[str]
    exercise_weight_points: List[TrendPoint]
    weekly_volume_points: List[TrendPoint]
    one_rm_points: List[TrendPoint]
    workout_frequency_points: List[TrendPoint]
    muscle_group_volume: Dict[str, float]
    muscle_group_points: List[TrendPoint]
    body_weight_points: List[TrendPoint]


class ExerciseProgressOut(BaseModel):
    user_id: int
    exercise_key: Optional[str] = None
    weight_points: List[TrendPoint]
    one_rm_points: List[TrendPoint]
