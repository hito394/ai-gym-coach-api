from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class FormAnalyzeIn(BaseModel):
    user_id: int
    exercise_key: str
    diagnostics: Dict[str, Any]


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
