from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import get_settings
from app.db import models
from app.schemas.form import (
    FormAnalyzeIn,
    FormAnalyzeOut,
    FormBatchIn,
    FormBatchOut,
    FormHistoryItemOut,
    FormHistoryOut,
    FormTrendOut,
    FormTrendPoint,
)
from app.schemas.realtime import FormRealtimeIn, FormRealtimeOut, JointColor, BoneColor
from app.services.form_analysis import analyze_form_diagnostics
from app.services.keypoint_analysis import analyse_keypoints
from app.services.ai_form_feedback import generate_ai_feedback
from app.services.achievements import process_session, ACHIEVEMENT_META
from app.services.multi_frame_analysis import analyse_batch

router = APIRouter(prefix="/form", tags=["form"])


@router.post("/analyze", response_model=FormAnalyzeOut)
def analyze_form(payload: FormAnalyzeIn, db: Session = Depends(get_db)):
    settings = get_settings()
    user = db.query(models.User).filter(models.User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    result = analyze_form_diagnostics(payload.diagnostics, exercise_key=payload.exercise_key)

    # Fetch historical trend for AI context (last 5 sessions)
    trend_sessions = (
        db.query(models.FormAnalysisSession)
        .filter(
            models.FormAnalysisSession.user_id == payload.user_id,
            models.FormAnalysisSession.exercise_key == payload.exercise_key,
        )
        .order_by(models.FormAnalysisSession.created_at.desc())
        .limit(5)
        .all()
    )
    trend: str | None = None
    if len(trend_sessions) >= 2:
        scores_desc = [s.overall_score for s in trend_sessions]
        diff = scores_desc[0] - scores_desc[-1]
        if diff >= 3.0:
            trend = "improving"
        elif diff <= -3.0:
            trend = "declining"
        else:
            trend = "stable"

    # Try AI-powered personalised feedback; fall back to rule-based feedback
    ai_feedback = generate_ai_feedback(
        exercise_key=payload.exercise_key,
        scores=result,
        issues=result["issues"],
        experience_level=user.experience_level,
        goal=user.goal,
        trend=trend,
        api_key=settings.anthropic_api_key or None,
    )
    feedback = ai_feedback if ai_feedback else result["feedback"]

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
        feedback=feedback,
    )
    db.add(record)
    db.flush()  # get record.id before achievement processing

    # Detect milestones + update personal best
    process_session(db, record)
    db.commit()

    return FormAnalyzeOut(
        overall_score=result["overall_score"],
        depth_score=result["depth_score"],
        torso_angle_score=result["torso_angle_score"],
        symmetry_score=result["symmetry_score"],
        tempo_score=result["tempo_score"],
        bar_path_score=result["bar_path_score"],
        issues=result["issues"],
        feedback=feedback,
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


@router.get("/achievements/{user_id}", summary="List user form achievements")
def form_achievements(
    user_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
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
                "type":         a.achievement_type,
                "exercise_key": a.exercise_key,
                "score":        a.score,
                "earned_at":    a.created_at.isoformat() if a.created_at else None,
                **ACHIEVEMENT_META.get(a.achievement_type, {}),
            }
            for a in rows
        ],
    }


@router.post("/analyze-batch", response_model=FormBatchOut)
def analyze_batch(payload: FormBatchIn, db: Session = Depends(get_db)):
    """
    Analyse a full set from a sequence of keypoint frames.

    More accurate than single-frame /analyze because it:
    - Detects individual reps and finds the deepest point of each
    - Uses the worst torso angle across the full eccentric phase (conservative/safe)
    - Derives tempo score from rep-duration consistency
    - Returns per-rep breakdowns + global aggregates
    """
    settings = get_settings()
    user = db.query(models.User).filter(models.User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    result = analyse_batch(payload)

    # Optional AI feedback
    trend_sessions = (
        db.query(models.FormAnalysisSession)
        .filter(
            models.FormAnalysisSession.user_id == payload.user_id,
            models.FormAnalysisSession.exercise_key == payload.exercise_key,
        )
        .order_by(models.FormAnalysisSession.created_at.desc())
        .limit(5)
        .all()
    )
    trend: str | None = None
    if len(trend_sessions) >= 2:
        scores_desc = [s.overall_score for s in trend_sessions]
        diff = scores_desc[0] - scores_desc[-1]
        trend = "improving" if diff >= 3 else ("declining" if diff <= -3 else "stable")

    ai_feedback = generate_ai_feedback(
        exercise_key=payload.exercise_key,
        scores=result,
        issues=result["issues"],
        experience_level=user.experience_level,
        goal=user.goal,
        trend=trend,
        api_key=settings.anthropic_api_key or None,
    )
    feedback = ai_feedback if ai_feedback else result["feedback"]

    record = models.FormAnalysisSession(
        user_id=payload.user_id,
        exercise_key=payload.exercise_key,
        model_name="movenet-batch",
        model_version=f"v1-reps{result['rep_count']}",
        depth_score=result["depth_score"],
        torso_angle_score=result["torso_angle_score"],
        symmetry_score=result["symmetry_score"],
        tempo_score=result["tempo_score"],
        bar_path_score=result["bar_path_score"],
        overall_score=result["overall_score"],
        issues=result["issues"],
        diagnostics={"frame_count": result["frame_count"], "duration_ms": result["duration_ms"]},
        feedback=feedback,
    )
    db.add(record)
    db.flush()
    process_session(db, record)
    db.commit()

    return FormBatchOut(
        overall_score=result["overall_score"],
        depth_score=result["depth_score"],
        torso_angle_score=result["torso_angle_score"],
        symmetry_score=result["symmetry_score"],
        tempo_score=result["tempo_score"],
        bar_path_score=result["bar_path_score"],
        issues=result["issues"],
        feedback=feedback,
        diagnostics=result["diagnostics"],
        model_name="movenet-batch",
        model_version=f"v1-reps{result['rep_count']}",
        frame_count=result["frame_count"],
        duration_ms=result["duration_ms"],
        rep_count=result["rep_count"],
        reps=result["reps"],
        depth_achieved_deg=result["depth_achieved_deg"],
        worst_torso_deg=result["worst_torso_deg"],
        tempo_cv=result["tempo_cv"],
    )


@router.post("/realtime", response_model=FormRealtimeOut)
def realtime_form(payload: FormRealtimeIn, db: Session = Depends(get_db)):
    """
    Frame-by-frame keypoint analysis for real-time skeleton overlay.

    The client (mobile app) runs on-device pose estimation (MoveNet / BlazePose),
    sends the 2-D keypoints for the current frame, and receives per-joint and
    per-bone colour annotations:
      - "green"  : correct form
      - "yellow" : minor deviation
      - "red"    : significant error / injury risk

    The endpoint is intentionally lightweight (no DB write) so it can be called
    at ~15-30 fps without overwhelming the database.
    """
    user = db.query(models.User).filter(models.User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Convert Pydantic Keypoint objects to plain dicts for the service layer
    kp_dicts = {
        name: {"x": kp.x, "y": kp.y, "confidence": kp.confidence}
        for name, kp in payload.keypoints.items()
    }

    result = analyse_keypoints(kp_dicts, payload.exercise_key, view=payload.view)

    return FormRealtimeOut(
        joint_colors=[JointColor(**jc) for jc in result["joint_colors"]],
        bone_colors=[BoneColor(**bc) for bc in result["bone_colors"]],
        issues=result["issues"],
        feedback=result["feedback"],
        overall_score=result["overall_score"],
    )
