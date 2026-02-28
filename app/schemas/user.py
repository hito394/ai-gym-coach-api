from typing import List, Optional
from pydantic import BaseModel, Field


class UserProfileIn(BaseModel):
    age: int
    weight_kg: float
    height_cm: float
    experience_level: str = Field(..., pattern="^(beginner|intermediate|advanced)$")
    goal: str = Field(..., pattern="^(muscle_gain|strength|fat_loss)$")
    training_days: int = Field(..., ge=2, le=6)
    equipment: List[str]


class UserProfileOut(UserProfileIn):
    id: int


class UserPreferenceIn(BaseModel):
    split_preference: Optional[str] = Field(
        default=None, pattern="^(ppl|upper_lower|full_body)$"
    )
