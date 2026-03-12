from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db import models
from app.schemas.analytics import AnalyticsSummaryOut, ExerciseProgressOut, ProgressScoreOut
from app.services.analytics import build_analytics_snapshot, build_exercise_progress

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary/{user_id}", response_model=AnalyticsSummaryOut)
def analytics_summary(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    logs = db.query(models.SetLog).filter(models.SetLog.user_id == user_id).all()
    body_weight_logs = (
        db.query(models.BodyWeightLog)
        .filter(models.BodyWeightLog.user_id == user_id)
        .order_by(models.BodyWeightLog.measured_at.asc())
        .all()
    )
    snapshot = build_analytics_snapshot(user, logs, body_weight_logs)
    return AnalyticsSummaryOut.model_validate(snapshot["summary"])


@router.get("/progress/{user_id}", response_model=ExerciseProgressOut)
def analytics_progress(
    user_id: int,
    exercise_key: str | None = None,
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    logs = db.query(models.SetLog).filter(models.SetLog.user_id == user_id).all()
    body_weight_logs = (
        db.query(models.BodyWeightLog)
        .filter(models.BodyWeightLog.user_id == user_id)
        .order_by(models.BodyWeightLog.measured_at.asc())
        .all()
    )
    snapshot = build_analytics_snapshot(user, logs, body_weight_logs)

    progress = build_exercise_progress(
        user_id=user_id,
        labels=snapshot["labels"],
        exercise_week_weight=snapshot["exercise_week_weight"],
        exercise_week_1rm=snapshot["exercise_week_1rm"],
        exercise_key=exercise_key,
        strongest_exercise=snapshot["summary"].get("strongest_exercise"),
    )
    return ExerciseProgressOut.model_validate(progress)


@router.get("/progress-score/{user_id}", response_model=ProgressScoreOut)
def analytics_progress_score(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    logs = db.query(models.SetLog).filter(models.SetLog.user_id == user_id).all()
    body_weight_logs = (
        db.query(models.BodyWeightLog)
        .filter(models.BodyWeightLog.user_id == user_id)
        .order_by(models.BodyWeightLog.measured_at.asc())
        .all()
    )
    snapshot = build_analytics_snapshot(user, logs, body_weight_logs)
    return ProgressScoreOut.model_validate(snapshot["score"])
