from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.schemas.user import (
    UserProfileIn,
    UserProfileOut,
    BodyWeightLogIn,
    BodyWeightLogOut,
)
from app.db import models
from datetime import datetime

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


@router.post("/{user_id}/body-weight", response_model=BodyWeightLogOut)
def log_body_weight(user_id: int, payload: BodyWeightLogIn, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="User not found")

    measured_at = payload.measured_at or datetime.utcnow()
    record = models.BodyWeightLog(
        user_id=user_id,
        weight_kg=payload.weight_kg,
        measured_at=measured_at,
    )
    user.weight_kg = payload.weight_kg
    db.add(record)
    db.commit()
    db.refresh(record)

    return BodyWeightLogOut(
        id=record.id,
        user_id=record.user_id,
        weight_kg=record.weight_kg,
        measured_at=record.measured_at,
    )


@router.get("/{user_id}/body-weight", response_model=list[BodyWeightLogOut])
def get_body_weight_logs(user_id: int, limit: int = 30, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="User not found")

    rows = (
        db.query(models.BodyWeightLog)
        .filter(models.BodyWeightLog.user_id == user_id)
        .order_by(models.BodyWeightLog.measured_at.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )

    return [
        BodyWeightLogOut(
            id=row.id,
            user_id=row.user_id,
            weight_kg=row.weight_kg,
            measured_at=row.measured_at,
        )
        for row in rows
    ]
