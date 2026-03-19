import uuid
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.security import get_current_user_id
from app.db import models
from app.schemas.workout import (
    ExercisePrescription,
    GenerateAIMenuIn,
    GenerateWorkoutIn,
    ProgressSummaryOut,
    SessionFinishIn,
    SessionLogSetIn,
    SessionOut,
    SessionSetOut,
    SessionStartIn,
    SetLogIn,
    SetLogOut,
    WorkoutDayOut,
    WorkoutHistoryOut,
    WorkoutHistorySessionOut,
    WorkoutHistorySetOut,
    WorkoutPlanOut,
)
from app.services.ai_menu import generate_ai_menu
from app.services.workout_generator import generate_plan
from app.utils.exercise_key import normalize_exercise_key

router = APIRouter(prefix="/workouts", tags=["workouts"])


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_plan_out_from_dict(data: dict) -> WorkoutPlanOut:
    days = []
    for d in data.get("days", []):
        exercises = [
            ExercisePrescription(
                name=e["name"],
                exercise_key=e.get("exercise_key", normalize_exercise_key(e["name"])),
                sets=int(e["sets"]),
                rep_range=str(e["rep_range"]),
                rpe_target=float(e["rpe_target"]),
                rest_seconds=int(e["rest_seconds"]),
                notes=e.get("notes"),
            )
            for e in d.get("exercises", [])
        ]
        days.append(WorkoutDayOut(
            day_index=int(d["day_index"]),
            focus=str(d["focus"]),
            exercises=exercises,
        ))
    vl = data.get("volume_landmarks", {"mev": 8, "mav": 12, "mrv": 18})
    return WorkoutPlanOut(
        plan_name=data.get("plan_name", "AI Plan"),
        split=data["split"],
        week_index=int(data["week_index"]),
        block_index=int(data["block_index"]),
        days=days,
        volume_landmarks=vl,
        readiness_score=float(data.get("readiness_score", 0.7)),
        fatigue_score=float(data.get("fatigue_score", 0.3)),
    )


def _recent_muscle_groups(user_id: int, db: Session) -> list[str]:
    cutoff = datetime.utcnow() - timedelta(hours=48)
    logs = (
        db.query(models.SetLog)
        .filter(models.SetLog.user_id == user_id, models.SetLog.performed_at >= cutoff)
        .all()
    )
    _map = {
        "squat": "legs", "leg": "legs", "lunge": "legs",
        "deadlift": "posterior", "rdl": "posterior", "hip": "posterior",
        "bench": "chest", "fly": "chest", "push": "chest",
        "row": "back", "pull": "back", "lat": "back",
        "press": "shoulders", "lateral": "shoulders",
        "curl": "arms", "tricep": "arms", "extension": "arms",
    }
    groups = []
    for log in logs:
        name = (log.exercise or "").lower()
        for kw, grp in _map.items():
            if kw in name:
                groups.append(grp)
                break
    return groups


def _session_to_out(session: models.WorkoutSession, sets: list) -> SessionOut:
    return SessionOut(
        id=session.id,
        session_key=session.session_key,
        user_id=session.user_id,
        plan_id=session.plan_id,
        notes=session.notes,
        started_at=session.started_at.isoformat(),
        finished_at=session.finished_at.isoformat() if session.finished_at else None,
        is_active=session.finished_at is None,
        total_sets=session.total_sets,
        total_volume=round(session.total_volume, 2),
        sets=[
            SessionSetOut(
                id=s.id,
                exercise=s.exercise,
                exercise_key=s.exercise_key or normalize_exercise_key(s.exercise),
                reps=s.reps,
                weight=s.weight,
                rpe=s.rpe,
                rest_seconds=None,
                performed_at=s.performed_at.isoformat(),
            )
            for s in sets
        ],
    )


# ---------------------------------------------------------------------------
# Rule-based plan generation (existing)
# ---------------------------------------------------------------------------

@router.post("/generate", response_model=WorkoutPlanOut)
def generate_workout(
    payload: GenerateWorkoutIn,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    if current_user_id != payload.profile_id:
        raise HTTPException(status_code=403, detail="Access denied")
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
            "source": "rule_based",
        },
    )
    db.add(plan_record)
    db.commit()
    db.refresh(plan_record)
    for day in plan.days:
        db.add(models.WorkoutDay(
            plan_id=plan_record.id,
            day_index=day.day_index,
            focus=day.focus,
            exercises=[e.model_dump() for e in day.exercises],
        ))
    db.commit()
    return plan


# ---------------------------------------------------------------------------
# AI-powered plan generation
# ---------------------------------------------------------------------------

@router.post("/generate-ai", response_model=WorkoutPlanOut, summary="AI workout menu generation")
def generate_workout_ai(
    payload: GenerateAIMenuIn,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    if current_user_id != payload.profile_id:
        raise HTTPException(status_code=403, detail="Access denied")
    """
    Generate a fully personalised workout plan using Claude.

    Takes into account user profile (experience, goal, equipment),
    recent training history (recovery avoidance), and readiness score.
    Falls back to the rule-based generator if no Anthropic API key is set.
    """
    settings = get_settings()
    user = db.query(models.User).filter(models.User.id == payload.profile_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    recent_mgs = _recent_muscle_groups(user.id, db)
    ai_data = generate_ai_menu(
        split=payload.split,
        training_days=user.training_days or 3,
        experience=user.experience_level or "beginner",
        goal=user.goal or "muscle_gain",
        equipment=user.equipment or ["barbell", "dumbbell"],
        week_index=payload.week_index,
        block_index=payload.block_index,
        readiness_score=payload.readiness_score,
        recent_muscle_groups=recent_mgs,
        api_key=settings.anthropic_api_key or None,
    )

    if ai_data:
        plan = _build_plan_out_from_dict(ai_data)
        source = "ai"
    else:
        plan = generate_plan(
            split=payload.split,
            training_days=user.training_days or 3,
            experience=user.experience_level or "beginner",
            week_index=payload.week_index,
            block_index=payload.block_index,
            readiness_score=payload.readiness_score,
        )
        source = "rule_based"

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
            "source": source,
        },
    )
    db.add(plan_record)
    db.commit()
    db.refresh(plan_record)
    for day in plan.days:
        db.add(models.WorkoutDay(
            plan_id=plan_record.id,
            day_index=day.day_index,
            focus=day.focus,
            exercises=[e.model_dump() for e in day.exercises],
        ))
    db.commit()
    return plan


# ---------------------------------------------------------------------------
# Saved plans listing
# ---------------------------------------------------------------------------

@router.get("/plans/{user_id}", summary="List saved workout plans")
def list_plans(
    user_id: int,
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    plans = (
        db.query(models.WorkoutPlan)
        .filter(models.WorkoutPlan.user_id == user_id)
        .order_by(models.WorkoutPlan.created_at.desc())
        .limit(limit)
        .all()
    )
    out = []
    for p in plans:
        days = (
            db.query(models.WorkoutDay)
            .filter(models.WorkoutDay.plan_id == p.id)
            .order_by(models.WorkoutDay.day_index)
            .all()
        )
        out.append({
            "id": p.id,
            "name": p.name,
            "split": p.split,
            "week_index": p.week_index,
            "block_index": p.block_index,
            "created_at": p.created_at.isoformat(),
            "source": (p.meta or {}).get("source", "rule_based"),
            "days": [
                {
                    "day_index": d.day_index,
                    "focus": d.focus,
                    "exercise_count": len(d.exercises or []),
                    "exercises": [
                        {"name": e.get("name"), "sets": e.get("sets"), "rep_range": e.get("rep_range")}
                        for e in (d.exercises or [])
                    ],
                }
                for d in days
            ],
        })
    return {"user_id": user_id, "plans": out}


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

@router.post("/sessions", response_model=SessionOut, summary="Start a workout session")
def start_session(
    payload: SessionStartIn,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    if current_user_id != payload.user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    user = db.query(models.User).filter(models.User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.plan_id:
        plan = db.query(models.WorkoutPlan).filter(
            models.WorkoutPlan.id == payload.plan_id,
            models.WorkoutPlan.user_id == payload.user_id,
        ).first()
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")

    session = models.WorkoutSession(
        user_id=payload.user_id,
        session_key=str(uuid.uuid4()),
        plan_id=payload.plan_id,
        notes=payload.notes,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _session_to_out(session, [])


@router.get("/sessions/active/{user_id}", response_model=SessionOut, summary="Get active session")
def get_active_session(
    user_id: int,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    session = (
        db.query(models.WorkoutSession)
        .filter(
            models.WorkoutSession.user_id == user_id,
            models.WorkoutSession.finished_at.is_(None),
        )
        .order_by(models.WorkoutSession.started_at.desc())
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="No active session")
    sets = (
        db.query(models.SetLog)
        .filter(models.SetLog.user_id == user_id)
        .join(models.SetLogMeta, models.SetLogMeta.set_log_id == models.SetLog.id)
        .filter(models.SetLogMeta.session_id == session.session_key)
        .order_by(models.SetLog.performed_at.asc())
        .all()
    )
    return _session_to_out(session, sets)


@router.get("/sessions/{session_key}", response_model=SessionOut, summary="View a session")
def get_session(
    session_key: str,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    session = db.query(models.WorkoutSession).filter(
        models.WorkoutSession.session_key == session_key
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if current_user_id != session.user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    sets = (
        db.query(models.SetLog)
        .filter(models.SetLog.user_id == session.user_id)
        .join(models.SetLogMeta, models.SetLogMeta.set_log_id == models.SetLog.id)
        .filter(models.SetLogMeta.session_id == session_key)
        .order_by(models.SetLog.performed_at.asc())
        .all()
    )
    return _session_to_out(session, sets)


@router.post(
    "/sessions/{session_key}/sets",
    response_model=SessionSetOut,
    summary="Log a set in a session",
)
def log_set_in_session(
    session_key: str,
    payload: SessionLogSetIn,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    session = db.query(models.WorkoutSession).filter(
        models.WorkoutSession.session_key == session_key
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if current_user_id != session.user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    if session.finished_at is not None:
        raise HTTPException(status_code=409, detail="Session already finished")

    ex_key = normalize_exercise_key(payload.exercise_key)
    ex_name = payload.exercise_name or ex_key

    record = models.SetLog(
        user_id=session.user_id,
        exercise=ex_name,
        exercise_key=ex_key,
        reps=payload.reps,
        weight=payload.weight,
        rpe=payload.rpe,
    )
    db.add(record)
    db.flush()

    db.add(models.SetLogMeta(
        set_log_id=record.id,
        user_id=session.user_id,
        session_id=session_key,
        rest_seconds=payload.rest_seconds,
        form_session_id=payload.form_session_id,
    ))

    session.total_sets = (session.total_sets or 0) + 1
    session.total_volume = (session.total_volume or 0.0) + payload.reps * payload.weight
    db.commit()
    db.refresh(record)

    return SessionSetOut(
        id=record.id,
        exercise=record.exercise,
        exercise_key=record.exercise_key,
        reps=record.reps,
        weight=record.weight,
        rpe=record.rpe,
        rest_seconds=payload.rest_seconds,
        form_session_id=payload.form_session_id,
        performed_at=record.performed_at.isoformat(),
    )


@router.post(
    "/sessions/{session_key}/finish",
    response_model=SessionOut,
    summary="Finish a session",
)
def finish_session(
    session_key: str,
    payload: SessionFinishIn,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    session = db.query(models.WorkoutSession).filter(
        models.WorkoutSession.session_key == session_key
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if current_user_id != session.user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    if session.finished_at is not None:
        raise HTTPException(status_code=409, detail="Session already finished")

    session.finished_at = datetime.utcnow()
    if payload.notes:
        session.notes = (session.notes or "") + ("\n" if session.notes else "") + payload.notes
    db.commit()

    sets = (
        db.query(models.SetLog)
        .filter(models.SetLog.user_id == session.user_id)
        .join(models.SetLogMeta, models.SetLogMeta.set_log_id == models.SetLog.id)
        .filter(models.SetLogMeta.session_id == session_key)
        .order_by(models.SetLog.performed_at.asc())
        .all()
    )
    return _session_to_out(session, sets)


# ---------------------------------------------------------------------------
# Legacy log_set (backwards compatible)
# ---------------------------------------------------------------------------

@router.post("/log_set", response_model=SetLogOut)
def log_set(
    payload: SetLogIn,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    if current_user_id != payload.user_id:
        raise HTTPException(status_code=403, detail="Access denied")
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


# ---------------------------------------------------------------------------
# Weight suggestion
# ---------------------------------------------------------------------------

@router.get("/suggest/{user_id}", summary="Suggest weight for next set")
def suggest_weight(
    user_id: int,
    exercise_key: str = Query(..., description="Normalised exercise key, e.g. bench_press"),
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    """
    Suggest a starting weight for the given exercise based on:
      - The user's best logged weight × reps (1RM estimate via Epley formula)
      - The most recent form score for that exercise (lower form → conservative suggestion)

    Returns:
      - suggested_weight_kg: recommended working weight
      - basis: the best set that informed the recommendation
      - form_score: last form analysis score (None if never analysed)
      - form_note: human-readable note about form quality
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Best set by estimated 1RM for this exercise
    logs = (
        db.query(models.SetLog)
        .filter(
            models.SetLog.user_id == user_id,
            models.SetLog.exercise_key == exercise_key,
        )
        .all()
    )
    if not logs:
        raise HTTPException(status_code=404, detail="No logged sets found for this exercise")

    def epley_1rm(weight: float, reps: int) -> float:
        return weight * (1 + reps / 30.0) if reps > 0 else weight

    best = max(logs, key=lambda s: epley_1rm(s.weight, s.reps))
    best_1rm = epley_1rm(best.weight, best.reps)

    # Last form analysis for this exercise
    last_form = (
        db.query(models.FormAnalysisSession)
        .filter(
            models.FormAnalysisSession.user_id == user_id,
            models.FormAnalysisSession.exercise_key == exercise_key,
        )
        .order_by(models.FormAnalysisSession.created_at.desc())
        .first()
    )

    form_score = last_form.overall_score if last_form else None

    # Form-adjusted working weight:
    # - form ≥ 85: 85% 1RM (standard training weight)
    # - form 70–84: 80% 1RM
    # - form < 70 or unknown: 75% 1RM (build form first)
    if form_score is None or form_score < 70:
        pct = 0.75
        form_note = "Focus on form — start conservative"
    elif form_score < 85:
        pct = 0.80
        form_note = "Form is decent — moderate load"
    else:
        pct = 0.85
        form_note = "Good form — standard training load"

    # Round to nearest 2.5 kg
    raw = best_1rm * pct
    suggested = round(raw / 2.5) * 2.5

    return {
        "user_id": user_id,
        "exercise_key": exercise_key,
        "suggested_weight_kg": suggested,
        "estimated_1rm_kg": round(best_1rm, 1),
        "load_percentage": pct,
        "basis": {
            "weight": best.weight,
            "reps": best.reps,
            "rpe": best.rpe,
            "performed_at": best.performed_at.isoformat(),
        },
        "form_score": form_score,
        "form_note": form_note,
    }


# ---------------------------------------------------------------------------
# History & summary (unchanged)
# ---------------------------------------------------------------------------

@router.get("/history/{user_id}", response_model=WorkoutHistoryOut)
def workout_history(
    user_id: int,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
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
    meta_by_log_id = {m.set_log_id: m for m in meta_rows}

    grouped_entries: dict[str, list[WorkoutHistorySetOut]] = defaultdict(list)
    session_time: dict[str, datetime] = {}

    for log in logs:
        meta = meta_by_log_id.get(log.id)
        performed_at = log.performed_at or datetime.utcnow()
        sid = meta.session_id if meta and meta.session_id else f"legacy-{performed_at.date().isoformat()}"
        grouped_entries[sid].append(
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
        if sid not in session_time or performed_at > session_time[sid]:
            session_time[sid] = performed_at

    ordered = sorted(grouped_entries, key=lambda s: session_time[s], reverse=True)[: max(1, min(limit, 100))]
    sessions_out = []
    for sid in ordered:
        entries = sorted(grouped_entries[sid], key=lambda e: e.performed_at)
        total_vol = sum(e.reps * e.weight for e in entries)
        sessions_out.append(WorkoutHistorySessionOut(
            session_id=sid,
            performed_at=session_time[sid].isoformat(),
            total_sets=len(entries),
            total_volume=round(total_vol, 2),
            entries=entries,
        ))

    return WorkoutHistoryOut(user_id=user_id, sessions=sessions_out)


@router.get("/summary/{user_id}", response_model=ProgressSummaryOut)
def progress_summary(
    user_id: int,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    def estimate_one_rm(weight: float, reps: int) -> float:
        return weight * (1 + reps / 30.0) if reps > 0 else 0.0

    muscle_map = {
        "bench": "chest", "incline": "chest", "fly": "chest",
        "squat": "legs", "deadlift": "posterior_chain", "rdl": "posterior_chain",
        "row": "back", "pulldown": "back", "pull up": "back",
        "overhead press": "shoulders", "shoulder press": "shoulders", "lateral raise": "shoulders",
        "curl": "arms", "triceps": "arms", "extension": "arms",
    }
    key_lifts = {
        "bench press":    ["bench press", "bench"],
        "squat":          ["squat"],
        "deadlift":       ["deadlift"],
        "overhead press": ["overhead press", "shoulder press"],
    }

    total_volume = float(
        db.query(func.sum(models.SetLog.reps * models.SetLog.weight))
        .filter(models.SetLog.user_id == user_id).scalar() or 0.0
    )

    week_start = datetime.utcnow() - timedelta(days=7)
    weekly_volume_by_muscle_group: dict[str, float] = {}
    for log in db.query(models.SetLog).filter(
        models.SetLog.user_id == user_id, models.SetLog.performed_at >= week_start
    ).all():
        name = log.exercise.lower()
        group = next((g for kw, g in muscle_map.items() if kw in name), "other")
        weekly_volume_by_muscle_group[group] = weekly_volume_by_muscle_group.get(group, 0.0) + log.reps * log.weight

    rep_prs: dict[str, int] = {}
    one_rm_prs: dict[str, float] = {}
    for log in db.query(models.SetLog).filter(models.SetLog.user_id == user_id).all():
        rep_prs[log.exercise] = max(rep_prs.get(log.exercise, 0), log.reps)
        one_rm_prs[log.exercise] = max(one_rm_prs.get(log.exercise, 0.0), estimate_one_rm(log.weight, log.reps))

    bodyweight = user.weight_kg or 0.0
    strength_index_by_lift: dict[str, float] = {}
    for lift, aliases in key_lifts.items():
        best = max((v for ex, v in one_rm_prs.items() if any(a in ex.lower() for a in aliases)), default=0.0)
        if best > 0:
            strength_index_by_lift[lift] = (best / bodyweight * 100.0) if bodyweight > 0 else best

    strength_index = (
        sum(strength_index_by_lift.values()) / len(strength_index_by_lift)
        if strength_index_by_lift else 0.0
    )

    return ProgressSummaryOut(
        user_id=user_id,
        total_volume=total_volume,
        weekly_volume_by_muscle_group=weekly_volume_by_muscle_group,
        rep_prs=rep_prs,
        one_rm_prs=one_rm_prs,
        strength_index=strength_index,
        strength_index_by_lift=strength_index_by_lift,
    )
