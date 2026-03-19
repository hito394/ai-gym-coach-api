from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class UserProfileIn(BaseModel):
    age: int
    weight_kg: float
    height_cm: float
    experience_level: str = Field(..., pattern="^(beginner|intermediate|advanced)$")
    goal: str = Field(..., pattern="^(muscle_gain|strength|fat_loss)$")
    training_days: int = Field(..., ge=2, le=6)
    equipment: List[str]


class UserProfileOut(BaseModel):
    id: int
    age: Optional[int] = None
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    experience_level: Optional[str] = None
    goal: Optional[str] = None
    training_days: Optional[int] = None
    equipment: Optional[List[str]] = None


class UserPreferenceIn(BaseModel):
    split_preference: Optional[str] = Field(
        default=None, pattern="^(ppl|upper_lower|full_body)$"
    )


class BodyWeightLogIn(BaseModel):
    weight_kg: float = Field(..., gt=0)
    measured_at: Optional[datetime] = None


class BodyWeightLogOut(BaseModel):
    id: int
    user_id: int
    weight_kg: float
    measured_at: datetime


# ---------------------------------------------------------------------------
# Body measurements (detailed composition + circumferences)
# ---------------------------------------------------------------------------

class BodyMeasurementIn(BaseModel):
    measured_at: Optional[datetime] = None
    body_fat_pct: Optional[float] = Field(default=None, ge=0, le=70)
    muscle_mass_kg: Optional[float] = Field(default=None, gt=0)
    chest_cm: Optional[float] = Field(default=None, gt=0)
    waist_cm: Optional[float] = Field(default=None, gt=0)
    hips_cm: Optional[float] = Field(default=None, gt=0)
    left_arm_cm: Optional[float] = Field(default=None, gt=0)
    right_arm_cm: Optional[float] = Field(default=None, gt=0)
    left_thigh_cm: Optional[float] = Field(default=None, gt=0)
    right_thigh_cm: Optional[float] = Field(default=None, gt=0)
    neck_cm: Optional[float] = Field(default=None, gt=0)
    notes: Optional[str] = None


class BodyMeasurementOut(BaseModel):
    id: int
    user_id: int
    measured_at: datetime
    body_fat_pct: Optional[float] = None
    muscle_mass_kg: Optional[float] = None
    chest_cm: Optional[float] = None
    waist_cm: Optional[float] = None
    hips_cm: Optional[float] = None
    left_arm_cm: Optional[float] = None
    right_arm_cm: Optional[float] = None
    left_thigh_cm: Optional[float] = None
    right_thigh_cm: Optional[float] = None
    neck_cm: Optional[float] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Growth graph data (ready for charting)
# ---------------------------------------------------------------------------

class GraphPoint(BaseModel):
    date: str          # ISO date string "YYYY-MM-DD"
    value: Optional[float]


class GrowthGraphOut(BaseModel):
    user_id: int
    metric: str
    unit: str
    points: List[GraphPoint]
    first_value: Optional[float] = None
    latest_value: Optional[float] = None
    change: Optional[float] = None      # latest - first
    change_pct: Optional[float] = None  # (change / first) * 100
