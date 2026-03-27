from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.security import get_current_user_id
from app.db import models
from app.schemas.form import (
    FormLogIn,
    FormLogOut,
    FormHistoryItemOut,
    FormHistoryOut,
    FormTrendOut,
    FormTrendPoint,
)
from app.services.achievements import process_session, ACHIEVEMENT_META

router = APIRouter(prefix="/form", tags=["form"])


def _feeling_to_score(feeling: int) -> float:
    """Map 1–10 feeling rating to 0–100 score for DB storage."""
    return float(feeling * 10)


def _score_to_feeling(score: float) -> int:
    """Map stored 0–100 score back to 1–10 feeling rating."""
    return max(1, min(10, round(score / 10)))


@router.post("/log", response_model=FormLogOut, summary="Log workout feeling")
def log_form(
    payload: FormLogIn,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    """Record how a set felt — simple 1–10 rating with an optional text note."""
    if current_user_id != payload.user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    user = db.query(models.User).filter(models.User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    score = _feeling_to_score(payload.feeling)
    record = models.FormAnalysisSession(
        user_id=payload.user_id,
        exercise_key=payload.exercise_key,
        model_name="manual",
        model_version="v1",
        overall_score=score,
        depth_score=score,
        torso_angle_score=score,
        symmetry_score=score,
        tempo_score=score,
        bar_path_score=score,
        issues=[],
        diagnostics={},
        feedback=payload.note or "",
    )
    db.add(record)
    db.flush()
    process_session(db, record)
    db.commit()

    return FormLogOut(
        id=record.id,
        exercise_key=record.exercise_key,
        feeling=payload.feeling,
        note=payload.note,
        created_at=record.created_at.isoformat(),
    )


@router.get("/history/{user_id}", response_model=FormHistoryOut, summary="Get form log history")
def form_history(
    user_id: int,
    exercise_key: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    query = db.query(models.FormAnalysisSession).filter(
        models.FormAnalysisSession.user_id == user_id
    )
    if exercise_key:
        query = query.filter(models.FormAnalysisSession.exercise_key == exercise_key)

    sessions = query.order_by(models.FormAnalysisSession.created_at.desc()).limit(limit).all()

    items = [
        FormHistoryItemOut(
            id=s.id,
            exercise_key=s.exercise_key,
            feeling=_score_to_feeling(s.overall_score),
            note=s.feedback or None,
            created_at=s.created_at.isoformat(),
        )
        for s in sessions
    ]
    return FormHistoryOut(user_id=user_id, sessions=items)


@router.get("/trend/{user_id}", response_model=FormTrendOut, summary="Get feeling trend")
def form_trend(
    user_id: int,
    exercise_key: str = Query(...),
    limit: int = Query(default=10, ge=2, le=50),
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    sessions = (
        db.query(models.FormAnalysisSession)
        .filter(
            models.FormAnalysisSession.user_id == user_id,
            models.FormAnalysisSession.exercise_key == exercise_key,
        )
        .order_by(models.FormAnalysisSession.created_at.asc())
        .limit(limit)
        .all()
    )

    if not sessions:
        return FormTrendOut(
            user_id=user_id,
            exercise_key=exercise_key,
            points=[],
            avg_feeling=0.0,
            trend="stable",
        )

    points = [
        FormTrendPoint(
            created_at=s.created_at.isoformat(),
            feeling=_score_to_feeling(s.overall_score),
        )
        for s in sessions
    ]

    avg_feeling = sum(p.feeling for p in points) / len(points)

    trend = "stable"
    if len(points) >= 2:
        first_half = points[: len(points) // 2]
        second_half = points[len(points) // 2 :]
        first_avg = sum(p.feeling for p in first_half) / len(first_half)
        second_avg = sum(p.feeling for p in second_half) / len(second_half)
        diff = second_avg - first_avg
        if diff >= 1.0:
            trend = "improving"
        elif diff <= -1.0:
            trend = "declining"

    return FormTrendOut(
        user_id=user_id,
        exercise_key=exercise_key,
        points=points,
        avg_feeling=round(avg_feeling, 2),
        trend=trend,
    )


@router.get("/achievements/{user_id}", summary="List user form achievements")
def form_achievements(
    user_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    rows = (
        db.query(models.FormAchievement)
        .filter(models.FormAchievement.user_id == user_id)
        .order_by(models.FormAchievement.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "user_id": user_id,
        "achievements": [
            {
                "type": a.achievement_type,
                "exercise_key": a.exercise_key,
                "feeling": _score_to_feeling(a.score) if a.score else None,
                "earned_at": a.created_at.isoformat() if a.created_at else None,
                **ACHIEVEMENT_META.get(a.achievement_type, {}),
            }
            for a in rows
        ],
    }
