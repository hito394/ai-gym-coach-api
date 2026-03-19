from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.core.security import get_current_user_id
from app.schemas.user import (
    BodyMeasurementIn,
    BodyMeasurementOut,
    GrowthGraphOut,
    GraphPoint,
    UserProfileIn,
    UserProfileOut,
    BodyWeightLogIn,
    BodyWeightLogOut,
)
from app.db import models
from datetime import datetime
from typing import Optional

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/{user_id}/profile", response_model=UserProfileOut)
def get_profile(
    user_id: int,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserProfileOut(
        id=user.id,
        age=user.age,
        weight_kg=user.weight_kg,
        height_cm=user.height_cm,
        experience_level=user.experience_level,
        goal=user.goal,
        training_days=user.training_days,
        equipment=user.equipment or [],
    )


@router.post("/profile", response_model=UserProfileOut)
def create_profile(payload: UserProfileIn, db: Session = Depends(get_db)):
    """Legacy: create a user profile without auth (pre-auth clients)."""
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
def log_body_weight(
    user_id: int,
    payload: BodyWeightLogIn,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
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
def get_body_weight_logs(
    user_id: int,
    limit: int = 30,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
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


# ---------------------------------------------------------------------------
# Body measurements (composition + circumferences)
# ---------------------------------------------------------------------------

@router.post("/{user_id}/measurements", response_model=BodyMeasurementOut, status_code=201)
def log_measurement(
    user_id: int,
    payload: BodyMeasurementIn,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    record = models.BodyMeasurement(
        user_id=user_id,
        measured_at=payload.measured_at or datetime.utcnow(),
        body_fat_pct=payload.body_fat_pct,
        muscle_mass_kg=payload.muscle_mass_kg,
        chest_cm=payload.chest_cm,
        waist_cm=payload.waist_cm,
        hips_cm=payload.hips_cm,
        left_arm_cm=payload.left_arm_cm,
        right_arm_cm=payload.right_arm_cm,
        left_thigh_cm=payload.left_thigh_cm,
        right_thigh_cm=payload.right_thigh_cm,
        neck_cm=payload.neck_cm,
        notes=payload.notes,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _measurement_to_out(record)


@router.get("/{user_id}/measurements", response_model=list[BodyMeasurementOut])
def get_measurements(
    user_id: int,
    limit: int = 30,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    rows = (
        db.query(models.BodyMeasurement)
        .filter(models.BodyMeasurement.user_id == user_id)
        .order_by(models.BodyMeasurement.measured_at.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return [_measurement_to_out(r) for r in rows]


# ---------------------------------------------------------------------------
# Growth graph endpoint (multi-metric trend for charting)
# ---------------------------------------------------------------------------

_METRIC_META = {
    "weight_kg":     ("body_weight_logs",  "weight_kg",    "kg"),
    "body_fat_pct":  ("body_measurements", "body_fat_pct", "%"),
    "muscle_mass_kg":("body_measurements", "muscle_mass_kg","kg"),
    "chest_cm":      ("body_measurements", "chest_cm",     "cm"),
    "waist_cm":      ("body_measurements", "waist_cm",     "cm"),
    "hips_cm":       ("body_measurements", "hips_cm",      "cm"),
    "left_arm_cm":   ("body_measurements", "left_arm_cm",  "cm"),
    "right_arm_cm":  ("body_measurements", "right_arm_cm", "cm"),
}

from fastapi import Query as _Q


@router.get("/{user_id}/growth", response_model=GrowthGraphOut)
def growth_graph(
    user_id: int,
    metric: str = _Q(
        default="weight_kg",
        description="One of: weight_kg, body_fat_pct, muscle_mass_kg, chest_cm, waist_cm, hips_cm, left_arm_cm, right_arm_cm",
    ),
    limit: int = _Q(default=60, ge=2, le=365),
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    """
    Returns a list of date-value points for the given body metric,
    ready to be plotted as a line chart.
    Also includes first/latest value and total change.
    """
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if metric not in _METRIC_META:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown metric '{metric}'. Valid: {list(_METRIC_META.keys())}",
        )

    _, field_name, unit = _METRIC_META[metric]

    if metric == "weight_kg":
        rows = (
            db.query(models.BodyWeightLog)
            .filter(models.BodyWeightLog.user_id == user_id)
            .order_by(models.BodyWeightLog.measured_at.asc())
            .limit(limit)
            .all()
        )
        points = [
            GraphPoint(date=r.measured_at.date().isoformat(), value=r.weight_kg)
            for r in rows
        ]
    else:
        rows = (
            db.query(models.BodyMeasurement)
            .filter(models.BodyMeasurement.user_id == user_id)
            .order_by(models.BodyMeasurement.measured_at.asc())
            .limit(limit)
            .all()
        )
        points = [
            GraphPoint(
                date=r.measured_at.date().isoformat(),
                value=getattr(r, field_name),
            )
            for r in rows
            if getattr(r, field_name) is not None
        ]

    values = [p.value for p in points if p.value is not None]
    first_val = values[0] if values else None
    latest_val = values[-1] if values else None
    change = round(latest_val - first_val, 2) if (first_val and latest_val) else None
    change_pct = round(change / first_val * 100, 1) if (change is not None and first_val) else None

    return GrowthGraphOut(
        user_id=user_id,
        metric=metric,
        unit=unit,
        points=points,
        first_value=first_val,
        latest_value=latest_val,
        change=change,
        change_pct=change_pct,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _measurement_to_out(r: models.BodyMeasurement) -> BodyMeasurementOut:
    return BodyMeasurementOut(
        id=r.id,
        user_id=r.user_id,
        measured_at=r.measured_at,
        body_fat_pct=r.body_fat_pct,
        muscle_mass_kg=r.muscle_mass_kg,
        chest_cm=r.chest_cm,
        waist_cm=r.waist_cm,
        hips_cm=r.hips_cm,
        left_arm_cm=r.left_arm_cm,
        right_arm_cm=r.right_arm_cm,
        left_thigh_cm=r.left_thigh_cm,
        right_thigh_cm=r.right_thigh_cm,
        neck_cm=r.neck_cm,
        notes=r.notes,
    )
