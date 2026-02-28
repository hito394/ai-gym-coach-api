from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.db import models
from sqlalchemy import func
from app.schemas.workout import GenerateWorkoutIn, WorkoutPlanOut, SetLogIn, SetLogOut, ProgressSummaryOut
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

    record = models.SetLog(
        user_id=payload.user_id,
        exercise=payload.exercise,
        reps=payload.reps,
        weight=payload.weight,
        rpe=payload.rpe,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return SetLogOut(
        id=record.id,
        user_id=record.user_id,
        exercise=record.exercise,
        reps=record.reps,
        weight=record.weight,
        rpe=record.rpe,
    )


@router.get("/summary/{user_id}", response_model=ProgressSummaryOut)
def progress_summary(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    total_volume = (
        db.query(func.sum(models.SetLog.reps * models.SetLog.weight))
        .filter(models.SetLog.user_id == user_id)
        .scalar()
        or 0.0
    )

    prs_query = (
        db.query(models.SetLog.exercise, func.max(models.SetLog.weight))
        .filter(models.SetLog.user_id == user_id)
        .group_by(models.SetLog.exercise)
        .all()
    )

    prs = {exercise: max_weight for exercise, max_weight in prs_query}

    return ProgressSummaryOut(
        user_id=user_id,
        total_volume=float(total_volume),
        prs=prs,
    )
