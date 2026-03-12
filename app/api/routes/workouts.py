from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.db import models
from sqlalchemy import func
from datetime import datetime, timedelta
from collections import defaultdict
from app.schemas.workout import (
    GenerateWorkoutIn,
    WorkoutPlanOut,
    SetLogIn,
    SetLogOut,
    ProgressSummaryOut,
    WorkoutHistoryOut,
    WorkoutHistorySessionOut,
    WorkoutHistorySetOut,
)
from app.utils.exercise_key import normalize_exercise_key
from app.services.workout_generator import generate_plan

router = APIRouter(prefix="/workouts", tags=["workouts"])


@router.post("/generate", response_model=WorkoutPlanOut)
def generate_workout(payload: GenerateWorkoutIn, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == payload.profile_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    plan = generate_plan(
        split=payload.split,
        training_days=user.training_days or 3,
        experience=user.experience_level or "beginner",
        week_index=payload.week_index,
        block_index=payload.block_index,
        readiness_score=payload.readiness_score,
    )

    plan_record = models.WorkoutPlan(
        user_id=user.id,
        name=plan.plan_name,
        split=plan.split,
        week_index=plan.week_index,
        block_index=plan.block_index,
        meta={
            "volume_landmarks": plan.volume_landmarks,
            "readiness_score": plan.readiness_score,
            "fatigue_score": plan.fatigue_score,
        },
    )
    db.add(plan_record)
    db.commit()
    db.refresh(plan_record)

    for day in plan.days:
        db.add(
            models.WorkoutDay(
                plan_id=plan_record.id,
                day_index=day.day_index,
                focus=day.focus,
                exercises=[e.model_dump() for e in day.exercises],
            )
        )
    db.commit()

    return plan


@router.post("/log_set", response_model=SetLogOut)
def log_set(payload: SetLogIn, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    exercise_name = (payload.exercise_name or payload.exercise or payload.exercise_key or "").strip()
    exercise_key = (payload.exercise_key or "").strip()
    if not exercise_key:
        exercise_key = normalize_exercise_key(exercise_name)

    if payload.client_id:
        existing = (
            db.query(models.SetLog)
            .filter(models.SetLog.user_id == payload.user_id)
            .filter(models.SetLog.client_id == payload.client_id)
            .first()
        )
        if existing:
            existing_meta = (
                db.query(models.SetLogMeta)
                .filter(models.SetLogMeta.set_log_id == existing.id)
                .first()
            )
            if existing_meta is None:
                existing_meta = models.SetLogMeta(
                    set_log_id=existing.id,
                    user_id=existing.user_id,
                    session_id=payload.session_id,
                    rest_seconds=payload.rest_seconds,
                )
                db.add(existing_meta)
                db.commit()
            else:
                changed = False
                if payload.session_id and existing_meta.session_id != payload.session_id:
                    existing_meta.session_id = payload.session_id
                    changed = True
                if payload.rest_seconds is not None and existing_meta.rest_seconds != payload.rest_seconds:
                    existing_meta.rest_seconds = payload.rest_seconds
                    changed = True
                if changed:
                    db.commit()
            return SetLogOut(
                id=existing.id,
                user_id=existing.user_id,
                client_id=existing.client_id,
                exercise=existing.exercise,
                exercise_key=existing.exercise_key or normalize_exercise_key(existing.exercise),
                reps=existing.reps,
                weight=existing.weight,
                rpe=existing.rpe,
                rest_seconds=existing_meta.rest_seconds if existing_meta else None,
                session_id=existing_meta.session_id if existing_meta else None,
            )

    record = models.SetLog(
        user_id=payload.user_id,
        client_id=payload.client_id,
        exercise=exercise_name or exercise_key,
        exercise_key=exercise_key,
        reps=payload.reps,
        weight=payload.weight,
        rpe=payload.rpe,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    meta = models.SetLogMeta(
        set_log_id=record.id,
        user_id=payload.user_id,
        session_id=payload.session_id,
        rest_seconds=payload.rest_seconds,
    )
    db.add(meta)
    db.commit()

    return SetLogOut(
        id=record.id,
        user_id=record.user_id,
        client_id=record.client_id,
        exercise=record.exercise,
        exercise_key=record.exercise_key or normalize_exercise_key(record.exercise),
        reps=record.reps,
        weight=record.weight,
        rpe=record.rpe,
        rest_seconds=meta.rest_seconds,
        session_id=meta.session_id,
    )


@router.get("/history/{user_id}", response_model=WorkoutHistoryOut)
def workout_history(user_id: int, limit: int = 20, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    logs = (
        db.query(models.SetLog)
        .filter(models.SetLog.user_id == user_id)
        .order_by(models.SetLog.performed_at.desc())
        .all()
    )

    if not logs:
        return WorkoutHistoryOut(user_id=user_id, sessions=[])

    log_ids = [log.id for log in logs]
    meta_rows = (
        db.query(models.SetLogMeta)
        .filter(models.SetLogMeta.user_id == user_id)
        .filter(models.SetLogMeta.set_log_id.in_(log_ids))
        .all()
    )
    meta_by_log_id = {meta.set_log_id: meta for meta in meta_rows}

    grouped_entries: dict[str, list[WorkoutHistorySetOut]] = defaultdict(list)
    session_time: dict[str, datetime] = {}

    for log in logs:
        meta = meta_by_log_id.get(log.id)
        performed_at = log.performed_at or datetime.utcnow()
        fallback_session = f"legacy-{performed_at.date().isoformat()}"
        session_id = (meta.session_id if meta and meta.session_id else fallback_session)

        grouped_entries[session_id].append(
            WorkoutHistorySetOut(
                exercise=log.exercise,
                exercise_key=log.exercise_key or normalize_exercise_key(log.exercise),
                reps=log.reps,
                weight=log.weight,
                rpe=log.rpe,
                rest_seconds=meta.rest_seconds if meta else None,
                performed_at=performed_at.isoformat(),
            )
        )
        if session_id not in session_time or performed_at > session_time[session_id]:
            session_time[session_id] = performed_at

    ordered_sessions = sorted(
        grouped_entries.keys(), key=lambda sid: session_time[sid], reverse=True
    )[: max(1, min(limit, 100))]

    sessions_out: list[WorkoutHistorySessionOut] = []
    for session_id in ordered_sessions:
        entries = sorted(
            grouped_entries[session_id], key=lambda entry: entry.performed_at
        )
        total_volume = sum(entry.reps * entry.weight for entry in entries)
        sessions_out.append(
            WorkoutHistorySessionOut(
                session_id=session_id,
                performed_at=session_time[session_id].isoformat(),
                total_sets=len(entries),
                total_volume=round(total_volume, 2),
                entries=entries,
            )
        )

    return WorkoutHistoryOut(user_id=user_id, sessions=sessions_out)


@router.get("/summary/{user_id}", response_model=ProgressSummaryOut)
def progress_summary(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    def estimate_one_rm(weight: float, reps: int) -> float:
        if reps <= 0:
            return 0.0
        return weight * (1 + reps / 30.0)

    muscle_map = {
        "bench": "chest",
        "incline": "chest",
        "fly": "chest",
        "squat": "legs",
        "deadlift": "posterior_chain",
        "rdl": "posterior_chain",
        "row": "back",
        "pulldown": "back",
        "pull up": "back",
        "overhead press": "shoulders",
        "shoulder press": "shoulders",
        "lateral raise": "shoulders",
        "curl": "arms",
        "triceps": "arms",
        "extension": "arms",
    }

    key_lifts = {
        "bench press": ["bench press", "bench"],
        "squat": ["squat"],
        "deadlift": ["deadlift"],
        "overhead press": ["overhead press", "shoulder press"],
    }

    total_volume = (
        db.query(func.sum(models.SetLog.reps * models.SetLog.weight))
        .filter(models.SetLog.user_id == user_id)
        .scalar()
        or 0.0
    )

    week_start = datetime.utcnow() - timedelta(days=7)
    weekly_logs = (
        db.query(models.SetLog)
        .filter(models.SetLog.user_id == user_id)
        .filter(models.SetLog.performed_at >= week_start)
        .all()
    )

    weekly_volume_by_muscle_group = {}
    for log in weekly_logs:
        name = log.exercise.lower()
        group = "other"
        for key, group_name in muscle_map.items():
            if key in name:
                group = group_name
                break
        volume = float(log.reps * log.weight)
        weekly_volume_by_muscle_group[group] = (
            weekly_volume_by_muscle_group.get(group, 0.0) + volume
        )

    logs = db.query(models.SetLog).filter(models.SetLog.user_id == user_id).all()
    rep_prs: dict[str, int] = {}
    one_rm_prs: dict[str, float] = {}
    strength_index_by_lift: dict[str, float] = {}

    for log in logs:
        exercise = log.exercise
        rep_prs[exercise] = max(rep_prs.get(exercise, 0), log.reps)
        est_one_rm = estimate_one_rm(log.weight, log.reps)
        one_rm_prs[exercise] = max(one_rm_prs.get(exercise, 0.0), est_one_rm)

    bodyweight = user.weight_kg or 0.0
    for lift, aliases in key_lifts.items():
        best_one_rm = 0.0
        for exercise, value in one_rm_prs.items():
            name = exercise.lower()
            if any(alias in name for alias in aliases):
                best_one_rm = max(best_one_rm, value)
        if best_one_rm > 0:
            strength_index_by_lift[lift] = (
                (best_one_rm / bodyweight) * 100.0
                if bodyweight > 0
                else best_one_rm
            )

    strength_index = (
        sum(strength_index_by_lift.values()) / len(strength_index_by_lift)
        if strength_index_by_lift
        else 0.0
    )

    return ProgressSummaryOut(
        user_id=user_id,
        total_volume=float(total_volume),
        weekly_volume_by_muscle_group=weekly_volume_by_muscle_group,
        rep_prs=rep_prs,
        one_rm_prs=one_rm_prs,
        strength_index=strength_index,
        strength_index_by_lift=strength_index_by_lift,
    )
