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
