from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db import models
from app.schemas.form import (
    FormAnalyzeIn,
    FormAnalyzeOut,
    FormHistoryItemOut,
    FormHistoryOut,
    FormTrendOut,
    FormTrendPoint,
)
from app.services.form_analysis import analyze_form_diagnostics

router = APIRouter(prefix="/form", tags=["form"])


@router.post("/analyze", response_model=FormAnalyzeOut)
def analyze_form(payload: FormAnalyzeIn, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    result = analyze_form_diagnostics(payload.diagnostics, exercise_key=payload.exercise_key)

    record = models.FormAnalysisSession(
        user_id=payload.user_id,
        exercise_key=payload.exercise_key,
        model_name="movenet",
        model_version="mvp-rules-v1",
        depth_score=result["depth_score"],
        torso_angle_score=result["torso_angle_score"],
        symmetry_score=result["symmetry_score"],
        tempo_score=result["tempo_score"],
        bar_path_score=result["bar_path_score"],
        overall_score=result["overall_score"],
        issues=result["issues"],
        diagnostics=payload.diagnostics,
        feedback=result["feedback"],
    )
    db.add(record)
    db.commit()

    return FormAnalyzeOut(
        overall_score=result["overall_score"],
        depth_score=result["depth_score"],
        torso_angle_score=result["torso_angle_score"],
        symmetry_score=result["symmetry_score"],
        tempo_score=result["tempo_score"],
        bar_path_score=result["bar_path_score"],
        issues=result["issues"],
        feedback=result["feedback"],
        diagnostics=payload.diagnostics,
        model_name="movenet",
        model_version="mvp-rules-v1",
    )


@router.get("/history/{user_id}", response_model=FormHistoryOut)
def form_history(
    user_id: int,
    exercise_key: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    query = db.query(models.FormAnalysisSession).filter(
        models.FormAnalysisSession.user_id == user_id
    )
    if exercise_key:
        query = query.filter(models.FormAnalysisSession.exercise_key == exercise_key)

    sessions = (
        query.order_by(models.FormAnalysisSession.created_at.desc()).limit(limit).all()
    )

    items = [
        FormHistoryItemOut(
            id=s.id,
            exercise_key=s.exercise_key,
            overall_score=s.overall_score,
            depth_score=s.depth_score,
            torso_angle_score=s.torso_angle_score,
            symmetry_score=s.symmetry_score,
            tempo_score=s.tempo_score,
            bar_path_score=s.bar_path_score,
            issues=s.issues or [],
            feedback=s.feedback or "",
            model_name=s.model_name,
            model_version=s.model_version,
            created_at=s.created_at.isoformat(),
        )
        for s in sessions
    ]

    return FormHistoryOut(user_id=user_id, sessions=items)


@router.get("/trend/{user_id}", response_model=FormTrendOut)
def form_trend(
    user_id: int,
    exercise_key: str = Query(...),
    limit: int = Query(default=10, ge=2, le=50),
    db: Session = Depends(get_db),
):
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
            avg_score=0.0,
            trend="stable",
        )

    points = [
        FormTrendPoint(
            created_at=s.created_at.isoformat(),
            overall_score=s.overall_score,
        )
        for s in sessions
    ]

    avg_score = sum(p.overall_score for p in points) / len(points)

    trend = "stable"
    if len(points) >= 2:
        first_half = points[: len(points) // 2]
        second_half = points[len(points) // 2 :]
        first_avg = sum(p.overall_score for p in first_half) / len(first_half)
        second_avg = sum(p.overall_score for p in second_half) / len(second_half)
        diff = second_avg - first_avg
        if diff >= 3.0:
            trend = "improving"
        elif diff <= -3.0:
            trend = "declining"

    return FormTrendOut(
        user_id=user_id,
        exercise_key=exercise_key,
        points=points,
        avg_score=round(avg_score, 2),
        trend=trend,
    )
