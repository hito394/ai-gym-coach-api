from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.schemas.user import UserProfileIn, UserProfileOut
from app.db import models

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/profile", response_model=UserProfileOut)
def create_profile(payload: UserProfileIn, db: Session = Depends(get_db)):
    user = models.User(
        age=payload.age,
        weight_kg=payload.weight_kg,
        height_cm=payload.height_cm,
        experience_level=payload.experience_level,
        goal=payload.goal,
        training_days=payload.training_days,
        equipment=payload.equipment,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return UserProfileOut(
        id=user.id,
        age=user.age,
        weight_kg=user.weight_kg,
        height_cm=user.height_cm,
        experience_level=user.experience_level,
        goal=user.goal,
        training_days=user.training_days,
        equipment=user.equipment,
    )
