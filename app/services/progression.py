from app.schemas.progression import ProgressionInput, ProgressionDecision
from app.utils.exercise_key import normalize_exercise_key
from app.db import models
from sqlalchemy.orm import Session


def adjust_progression(payload: ProgressionInput, db: Session) -> ProgressionDecision:
    exercise_name = (payload.exercise_name or payload.exercise or payload.exercise_key or "").strip()
    exercise_key = (payload.exercise_key or "").strip()
    if not exercise_key:
        exercise_key = normalize_exercise_key(exercise_name)
    deload = False
    weight_delta = 0.0
    volume_delta_sets = 0

    if payload.plateau_weeks >= 3:
        deload = True
        volume_delta_sets = -2
        message = "Plateau detected. Initiating deload week."
        decision = ProgressionDecision(
            action="deload",
            weight_delta=weight_delta,
            volume_delta_sets=volume_delta_sets,
            deload=deload,
            message=message,
            exercise_key=exercise_key,
            exercise_name=exercise_name,
        )
        record = models.RecommendationLog(
            user_id=payload.user_id,
            exercise=exercise_name,
            exercise_key=exercise_key,
            recommendation=decision.model_dump(),
            accuracy=0.0,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        decision.recommendation_id = record.id
        return decision

    if payload.fatigue_score > 0.7:
        volume_delta_sets = -1
        message = "High fatigue. Reduce volume slightly."
        decision = ProgressionDecision(
            action="reduce_volume",
            weight_delta=weight_delta,
            volume_delta_sets=volume_delta_sets,
            deload=False,
            message=message,
            exercise_key=exercise_key,
            exercise_name=exercise_name,
        )
        record = models.RecommendationLog(
            user_id=payload.user_id,
            exercise=exercise_name,
            exercise_key=exercise_key,
            recommendation=decision.model_dump(),
            accuracy=0.0,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        decision.recommendation_id = record.id
        return decision

    if payload.readiness_score >= 0.75 and payload.last_week_avg_rpe <= 8.0:
        weight_delta = 2.5
        volume_delta_sets = 1 if payload.last_week_volume < 16 else 0
        message = "Good readiness. Increase load and/or volume."
        decision = ProgressionDecision(
            action="increase",
            weight_delta=weight_delta,
            volume_delta_sets=volume_delta_sets,
            deload=False,
            message=message,
            exercise_key=exercise_key,
            exercise_name=exercise_name,
        )
        record = models.RecommendationLog(
            user_id=payload.user_id,
            exercise=exercise_name,
            exercise_key=exercise_key,
            recommendation=decision.model_dump(),
            accuracy=0.0,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        decision.recommendation_id = record.id
        return decision

    message = "Maintain current load and volume."
    decision = ProgressionDecision(
        action="maintain",
        weight_delta=weight_delta,
        volume_delta_sets=volume_delta_sets,
        deload=False,
        message=message,
        exercise_key=exercise_key,
        exercise_name=exercise_name,
    )
    record = models.RecommendationLog(
        user_id=payload.user_id,
        exercise=exercise_name,
        exercise_key=exercise_key,
        recommendation=decision.model_dump(),
        accuracy=0.0,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    decision.recommendation_id = record.id
    return decision
